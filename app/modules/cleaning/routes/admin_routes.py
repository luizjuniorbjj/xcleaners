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

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.auth import get_current_user
from app.database import get_db, Database

logger = logging.getLogger("xcleaners.admin_routes")


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
