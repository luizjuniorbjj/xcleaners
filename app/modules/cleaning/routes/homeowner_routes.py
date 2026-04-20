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


class BookingRequestBody(BaseModel):
    """Homeowner-initiated booking request. Stored as status='draft'."""
    service_id: str = Field(..., description="UUID of cleaning_services")
    date: str = Field(..., description="YYYY-MM-DD preferred date")
    time: str = Field("09:00", description="HH:MM preferred start time")
    notes: Optional[str] = Field(None, max_length=2000)


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
# POST /my-bookings/request  (homeowner-initiated request)
# ============================================

@router.post("/my-bookings/request")
async def request_booking_route(
    slug: str,
    body: BookingRequestBody,
    user: dict = Depends(require_role("homeowner")),
    db: Database = Depends(get_db),
):
    """
    Homeowner requests a new cleaning.

    Persists as status='draft' + source='booking_page' so the owner sees it
    in their pending list and can confirm (→ 'scheduled') or cancel.
    Owner gets an email alert. Pricing is snapshotted from the service's
    base_price; owner can adjust on confirm.
    """
    from datetime import date as _date, datetime, time as _time, timedelta
    import uuid as _uuid

    client_id = await _resolve_client_id(user, db)
    business_id = user["business_id"]

    # Validate date is in the future (allow today too)
    try:
        req_date = _date.fromisoformat(body.date)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid date format (expected YYYY-MM-DD).")

    if req_date < _date.today():
        raise HTTPException(status_code=400, detail="Please choose today or a future date.")

    # Validate time format
    try:
        req_time = _time.fromisoformat(body.time if len(body.time) > 5 else body.time + ":00")
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid time format (expected HH:MM).")

    # Validate service belongs to this business
    try:
        service_uuid = _uuid.UUID(body.service_id)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=400, detail="Invalid service selection.")

    service = await db.pool.fetchrow(
        """SELECT id, name, base_price, duration_minutes
           FROM cleaning_services
           WHERE id = $1 AND business_id = $2 AND is_active = true""",
        service_uuid, business_id,
    )
    if not service:
        raise HTTPException(status_code=404, detail="Service not available for this business.")

    # Pull client's address as booking snapshot
    client_row = await db.pool.fetchrow(
        """SELECT address_line1, address_line2, city, state, zip_code,
                  latitude, longitude, access_instructions
           FROM cleaning_clients WHERE id = $1""",
        _uuid.UUID(client_id),
    )

    duration = service["duration_minutes"] or 120
    price = service["base_price"] or 0
    scheduled_end = (datetime.combine(req_date, req_time) + timedelta(minutes=duration)).time()

    booking_id = await db.pool.fetchval(
        """INSERT INTO cleaning_bookings (
               business_id, client_id, service_id,
               scheduled_date, scheduled_start, scheduled_end, estimated_duration_minutes,
               address_line1, address_line2, city, state, zip_code, latitude, longitude,
               access_instructions, quoted_price, final_price, status, source,
               special_instructions
           ) VALUES (
               $1, $2, $3, $4, $5, $6, $7,
               $8, $9, $10, $11, $12, $13, $14,
               $15, $16, $16, 'draft', 'booking_page', $17
           )
           RETURNING id""",
        business_id, _uuid.UUID(client_id), service_uuid,
        req_date, req_time, scheduled_end, duration,
        client_row["address_line1"] if client_row else None,
        client_row["address_line2"] if client_row else None,
        client_row["city"] if client_row else None,
        client_row["state"] if client_row else None,
        client_row["zip_code"] if client_row else None,
        client_row["latitude"] if client_row else None,
        client_row["longitude"] if client_row else None,
        client_row["access_instructions"] if client_row else None,
        price,
        body.notes,
    )

    logger.info(
        "[booking-request] client %s requested %s for %s %s in business %s (booking %s, service %s)",
        client_id, service["name"], req_date, req_time, business_id, booking_id, service_uuid,
    )

    # Fire-and-forget owner notification
    try:
        from app.modules.cleaning.services.email_service import send_owner_new_booking
        await send_owner_new_booking(db, str(booking_id))
    except Exception:
        logger.exception("[booking-request] owner email failed for booking %s", booking_id)

    return {
        "booking_id": str(booking_id),
        "status": "draft",
        "scheduled_date": req_date.isoformat(),
        "scheduled_start": req_time.strftime("%H:%M"),
        "service_name": service["name"],
        "message": "Request submitted. You'll get a confirmation once the business reviews it.",
    }


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
