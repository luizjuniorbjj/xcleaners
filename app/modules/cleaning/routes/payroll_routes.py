"""
Xcleaners — Payroll Routes (60% Commission Split)

Owner-facing endpoints to list, summarize and mark-paid cleaner earnings,
plus a cleaner-facing /my-earnings endpoint.

Endpoints:
  GET  /api/v1/clean/{slug}/payroll/earnings       (owner)  list + filters
  GET  /api/v1/clean/{slug}/payroll/summary        (owner)  totals per cleaner
  POST /api/v1/clean/{slug}/payroll/mark-paid      (owner)  bulk update status → paid
  POST /api/v1/clean/{slug}/payroll/{id}/void      (owner)  void single earning
  GET  /api/v1/clean/{slug}/my-earnings            (cleaner) self-view

Author: @dev (Neo), 2026-04-16 (Sprint D Track B)
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator

from app.database import get_db, Database
from app.modules.cleaning.middleware.role_guard import require_role
from app.modules.cleaning.services.payroll_service import (
    PayrollError,
    get_cleaner_summary,
    list_earnings,
    mark_paid,
    void_earning,
)

logger = logging.getLogger("xcleaners.payroll_routes")


# ============================================================================
# PYDANTIC MODELS
# ============================================================================

class MarkPaidRequest(BaseModel):
    earnings_ids: list[UUID] = Field(..., min_length=1, max_length=500)
    payout_ref: str = Field(..., min_length=1, max_length=100)

    @field_validator("payout_ref")
    @classmethod
    def _strip(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("payout_ref must not be blank")
        return v


class VoidRequest(BaseModel):
    reason: Optional[str] = Field(None, max_length=255)


# ============================================================================
# ROUTER
# ============================================================================

router = APIRouter(
    prefix="/api/v1/clean/{slug}",
    tags=["Xcleaners Payroll"],
)


# ============================================================================
# OWNER ENDPOINTS
# ============================================================================

@router.get("/payroll/earnings")
async def get_earnings(
    slug: str,
    cleaner_id: Optional[UUID] = Query(None),
    status: Optional[str] = Query(None, pattern=r"^(pending|paid|void)$"),
    from_date: Optional[date] = Query(None, description="YYYY-MM-DD inclusive"),
    to_date: Optional[date] = Query(None, description="YYYY-MM-DD inclusive"),
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    user: dict = Depends(require_role("owner")),
    db: Database = Depends(get_db),
):
    """List earnings for the current business, with filters."""
    try:
        rows = await list_earnings(
            db, user["business_id"],
            cleaner_id=cleaner_id,
            status=status,
            from_date=from_date,
            to_date=to_date,
            limit=limit,
            offset=offset,
        )
    except PayrollError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    # Serialize Decimals → str (match pricing_routes convention)
    for r in rows:
        for k in ("gross_amount", "net_amount", "commission_pct", "booking_final_price"):
            if r.get(k) is not None:
                r[k] = str(r[k])
    return {"items": rows, "count": len(rows), "limit": limit, "offset": offset}


@router.get("/payroll/summary")
async def get_summary(
    slug: str,
    from_date: Optional[date] = Query(None),
    to_date: Optional[date] = Query(None),
    user: dict = Depends(require_role("owner")),
    db: Database = Depends(get_db),
):
    """Aggregate earnings by cleaner for a period."""
    rows = await get_cleaner_summary(
        db, user["business_id"],
        from_date=from_date,
        to_date=to_date,
    )
    for r in rows:
        for k in ("gross_total", "net_total", "pending_net", "paid_net"):
            if r.get(k) is not None:
                r[k] = str(r[k])
    return {"items": rows, "from_date": from_date, "to_date": to_date}


@router.post("/payroll/mark-paid")
async def post_mark_paid(
    slug: str,
    body: MarkPaidRequest,
    user: dict = Depends(require_role("owner")),
    db: Database = Depends(get_db),
):
    """Bulk mark earnings as paid (idempotent with same payout_ref)."""
    try:
        return await mark_paid(
            db, user["business_id"], body.earnings_ids, body.payout_ref,
        )
    except PayrollError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/payroll/{earning_id}/void")
async def post_void(
    slug: str,
    earning_id: UUID,
    body: VoidRequest,
    user: dict = Depends(require_role("owner")),
    db: Database = Depends(get_db),
):
    """Void a single pending earning (e.g. booking refunded)."""
    ok = await void_earning(db, user["business_id"], earning_id, body.reason)
    if not ok:
        raise HTTPException(
            status_code=409,
            detail="Earning not found, not owned by this business, or not in pending state",
        )
    return {"voided": True, "id": str(earning_id)}


# ============================================================================
# CLEANER ENDPOINT — REMOVED in Sprint Fix 2026-04-17 (Fase 2b.2)
# ============================================================================
# The GET /my-earnings endpoint previously declared here collided with
# cleaner_routes.py:314 which registers the SAME path on the SAME prefix.
# Since xcleaners_main.py registers cleaning_cleaner_router BEFORE
# cleaning_payroll_router, the cleaner_routes version won and this one
# was silently dead code. Removing it eliminates the ambiguity and the
# maintenance trap. When Sprint D Track C (UI refactor) ships, the
# cleaner-facing earnings view will be migrated to this module's shape
# ({items, count} with commission snapshots) and the cleaner_routes
# version will be removed. Until then, cleaner_routes.py:/my-earnings
# remains the single source of truth for this endpoint.
# ============================================================================
