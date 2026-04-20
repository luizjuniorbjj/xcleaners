"""
Xcleaners v3 — Schedule Routes (S2.4 engine + S2.5 + S2.6).

Endpoints:
  POST /api/v1/clean/{slug}/schedule/generate/{date}         — S2.4: generate daily schedule (engine)
  POST /api/v1/clean/{slug}/schedule/regenerate/{date}       — S2.4: regenerate daily schedule
  POST /api/v1/clean/{slug}/schedule/assign                  — S2.4: assign job to team
  POST /api/v1/clean/{slug}/schedule/move                    — S2.4: move job between teams
  GET  /api/v1/clean/{slug}/schedule/unassigned/{date}       — S2.4: unassigned jobs
  GET  /api/v1/clean/{slug}/schedule/conflicts/{date}        — S2.4: conflicts for date
  GET  /api/v1/clean/{slug}/schedule/calendar                — FullCalendar event feed
  GET  /api/v1/clean/{slug}/schedule/daily/{date}            — daily schedule for all teams
  POST /api/v1/clean/{slug}/schedule/generate                — legacy placeholder generate
  GET  /api/v1/clean/{slug}/schedule/summary                 — summary stats
  GET  /api/v1/clean/{slug}/schedule/stream                  — SSE stream (owner: all events)
  GET  /api/v1/clean/{slug}/schedule/stream/team/{team_id}   — SSE stream (team-specific)
"""

import asyncio
import json
import logging
from datetime import date, datetime, timedelta
from typing import Optional

from app.modules.cleaning.services._type_helpers import to_date, to_time

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from app.database import get_db, Database
from app.modules.cleaning.middleware.role_guard import require_role
# S2.4 engine imports — guarded because S2.4 services may not exist yet
from app.modules.cleaning.models.schedules import (
    AssignJobRequest,
    MoveJobRequest,
)
try:
    from app.modules.cleaning.services.daily_generator import (
        generate_daily_schedule,
        regenerate_daily_schedule,
        get_daily_schedule as engine_get_daily_schedule,
        assign_job_to_team,
        move_job_between_teams,
        get_unassigned_jobs,
    )
    from app.modules.cleaning.services.conflict_resolver import (
        detect_all_conflicts,
    )
    _S24_AVAILABLE = True
except ImportError:
    _S24_AVAILABLE = False

logger = logging.getLogger("xcleaners.schedule_routes")

router = APIRouter(
    prefix="/api/v1/clean/{slug}",
    tags=["Xcleaners Schedule"],
)


# ============================================
# STATUS COLOR MAP
# ============================================

STATUS_COLORS = {
    "draft": "#9E9E9E",
    "scheduled": "#4285F4",
    "confirmed": "#4285F4",
    "in_progress": "#34A853",
    "completed": "#9E9E9E",
    "cancelled": "#EA4335",
    "rescheduled": "#FB8C00",
    "no_show": "#EA4335",
}


# ============================================
# S2.4 — SCHEDULE ENGINE ENDPOINTS
# ============================================


def _parse_date_param(date_str: str) -> date:
    """Parse YYYY-MM-DD string to date object."""
    try:
        return date.fromisoformat(date_str)
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid date format: '{date_str}'. Expected YYYY-MM-DD.",
        )


@router.post("/schedule/generate/{target_date}")
async def engine_generate_schedule(
    slug: str,
    target_date: str,
    user: dict = Depends(require_role("owner")),
    db: Database = Depends(get_db),
):
    """
    S2.4 — Generate the daily schedule using the full 5-step engine.

    This is THE core operation of Xcleaners. It:
    1. Collects all eligible jobs (recurring + manual one-offs)
    2. Computes team availability (members, time windows, exceptions)
    3. Scores and assigns teams to jobs (5-factor weighted algorithm)
    4. Applies travel buffers and detects conflicts
    5. Persists bookings and caches results in Redis

    Idempotent: re-running replaces unconfirmed bookings, preserves confirmed.
    Uses distributed Redis lock to prevent concurrent generation.
    """
    parsed_date = _parse_date_param(target_date)
    result = await generate_daily_schedule(
        db=db, business_id=user["business_id"], target_date=parsed_date,
    )
    if isinstance(result, dict) and result.get("error"):
        raise HTTPException(
            status_code=409,
            detail=result.get("message", "Schedule generation failed"),
        )
    return result


@router.post("/schedule/regenerate/{target_date}")
async def engine_regenerate_schedule(
    slug: str,
    target_date: str,
    user: dict = Depends(require_role("owner")),
    db: Database = Depends(get_db),
):
    """S2.4 — Clear unconfirmed bookings and regenerate the schedule."""
    parsed_date = _parse_date_param(target_date)
    result = await regenerate_daily_schedule(
        db=db, business_id=user["business_id"], target_date=parsed_date,
    )
    if isinstance(result, dict) and result.get("error"):
        raise HTTPException(
            status_code=409,
            detail=result.get("message", "Schedule regeneration failed"),
        )
    return result


@router.get("/schedule/engine/daily/{target_date}")
async def engine_get_daily(
    slug: str,
    target_date: str,
    user: dict = Depends(require_role("owner")),
    db: Database = Depends(get_db),
):
    """S2.4 — Get the daily schedule (all teams) from engine/cache."""
    parsed_date = _parse_date_param(target_date)
    return await engine_get_daily_schedule(
        db=db, business_id=user["business_id"], target_date=parsed_date,
    )


@router.get("/schedule/team/{team_id}/{target_date}")
async def engine_get_team_schedule(
    slug: str,
    team_id: str,
    target_date: str,
    user: dict = Depends(require_role("owner", "team_lead")),
    db: Database = Depends(get_db),
):
    """S2.4 — Get a single team's schedule for a date."""
    parsed_date = _parse_date_param(target_date)
    return await engine_get_daily_schedule(
        db=db, business_id=user["business_id"],
        target_date=parsed_date, team_id=team_id,
    )


@router.post("/schedule/assign")
async def engine_assign_job(
    slug: str,
    body: AssignJobRequest,
    user: dict = Depends(require_role("owner")),
    db: Database = Depends(get_db),
):
    """S2.4 — Manually assign a booking to a team."""
    result = await assign_job_to_team(
        db=db, business_id=user["business_id"],
        booking_id=body.booking_id, team_id=body.team_id,
    )
    if isinstance(result, dict) and result.get("error"):
        raise HTTPException(
            status_code=result.get("status_code", 400),
            detail=result.get("message", "Assignment failed"),
        )
    return result


@router.post("/schedule/move")
async def engine_move_job(
    slug: str,
    body: MoveJobRequest,
    user: dict = Depends(require_role("owner")),
    db: Database = Depends(get_db),
):
    """S2.4 — Move a booking from one team to another (drag-and-drop)."""
    result = await move_job_between_teams(
        db=db, business_id=user["business_id"],
        booking_id=body.booking_id,
        from_team_id=body.from_team_id, to_team_id=body.to_team_id,
    )
    if isinstance(result, dict) and result.get("error"):
        raise HTTPException(
            status_code=result.get("status_code", 400),
            detail=result.get("message", "Move failed"),
        )
    return result


@router.get("/schedule/unassigned/{target_date}")
async def engine_get_unassigned(
    slug: str,
    target_date: str,
    user: dict = Depends(require_role("owner")),
    db: Database = Depends(get_db),
):
    """S2.4 — Get all bookings without team assignment for a date."""
    parsed_date = _parse_date_param(target_date)
    return await get_unassigned_jobs(
        db=db, business_id=user["business_id"], target_date=parsed_date,
    )


@router.get("/schedule/conflicts/{target_date}")
async def engine_get_conflicts(
    slug: str,
    target_date: str,
    user: dict = Depends(require_role("owner")),
    db: Database = Depends(get_db),
):
    """S2.4 — Get all scheduling conflicts for a date."""
    parsed_date = _parse_date_param(target_date)
    business_id = user["business_id"]

    teams = await db.pool.fetch(
        "SELECT id, name, max_daily_jobs FROM cleaning_teams "
        "WHERE business_id = $1 AND is_active = true",
        business_id,
    )

    all_conflicts = []
    for team_row in teams:
        team_id_val = team_row["id"]
        bookings = await db.pool.fetch(
            """SELECT b.id, b.scheduled_start, b.scheduled_end,
                      b.estimated_duration_minutes, b.zip_code, b.client_id
               FROM cleaning_bookings b
               WHERE b.business_id = $1 AND b.team_id = $2
                 AND b.scheduled_date = $3
                 AND b.status NOT IN ('cancelled', 'no_show')
               ORDER BY b.scheduled_start ASC NULLS LAST""",
            business_id, team_id_val, parsed_date,
        )
        if not bookings:
            continue

        assignments = [{
            "id": str(b["id"]),
            "scheduled_start": str(b["scheduled_start"]) if b["scheduled_start"] else None,
            "scheduled_end": str(b["scheduled_end"]) if b["scheduled_end"] else None,
            "estimated_duration_minutes": b["estimated_duration_minutes"] or 120,
            "zip_code": b["zip_code"],
            "client_id": str(b["client_id"]),
            "min_team_size": 1,
        } for b in bookings]

        available = await db.pool.fetchval(
            """SELECT COUNT(DISTINCT a.member_id)
               FROM cleaning_team_assignments a
               JOIN cleaning_team_members m ON m.id = a.member_id
               WHERE a.team_id = $1 AND a.is_active = true
                 AND m.status = 'active'
                 AND a.effective_from <= $2
                 AND (a.effective_until IS NULL OR a.effective_until >= $2)
                 AND NOT EXISTS (
                     SELECT 1 FROM cleaning_team_availability exc
                     WHERE exc.team_member_id = a.member_id
                       AND exc.business_id = $3
                       AND exc.effective_from = $2
                       AND exc.effective_until = $2
                       AND exc.is_available = false
                 )""",
            team_id_val, parsed_date, business_id,
        )

        conflicts = detect_all_conflicts(
            team={"id": str(team_id_val), "name": team_row["name"],
                  "max_daily_jobs": team_row["max_daily_jobs"]},
            assignments=assignments,
            available_members=available or 0,
        )
        all_conflicts.extend(conflicts)

    return {
        "date": parsed_date.isoformat(),
        "conflicts": all_conflicts,
        "total": len(all_conflicts),
    }


# ============================================
# CALENDAR FEED (FullCalendar-compatible)
# ============================================

@router.get("/schedule/calendar")
async def get_calendar_events(
    slug: str,
    start: str = Query(..., description="ISO date: start of range"),
    end: str = Query(..., description="ISO date: end of range"),
    team_id: Optional[str] = Query(None, description="Filter by team ID"),
    user: dict = Depends(require_role("owner")),
    db: Database = Depends(get_db),
):
    """
    Returns events in FullCalendar-compatible format.
    FullCalendar automatically sends start/end query params.
    """
    business_id = user["business_id"]

    conditions = [
        "b.business_id = $1",
        "b.scheduled_date >= $2",
        "b.scheduled_date <= $3",
    ]
    params = [business_id, to_date(start), to_date(end)]
    idx = 4

    if team_id:
        conditions.append(f"b.team_id = ${idx}")
        params.append(team_id)
        idx += 1

    where = " AND ".join(conditions)

    rows = await db.pool.fetch(
        f"""
        SELECT
            b.id,
            b.team_id,
            b.scheduled_date,
            b.scheduled_start,
            b.scheduled_end,
            b.estimated_duration_minutes,
            b.status,
            b.address_line1,
            b.special_instructions,
            b.access_instructions,
            b.quoted_price,
            c.first_name AS client_first,
            c.last_name AS client_last,
            c.address_line1 AS client_address,
            c.city AS client_city,
            s.name AS service_name,
            t.name AS team_name,
            t.color AS team_color
        FROM cleaning_bookings b
        JOIN cleaning_clients c ON c.id = b.client_id
        LEFT JOIN cleaning_services s ON s.id = b.service_id
        LEFT JOIN cleaning_teams t ON t.id = b.team_id
        WHERE {where}
        ORDER BY b.scheduled_date, b.scheduled_start
        """,
        *params,
    )

    events = []
    for row in rows:
        client_name = f"{row['client_first'] or ''} {row['client_last'] or ''}".strip()
        service_name = row["service_name"] or "Cleaning"
        status = row["status"] or "scheduled"

        # Build start/end datetime strings
        sched_date = str(row["scheduled_date"])
        start_time = str(row["scheduled_start"]) if row["scheduled_start"] else "09:00:00"
        # Ensure HH:MM:SS format
        if len(start_time) == 5:
            start_time += ":00"

        end_time = None
        if row["scheduled_end"]:
            end_time = str(row["scheduled_end"])
            if len(end_time) == 5:
                end_time += ":00"
        elif row["estimated_duration_minutes"]:
            # Compute end from start + duration
            try:
                st = datetime.strptime(f"{sched_date} {start_time}", "%Y-%m-%d %H:%M:%S")
                et = st + timedelta(minutes=row["estimated_duration_minutes"])
                end_time = et.strftime("%H:%M:%S")
            except Exception:
                end_time = None

        event = {
            "id": str(row["id"]),
            "resourceId": str(row["team_id"]) if row["team_id"] else "unassigned",
            "title": f"{client_name} - {service_name}",
            "start": f"{sched_date}T{start_time}",
            "end": f"{sched_date}T{end_time}" if end_time else None,
            "color": row["team_color"] if row["team_color"] and status not in ("cancelled", "completed") else STATUS_COLORS.get(status, "#4285F4"),
            "borderColor": "#EA4335" if status == "cancelled" else None,
            "textColor": "#FFFFFF" if status != "cancelled" else "#EA4335",
            "classNames": [f"cc-status-{status}"],
            "extendedProps": {
                "client_name": client_name,
                "address": row["address_line1"] or row["client_address"] or "",
                "city": row["client_city"] or "",
                "service_type": service_name,
                "status": status,
                "team_name": row["team_name"] or "Unassigned",
                "team_id": str(row["team_id"]) if row["team_id"] else None,
                "duration_minutes": row["estimated_duration_minutes"],
                "quoted_price": float(row["quoted_price"]) if row["quoted_price"] else None,
                "access_instructions": row["access_instructions"],
                "special_instructions": row["special_instructions"],
            },
        }
        events.append(event)

    return events


# ============================================
# DAILY SCHEDULE (structured view)
# ============================================

@router.get("/schedule/daily/{date}")
async def get_daily_schedule(
    slug: str,
    date: str,
    user: dict = Depends(require_role("owner")),
    db: Database = Depends(get_db),
):
    """Get structured daily schedule grouped by team."""
    business_id = user["business_id"]

    # Convert string date to date object for asyncpg
    try:
        target_date = datetime.strptime(date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD.")

    # Get all teams
    teams = await db.pool.fetch(
        "SELECT id, name, color FROM cleaning_teams WHERE business_id = $1 AND is_active = true ORDER BY name",
        business_id,
    )

    # Get all bookings for the day
    bookings = await db.pool.fetch(
        """
        SELECT
            b.*,
            c.first_name AS client_first, c.last_name AS client_last,
            c.address_line1 AS client_address, c.city AS client_city,
            s.name AS service_name
        FROM cleaning_bookings b
        JOIN cleaning_clients c ON c.id = b.client_id
        LEFT JOIN cleaning_services s ON s.id = b.service_id
        WHERE b.business_id = $1 AND b.scheduled_date = $2
        ORDER BY b.scheduled_start
        """,
        business_id, target_date,
    )

    # Group by team
    team_schedules = []
    unassigned = []

    for team in teams:
        team_id = str(team["id"])
        team_bookings = [
            _booking_to_summary(b)
            for b in bookings
            if str(b["team_id"]) == team_id
        ]
        team_schedules.append({
            "team_id": team_id,
            "team_name": team["name"],
            "team_color": team["color"],
            "jobs": team_bookings,
            "job_count": len(team_bookings),
        })

    # Unassigned bookings
    for b in bookings:
        if not b["team_id"]:
            unassigned.append(_booking_to_summary(b))

    return {
        "date": date,
        "teams": team_schedules,
        "unassigned": unassigned,
        "total_jobs": len(bookings),
        "unassigned_count": len(unassigned),
    }


# ============================================
# SUMMARY STATS
# ============================================

@router.get("/schedule/summary")
async def get_schedule_summary(
    slug: str,
    date: Optional[str] = Query(None),
    user: dict = Depends(require_role("owner")),
    db: Database = Depends(get_db),
):
    """Summary stats for the schedule view header."""
    business_id = user["business_id"]
    if date:
        try:
            target_date = datetime.strptime(date, "%Y-%m-%d").date()
        except ValueError:
            target_date = datetime.now().date()
    else:
        target_date = datetime.now().date()
    target = str(target_date)

    # Today's stats
    today_row = await db.pool.fetchrow(
        """
        SELECT
            COUNT(*) AS total_jobs,
            COUNT(*) FILTER (WHERE status NOT IN ('cancelled', 'no_show')) AS active_jobs,
            COALESCE(SUM(quoted_price) FILTER (WHERE status NOT IN ('cancelled', 'no_show')), 0) AS total_revenue,
            COUNT(*) FILTER (WHERE team_id IS NULL AND status NOT IN ('cancelled', 'no_show')) AS unassigned_jobs
        FROM cleaning_bookings
        WHERE business_id = $1 AND scheduled_date = $2
        """,
        business_id, target_date,
    )

    # Active teams today
    teams_active = await db.pool.fetchval(
        """
        SELECT COUNT(DISTINCT team_id)
        FROM cleaning_bookings
        WHERE business_id = $1 AND scheduled_date = $2
          AND team_id IS NOT NULL AND status NOT IN ('cancelled', 'no_show')
        """,
        business_id, target_date,
    )

    # Week stats (Mon-Sun of current week)
    week_start = target_date - timedelta(days=target_date.weekday())
    week_end = week_start + timedelta(days=6)

    week_row = await db.pool.fetchrow(
        """
        SELECT
            COUNT(*) AS week_jobs,
            COALESCE(SUM(quoted_price) FILTER (WHERE status NOT IN ('cancelled', 'no_show')), 0) AS week_revenue
        FROM cleaning_bookings
        WHERE business_id = $1 AND scheduled_date BETWEEN $2 AND $3
        """,
        business_id, week_start, week_end,
    )

    return {
        "date": target,
        "today": {
            "total_jobs": today_row["total_jobs"],
            "active_jobs": today_row["active_jobs"],
            "revenue": float(today_row["total_revenue"]),
            "unassigned_jobs": today_row["unassigned_jobs"],
            "teams_active": teams_active or 0,
        },
        "week": {
            "total_jobs": week_row["week_jobs"],
            "revenue": float(week_row["week_revenue"]),
            "start": str(week_start),
            "end": str(week_end),
        },
    }


# ============================================
# GENERATE SCHEDULE (placeholder — ties to S2.4 engine)
# ============================================

@router.post("/schedule/generate")
async def generate_schedule(
    slug: str,
    body: dict = None,
    user: dict = Depends(require_role("owner")),
    db: Database = Depends(get_db),
):
    """
    Trigger schedule generation for a specific date.

    Creates bookings from recurring client schedules and runs each through
    the pricing engine (Story 1.1 Task 6): each booking gets final_price,
    tax/discount/adjustment columns, and an immutable price_snapshot JSONB.

    Graceful fallback: if pricing engine is missing config (no formula,
    no override), falls back to sched.agreed_price with an empty snapshot
    so schedule generation never halts the dashboard.
    """
    from app.modules.cleaning.services.schedule_service import list_schedules_due_on
    from app.modules.cleaning.services.change_propagator import on_schedule_generated
    from app.modules.cleaning.services.booking_service import create_booking_with_pricing
    from app.modules.cleaning.services.pricing_engine import PricingConfigError

    business_id = user["business_id"]

    if not body:
        body = {}
    target_date = body.get("date", str(datetime.now().date()))

    try:
        target = datetime.strptime(target_date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD.")

    # Check for existing bookings on this date
    existing = await db.pool.fetchval(
        "SELECT COUNT(*) FROM cleaning_bookings WHERE business_id = $1 AND scheduled_date = $2 AND source = 'recurring'",
        business_id, target,
    )

    if existing > 0 and not body.get("force"):
        raise HTTPException(
            status_code=409,
            detail=f"Schedule already exists for {target_date} ({existing} bookings). Set force=true to regenerate.",
        )

    # If force regenerate, cancel existing recurring bookings
    if existing > 0 and body.get("force"):
        await db.pool.execute(
            """UPDATE cleaning_bookings SET status = 'cancelled', cancellation_reason = 'Regenerated schedule'
               WHERE business_id = $1 AND scheduled_date = $2 AND source = 'recurring' AND status IN ('draft', 'scheduled')""",
            business_id, target,
        )

    # Get schedules due on this date
    due_schedules = await list_schedules_due_on(db, business_id, target)

    created_count = 0
    priced_count = 0
    fallback_count = 0
    team_jobs: dict[str, int] = {}

    for sched in due_schedules:
        team_id = sched.get("preferred_team_id")
        start_time = sched.get("preferred_time_start") or "09:00:00"
        duration = sched.get("estimated_duration_minutes") or 120

        try:
            start_parsed = datetime.strptime(start_time, "%H:%M:%S").time()
        except ValueError:
            try:
                start_parsed = datetime.strptime(start_time, "%H:%M").time()
            except ValueError:
                start_parsed = datetime.strptime("09:00:00", "%H:%M:%S").time()

        booking_id: str | None = None
        try:
            result = await create_booking_with_pricing(
                db,
                business_id=business_id,
                client_id=sched["client_id"],
                service_id=sched["service_id"],
                scheduled_date=target,
                scheduled_start=start_parsed,
                estimated_duration_minutes=duration,
                team_id=team_id,
                recurring_schedule_id=sched["id"],
                source="recurring",
                status="scheduled",
            )
            booking_id = result["booking_id"]
            priced_count += 1
        except PricingConfigError as exc:
            logger.warning(
                "schedule/generate: pricing engine fallback for schedule=%s: %s",
                sched.get("id"), exc,
            )
            end_time = (datetime.combine(target, start_parsed)
                        + timedelta(minutes=duration)).time()
            row = await db.pool.fetchrow(
                """INSERT INTO cleaning_bookings
                   (business_id, client_id, service_id, recurring_schedule_id,
                    scheduled_date, scheduled_start, scheduled_end,
                    estimated_duration_minutes, team_id,
                    quoted_price, final_price, status, source)
                   VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $10,
                           'scheduled', 'recurring')
                   RETURNING id""",
                business_id,
                sched["client_id"],
                sched["service_id"],
                sched["id"],
                target,
                start_parsed,
                end_time,
                duration,
                team_id,
                sched.get("agreed_price"),
            )
            booking_id = str(row["id"]) if row else None
            fallback_count += 1

        if booking_id:
            created_count += 1
            if team_id:
                team_jobs[team_id] = team_jobs.get(team_id, 0) + 1

    # Publish SSE events
    if team_jobs:
        teams_info = []
        for tid, count in team_jobs.items():
            team_row = await db.pool.fetchrow(
                "SELECT name FROM cleaning_teams WHERE id = $1", tid
            )
            teams_info.append({
                "team_id": tid,
                "team_name": team_row["name"] if team_row else "Unknown",
                "job_count": count,
            })
        await on_schedule_generated(business_id, target_date, teams_info)

    return {
        "message": f"Generated {created_count} bookings for {target_date}",
        "date": target_date,
        "created": created_count,
        "priced": priced_count,
        "pricing_fallback": fallback_count,
        "teams_affected": len(team_jobs),
    }


# ============================================
# SSE STREAM — OWNER (all schedule events)
# ============================================

async def _sse_auth(slug: str, request: Request, token: str = Query(None), db: Database = Depends(get_db)):
    """SSE auth — accepts token via query param since EventSource can't send headers."""
    if not token:
        raise HTTPException(status_code=401, detail="Token required")
    from app.auth import verify_token
    payload = verify_token(token)
    if not payload or payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="Invalid token")
    from app.modules.cleaning.routes.auth_middleware import _resolve_business_id, resolve_cleaning_role
    business_id = await _resolve_business_id(db, slug)
    role_data = await resolve_cleaning_role(request, payload["sub"], business_id, db)
    return {
        "user_id": payload["sub"], "email": payload["email"],
        "role": payload.get("role", "lead"),
        "cleaning_role": role_data["role"] if role_data else None,
        "cleaning_team_id": role_data["team_id"] if role_data else None,
        "business_id": business_id, "business_slug": slug,
    }


@router.get("/schedule/stream")
async def schedule_stream(
    slug: str,
    request: Request,
    user: dict = Depends(_sse_auth),
):
    """
    SSE stream for the owner. Subscribes to the business-level schedule channel.
    Returns text/event-stream with real-time schedule events.
    """
    business_id = user["business_id"]
    channel = f"clean:{business_id}:sse:schedule"

    return StreamingResponse(
        _sse_generator(channel, request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ============================================
# SSE STREAM — TEAM (team-specific events)
# ============================================

@router.get("/schedule/stream/team/{team_id}")
async def team_schedule_stream(
    slug: str,
    team_id: str,
    request: Request,
    user: dict = Depends(_sse_auth),
):
    """
    SSE stream for a specific team. Team members only see their team's events.
    Owners can also subscribe to individual team channels.
    """
    business_id = user["business_id"]

    # Verify team_lead/cleaner belongs to this team
    if user["cleaning_role"] in ("team_lead", "cleaner"):
        if user.get("cleaning_team_id") != team_id:
            raise HTTPException(
                status_code=403,
                detail="You can only subscribe to your own team's schedule stream.",
            )

    channel = f"clean:{business_id}:sse:team:{team_id}"

    return StreamingResponse(
        _sse_generator(channel, request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ============================================
# SSE GENERATOR (Redis PubSub)
# ============================================

async def _sse_generator(channel: str, request: Request):
    """
    Async generator that subscribes to a Redis PubSub channel
    and yields SSE-formatted messages.

    Sends a heartbeat comment every 30s to keep the connection alive.
    Gracefully exits when the client disconnects.
    """
    from app.redis_client import get_redis

    redis = get_redis()
    if not redis:
        # No Redis — send an error event and close
        yield "event: error\ndata: {\"message\": \"Real-time updates unavailable\"}\n\n"
        return

    pubsub = redis.pubsub()
    try:
        await pubsub.subscribe(channel)
        logger.info("[SSE] Client subscribed to %s", channel)

        # Send initial connected event
        yield f"event: connected\ndata: {{\"channel\": \"{channel}\"}}\n\n"

        while True:
            # Check if client disconnected
            if await request.is_disconnected():
                logger.info("[SSE] Client disconnected from %s", channel)
                break

            try:
                message = await asyncio.wait_for(
                    pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0),
                    timeout=30.0,
                )

                if message and message["type"] == "message":
                    data = message["data"]
                    if isinstance(data, bytes):
                        data = data.decode("utf-8")

                    # Parse to extract event type
                    try:
                        parsed = json.loads(data)
                        event_type = parsed.get("event", "message")
                    except (json.JSONDecodeError, TypeError):
                        event_type = "message"

                    yield f"event: {event_type}\ndata: {data}\n\n"

            except asyncio.TimeoutError:
                # Send heartbeat to keep connection alive
                yield ": heartbeat\n\n"

    except asyncio.CancelledError:
        logger.info("[SSE] Stream cancelled for %s", channel)
    except Exception as e:
        logger.error("[SSE] Error in stream %s: %s", channel, e)
        yield f"event: error\ndata: {{\"message\": \"Stream error\"}}\n\n"
    finally:
        try:
            await pubsub.unsubscribe(channel)
            await pubsub.close()
        except Exception:
            pass
        logger.info("[SSE] Cleaned up subscription for %s", channel)


# ============================================
# BOOKINGS CRUD (GET list, PATCH for drag-and-drop)
# ============================================

@router.get("/bookings")
async def list_bookings(
    slug: str,
    status: Optional[str] = Query(None, description="Filter by status (scheduled, completed, etc)"),
    date_from: Optional[str] = Query(None, description="ISO date: lower bound (inclusive)"),
    date_to: Optional[str] = Query(None, description="ISO date: upper bound (inclusive)"),
    limit: int = Query(500, ge=1, le=2000),
    user: dict = Depends(require_role("owner")),
    db: Database = Depends(get_db),
):
    """
    Return bookings scoped to the caller's business_id.

    Used by the Owner "All Bookings" page (frontend route /bookings).
    Filter flags are optional — frontend can filter client-side too.
    Max `limit` rows to avoid runaway payloads.
    """
    business_id = user["business_id"]

    conditions = ["b.business_id = $1"]
    params: list = [business_id]
    idx = 2

    if status:
        conditions.append(f"b.status = ${idx}")
        params.append(status)
        idx += 1

    if date_from:
        conditions.append(f"b.scheduled_date >= ${idx}")
        params.append(to_date(date_from))
        idx += 1

    if date_to:
        conditions.append(f"b.scheduled_date <= ${idx}")
        params.append(to_date(date_to))
        idx += 1

    where = " AND ".join(conditions)

    rows = await db.pool.fetch(
        f"""
        SELECT
            b.id,
            b.business_id,
            b.scheduled_date,
            b.scheduled_start,
            b.scheduled_end,
            b.estimated_duration_minutes,
            b.status,
            b.address_line1,
            b.city,
            b.state,
            b.zip_code,
            b.quoted_price,
            b.final_price,
            b.tax_amount,
            b.adjustment_amount,
            b.special_instructions,
            b.team_id,
            b.client_id,
            b.service_id,
            c.first_name AS client_first,
            c.last_name  AS client_last,
            s.name       AS service_name,
            t.name       AS team_name,
            t.color      AS team_color
        FROM cleaning_bookings b
        JOIN cleaning_clients c ON c.id = b.client_id
        LEFT JOIN cleaning_services s ON s.id = b.service_id
        LEFT JOIN cleaning_teams t ON t.id = b.team_id
        WHERE {where}
        ORDER BY b.scheduled_date DESC, b.scheduled_start DESC
        LIMIT ${idx}
        """,
        *params, limit,
    )

    bookings = []
    for row in rows:
        first = row["client_first"] or ""
        last = row["client_last"] or ""
        client_name = f"{first} {last}".strip() or "—"

        address_parts = [row["address_line1"], row["city"], row["state"]]
        address = ", ".join(p for p in address_parts if p) or None

        bookings.append({
            "id": str(row["id"]),
            "business_id": str(row["business_id"]),
            "scheduled_date": str(row["scheduled_date"]) if row["scheduled_date"] else None,
            "scheduled_start": str(row["scheduled_start"]) if row["scheduled_start"] else None,
            "scheduled_end": str(row["scheduled_end"]) if row["scheduled_end"] else None,
            "estimated_duration_minutes": row["estimated_duration_minutes"],
            "status": row["status"],
            "address": address,
            "address_line1": row["address_line1"],
            "city": row["city"],
            "state": row["state"],
            "zip_code": row["zip_code"],
            "quoted_price": float(row["quoted_price"]) if row["quoted_price"] is not None else None,
            "final_price": float(row["final_price"]) if row["final_price"] is not None else None,
            "tax_amount": float(row["tax_amount"]) if row["tax_amount"] is not None else None,
            "adjustment_amount": float(row["adjustment_amount"]) if row["adjustment_amount"] is not None else None,
            "special_instructions": row["special_instructions"],
            "client_id": str(row["client_id"]) if row["client_id"] else None,
            "client_name": client_name,
            "service_id": str(row["service_id"]) if row["service_id"] else None,
            "service": row["service_name"],
            "team_id": str(row["team_id"]) if row["team_id"] else None,
            "team_name": row["team_name"],
            "team_color": row["team_color"],
        })

    return {"bookings": bookings, "total": len(bookings)}


@router.patch("/bookings/{booking_id}")
async def patch_booking(
    slug: str,
    booking_id: str,
    body: dict,
    user: dict = Depends(require_role("owner")),
    db: Database = Depends(get_db),
):
    """
    Partial update for a booking. Used by calendar drag-and-drop.
    Supports: scheduled_date, scheduled_start, scheduled_end, team_id, status, notes.
    """
    from app.modules.cleaning.services.change_propagator import on_booking_updated

    business_id = user["business_id"]

    # Fetch current booking
    current = await db.pool.fetchrow(
        """SELECT b.*, c.first_name AS client_first, c.last_name AS client_last,
                  s.name AS service_name
           FROM cleaning_bookings b
           JOIN cleaning_clients c ON c.id = b.client_id
           LEFT JOIN cleaning_services s ON s.id = b.service_id
           WHERE b.id = $1 AND b.business_id = $2""",
        booking_id, business_id,
    )

    if not current:
        raise HTTPException(status_code=404, detail="Booking not found")

    old_team_id = str(current["team_id"]) if current["team_id"] else None

    # Allowed update fields
    allowed = {
        "scheduled_date", "scheduled_start", "scheduled_end",
        "estimated_duration_minutes", "team_id", "status",
        "notes", "special_instructions",
    }
    update_data = {k: v for k, v in body.items() if k in allowed and v is not None}

    if not update_data:
        return {"message": "No changes", "booking_id": booking_id}

    # Conflict check if changing time/team
    if ("scheduled_start" in update_data or "team_id" in update_data) and (update_data.get("team_id") or current["team_id"]):
        target_team = update_data.get("team_id") or (str(current["team_id"]) if current["team_id"] else None)
        target_date = update_data.get("scheduled_date") or str(current["scheduled_date"])
        target_start = update_data.get("scheduled_start") or str(current["scheduled_start"])

        if target_team:
            conflict = await db.pool.fetchrow(
                """SELECT id FROM cleaning_bookings
                   WHERE business_id = $1 AND team_id = $2
                     AND scheduled_date = $3
                     AND scheduled_start = $4
                     AND id != $5
                     AND status NOT IN ('cancelled', 'no_show')""",
                business_id, target_team, to_date(target_date), to_time(target_start), booking_id,
            )
            if conflict:
                raise HTTPException(
                    status_code=409,
                    detail=f"Time conflict: another booking exists at {target_start} for this team.",
                )

    # Build UPDATE query
    set_parts = []
    values = []
    idx = 1
    for col, val in update_data.items():
        if col == "scheduled_date":
            set_parts.append(f"{col} = ${idx}")
            val = to_date(val)
        elif col in ("scheduled_start", "scheduled_end"):
            set_parts.append(f"{col} = ${idx}")
            val = to_time(val)
        else:
            set_parts.append(f"{col} = ${idx}")
        values.append(val)
        idx += 1

    set_parts.append("updated_at = NOW()")
    values.extend([booking_id, business_id])

    row = await db.pool.fetchrow(
        f"""UPDATE cleaning_bookings
            SET {', '.join(set_parts)}
            WHERE id = ${idx} AND business_id = ${idx + 1}
            RETURNING *""",
        *values,
    )

    if not row:
        raise HTTPException(status_code=404, detail="Booking not found or update failed")

    # Publish SSE event
    client_name = f"{current['client_first'] or ''} {current['client_last'] or ''}".strip()
    booking_info = {
        "id": str(row["id"]),
        "team_id": str(row["team_id"]) if row["team_id"] else None,
        "scheduled_date": str(row["scheduled_date"]),
        "scheduled_start": str(row["scheduled_start"]) if row["scheduled_start"] else None,
        "scheduled_end": str(row["scheduled_end"]) if row["scheduled_end"] else None,
        "client_name": client_name,
        "service_name": current["service_name"] or "",
        "status": row["status"],
    }
    await on_booking_updated(business_id, booking_info, old_team_id)

    # Client-facing transition emails when status changes
    old_status = current["status"]
    new_status = row["status"]
    if old_status != new_status:
        try:
            from app.modules.cleaning.services.email_service import (
                send_booking_confirmed,
                send_booking_cancelled,
            )
            if old_status == "draft" and new_status == "scheduled":
                await send_booking_confirmed(db, str(row["id"]))
            elif new_status == "cancelled" and old_status != "cancelled":
                await send_booking_cancelled(
                    db, str(row["id"]),
                    reason=row.get("cancellation_reason") if hasattr(row, "get") else (row["cancellation_reason"] or ""),
                )
        except Exception:
            import logging
            logging.getLogger("xcleaners.schedule").exception(
                "patch_booking: client notify failed for %s (status %s→%s)",
                booking_id, old_status, new_status,
            )

    return {
        "message": "Booking updated",
        "booking_id": str(row["id"]),
        "status": row["status"],
        "scheduled_date": str(row["scheduled_date"]),
        "scheduled_start": str(row["scheduled_start"]) if row["scheduled_start"] else None,
        "team_id": str(row["team_id"]) if row["team_id"] else None,
    }


# ============================================
# HELPERS
# ============================================

def _booking_to_summary(row) -> dict:
    """Convert a booking DB row to a summary dict."""
    client_name = f"{row.get('client_first', '') or ''} {row.get('client_last', '') or ''}".strip()
    return {
        "id": str(row["id"]),
        "client_name": client_name,
        "service_name": row.get("service_name") or "Cleaning",
        "address": row.get("address_line1") or row.get("client_address") or "",
        "city": row.get("client_city") or "",
        "scheduled_start": str(row["scheduled_start"]) if row.get("scheduled_start") else None,
        "scheduled_end": str(row["scheduled_end"]) if row.get("scheduled_end") else None,
        "estimated_duration_minutes": row.get("estimated_duration_minutes"),
        "status": row.get("status", "scheduled"),
        "quoted_price": float(row["quoted_price"]) if row.get("quoted_price") else None,
        "team_id": str(row["team_id"]) if row.get("team_id") else None,
    }
