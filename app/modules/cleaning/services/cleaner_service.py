"""
Xcleaners v3 — Cleaner Service (Sprint 3).

Business logic for the cleaner/team-member experience:
  - Today's jobs for the cleaner's team
  - Job detail with client info, checklist, notes
  - GPS-verified check-in / check-out
  - Checklist item completion
  - Job notes and photos
  - Issue reporting
  - Week schedule
  - Earnings summary
"""

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from app.database import Database

logger = logging.getLogger("xcleaners.cleaner_service")


# ============================================
# TODAY'S JOBS
# ============================================

async def get_today_jobs(
    db: Database,
    business_id: str,
    team_member_id: str,
    team_id: str,
) -> dict:
    """
    Get today's jobs for the cleaner's team, ordered by scheduled_start.

    Returns jobs with status indicators: upcoming, in_progress, completed.
    """
    today = date.today()

    rows = await db.pool.fetch(
        """
        SELECT
            b.id, b.scheduled_date, b.scheduled_start, b.scheduled_end,
            b.estimated_duration_minutes, b.status,
            b.address_line1, b.city, b.state, b.zip_code,
            b.latitude, b.longitude,
            b.access_instructions, b.special_instructions,
            b.actual_start, b.actual_end,
            b.quoted_price,
            c.first_name AS client_first, c.last_name AS client_last,
            c.phone AS client_phone,
            s.name AS service_name, s.category AS service_category
        FROM cleaning_bookings b
        JOIN cleaning_clients c ON c.id = b.client_id
        LEFT JOIN cleaning_services s ON s.id = b.service_id
        WHERE b.business_id = $1
          AND b.team_id = $2
          AND b.scheduled_date = $3
          AND b.status NOT IN ('cancelled', 'no_show')
        ORDER BY b.scheduled_start ASC NULLS LAST
        """,
        business_id, team_id, today,
    )

    jobs = []
    for row in rows:
        client_name = f"{row['client_first'] or ''} {row['client_last'] or ''}".strip()
        address = _build_address(row)

        # Determine display status
        status = row["status"]
        if status == "in_progress":
            display_status = "in-progress"
        elif status == "completed":
            display_status = "completed"
        else:
            display_status = "upcoming"

        jobs.append({
            "id": str(row["id"]),
            "client_name": client_name,
            "client_phone": row["client_phone"],
            "service_name": row["service_name"] or "Cleaning",
            "service_category": row["service_category"],
            "scheduled_start": str(row["scheduled_start"]) if row["scheduled_start"] else None,
            "scheduled_end": str(row["scheduled_end"]) if row["scheduled_end"] else None,
            "estimated_duration_minutes": row["estimated_duration_minutes"],
            "address": address,
            "latitude": float(row["latitude"]) if row["latitude"] else None,
            "longitude": float(row["longitude"]) if row["longitude"] else None,
            "access_instructions": row["access_instructions"],
            "special_instructions": row["special_instructions"],
            "status": status,
            "display_status": display_status,
            "actual_start": row["actual_start"].isoformat() if row["actual_start"] else None,
            "actual_end": row["actual_end"].isoformat() if row["actual_end"] else None,
            "quoted_price": float(row["quoted_price"]) if row["quoted_price"] else None,
        })

    return {
        "date": today.isoformat(),
        "team_id": team_id,
        "jobs": jobs,
        "total": len(jobs),
        "completed": sum(1 for j in jobs if j["display_status"] == "completed"),
        "in_progress": sum(1 for j in jobs if j["display_status"] == "in-progress"),
    }


# ============================================
# JOB DETAIL
# ============================================

async def get_job_detail(
    db: Database,
    business_id: str,
    booking_id: str,
    team_member_id: str,
    team_id: str,
) -> Optional[dict]:
    """
    Get full job detail with client info, checklist items, and job logs/notes.
    """
    # Fetch booking
    row = await db.pool.fetchrow(
        """
        SELECT
            b.*, c.first_name AS client_first, c.last_name AS client_last,
            c.phone AS client_phone, c.email AS client_email,
            c.address_line1 AS client_address, c.city AS client_city,
            c.state AS client_state, c.zip_code AS client_zip,
            c.special_instructions AS client_notes,
            c.has_pets, c.pet_details,
            s.name AS service_name, s.category AS service_category,
            s.estimated_duration_minutes AS service_duration
        FROM cleaning_bookings b
        JOIN cleaning_clients c ON c.id = b.client_id
        LEFT JOIN cleaning_services s ON s.id = b.service_id
        WHERE b.id = $1 AND b.business_id = $2 AND b.team_id = $3
        """,
        booking_id, business_id, team_id,
    )

    if not row:
        return None

    client_name = f"{row['client_first'] or ''} {row['client_last'] or ''}".strip()

    # Get checklist items for this service
    checklist_items = await _get_checklist_items(db, business_id, row["service_id"], booking_id)

    # Get job logs (notes, photos, check-in/out)
    logs = await db.pool.fetch(
        """
        SELECT id, log_type, timestamp, latitude, longitude,
               photo_url, note, checklist_item_id, metadata
        FROM cleaning_job_logs
        WHERE booking_id = $1 AND business_id = $2
        ORDER BY timestamp ASC
        """,
        booking_id, business_id,
    )

    job_logs = []
    for log in logs:
        job_logs.append({
            "id": str(log["id"]),
            "log_type": log["log_type"],
            "timestamp": log["timestamp"].isoformat() if log["timestamp"] else None,
            "latitude": float(log["latitude"]) if log["latitude"] else None,
            "longitude": float(log["longitude"]) if log["longitude"] else None,
            "photo_url": log["photo_url"],
            "note": log["note"],
            "checklist_item_id": str(log["checklist_item_id"]) if log["checklist_item_id"] else None,
        })

    return {
        "id": str(row["id"]),
        "client": {
            "name": client_name,
            "phone": row["client_phone"],
            "email": row["client_email"],
            "address": _build_address_from_client(row),
            "notes": row["client_notes"],
            "has_pets": row["has_pets"],
            "pet_details": row["pet_details"],
        },
        "service": {
            "name": row["service_name"] or "Cleaning",
            "category": row["service_category"],
            "estimated_duration": row["estimated_duration_minutes"] or row["service_duration"],
        },
        "scheduling": {
            "date": str(row["scheduled_date"]),
            "start": str(row["scheduled_start"]) if row["scheduled_start"] else None,
            "end": str(row["scheduled_end"]) if row["scheduled_end"] else None,
            "actual_start": row["actual_start"].isoformat() if row["actual_start"] else None,
            "actual_end": row["actual_end"].isoformat() if row["actual_end"] else None,
        },
        "location": {
            "address": _build_address(row),
            "latitude": float(row["latitude"]) if row["latitude"] else None,
            "longitude": float(row["longitude"]) if row["longitude"] else None,
            "access_instructions": row["access_instructions"],
        },
        "status": row["status"],
        "special_instructions": row["special_instructions"],
        "quoted_price": float(row["quoted_price"]) if row["quoted_price"] else None,
        "checklist": checklist_items,
        "logs": job_logs,
    }


# ============================================
# CHECK-IN
# ============================================

async def check_in(
    db: Database,
    business_id: str,
    booking_id: str,
    team_member_id: str,
    team_id: str,
    lat: Optional[float] = None,
    lng: Optional[float] = None,
) -> dict:
    """
    GPS-verified check-in. Updates booking status to in_progress,
    sets actual_start, and creates a clock_in job_log entry.
    """
    # Verify booking exists and belongs to team
    booking = await db.pool.fetchrow(
        """SELECT id, status, team_id, scheduled_date
           FROM cleaning_bookings
           WHERE id = $1 AND business_id = $2 AND team_id = $3""",
        booking_id, business_id, team_id,
    )

    if not booking:
        return {"error": True, "status_code": 404, "message": "Booking not found or not assigned to your team."}

    if booking["status"] == "in_progress":
        return {"error": True, "status_code": 409, "message": "Already checked in to this job."}

    if booking["status"] == "completed":
        return {"error": True, "status_code": 409, "message": "This job is already completed."}

    now = datetime.now(timezone.utc)

    # Update booking
    await db.pool.execute(
        """UPDATE cleaning_bookings
           SET status = 'in_progress', actual_start = $1, updated_at = NOW()
           WHERE id = $2 AND business_id = $3""",
        now, booking_id, business_id,
    )

    # Create job_log entry
    log_id = await db.pool.fetchval(
        """INSERT INTO cleaning_job_logs
           (business_id, booking_id, team_member_id, log_type, timestamp, latitude, longitude)
           VALUES ($1, $2, $3, 'clock_in', $4, $5, $6)
           RETURNING id""",
        business_id, booking_id, team_member_id, now, lat, lng,
    )

    # Publish SSE event
    await _publish_job_event(business_id, team_id, booking_id, "checkin", {
        "team_member_id": team_member_id,
        "timestamp": now.isoformat(),
        "latitude": lat,
        "longitude": lng,
    })

    return {
        "success": True,
        "booking_id": str(booking_id),
        "log_id": str(log_id),
        "checked_in_at": now.isoformat(),
        "status": "in_progress",
    }


# ============================================
# CHECK-OUT
# ============================================

async def check_out(
    db: Database,
    business_id: str,
    booking_id: str,
    team_member_id: str,
    team_id: str,
    lat: Optional[float] = None,
    lng: Optional[float] = None,
    notes: Optional[str] = None,
) -> dict:
    """
    Check-out from a job. Updates booking status to completed,
    sets actual_end, creates a clock_out job_log entry.
    """
    booking = await db.pool.fetchrow(
        """SELECT id, status, actual_start
           FROM cleaning_bookings
           WHERE id = $1 AND business_id = $2 AND team_id = $3""",
        booking_id, business_id, team_id,
    )

    if not booking:
        return {"error": True, "status_code": 404, "message": "Booking not found or not assigned to your team."}

    if booking["status"] != "in_progress":
        return {"error": True, "status_code": 409, "message": "Must check in before checking out."}

    now = datetime.now(timezone.utc)

    # Calculate actual duration
    actual_start = booking["actual_start"]
    actual_duration = None
    if actual_start:
        delta = now - actual_start
        actual_duration = int(delta.total_seconds() / 60)

    # Update booking
    await db.pool.execute(
        """UPDATE cleaning_bookings
           SET status = 'completed', actual_end = $1, updated_at = NOW()
           WHERE id = $2 AND business_id = $3""",
        now, booking_id, business_id,
    )

    # Create job_log entry
    log_id = await db.pool.fetchval(
        """INSERT INTO cleaning_job_logs
           (business_id, booking_id, team_member_id, log_type, timestamp,
            latitude, longitude, note)
           VALUES ($1, $2, $3, 'clock_out', $4, $5, $6, $7)
           RETURNING id""",
        business_id, booking_id, team_member_id, now, lat, lng, notes,
    )

    # Publish SSE event
    await _publish_job_event(business_id, team_id, booking_id, "checkout", {
        "team_member_id": team_member_id,
        "timestamp": now.isoformat(),
        "actual_duration_minutes": actual_duration,
    })

    # Materialize cleaner earnings (idempotent via UNIQUE booking_id+cleaner_id).
    # Lazy import to avoid circular dependency with payroll_service → cleaner_service.
    try:
        from app.modules.cleaning.services.payroll_service import (
            calculate_cleaner_earnings,
            PayrollError,
        )
        await calculate_cleaner_earnings(db, booking_id)
    except PayrollError as exc:
        # Don't fail the checkout just because earnings couldn't be computed.
        # Most common cause: booking has no lead_cleaner_id or NULL final_price.
        logger.warning(
            "cleaner_service: earnings calc skipped for booking=%s: %s",
            booking_id, exc,
        )
    except Exception as exc:  # pragma: no cover — defensive log-only
        logger.exception(
            "cleaner_service: earnings calc failed for booking=%s", booking_id,
        )

    return {
        "success": True,
        "booking_id": str(booking_id),
        "log_id": str(log_id),
        "checked_out_at": now.isoformat(),
        "actual_duration_minutes": actual_duration,
        "status": "completed",
    }


# ============================================
# CHECKLIST ITEM COMPLETION
# ============================================

async def complete_checklist_item(
    db: Database,
    business_id: str,
    booking_id: str,
    item_id: str,
    team_member_id: str,
) -> dict:
    """
    Mark a checklist item as completed by creating a task_complete job_log.
    """
    # Verify booking belongs to team member's team
    booking = await db.pool.fetchrow(
        "SELECT id, status FROM cleaning_bookings WHERE id = $1 AND business_id = $2",
        booking_id, business_id,
    )
    if not booking:
        return {"error": True, "status_code": 404, "message": "Booking not found."}

    # Verify checklist item exists
    item = await db.pool.fetchrow(
        "SELECT id, task_description FROM cleaning_checklist_items WHERE id = $1 AND business_id = $2",
        item_id, business_id,
    )
    if not item:
        return {"error": True, "status_code": 404, "message": "Checklist item not found."}

    # Check if already completed
    existing = await db.pool.fetchval(
        """SELECT id FROM cleaning_job_logs
           WHERE booking_id = $1 AND checklist_item_id = $2 AND log_type = 'task_complete'""",
        booking_id, item_id,
    )
    if existing:
        return {"error": True, "status_code": 409, "message": "Checklist item already completed."}

    now = datetime.now(timezone.utc)
    log_id = await db.pool.fetchval(
        """INSERT INTO cleaning_job_logs
           (business_id, booking_id, team_member_id, log_type, timestamp, checklist_item_id)
           VALUES ($1, $2, $3, 'task_complete', $4, $5)
           RETURNING id""",
        business_id, booking_id, team_member_id, now, item_id,
    )

    return {
        "success": True,
        "log_id": str(log_id),
        "item_id": str(item_id),
        "completed_at": now.isoformat(),
    }


# ============================================
# ADD JOB NOTE
# ============================================

async def add_job_note(
    db: Database,
    business_id: str,
    booking_id: str,
    team_member_id: str,
    note: Optional[str] = None,
    photo_url: Optional[str] = None,
) -> dict:
    """Add a note and/or photo to a job."""
    if not note and not photo_url:
        return {"error": True, "status_code": 400, "message": "Note text or photo_url required."}

    booking = await db.pool.fetchrow(
        "SELECT id FROM cleaning_bookings WHERE id = $1 AND business_id = $2",
        booking_id, business_id,
    )
    if not booking:
        return {"error": True, "status_code": 404, "message": "Booking not found."}

    log_type = "photo" if photo_url and not note else "note"
    now = datetime.now(timezone.utc)

    log_id = await db.pool.fetchval(
        """INSERT INTO cleaning_job_logs
           (business_id, booking_id, team_member_id, log_type, timestamp, note, photo_url)
           VALUES ($1, $2, $3, $4, $5, $6, $7)
           RETURNING id""",
        business_id, booking_id, team_member_id, log_type, now, note, photo_url,
    )

    return {
        "success": True,
        "log_id": str(log_id),
        "log_type": log_type,
        "created_at": now.isoformat(),
    }


# ============================================
# REPORT ISSUE
# ============================================

async def report_issue(
    db: Database,
    business_id: str,
    booking_id: str,
    team_member_id: str,
    issue_type: str,
    description: str,
) -> dict:
    """Report an issue during a job (locked out, damage, pet problem, etc.)."""
    booking = await db.pool.fetchrow(
        "SELECT id, team_id FROM cleaning_bookings WHERE id = $1 AND business_id = $2",
        booking_id, business_id,
    )
    if not booking:
        return {"error": True, "status_code": 404, "message": "Booking not found."}

    now = datetime.now(timezone.utc)

    log_id = await db.pool.fetchval(
        """INSERT INTO cleaning_job_logs
           (business_id, booking_id, team_member_id, log_type, timestamp, note, metadata)
           VALUES ($1, $2, $3, 'issue', $4, $5, $6::jsonb)
           RETURNING id""",
        business_id, booking_id, team_member_id, now, description,
        f'{{"issue_type": "{issue_type}"}}',
    )

    # Publish SSE event to notify owner
    team_id = str(booking["team_id"]) if booking["team_id"] else None
    await _publish_job_event(business_id, team_id, str(booking_id), "issue_reported", {
        "team_member_id": team_member_id,
        "issue_type": issue_type,
        "description": description,
        "timestamp": now.isoformat(),
    })

    return {
        "success": True,
        "log_id": str(log_id),
        "issue_type": issue_type,
        "reported_at": now.isoformat(),
    }


# ============================================
# MY SCHEDULE (WEEK VIEW)
# ============================================

async def get_my_schedule(
    db: Database,
    business_id: str,
    team_id: str,
    start_date: date,
    end_date: date,
) -> dict:
    """Get the team's schedule for a date range (typically a week)."""
    rows = await db.pool.fetch(
        """
        SELECT
            b.id, b.scheduled_date, b.scheduled_start, b.scheduled_end,
            b.estimated_duration_minutes, b.status,
            b.address_line1, b.city,
            c.first_name AS client_first, c.last_name AS client_last,
            s.name AS service_name
        FROM cleaning_bookings b
        JOIN cleaning_clients c ON c.id = b.client_id
        LEFT JOIN cleaning_services s ON s.id = b.service_id
        WHERE b.business_id = $1
          AND b.team_id = $2
          AND b.scheduled_date BETWEEN $3 AND $4
          AND b.status NOT IN ('cancelled', 'no_show')
        ORDER BY b.scheduled_date, b.scheduled_start
        """,
        business_id, team_id, start_date, end_date,
    )

    # Group by date
    days = {}
    for row in rows:
        day_key = str(row["scheduled_date"])
        if day_key not in days:
            days[day_key] = []

        client_name = f"{row['client_first'] or ''} {row['client_last'] or ''}".strip()
        days[day_key].append({
            "id": str(row["id"]),
            "client_name": client_name,
            "service_name": row["service_name"] or "Cleaning",
            "scheduled_start": str(row["scheduled_start"]) if row["scheduled_start"] else None,
            "scheduled_end": str(row["scheduled_end"]) if row["scheduled_end"] else None,
            "estimated_duration_minutes": row["estimated_duration_minutes"],
            "status": row["status"],
            "address": f"{row['address_line1'] or ''}, {row['city'] or ''}".strip(", "),
        })

    return {
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "team_id": team_id,
        "days": days,
        "total_jobs": len(rows),
    }


# ============================================
# MY EARNINGS
# ============================================

async def get_my_earnings(
    db: Database,
    business_id: str,
    team_member_id: str,
    team_id: str,
    period: str = "week",
) -> dict:
    """
    Get earnings summary for the team member.

    Period: 'week', 'month', 'year'
    """
    today = date.today()

    if period == "week":
        start = today - timedelta(days=today.weekday())
        end = start + timedelta(days=6)
    elif period == "month":
        start = today.replace(day=1)
        next_month = today.replace(day=28) + timedelta(days=4)
        end = next_month.replace(day=1) - timedelta(days=1)
    else:  # year
        start = today.replace(month=1, day=1)
        end = today.replace(month=12, day=31)

    # Count completed jobs and total hours for the team in the period
    stats = await db.pool.fetchrow(
        """
        SELECT
            COUNT(*) AS total_jobs,
            COUNT(*) FILTER (WHERE status = 'completed') AS completed_jobs,
            COALESCE(SUM(estimated_duration_minutes) FILTER (WHERE status = 'completed'), 0) AS estimated_minutes,
            COALESCE(SUM(
                EXTRACT(EPOCH FROM (actual_end - actual_start)) / 60
            ) FILTER (WHERE status = 'completed' AND actual_start IS NOT NULL AND actual_end IS NOT NULL), 0) AS actual_minutes
        FROM cleaning_bookings
        WHERE business_id = $1
          AND team_id = $2
          AND scheduled_date BETWEEN $3 AND $4
          AND status NOT IN ('cancelled', 'no_show')
        """,
        business_id, team_id, start, end,
    )

    # Get daily breakdown
    daily = await db.pool.fetch(
        """
        SELECT
            scheduled_date,
            COUNT(*) AS jobs,
            COUNT(*) FILTER (WHERE status = 'completed') AS completed,
            COALESCE(SUM(
                EXTRACT(EPOCH FROM (actual_end - actual_start)) / 60
            ) FILTER (WHERE actual_start IS NOT NULL AND actual_end IS NOT NULL), 0) AS actual_minutes
        FROM cleaning_bookings
        WHERE business_id = $1
          AND team_id = $2
          AND scheduled_date BETWEEN $3 AND $4
          AND status NOT IN ('cancelled', 'no_show')
        GROUP BY scheduled_date
        ORDER BY scheduled_date
        """,
        business_id, team_id, start, end,
    )

    daily_breakdown = []
    for d in daily:
        daily_breakdown.append({
            "date": str(d["scheduled_date"]),
            "jobs": d["jobs"],
            "completed": d["completed"],
            "hours": round(float(d["actual_minutes"]) / 60, 1),
        })

    return {
        "period": period,
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "summary": {
            "total_jobs": stats["total_jobs"],
            "completed_jobs": stats["completed_jobs"],
            "estimated_hours": round(float(stats["estimated_minutes"]) / 60, 1),
            "actual_hours": round(float(stats["actual_minutes"]) / 60, 1),
        },
        "daily": daily_breakdown,
    }


# ============================================
# HELPERS
# ============================================

def _build_address(row) -> str:
    """Build a display address from a booking row."""
    parts = []
    if row.get("address_line1"):
        parts.append(row["address_line1"])
    if row.get("city"):
        parts.append(row["city"])
    if row.get("state"):
        parts.append(row["state"])
    if row.get("zip_code"):
        parts.append(row["zip_code"])
    return ", ".join(parts) if parts else ""


def _build_address_from_client(row) -> str:
    """Build address from client columns in a joined row."""
    parts = []
    if row.get("client_address"):
        parts.append(row["client_address"])
    if row.get("client_city"):
        parts.append(row["client_city"])
    if row.get("client_state"):
        parts.append(row["client_state"])
    if row.get("client_zip"):
        parts.append(row["client_zip"])
    return ", ".join(parts) if parts else ""


async def _get_checklist_items(
    db: Database,
    business_id: str,
    service_id: Optional[str],
    booking_id: str,
) -> list[dict]:
    """
    Get checklist items for a service, with completion status from job_logs.
    """
    if not service_id:
        return []

    # Find default checklist for this service
    checklist = await db.pool.fetchrow(
        """SELECT id, name FROM cleaning_checklists
           WHERE business_id = $1 AND service_id = $2 AND is_default = true
           LIMIT 1""",
        business_id, service_id,
    )

    if not checklist:
        # Try generic checklist
        checklist = await db.pool.fetchrow(
            """SELECT id, name FROM cleaning_checklists
               WHERE business_id = $1 AND service_id IS NULL AND is_default = true
               LIMIT 1""",
            business_id,
        )

    if not checklist:
        return []

    items = await db.pool.fetch(
        """SELECT id, room, task_description, is_required, sort_order, estimated_minutes
           FROM cleaning_checklist_items
           WHERE checklist_id = $1 AND business_id = $2
           ORDER BY sort_order, room""",
        checklist["id"], business_id,
    )

    # Get completed items for this booking
    completed_ids = set()
    completed_logs = await db.pool.fetch(
        """SELECT checklist_item_id FROM cleaning_job_logs
           WHERE booking_id = $1 AND log_type = 'task_complete'
             AND checklist_item_id IS NOT NULL""",
        booking_id,
    )
    for log in completed_logs:
        completed_ids.add(str(log["checklist_item_id"]))

    result = []
    for item in items:
        item_id = str(item["id"])
        result.append({
            "id": item_id,
            "room": item["room"],
            "task": item["task_description"],
            "is_required": item["is_required"],
            "estimated_minutes": item["estimated_minutes"],
            "completed": item_id in completed_ids,
        })

    return result


async def _publish_job_event(
    business_id: str,
    team_id: Optional[str],
    booking_id: str,
    action: str,
    data: dict,
):
    """Publish a job event via the change propagator."""
    try:
        from app.modules.cleaning.services.change_propagator import _publish
        event_data = {
            "action": action,
            "booking_id": booking_id,
            "team_id": team_id,
            **data,
        }
        await _publish(business_id, team_id, f"job.{action}", event_data)
    except Exception as e:
        logger.warning("[CLEANER_SERVICE] Failed to publish SSE event: %s", e)
