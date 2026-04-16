"""
Xcleaners — Pricing CRUD Routes (Story 1.1b backend sprint)

Completes Story 1.1 UI by implementing the 7 CRUD endpoint groups that
the frontend modules (pricing-manager / extras-manager / frequencies-
manager / taxes-manager) expect:

  GET    /pricing/formulas              — list
  POST   /pricing/formulas              — create
  PATCH  /pricing/formulas/{id}         — update / archive
  GET    /pricing/overrides             — list (joined with service + formula prices)
  DELETE /pricing/overrides/{id}        — revert override
  GET    /pricing/extras                — list catalog
  POST   /pricing/extras                — create
  PATCH  /pricing/extras/{id}           — update / archive
  GET    /pricing/frequencies           — list (with usage_count)
  POST   /pricing/frequencies           — create
  PATCH  /pricing/frequencies/{id}      — update / archive
  POST   /pricing/frequencies/{id}/set-default  — atomic set-default
  GET    /pricing/taxes                 — list per location (with usage_count)
  POST   /pricing/taxes                 — create new rate (immutable-after-use)
  PATCH  /pricing/taxes/{id}            — update / archive
  GET    /services/{service_id}/extras  — list whitelisted extras for a service
  PUT    /services/{service_id}/extras  — replace whitelist
  POST   /bookings/{booking_id}/recalculate  — re-run engine, overwrite snapshot
  GET    /locations                     — list cleaning_areas for tax UI

All endpoints are owner-only (require_role("owner")).
Security: Pydantic models do UUID validation (Smith B1), max_length on list
fields (B2), bounds on numeric fields (B3), sanitized error details (B4).

Author: @dev (Neo), 2026-04-16 (Sprint close, Story 1.1b)
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any, Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator

from app.database import Database, get_db
from app.modules.cleaning.middleware.role_guard import require_role
from app.modules.cleaning.services.booking_service import (
    create_booking_with_pricing,
    recalculate_booking_snapshot,
)
from app.modules.cleaning.services.pricing_engine import PricingConfigError


logger = logging.getLogger("xcleaners.pricing_crud")

router = APIRouter(
    prefix="/api/v1/clean/{slug}",
    tags=["Xcleaners Pricing CRUD"],
)


# ===========================================================================
# Helpers
# ===========================================================================


def _uuid(v: str | UUID | None) -> Optional[UUID]:
    if v is None or v == "":
        return None
    if isinstance(v, UUID):
        return v
    try:
        return UUID(v)
    except (ValueError, AttributeError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid UUID format.")


def _validate_uuid(v: Optional[str], name: str) -> Optional[str]:
    if v is None or v == "":
        return v
    try:
        UUID(v)
        return v
    except (ValueError, AttributeError, TypeError):
        raise ValueError(f"{name} must be a valid UUID")


# ===========================================================================
# PRICING FORMULAS
# ===========================================================================


class TierMultipliers(BaseModel):
    basic: Decimal = Field(..., ge=Decimal("0.1"), le=Decimal("100"))
    deep: Decimal = Field(..., ge=Decimal("0.1"), le=Decimal("100"))
    premium: Decimal = Field(..., ge=Decimal("0.1"), le=Decimal("100"))


class FormulaCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    base_amount: Decimal = Field(..., ge=Decimal("0"), le=Decimal("100000"))
    bedroom_delta: Decimal = Field(..., ge=Decimal("0"), le=Decimal("10000"))
    bathroom_delta: Decimal = Field(..., ge=Decimal("0"), le=Decimal("10000"))
    tier_multipliers: TierMultipliers
    location_id: Optional[str] = None
    is_active: bool = True

    @field_validator("location_id")
    @classmethod
    def _uuid_loc(cls, v):
        return _validate_uuid(v, "location_id")


class FormulaUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    base_amount: Optional[Decimal] = Field(None, ge=Decimal("0"), le=Decimal("100000"))
    bedroom_delta: Optional[Decimal] = Field(None, ge=Decimal("0"), le=Decimal("10000"))
    bathroom_delta: Optional[Decimal] = Field(None, ge=Decimal("0"), le=Decimal("10000"))
    tier_multipliers: Optional[TierMultipliers] = None
    is_active: Optional[bool] = None


@router.get("/pricing/formulas")
async def list_formulas(
    slug: str,
    user: dict = Depends(require_role("owner")),
    db: Database = Depends(get_db),
):
    rows = await db.pool.fetch(
        """SELECT id, name, base_amount, bedroom_delta, bathroom_delta,
                  tier_multipliers, location_id, is_active, created_at, updated_at
           FROM cleaning_pricing_formulas
           WHERE business_id = $1
           ORDER BY location_id NULLS FIRST, name""",
        user["business_id"],
    )
    import json as _json
    formulas = []
    for r in rows:
        tm = r["tier_multipliers"]
        if isinstance(tm, str):
            tm = _json.loads(tm)
        formulas.append({
            "id": str(r["id"]),
            "name": r["name"],
            "base_amount": str(r["base_amount"]),
            "bedroom_delta": str(r["bedroom_delta"]),
            "bathroom_delta": str(r["bathroom_delta"]),
            "tier_multipliers": tm,
            "location_id": str(r["location_id"]) if r["location_id"] else None,
            "is_active": r["is_active"],
            "created_at": r["created_at"].isoformat() if r["created_at"] else None,
            "updated_at": r["updated_at"].isoformat() if r["updated_at"] else None,
        })
    return {"formulas": formulas}


@router.post("/pricing/formulas", status_code=201)
async def create_formula(
    slug: str,
    body: FormulaCreate,
    user: dict = Depends(require_role("owner")),
    db: Database = Depends(get_db),
):
    import json as _json
    row = await db.pool.fetchrow(
        """INSERT INTO cleaning_pricing_formulas
             (business_id, name, base_amount, bedroom_delta, bathroom_delta,
              tier_multipliers, location_id, is_active)
           VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7, $8)
           RETURNING id""",
        user["business_id"], body.name, body.base_amount, body.bedroom_delta,
        body.bathroom_delta,
        _json.dumps({
            "basic": str(body.tier_multipliers.basic),
            "deep": str(body.tier_multipliers.deep),
            "premium": str(body.tier_multipliers.premium),
        }),
        _uuid(body.location_id), body.is_active,
    )
    return {"id": str(row["id"])}


@router.patch("/pricing/formulas/{formula_id}")
async def update_formula(
    slug: str,
    formula_id: str,
    body: FormulaUpdate,
    user: dict = Depends(require_role("owner")),
    db: Database = Depends(get_db),
):
    import json as _json
    fid = _uuid(formula_id)
    updates = body.model_dump(exclude_unset=True)
    if not updates:
        return {"ok": True}
    sets, vals = [], []
    idx = 1
    for k, v in updates.items():
        if k == "tier_multipliers":
            sets.append(f"tier_multipliers = ${idx}::jsonb")
            vals.append(_json.dumps({
                "basic": str(v["basic"]),
                "deep": str(v["deep"]),
                "premium": str(v["premium"]),
            }))
        else:
            sets.append(f"{k} = ${idx}")
            vals.append(v)
        idx += 1
    sets.append("updated_at = NOW()")
    vals.extend([fid, user["business_id"]])
    sql = f"UPDATE cleaning_pricing_formulas SET {', '.join(sets)} WHERE id = ${idx} AND business_id = ${idx+1}"
    res = await db.pool.execute(sql, *vals)
    if res.endswith("0"):
        raise HTTPException(status_code=404, detail="Formula not found.")
    return {"ok": True}


# ===========================================================================
# OVERRIDES
# ===========================================================================


@router.get("/pricing/overrides")
async def list_overrides(
    slug: str,
    is_active: Optional[bool] = True,
    user: dict = Depends(require_role("owner")),
    db: Database = Depends(get_db),
):
    where = ["s.business_id = $1"]
    params: list[Any] = [user["business_id"]]
    if is_active is not None:
        where.append("o.is_active = $2")
        params.append(is_active)
    rows = await db.pool.fetch(
        f"""SELECT o.id, o.service_id, o.tier, o.price_override, o.reason,
                   o.is_active, o.created_at,
                   s.name AS service_name, s.base_price AS formula_price
            FROM cleaning_service_overrides o
            JOIN cleaning_services s ON s.id = o.service_id
            WHERE {' AND '.join(where)}
            ORDER BY s.name, o.tier""",
        *params,
    )
    return {"overrides": [
        {
            "id": str(r["id"]),
            "service_id": str(r["service_id"]),
            "service_name": r["service_name"],
            "tier": r["tier"],
            "price_override": str(r["price_override"]),
            "formula_price": str(r["formula_price"]) if r["formula_price"] else None,
            "reason": r["reason"],
            "is_active": r["is_active"],
            "created_at": r["created_at"].isoformat() if r["created_at"] else None,
        }
        for r in rows
    ]}


@router.delete("/pricing/overrides/{override_id}")
async def delete_override(
    slug: str,
    override_id: str,
    user: dict = Depends(require_role("owner")),
    db: Database = Depends(get_db),
):
    oid = _uuid(override_id)
    res = await db.pool.execute(
        """DELETE FROM cleaning_service_overrides
           WHERE id = $1
             AND service_id IN (SELECT id FROM cleaning_services WHERE business_id = $2)""",
        oid, user["business_id"],
    )
    if res.endswith("0"):
        raise HTTPException(status_code=404, detail="Override not found.")
    return {"ok": True}


# ===========================================================================
# EXTRAS (catalog)
# ===========================================================================


class ExtraCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    price: Decimal = Field(..., ge=Decimal("0"), le=Decimal("10000"))
    sort_order: int = Field(default=0, ge=0, le=1000)
    is_active: bool = True


class ExtraUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    price: Optional[Decimal] = Field(None, ge=Decimal("0"), le=Decimal("10000"))
    sort_order: Optional[int] = Field(None, ge=0, le=1000)
    is_active: Optional[bool] = None


@router.get("/pricing/extras")
async def list_extras(
    slug: str,
    include_inactive: bool = False,
    user: dict = Depends(require_role("owner")),
    db: Database = Depends(get_db),
):
    where = ["business_id = $1"]
    if not include_inactive:
        where.append("is_active = TRUE")
    rows = await db.pool.fetch(
        f"""SELECT e.id, e.name, e.price, e.sort_order, e.is_active, e.created_at,
                   (SELECT COUNT(*) FROM cleaning_service_extras se WHERE se.extra_id = e.id) AS allowed_in_count
            FROM cleaning_extras e
            WHERE {' AND '.join(where)}
            ORDER BY e.sort_order, e.name""",
        user["business_id"],
    )
    return {"extras": [
        {
            "id": str(r["id"]),
            "name": r["name"],
            "price": str(r["price"]),
            "sort_order": r["sort_order"],
            "is_active": r["is_active"],
            "allowed_in_count": r["allowed_in_count"],
            "created_at": r["created_at"].isoformat() if r["created_at"] else None,
        }
        for r in rows
    ]}


@router.post("/pricing/extras", status_code=201)
async def create_extra(
    slug: str,
    body: ExtraCreate,
    user: dict = Depends(require_role("owner")),
    db: Database = Depends(get_db),
):
    row = await db.pool.fetchrow(
        """INSERT INTO cleaning_extras (business_id, name, price, sort_order, is_active)
           VALUES ($1, $2, $3, $4, $5) RETURNING id""",
        user["business_id"], body.name, body.price, body.sort_order, body.is_active,
    )
    return {"id": str(row["id"])}


@router.patch("/pricing/extras/{extra_id}")
async def update_extra(
    slug: str,
    extra_id: str,
    body: ExtraUpdate,
    user: dict = Depends(require_role("owner")),
    db: Database = Depends(get_db),
):
    eid = _uuid(extra_id)
    updates = body.model_dump(exclude_unset=True)
    if not updates:
        return {"ok": True}
    sets, vals = [], []
    idx = 1
    for k, v in updates.items():
        sets.append(f"{k} = ${idx}")
        vals.append(v)
        idx += 1
    vals.extend([eid, user["business_id"]])
    sql = f"UPDATE cleaning_extras SET {', '.join(sets)} WHERE id = ${idx} AND business_id = ${idx+1}"
    res = await db.pool.execute(sql, *vals)
    if res.endswith("0"):
        raise HTTPException(status_code=404, detail="Extra not found.")
    return {"ok": True}


# ===========================================================================
# FREQUENCIES
# ===========================================================================


class FrequencyCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=50)
    interval_weeks: Optional[int] = Field(None, ge=1, le=52)
    discount_pct: Decimal = Field(..., ge=Decimal("0"), le=Decimal("100"))
    is_default: bool = False


class FrequencyUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=50)
    interval_weeks: Optional[int] = Field(None, ge=1, le=52)
    discount_pct: Optional[Decimal] = Field(None, ge=Decimal("0"), le=Decimal("100"))
    is_default: Optional[bool] = None
    is_archived: Optional[bool] = None


@router.get("/pricing/frequencies")
async def list_frequencies(
    slug: str,
    include_archived: bool = False,
    user: dict = Depends(require_role("owner")),
    db: Database = Depends(get_db),
):
    where = ["business_id = $1"]
    if not include_archived:
        where.append("(is_archived IS NULL OR is_archived = FALSE)")
    rows = await db.pool.fetch(
        f"""SELECT f.id, f.name, f.interval_weeks, f.discount_pct, f.is_default,
                   f.is_archived, f.created_at,
                   (SELECT COUNT(*) FROM cleaning_client_schedules s
                     WHERE s.business_id = f.business_id
                       AND s.status = 'active'
                       AND s.client_id IS NOT NULL) AS usage_count
            FROM cleaning_frequencies f
            WHERE {' AND '.join(where)}
            ORDER BY f.is_default DESC, COALESCE(f.interval_weeks, 999), f.name""",
        user["business_id"],
    )
    return {"frequencies": [
        {
            "id": str(r["id"]),
            "name": r["name"],
            "interval_weeks": r["interval_weeks"],
            "discount_pct": str(r["discount_pct"]),
            "is_default": r["is_default"],
            "is_archived": r["is_archived"] or False,
            "usage_count": r["usage_count"],
            "created_at": r["created_at"].isoformat() if r["created_at"] else None,
        }
        for r in rows
    ]}


@router.post("/pricing/frequencies", status_code=201)
async def create_frequency(
    slug: str,
    body: FrequencyCreate,
    user: dict = Depends(require_role("owner")),
    db: Database = Depends(get_db),
):
    async with db.pool.acquire() as conn:
        async with conn.transaction():
            if body.is_default:
                await conn.execute(
                    "UPDATE cleaning_frequencies SET is_default = FALSE WHERE business_id = $1",
                    user["business_id"],
                )
            row = await conn.fetchrow(
                """INSERT INTO cleaning_frequencies
                     (business_id, name, interval_weeks, discount_pct, is_default)
                   VALUES ($1, $2, $3, $4, $5) RETURNING id""",
                user["business_id"], body.name, body.interval_weeks,
                body.discount_pct, body.is_default,
            )
    return {"id": str(row["id"])}


@router.patch("/pricing/frequencies/{freq_id}")
async def update_frequency(
    slug: str,
    freq_id: str,
    body: FrequencyUpdate,
    user: dict = Depends(require_role("owner")),
    db: Database = Depends(get_db),
):
    fid = _uuid(freq_id)
    updates = body.model_dump(exclude_unset=True)
    if not updates:
        return {"ok": True}
    sets, vals = [], []
    idx = 1
    for k, v in updates.items():
        sets.append(f"{k} = ${idx}")
        vals.append(v)
        idx += 1
    vals.extend([fid, user["business_id"]])
    sql = f"UPDATE cleaning_frequencies SET {', '.join(sets)} WHERE id = ${idx} AND business_id = ${idx+1}"
    res = await db.pool.execute(sql, *vals)
    if res.endswith("0"):
        raise HTTPException(status_code=404, detail="Frequency not found.")
    return {"ok": True}


@router.post("/pricing/frequencies/{freq_id}/set-default")
async def set_default_frequency(
    slug: str,
    freq_id: str,
    user: dict = Depends(require_role("owner")),
    db: Database = Depends(get_db),
):
    fid = _uuid(freq_id)
    async with db.pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                "UPDATE cleaning_frequencies SET is_default = FALSE WHERE business_id = $1",
                user["business_id"],
            )
            res = await conn.execute(
                "UPDATE cleaning_frequencies SET is_default = TRUE WHERE id = $1 AND business_id = $2",
                fid, user["business_id"],
            )
            if res.endswith("0"):
                raise HTTPException(status_code=404, detail="Frequency not found.")
    return {"ok": True}


# ===========================================================================
# TAXES
# ===========================================================================


class TaxCreate(BaseModel):
    location_id: str
    tax_pct: Decimal = Field(..., ge=Decimal("0"), le=Decimal("100"))
    effective_date: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")

    @field_validator("location_id")
    @classmethod
    def _uuid_loc(cls, v):
        return _validate_uuid(v, "location_id")


class TaxUpdate(BaseModel):
    tax_pct: Optional[Decimal] = Field(None, ge=Decimal("0"), le=Decimal("100"))
    effective_date: Optional[str] = Field(None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    is_archived: Optional[bool] = None


@router.get("/pricing/taxes")
async def list_taxes(
    slug: str,
    location_id: Optional[str] = None,
    include_archived: bool = False,
    user: dict = Depends(require_role("owner")),
    db: Database = Depends(get_db),
):
    where = ["business_id = $1"]
    params: list[Any] = [user["business_id"]]
    if location_id:
        where.append(f"location_id = ${len(params) + 1}")
        params.append(_uuid(location_id))
    if not include_archived:
        where.append("(is_archived IS NULL OR is_archived = FALSE)")
    rows = await db.pool.fetch(
        f"""SELECT id, location_id, tax_pct, effective_date, is_archived, created_at,
                   (SELECT COUNT(*) FROM cleaning_bookings b
                     WHERE b.business_id = t.business_id
                       AND b.location_id = t.location_id
                       AND b.scheduled_date >= t.effective_date
                    ) AS usage_count
            FROM cleaning_sales_taxes t
            WHERE {' AND '.join(where)}
            ORDER BY effective_date DESC""",
        *params,
    )
    return {"taxes": [
        {
            "id": str(r["id"]),
            "location_id": str(r["location_id"]),
            "tax_pct": str(r["tax_pct"]),
            "effective_date": r["effective_date"].isoformat() if r["effective_date"] else None,
            "is_archived": r["is_archived"] or False,
            "usage_count": r["usage_count"],
            "created_at": r["created_at"].isoformat() if r["created_at"] else None,
        }
        for r in rows
    ]}


@router.post("/pricing/taxes", status_code=201)
async def create_tax(
    slug: str,
    body: TaxCreate,
    user: dict = Depends(require_role("owner")),
    db: Database = Depends(get_db),
):
    from datetime import date
    eff = date.fromisoformat(body.effective_date)
    # Chronology check — no later row must exist for this location (unarchived)
    later = await db.pool.fetchval(
        """SELECT COUNT(*) FROM cleaning_sales_taxes
           WHERE business_id = $1 AND location_id = $2
             AND effective_date >= $3
             AND (is_archived IS NULL OR is_archived = FALSE)""",
        user["business_id"], _uuid(body.location_id), eff,
    )
    if later:
        raise HTTPException(
            status_code=409,
            detail="A later rate exists for this location. Archive it first to supersede.",
        )
    row = await db.pool.fetchrow(
        """INSERT INTO cleaning_sales_taxes
             (business_id, location_id, tax_pct, effective_date, is_archived)
           VALUES ($1, $2, $3, $4, FALSE) RETURNING id""",
        user["business_id"], _uuid(body.location_id), body.tax_pct, eff,
    )
    return {"id": str(row["id"])}


@router.patch("/pricing/taxes/{tax_id}")
async def update_tax(
    slug: str,
    tax_id: str,
    body: TaxUpdate,
    user: dict = Depends(require_role("owner")),
    db: Database = Depends(get_db),
):
    from datetime import date
    tid = _uuid(tax_id)
    updates = body.model_dump(exclude_unset=True)
    if not updates:
        return {"ok": True}
    if "effective_date" in updates and updates["effective_date"]:
        updates["effective_date"] = date.fromisoformat(updates["effective_date"])
    sets, vals = [], []
    idx = 1
    for k, v in updates.items():
        sets.append(f"{k} = ${idx}")
        vals.append(v)
        idx += 1
    vals.extend([tid, user["business_id"]])
    sql = f"UPDATE cleaning_sales_taxes SET {', '.join(sets)} WHERE id = ${idx} AND business_id = ${idx+1}"
    res = await db.pool.execute(sql, *vals)
    if res.endswith("0"):
        raise HTTPException(status_code=404, detail="Tax rate not found.")
    return {"ok": True}


# ===========================================================================
# SERVICE EXTRAS WHITELIST
# ===========================================================================


class ServiceExtrasBody(BaseModel):
    extra_ids: list[str] = Field(default_factory=list, max_length=100)

    @field_validator("extra_ids")
    @classmethod
    def _uuid_all(cls, v):
        for eid in v:
            _validate_uuid(eid, "extra_ids[*]")
        return v


@router.get("/services/{service_id}/extras")
async def get_service_whitelist(
    slug: str,
    service_id: str,
    user: dict = Depends(require_role("owner")),
    db: Database = Depends(get_db),
):
    sid = _uuid(service_id)
    # Ensure service belongs to this business
    owner = await db.pool.fetchval(
        "SELECT 1 FROM cleaning_services WHERE id = $1 AND business_id = $2",
        sid, user["business_id"],
    )
    if not owner:
        raise HTTPException(status_code=404, detail="Service not found.")
    rows = await db.pool.fetch(
        """SELECT e.id, e.name, e.price
           FROM cleaning_service_extras se
           JOIN cleaning_extras e ON e.id = se.extra_id
           WHERE se.service_id = $1
           ORDER BY e.sort_order, e.name""",
        sid,
    )
    return {"extras": [
        {
            "id": str(r["id"]),
            "extra_id": str(r["id"]),
            "name": r["name"],
            "price": str(r["price"]),
        }
        for r in rows
    ]}


@router.put("/services/{service_id}/extras")
async def set_service_whitelist(
    slug: str,
    service_id: str,
    body: ServiceExtrasBody,
    user: dict = Depends(require_role("owner")),
    db: Database = Depends(get_db),
):
    sid = _uuid(service_id)
    owner = await db.pool.fetchval(
        "SELECT 1 FROM cleaning_services WHERE id = $1 AND business_id = $2",
        sid, user["business_id"],
    )
    if not owner:
        raise HTTPException(status_code=404, detail="Service not found.")
    extra_uuids = [_uuid(eid) for eid in body.extra_ids]
    async with db.pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                "DELETE FROM cleaning_service_extras WHERE service_id = $1", sid,
            )
            for eid in extra_uuids:
                await conn.execute(
                    "INSERT INTO cleaning_service_extras (service_id, extra_id) VALUES ($1, $2) ON CONFLICT DO NOTHING",
                    sid, eid,
                )
    return {"ok": True, "count": len(extra_uuids)}


# ===========================================================================
# BOOKING RECALCULATE
# ===========================================================================


# ===========================================================================
# BOOKING CREATE (via pricing engine — closes the last C4 gap)
# ===========================================================================


class BookingCreateRequest(BaseModel):
    """Create booking with real pricing engine integration."""

    client_id: str
    service_id: str
    scheduled_date: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    scheduled_start: str = Field(..., pattern=r"^\d{2}:\d{2}(:\d{2})?$")
    estimated_duration_minutes: int = Field(default=120, ge=15, le=600)
    team_id: Optional[str] = None
    tier: Literal["basic", "deep", "premium"] = "basic"
    extras: list[dict[str, Any]] = Field(default_factory=list, max_length=50)
    frequency_id: Optional[str] = None
    adjustment_amount: Decimal = Field(
        default=Decimal("0"), ge=Decimal("-10000"), le=Decimal("10000")
    )
    adjustment_reason: Optional[str] = Field(None, max_length=255)
    location_id: Optional[str] = None
    special_instructions: Optional[str] = Field(None, max_length=1000)
    source: Literal["manual", "ai_chat", "booking_page", "phone", "referral"] = "manual"

    @field_validator("client_id", "service_id", "team_id", "frequency_id", "location_id")
    @classmethod
    def _uuid(cls, v, info):
        return _validate_uuid(v, info.field_name)


@router.post("/bookings", status_code=201)
async def create_booking(
    slug: str,
    body: BookingCreateRequest,
    user: dict = Depends(require_role("owner")),
    db: Database = Depends(get_db),
):
    """
    Create a booking with pricing engine integration.

    Runs calculate_booking_price → persists cleaning_bookings row with
    final_price + discount/tax/adjustment columns + immutable
    price_snapshot JSONB + cleaning_booking_extras rows.
    """
    try:
        result = await create_booking_with_pricing(
            db,
            business_id=user["business_id"],
            client_id=_uuid(body.client_id),
            service_id=_uuid(body.service_id),
            scheduled_date=body.scheduled_date,
            scheduled_start=body.scheduled_start,
            estimated_duration_minutes=body.estimated_duration_minutes,
            team_id=_uuid(body.team_id) if body.team_id else None,
            tier=body.tier,
            extras=body.extras,
            frequency_id=_uuid(body.frequency_id) if body.frequency_id else None,
            adjustment_amount=body.adjustment_amount,
            adjustment_reason=body.adjustment_reason,
            location_id=_uuid(body.location_id) if body.location_id else None,
            special_instructions=body.special_instructions,
            source=body.source,
            status="scheduled",
        )
        return {
            "booking_id": result["booking_id"],
            "final_price": str(result["breakdown"]["final_amount"]),
            "extras_written": result["extras_written"],
        }
    except PricingConfigError as exc:
        logger.warning("create booking failed: %s", exc)
        msg = str(exc).lower()
        if "formula" in msg:
            public = "Pricing configuration incomplete."
        elif "service not found" in msg:
            public = "Service not found."
        else:
            public = "Pricing configuration error."
        raise HTTPException(status_code=400, detail=public)


@router.post("/bookings/{booking_id}/recalculate")
async def recalculate_booking(
    slug: str,
    booking_id: str,
    user: dict = Depends(require_role("owner")),
    db: Database = Depends(get_db),
):
    bid = _uuid(booking_id)
    # Ensure booking belongs to this business
    row = await db.pool.fetchval(
        "SELECT 1 FROM cleaning_bookings WHERE id = $1 AND business_id = $2",
        bid, user["business_id"],
    )
    if not row:
        raise HTTPException(status_code=404, detail="Booking not found.")
    try:
        result = await recalculate_booking_snapshot(
            db, booking_id=bid, recalculated_by=user.get("user_id"),
        )
        return {
            "ok": True,
            "breakdown": {
                k: str(v) if hasattr(v, "__class__") and v.__class__.__name__ == "Decimal" else v
                for k, v in result["breakdown"].items()
                if k not in ("extras",)  # nested, skip for simplicity
            },
        }
    except PricingConfigError as exc:
        logger.warning("recalculate failed for %s: %s", bid, exc)
        raise HTTPException(status_code=400, detail="Could not recalculate pricing.")


# ===========================================================================
# LOCATIONS (wrap cleaning_areas for UI)
# ===========================================================================


@router.get("/locations")
async def list_locations(
    slug: str,
    user: dict = Depends(require_role("owner")),
    db: Database = Depends(get_db),
):
    rows = await db.pool.fetch(
        """SELECT id, name, is_default,
                  CASE WHEN is_archived IS TRUE THEN TRUE ELSE FALSE END AS is_archived
           FROM cleaning_areas
           WHERE business_id = $1
             AND (is_archived IS NULL OR is_archived = FALSE)
           ORDER BY is_default DESC, name""",
        user["business_id"],
    )
    return {"locations": [
        {
            "id": str(r["id"]),
            "name": r["name"],
            "is_default": r["is_default"] or False,
        }
        for r in rows
    ]}
