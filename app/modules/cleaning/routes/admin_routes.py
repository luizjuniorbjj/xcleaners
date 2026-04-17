"""
Xcleaners — Platform Admin Routes (super_admin only)

Cross-tenant endpoints for the platform administrator (LPJ Services LLC).
NOT scoped to a single business — aggregates across all tenants.

Endpoints:
  GET  /api/v1/admin/businesses      — list all businesses + key stats
  GET  /api/v1/admin/stats           — platform-wide KPIs (MRR, user count, etc.)

Access control: ONLY users with platform role 'admin'.
Guarded by `require_platform_admin()` — 403 for anyone else.

Author: @dev (Neo), 2026-04-17
"""

from __future__ import annotations

import json
import logging
import re
from typing import Optional

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, EmailStr, Field

from app.auth import get_current_user
from app.database import get_db, Database
from app.security import hash_password

logger = logging.getLogger("xcleaners.admin_routes")


def _slugify(name: str) -> str:
    """Generate URL-safe slug from a business name."""
    s = name.lower().strip()
    s = re.sub(r"[^a-z0-9\s-]", "", s)
    s = re.sub(r"\s+", "-", s)
    s = re.sub(r"-+", "-", s)
    return s.strip("-") or "business"


class CreateBusinessBody(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    owner_email: EmailStr
    owner_password: str = Field(..., min_length=6, max_length=200)
    owner_name: Optional[str] = Field(None, max_length=200)
    plan: str = Field(default="basic", pattern=r"^(basic|intermediate|maximum)$")
    status: str = Field(default="active", pattern=r"^(active|trial|suspended)$")
    city: Optional[str] = Field(None, max_length=100)
    state: Optional[str] = Field(None, max_length=20)
    timezone: str = Field(default="America/New_York", max_length=50)


# ============================================================================
# GUARD
# ============================================================================

async def require_platform_admin(
    current_user: dict = Depends(get_current_user),
) -> dict:
    """Require users.role == 'admin'. 403 otherwise."""
    if current_user.get("role") != "admin":
        raise HTTPException(
            status_code=403,
            detail="Platform admin access required",
        )
    return current_user


# ============================================================================
# ROUTER
# ============================================================================

router = APIRouter(
    prefix="/api/v1/admin",
    tags=["Xcleaners Platform Admin"],
)


# ============================================================================
# GET /admin/businesses
# ============================================================================

@router.get("/businesses")
async def list_all_businesses(
    status: Optional[str] = Query(None, description="Filter by businesses.status"),
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    user: dict = Depends(require_platform_admin),
    db: Database = Depends(get_db),
):
    """
    List ALL businesses on the platform with per-business stats.
    Used by the super-admin dashboard.
    """
    where = []
    params: list = []
    if status:
        params.append(status)
        where.append(f"b.status = ${len(params)}")
    where_sql = f"WHERE {' AND '.join(where)}" if where else ""

    params.extend([limit, offset])
    sql = f"""
        SELECT
            b.id,
            b.slug,
            b.name,
            b.logo_url,
            b.status,
            b.created_at,
            b.stripe_account_id,
            b.stripe_account_status,
            b.stripe_charges_enabled,
            b.stripe_payouts_enabled,
            -- owner email (first owner of this business)
            (
                SELECT u.email
                FROM cleaning_user_roles cur
                JOIN users u ON u.id = cur.user_id
                WHERE cur.business_id = b.id
                  AND cur.role = 'owner'
                  AND cur.is_active = TRUE
                ORDER BY cur.created_at
                LIMIT 1
            ) AS owner_email,
            -- aggregates
            (SELECT COUNT(*) FROM cleaning_clients WHERE business_id = b.id) AS clients_count,
            (SELECT COUNT(*) FROM cleaning_team_members
                WHERE business_id = b.id AND status = 'active') AS cleaners_count,
            (SELECT COUNT(*) FROM cleaning_bookings
                WHERE business_id = b.id) AS bookings_total,
            (SELECT COUNT(*) FROM cleaning_bookings
                WHERE business_id = b.id AND status = 'completed') AS bookings_completed
        FROM businesses b
        {where_sql}
        ORDER BY b.created_at DESC
        LIMIT ${len(params) - 1} OFFSET ${len(params)}
    """
    rows = await db.pool.fetch(sql, *params)

    items = []
    for r in rows:
        d = dict(r)
        for k, v in list(d.items()):
            if hasattr(v, "isoformat"):  # datetime
                d[k] = v.isoformat()
            elif hasattr(v, "hex") and k.endswith("_id"):  # uuid
                d[k] = str(v)
        items.append(d)

    return {"items": items, "count": len(items), "limit": limit, "offset": offset}


# ============================================================================
# POST /admin/businesses  — create a new business (and owner user if needed)
# ============================================================================

@router.post("/businesses", status_code=201)
async def create_business(
    body: CreateBusinessBody,
    admin: dict = Depends(require_platform_admin),
    db: Database = Depends(get_db),
):
    """
    Create a new business + (reuse or create) owner user + grant owner role.

    Behavior:
      - If `owner_email` already belongs to an existing user, reuses that user
        (password is NOT overwritten).
      - Otherwise, creates a new users row with hashed_password + role='lead'.
      - Slug is derived from `name`. If the auto slug collides, suffixes -2, -3, ...
      - Inserts cleaning_user_roles(user_id, business_id, role='owner', is_active=TRUE).
      - All writes run in a single transaction — rolls back on any failure.
    """
    name = body.name.strip()
    base_slug = _slugify(name)
    email = str(body.owner_email).lower().strip()

    async with db.pool.acquire() as conn:
        async with conn.transaction():
            # 1. Resolve unique slug (suffix -2, -3 if needed — cap at 50 attempts)
            slug = base_slug
            for suffix in range(2, 52):
                exists = await conn.fetchval(
                    "SELECT 1 FROM businesses WHERE slug = $1", slug,
                )
                if not exists:
                    break
                slug = f"{base_slug}-{suffix}"
            else:
                raise HTTPException(status_code=409, detail="Could not resolve unique slug")

            # 2. Reuse existing user or create new one
            user_row = await conn.fetchrow(
                "SELECT id FROM users WHERE email = $1", email,
            )
            if user_row:
                owner_id = user_row["id"]
                logger.info("[ADMIN] Reusing existing user %s as owner of %s", email, slug)
            else:
                owner_id = await conn.fetchval(
                    """
                    INSERT INTO users (email, hashed_password, nome, role)
                    VALUES ($1, $2, $3, 'lead')
                    RETURNING id
                    """,
                    email,
                    hash_password(body.owner_password),
                    body.owner_name or name,
                )
                logger.info("[ADMIN] Created new user %s for business %s", email, slug)

            # 3. Build cleaning_settings default JSON
            cleaning_settings = {
                "business_hours": {"start": "07:00", "end": "18:00"},
                "cancellation_policy_hours": 24,
                "timezone": body.timezone,
                "tax_rate": 0.0,
                "currency": "USD",
                "language": "en",
            }
            if body.city:
                cleaning_settings["city"] = body.city
            if body.state:
                cleaning_settings["state"] = body.state.upper()

            # 4. Insert business
            try:
                business_row = await conn.fetchrow(
                    """
                    INSERT INTO businesses (name, slug, owner_id, plan, status, cleaning_settings)
                    VALUES ($1, $2, $3, $4, $5, $6::jsonb)
                    RETURNING id, name, slug, plan, status, created_at
                    """,
                    name, slug, owner_id, body.plan, body.status,
                    json.dumps(cleaning_settings),
                )
            except asyncpg.exceptions.UniqueViolationError as e:
                raise HTTPException(status_code=409, detail=f"Duplicate: {e.constraint_name}") from None
            except asyncpg.exceptions.UndefinedColumnError as e:
                # Minimal fallback if schema lacks optional columns
                logger.warning("[ADMIN] Schema drift on businesses INSERT (%s) — retrying minimal", e)
                business_row = await conn.fetchrow(
                    """
                    INSERT INTO businesses (name, slug, owner_id, status)
                    VALUES ($1, $2, $3, $4)
                    RETURNING id, name, slug, status, created_at
                    """,
                    name, slug, owner_id, body.status,
                )

            # 5. Grant owner role in cleaning_user_roles (idempotent)
            await conn.execute(
                """
                INSERT INTO cleaning_user_roles (user_id, business_id, role, is_active)
                VALUES ($1, $2, 'owner', TRUE)
                ON CONFLICT (user_id, business_id, role) DO UPDATE SET is_active = TRUE
                """,
                owner_id, business_row["id"],
            )

    return {
        "id": str(business_row["id"]),
        "name": business_row["name"],
        "slug": business_row["slug"],
        "plan": business_row.get("plan") if hasattr(business_row, "get") else body.plan,
        "status": business_row["status"],
        "owner_id": str(owner_id),
        "owner_email": email,
        "created_at": business_row["created_at"].isoformat() if business_row["created_at"] else None,
    }


# ============================================================================
# GET /admin/stats
# ============================================================================

@router.get("/stats")
async def platform_stats(
    user: dict = Depends(require_platform_admin),
    db: Database = Depends(get_db),
):
    """Platform-wide KPIs for the super-admin dashboard."""
    row = await db.pool.fetchrow(
        """
        SELECT
            (SELECT COUNT(*) FROM businesses) AS total_businesses,
            (SELECT COUNT(*) FROM businesses
                WHERE status IS NULL OR status NOT IN ('cancelled','suspended'))
                AS active_businesses,
            (SELECT COUNT(*) FROM users WHERE is_active = TRUE) AS active_users,
            (SELECT COUNT(*) FROM cleaning_team_members WHERE status = 'active')
                AS active_cleaners,
            (SELECT COUNT(*) FROM cleaning_clients) AS total_clients,
            (SELECT COUNT(*) FROM cleaning_bookings
                WHERE created_at >= NOW() - INTERVAL '30 days') AS bookings_last_30d,
            (SELECT COUNT(*) FROM businesses
                WHERE stripe_charges_enabled = TRUE) AS businesses_with_stripe
        """,
    )
    return dict(row) if row else {}
