"""
Xcleaners v3 — Homeowner Service (Sprint 3).

Business logic for the homeowner experience:
  - My bookings (upcoming + past)
  - Booking detail
  - Reschedule booking
  - Cancel booking (with policy check)
  - My invoices
  - Update preferences (house details, access codes, notes)
  - Rate/review service
"""

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from app.database import Database

logger = logging.getLogger("xcleaners.homeowner_service")


# ============================================
# MY BOOKINGS
# ============================================

async def get_my_bookings(
    db: Database,
    business_id: str,
    client_id: str,
) -> dict:
    """
    Get upcoming and past bookings for a homeowner.
    Upcoming: scheduled_date >= today, not cancelled.
    Past: scheduled_date < today or completed/cancelled.
    """
    today = date.today()

    rows = await db.pool.fetch(
        """
        SELECT
            b.id, b.scheduled_date, b.scheduled_start, b.scheduled_end,
            b.estimated_duration_minutes, b.status,
            b.address_line1, b.city,
            b.quoted_price, b.final_price,
            b.actual_start, b.actual_end,
            s.name AS service_name, s.category AS service_category,
            t.name AS team_name
        FROM cleaning_bookings b
        LEFT JOIN cleaning_services s ON s.id = b.service_id
        LEFT JOIN cleaning_teams t ON t.id = b.team_id
        WHERE b.business_id = $1 AND b.client_id = $2
        ORDER BY b.scheduled_date DESC, b.scheduled_start DESC
        """,
        business_id, client_id,
    )

    upcoming = []
    past = []

    for row in rows:
        booking = {
            "id": str(row["id"]),
            "scheduled_date": str(row["scheduled_date"]),
            "scheduled_start": str(row["scheduled_start"]) if row["scheduled_start"] else None,
            "scheduled_end": str(row["scheduled_end"]) if row["scheduled_end"] else None,
            "estimated_duration_minutes": row["estimated_duration_minutes"],
            "status": row["status"],
            "service_name": row["service_name"] or "Cleaning",
            "service_category": row["service_category"],
            "team_name": row["team_name"],
            "address": f"{row['address_line1'] or ''}, {row['city'] or ''}".strip(", "),
            "quoted_price": float(row["quoted_price"]) if row["quoted_price"] else None,
            "final_price": float(row["final_price"]) if row["final_price"] else None,
        }

        if row["scheduled_date"] >= today and row["status"] not in ("completed", "cancelled"):
            upcoming.append(booking)
        else:
            past.append(booking)

    # Sort upcoming chronologically (earliest first)
    upcoming.sort(key=lambda x: (x["scheduled_date"], x["scheduled_start"] or ""))

    return {
        "upcoming": upcoming,
        "past": past,
        "total_upcoming": len(upcoming),
        "total_past": len(past),
    }


# ============================================
# BOOKING DETAIL
# ============================================

async def get_booking_detail(
    db: Database,
    business_id: str,
    booking_id: str,
    client_id: str,
) -> Optional[dict]:
    """Get full booking detail for a homeowner."""
    row = await db.pool.fetchrow(
        """
        SELECT
            b.*,
            s.name AS service_name, s.category AS service_category,
            s.description AS service_description,
            t.name AS team_name
        FROM cleaning_bookings b
        LEFT JOIN cleaning_services s ON s.id = b.service_id
        LEFT JOIN cleaning_teams t ON t.id = b.team_id
        WHERE b.id = $1 AND b.business_id = $2 AND b.client_id = $3
        """,
        booking_id, business_id, client_id,
    )

    if not row:
        return None

    # Check if there's a review for this booking
    review = await db.pool.fetchrow(
        """SELECT id, rating, comment, created_at
           FROM cleaning_reviews
           WHERE booking_id = $1 AND client_id = $2""",
        booking_id, client_id,
    )

    # Check if there's an invoice
    invoice = await db.pool.fetchrow(
        """SELECT id, invoice_number, total, status, due_date
           FROM cleaning_invoices
           WHERE booking_id = $1 AND business_id = $2""",
        booking_id, business_id,
    )

    return {
        "id": str(row["id"]),
        "scheduled_date": str(row["scheduled_date"]),
        "scheduled_start": str(row["scheduled_start"]) if row["scheduled_start"] else None,
        "scheduled_end": str(row["scheduled_end"]) if row["scheduled_end"] else None,
        "estimated_duration_minutes": row["estimated_duration_minutes"],
        "actual_start": row["actual_start"].isoformat() if row["actual_start"] else None,
        "actual_end": row["actual_end"].isoformat() if row["actual_end"] else None,
        "status": row["status"],
        "service": {
            "name": row["service_name"] or "Cleaning",
            "category": row["service_category"],
            "description": row["service_description"],
        },
        "team_name": row["team_name"],
        "address": f"{row['address_line1'] or ''}, {row['city'] or ''}".strip(", "),
        "access_instructions": row["access_instructions"],
        "special_instructions": row["special_instructions"],
        "quoted_price": float(row["quoted_price"]) if row["quoted_price"] else None,
        "final_price": float(row["final_price"]) if row["final_price"] else None,
        "cancellation_reason": row["cancellation_reason"],
        "can_reschedule": _can_reschedule(row),
        "can_cancel": _can_cancel(row),
        "review": {
            "id": str(review["id"]),
            "rating": review["rating"],
            "comment": review["comment"],
            "created_at": review["created_at"].isoformat(),
        } if review else None,
        "invoice": {
            "id": str(invoice["id"]),
            "number": invoice["invoice_number"],
            "total": float(invoice["total"]),
            "status": invoice["status"],
            "due_date": str(invoice["due_date"]),
        } if invoice else None,
    }


# ============================================
# RESCHEDULE BOOKING
# ============================================

async def reschedule_booking(
    db: Database,
    business_id: str,
    booking_id: str,
    client_id: str,
    new_date: str,
    new_time: Optional[str] = None,
) -> dict:
    """
    Reschedule a booking to a new date and optionally a new time.
    Policy: Must be at least 24 hours before the scheduled date.
    """
    booking = await db.pool.fetchrow(
        """SELECT id, scheduled_date, scheduled_start, status, team_id
           FROM cleaning_bookings
           WHERE id = $1 AND business_id = $2 AND client_id = $3""",
        booking_id, business_id, client_id,
    )

    if not booking:
        return {"error": True, "status_code": 404, "message": "Booking not found."}

    if not _can_reschedule(booking):
        return {
            "error": True, "status_code": 409,
            "message": "This booking cannot be rescheduled. Must be at least 24 hours before the scheduled date and status must be scheduled or confirmed.",
        }

    old_date = str(booking["scheduled_date"])
    old_start = str(booking["scheduled_start"]) if booking["scheduled_start"] else None

    update_fields = {"scheduled_date": new_date}
    if new_time:
        update_fields["scheduled_start"] = new_time

    # Update booking
    set_clause = ", ".join(f"{k} = ${i+1}" for i, k in enumerate(update_fields.keys()))
    values = list(update_fields.values())
    values.extend([booking_id, business_id])
    n = len(update_fields)

    await db.pool.execute(
        f"""UPDATE cleaning_bookings
            SET {set_clause}, status = 'rescheduled', updated_at = NOW()
            WHERE id = ${n+1} AND business_id = ${n+2}""",
        *values,
    )

    # Publish SSE
    team_id = str(booking["team_id"]) if booking["team_id"] else None
    try:
        from app.modules.cleaning.services.change_propagator import on_booking_rescheduled
        await on_booking_rescheduled(
            business_id,
            {"id": str(booking_id), "team_id": team_id,
             "scheduled_date": new_date,
             "scheduled_start": new_time or old_start,
             "status": "rescheduled"},
            old_date, team_id,
        )
    except Exception as e:
        logger.warning("[HOMEOWNER] SSE publish failed: %s", e)

    return {
        "success": True,
        "booking_id": str(booking_id),
        "old_date": old_date,
        "new_date": new_date,
        "new_time": new_time,
        "status": "rescheduled",
    }


# ============================================
# CANCEL BOOKING
# ============================================

async def cancel_booking(
    db: Database,
    business_id: str,
    booking_id: str,
    client_id: str,
    reason: Optional[str] = None,
) -> dict:
    """
    Cancel a booking.
    Policy: Must be at least 24 hours before scheduled date.
    Late cancellations (< 24h) require owner approval (not blocked, but flagged).
    """
    booking = await db.pool.fetchrow(
        """SELECT b.id, b.scheduled_date, b.status, b.team_id,
                  c.first_name || ' ' || COALESCE(c.last_name, '') AS client_name
           FROM cleaning_bookings b
           JOIN cleaning_clients c ON c.id = b.client_id
           WHERE b.id = $1 AND b.business_id = $2 AND b.client_id = $3""",
        booking_id, business_id, client_id,
    )

    if not booking:
        return {"error": True, "status_code": 404, "message": "Booking not found."}

    if not _can_cancel(booking):
        return {
            "error": True, "status_code": 409,
            "message": "This booking cannot be cancelled. It may be already completed or in progress.",
        }

    now = datetime.now(timezone.utc)
    is_late = _is_late_cancellation(booking)

    await db.pool.execute(
        """UPDATE cleaning_bookings
           SET status = 'cancelled', cancellation_reason = $1,
               cancelled_at = $2, cancelled_by = 'client', updated_at = NOW()
           WHERE id = $3 AND business_id = $4""",
        reason or "Client cancelled", now, booking_id, business_id,
    )

    # Publish SSE
    team_id = str(booking["team_id"]) if booking["team_id"] else None
    try:
        from app.modules.cleaning.services.change_propagator import on_booking_cancelled
        await on_booking_cancelled(business_id, {
            "id": str(booking_id), "team_id": team_id,
            "scheduled_date": str(booking["scheduled_date"]),
            "client_name": booking["client_name"] or "",
        })
    except Exception as e:
        logger.warning("[HOMEOWNER] SSE publish failed: %s", e)

    return {
        "success": True,
        "booking_id": str(booking_id),
        "status": "cancelled",
        "late_cancellation": is_late,
        "cancelled_at": now.isoformat(),
    }


# ============================================
# MY INVOICES
# ============================================

async def get_my_invoices(
    db: Database,
    business_id: str,
    client_id: str,
) -> dict:
    """Get all invoices for a homeowner."""
    rows = await db.pool.fetch(
        """
        SELECT
            i.id, i.invoice_number, i.subtotal, i.tax_amount,
            i.total, i.amount_paid, i.balance_due,
            i.issue_date, i.due_date, i.paid_at,
            i.status, i.payment_method, i.pdf_url,
            b.scheduled_date AS booking_date,
            s.name AS service_name
        FROM cleaning_invoices i
        LEFT JOIN cleaning_bookings b ON b.id = i.booking_id
        LEFT JOIN cleaning_services s ON s.id = b.service_id
        WHERE i.business_id = $1 AND i.client_id = $2
        ORDER BY i.issue_date DESC
        """,
        business_id, client_id,
    )

    invoices = []
    for row in rows:
        invoices.append({
            "id": str(row["id"]),
            "number": row["invoice_number"],
            "total": float(row["total"]),
            "amount_paid": float(row["amount_paid"]),
            "balance_due": float(row["balance_due"]),
            "status": row["status"],
            "issue_date": str(row["issue_date"]),
            "due_date": str(row["due_date"]),
            "paid_at": row["paid_at"].isoformat() if row["paid_at"] else None,
            "payment_method": row["payment_method"],
            "pdf_url": row["pdf_url"],
            "booking_date": str(row["booking_date"]) if row["booking_date"] else None,
            "service_name": row["service_name"],
        })

    total_due = sum(i["balance_due"] for i in invoices if i["status"] in ("sent", "viewed", "partial", "overdue"))

    return {
        "invoices": invoices,
        "total": len(invoices),
        "total_due": round(total_due, 2),
    }


# ============================================
# PREFERENCES
# ============================================

async def get_my_preferences(
    db: Database,
    business_id: str,
    client_id: str,
) -> Optional[dict]:
    """Get homeowner house preferences and details."""
    row = await db.pool.fetchrow(
        """
        SELECT
            id, first_name, last_name, email, phone,
            address_line1, address_line2, city, state, zip_code,
            property_type, square_feet, bedrooms, bathrooms,
            has_pets, pet_details,
            notes, access_instructions,
            preferred_day, preferred_time_start, preferred_time_end
        FROM cleaning_clients
        WHERE id = $1 AND business_id = $2
        """,
        client_id, business_id,
    )

    if not row:
        return None

    # Map preferred_time_start to a simple label
    preferred_time = None
    if row["preferred_time_start"]:
        hour = int(str(row["preferred_time_start"]).split(":")[0])
        if hour < 12:
            preferred_time = "morning"
        elif hour < 17:
            preferred_time = "afternoon"
        else:
            preferred_time = "evening"

    return {
        "id": str(row["id"]),
        "name": f"{row['first_name'] or ''} {row['last_name'] or ''}".strip(),
        "email": row["email"],
        "phone": row["phone"],
        "address": {
            "line1": row["address_line1"],
            "line2": row["address_line2"],
            "city": row["city"],
            "state": row["state"],
            "zip": row["zip_code"],
        },
        "property": {
            "type": row["property_type"],
            "square_feet": row["square_feet"],
            "bedrooms": row["bedrooms"],
            "bathrooms": float(row["bathrooms"]) if row["bathrooms"] else None,
        },
        "pets": {
            "has_pets": row["has_pets"],
            "details": row["pet_details"],
        },
        "instructions": {
            "special": row["notes"],
            "access": row["access_instructions"],
        },
        "preferences": {
            "preferred_day": row["preferred_day"],
            "preferred_time": preferred_time,
            "communication": None,
        },
    }


async def update_my_preferences(
    db: Database,
    business_id: str,
    client_id: str,
    preferences: dict,
) -> dict:
    """Update homeowner preferences. Only allowed fields are updated."""
    allowed_fields = {
        "phone", "address_line1", "address_line2", "city", "state", "zip_code",
        "property_type", "square_feet", "bedrooms", "bathrooms",
        "has_pets", "pet_details",
        "notes", "access_instructions",
        "preferred_day",
    }

    # Map frontend field names to DB columns
    field_mapping = {
        "special_instructions": "notes",
    }
    mapped = {}
    for k, v in preferences.items():
        db_col = field_mapping.get(k, k)
        if db_col in allowed_fields:
            mapped[db_col] = v

    # Handle preferred_time -> preferred_time_start mapping
    if "preferred_time" in preferences:
        time_map = {"morning": "08:00:00", "afternoon": "13:00:00", "evening": "17:00:00"}
        mapped["preferred_time_start"] = time_map.get(preferences["preferred_time"])

    update_data = mapped
    if not update_data:
        return {"error": True, "status_code": 400, "message": "No valid fields to update."}

    set_parts = []
    values = []
    idx = 1
    for col, val in update_data.items():
        set_parts.append(f"{col} = ${idx}")
        values.append(val)
        idx += 1

    set_parts.append("updated_at = NOW()")
    values.extend([client_id, business_id])

    await db.pool.execute(
        f"""UPDATE cleaning_clients
            SET {', '.join(set_parts)}
            WHERE id = ${idx} AND business_id = ${idx + 1}""",
        *values,
    )

    return {"success": True, "updated_fields": list(update_data.keys())}


# ============================================
# RATE SERVICE
# ============================================

async def rate_service(
    db: Database,
    business_id: str,
    booking_id: str,
    client_id: str,
    rating: int,
    comment: Optional[str] = None,
) -> dict:
    """Post-service review."""
    if not 1 <= rating <= 5:
        return {"error": True, "status_code": 400, "message": "Rating must be between 1 and 5."}

    # Verify booking exists and is completed
    booking = await db.pool.fetchrow(
        """SELECT id, status FROM cleaning_bookings
           WHERE id = $1 AND business_id = $2 AND client_id = $3""",
        booking_id, business_id, client_id,
    )

    if not booking:
        return {"error": True, "status_code": 404, "message": "Booking not found."}

    if booking["status"] != "completed":
        return {"error": True, "status_code": 409, "message": "Can only review completed bookings."}

    # Check for existing review
    existing = await db.pool.fetchval(
        "SELECT id FROM cleaning_reviews WHERE booking_id = $1 AND client_id = $2",
        booking_id, client_id,
    )
    if existing:
        return {"error": True, "status_code": 409, "message": "You have already reviewed this booking."}

    review_id = await db.pool.fetchval(
        """INSERT INTO cleaning_reviews
           (business_id, client_id, booking_id, rating, comment, is_verified, source)
           VALUES ($1, $2, $3, $4, $5, true, 'internal')
           RETURNING id""",
        business_id, client_id, booking_id, rating, comment,
    )

    return {
        "success": True,
        "review_id": str(review_id),
        "rating": rating,
    }


# ============================================
# HELPERS
# ============================================

def _can_reschedule(booking) -> bool:
    """Check if a booking can be rescheduled."""
    status = booking["status"]
    if status not in ("scheduled", "confirmed", "rescheduled"):
        return False
    # Must be at least 24 hours before
    scheduled_date = booking["scheduled_date"]
    if isinstance(scheduled_date, str):
        scheduled_date = date.fromisoformat(scheduled_date)
    return (scheduled_date - date.today()).days >= 1


def _can_cancel(booking) -> bool:
    """Check if a booking can be cancelled."""
    status = booking["status"]
    return status in ("scheduled", "confirmed", "rescheduled", "draft")


def _is_late_cancellation(booking) -> bool:
    """Check if cancellation is within 24 hours of scheduled date."""
    scheduled_date = booking["scheduled_date"]
    if isinstance(scheduled_date, str):
        scheduled_date = date.fromisoformat(scheduled_date)
    return (scheduled_date - date.today()).days < 1
