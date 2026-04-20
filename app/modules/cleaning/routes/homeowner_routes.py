"""
Xcleaners v3 — Homeowner Routes (Sprint 3).

Endpoints for the homeowner experience:
  GET  /api/v1/clean/{slug}/my-bookings               — my bookings
  GET  /api/v1/clean/{slug}/my-bookings/{id}           — booking detail
  POST /api/v1/clean/{slug}/my-bookings/{id}/reschedule — reschedule
  POST /api/v1/clean/{slug}/my-bookings/{id}/cancel     — cancel
  GET  /api/v1/clean/{slug}/my-invoices                — my invoices
  GET  /api/v1/clean/{slug}/my-preferences             — my house preferences
  PUT  /api/v1/clean/{slug}/my-preferences             — update preferences
  POST /api/v1/clean/{slug}/my-bookings/{id}/review    — rate service

All protected by require_role("homeowner").
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.database import get_db, Database
from app.modules.cleaning.middleware.role_guard import require_role
from app.modules.cleaning.services.homeowner_service import (
    get_my_bookings,
    get_booking_detail,
    reschedule_booking,
    cancel_booking,
    get_my_invoices,
    get_my_preferences,
    update_my_preferences,
    rate_service,
)

logger = logging.getLogger("xcleaners.homeowner_routes")

router = APIRouter(
    prefix="/api/v1/clean/{slug}",
    tags=["Xcleaners Homeowner"],
)


# ============================================
# REQUEST MODELS
# ============================================

class RescheduleRequest(BaseModel):
    new_date: str = Field(..., description="New date YYYY-MM-DD")
    new_time: Optional[str] = Field(None, description="New time HH:MM")


class CancelRequest(BaseModel):
    reason: Optional[str] = Field(None, max_length=1000)


class ReviewRequest(BaseModel):
    rating: int = Field(..., ge=1, le=5, description="1-5 star rating")
    comment: Optional[str] = Field(None, max_length=2000)


# ============================================
# HELPER: resolve client_id
# ============================================

async def _resolve_client_id(user: dict, db: Database) -> str:
    """
    Get the cleaning_clients.id linked to the current homeowner user.
    A homeowner's user_id is linked via cleaning_clients.user_id.
    """
    client = await db.pool.fetchrow(
        """SELECT id FROM cleaning_clients
           WHERE user_id = $1 AND business_id = $2 AND status != 'blocked'
           LIMIT 1""",
        user["user_id"], user["business_id"],
    )
    if not client:
        raise HTTPException(
            status_code=403,
            detail="Your client profile was not found. Contact your cleaning service.",
        )
    return str(client["id"])


# ============================================
# GET /my-bookings
# ============================================

@router.get("/my-bookings")
async def my_bookings_route(
    slug: str,
    user: dict = Depends(require_role("homeowner")),
    db: Database = Depends(get_db),
):
    """Get upcoming and past bookings."""
    client_id = await _resolve_client_id(user, db)
    return await get_my_bookings(db, user["business_id"], client_id)


# ============================================
# GET /my-bookings/{booking_id}
# ============================================

@router.get("/my-bookings/{booking_id}")
async def booking_detail_route(
    slug: str,
    booking_id: str,
    user: dict = Depends(require_role("homeowner")),
    db: Database = Depends(get_db),
):
    """Get full booking detail."""
    client_id = await _resolve_client_id(user, db)
    result = await get_booking_detail(db, user["business_id"], booking_id, client_id)

    if not result:
        raise HTTPException(status_code=404, detail="Booking not found.")

    return result


# ============================================
# POST /my-bookings/{booking_id}/reschedule
# ============================================

@router.post("/my-bookings/{booking_id}/reschedule")
async def reschedule_route(
    slug: str,
    booking_id: str,
    body: RescheduleRequest,
    user: dict = Depends(require_role("homeowner")),
    db: Database = Depends(get_db),
):
    """Reschedule a booking to a new date/time."""
    client_id = await _resolve_client_id(user, db)
    result = await reschedule_booking(
        db, user["business_id"], booking_id, client_id,
        new_date=body.new_date, new_time=body.new_time,
    )

    if isinstance(result, dict) and result.get("error"):
        raise HTTPException(status_code=result["status_code"], detail=result["message"])

    return result


# ============================================
# POST /my-bookings/{booking_id}/cancel
# ============================================

@router.post("/my-bookings/{booking_id}/cancel")
async def cancel_route(
    slug: str,
    booking_id: str,
    body: CancelRequest,
    user: dict = Depends(require_role("homeowner")),
    db: Database = Depends(get_db),
):
    """Cancel a booking."""
    client_id = await _resolve_client_id(user, db)
    result = await cancel_booking(
        db, user["business_id"], booking_id, client_id,
        reason=body.reason,
    )

    if isinstance(result, dict) and result.get("error"):
        raise HTTPException(status_code=result["status_code"], detail=result["message"])

    # Owner notification — fire-and-forget
    try:
        from app.modules.cleaning.services.email_service import send_owner_booking_cancelled
        await send_owner_booking_cancelled(
            db, booking_id, reason=body.reason or "", cancelled_by="client",
        )
    except Exception:
        import logging
        logging.getLogger("xcleaners.homeowner").exception(
            "cancel_route: owner alert failed for %s", booking_id,
        )

    return result


# ============================================
# GET /my-invoices
# ============================================

@router.get("/my-invoices")
async def my_invoices_route(
    slug: str,
    user: dict = Depends(require_role("homeowner")),
    db: Database = Depends(get_db),
):
    """Get all invoices."""
    client_id = await _resolve_client_id(user, db)
    return await get_my_invoices(db, user["business_id"], client_id)


# ============================================
# GET /my-preferences
# ============================================

@router.get("/my-preferences")
async def my_preferences_route(
    slug: str,
    user: dict = Depends(require_role("homeowner")),
    db: Database = Depends(get_db),
):
    """Get house preferences and details."""
    client_id = await _resolve_client_id(user, db)
    result = await get_my_preferences(db, user["business_id"], client_id)

    if not result:
        raise HTTPException(status_code=404, detail="Client profile not found.")

    return result


# ============================================
# PUT /my-preferences
# ============================================

@router.put("/my-preferences")
async def update_preferences_route(
    slug: str,
    body: dict,
    user: dict = Depends(require_role("homeowner")),
    db: Database = Depends(get_db),
):
    """Update house preferences."""
    client_id = await _resolve_client_id(user, db)
    result = await update_my_preferences(db, user["business_id"], client_id, body)

    if isinstance(result, dict) and result.get("error"):
        raise HTTPException(status_code=result["status_code"], detail=result["message"])

    return result


# ============================================
# POST /my-bookings/{booking_id}/review
# ============================================

@router.post("/my-bookings/{booking_id}/review")
async def review_route(
    slug: str,
    booking_id: str,
    body: ReviewRequest,
    user: dict = Depends(require_role("homeowner")),
    db: Database = Depends(get_db),
):
    """Rate/review a completed service."""
    client_id = await _resolve_client_id(user, db)
    result = await rate_service(
        db, user["business_id"], booking_id, client_id,
        rating=body.rating, comment=body.comment,
    )

    if isinstance(result, dict) and result.get("error"):
        raise HTTPException(status_code=result["status_code"], detail=result["message"])

    return result
