"""
Xcleaners — Availability Service (AI Turbo Sprint, 2026-04-20)

Hard gate de disponibilidade de slot. Usado por:
  - Tool check_availability (chat IA customer)
  - Futuro: validação em create_booking_with_pricing (backlog)

Schema real consultado:
  cleaning_bookings (scheduled_date, scheduled_start, scheduled_end,
                     estimated_duration_minutes, status, team_id, business_id)
  cleaning_teams (is_active)

Regras:
  - Um slot e conflitante se overlapa com booking ativo (status NOT IN cancelled/no_show).
  - Travel buffer 15 min (mesmo zip) ou 30 min (zip diferente).
  - Default duration 120 min quando scheduled_end e NULL.

Nota (backlog): advisory lock PostgreSQL + SELECT FOR UPDATE ficam para iteracao
seguinte — nesta sprint turbo usamos SELECT simples. Race TOCTOU mitigada por:
  (a) UNIQUE constraint em (business_id, client_id, scheduled_date, scheduled_start)
      WHERE status='draft' (backlog);
  (b) Idempotency_key por conversation_id na tool propose_booking_draft.
"""

from __future__ import annotations

import logging
from datetime import date as date_cls, datetime, time as time_cls, timedelta
from typing import Any, Optional
from uuid import UUID

from app.database import Database


logger = logging.getLogger("xcleaners.availability")


_DEFAULT_DURATION_MIN = 120
_TRAVEL_BUFFER_SAME_ZIP = 15
_TRAVEL_BUFFER_DIFF_ZIP = 30
_ACTIVE_STATUSES = ("draft", "scheduled", "confirmed", "in_progress", "rescheduled")


def _coerce_date(value: date_cls | str) -> date_cls:
    if isinstance(value, date_cls) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    return date_cls.fromisoformat(str(value)[:10])


def _coerce_time(value: time_cls | str) -> time_cls:
    if isinstance(value, time_cls):
        return value
    s = str(value)
    if len(s) == 5:
        s += ":00"
    return time_cls.fromisoformat(s)


def _compute_end(start: time_cls, duration_min: int) -> time_cls:
    anchor = datetime.combine(date_cls.today(), start)
    return (anchor + timedelta(minutes=duration_min)).time()


def _minutes(t: time_cls) -> int:
    return t.hour * 60 + t.minute


async def is_slot_available(
    db: Database,
    *,
    business_id: UUID | str,
    scheduled_date: date_cls | str,
    scheduled_start: time_cls | str,
    duration_minutes: int | None = None,
    team_id: UUID | str | None = None,
    client_zip: Optional[str] = None,
) -> dict[str, Any]:
    """
    Check if the given slot is available.

    Args:
        business_id: tenant scope
        scheduled_date: target date (date or ISO str)
        scheduled_start: start time (time or HH:MM[:SS])
        duration_minutes: service duration; default 120
        team_id: optional — if provided, checks only that team's bookings.
                 If None, checks ANY booking in the business for the slot
                 (conservative — returns all potential conflicts).
        client_zip: optional — enables zip-aware travel buffer (15 vs 30 min)

    Returns:
        {
            "available": bool,
            "scheduled_date": str,
            "scheduled_start": str,
            "scheduled_end": str,
            "duration_minutes": int,
            "conflicts": [
                {
                    "booking_id": str,
                    "scheduled_start": str,
                    "scheduled_end": str,
                    "team_id": str | None,
                    "status": str,
                    "reason": "overlap" | "travel_buffer",
                    "overlap_minutes": int (if overlap),
                    "gap_minutes": int (if travel_buffer),
                    "zip_code": str | None,
                }
            ],
            "alternative_suggestions": [...]  # TODO backlog
        }
    """
    date_obj = _coerce_date(scheduled_date)
    start_obj = _coerce_time(scheduled_start)
    duration = duration_minutes or _DEFAULT_DURATION_MIN
    end_obj = _compute_end(start_obj, duration)

    # Query bookings on this date (same team if team_id given, else all teams)
    query = """
        SELECT
            b.id,
            b.scheduled_start,
            b.scheduled_end,
            b.estimated_duration_minutes,
            b.team_id,
            b.status,
            b.zip_code
        FROM cleaning_bookings b
        WHERE b.business_id = $1
          AND b.scheduled_date = $2::date
          AND b.status = ANY($3::text[])
    """
    params: list[Any] = [business_id, date_obj, list(_ACTIVE_STATUSES)]

    if team_id is not None:
        query += " AND b.team_id = $4"
        params.append(team_id)

    query += " ORDER BY b.scheduled_start NULLS LAST"

    rows = await db.pool.fetch(query, *params)

    conflicts: list[dict[str, Any]] = []
    candidate_start_min = _minutes(start_obj)
    candidate_end_min = _minutes(end_obj)

    for row in rows:
        existing_start = row["scheduled_start"]
        existing_end = row["scheduled_end"]
        if existing_start is None:
            continue
        if existing_end is None:
            existing_dur = row["estimated_duration_minutes"] or _DEFAULT_DURATION_MIN
            existing_end = _compute_end(existing_start, existing_dur)

        existing_start_min = _minutes(existing_start)
        existing_end_min = _minutes(existing_end)

        # Direct overlap: candidate ends after existing starts AND candidate starts before existing ends
        if candidate_end_min > existing_start_min and candidate_start_min < existing_end_min:
            overlap = min(candidate_end_min, existing_end_min) - max(candidate_start_min, existing_start_min)
            conflicts.append({
                "booking_id": str(row["id"]),
                "scheduled_start": str(existing_start),
                "scheduled_end": str(existing_end),
                "team_id": str(row["team_id"]) if row["team_id"] else None,
                "status": row["status"],
                "reason": "overlap",
                "overlap_minutes": overlap,
                "zip_code": row["zip_code"],
            })
            continue

        # Travel buffer check (only for same team)
        if team_id is not None:
            existing_zip = row["zip_code"] or ""
            same_zip = bool(existing_zip and client_zip and existing_zip == client_zip)
            required_buffer = _TRAVEL_BUFFER_SAME_ZIP if same_zip else _TRAVEL_BUFFER_DIFF_ZIP

            # If existing is immediately before candidate
            if existing_end_min <= candidate_start_min:
                gap = candidate_start_min - existing_end_min
                if gap < required_buffer:
                    conflicts.append({
                        "booking_id": str(row["id"]),
                        "scheduled_start": str(existing_start),
                        "scheduled_end": str(existing_end),
                        "team_id": str(row["team_id"]) if row["team_id"] else None,
                        "status": row["status"],
                        "reason": "travel_buffer",
                        "gap_minutes": gap,
                        "required_buffer_minutes": required_buffer,
                        "same_zip": same_zip,
                        "zip_code": existing_zip or None,
                    })
            # If existing is immediately after candidate
            elif existing_start_min >= candidate_end_min:
                gap = existing_start_min - candidate_end_min
                if gap < required_buffer:
                    conflicts.append({
                        "booking_id": str(row["id"]),
                        "scheduled_start": str(existing_start),
                        "scheduled_end": str(existing_end),
                        "team_id": str(row["team_id"]) if row["team_id"] else None,
                        "status": row["status"],
                        "reason": "travel_buffer",
                        "gap_minutes": gap,
                        "required_buffer_minutes": required_buffer,
                        "same_zip": same_zip,
                        "zip_code": existing_zip or None,
                    })

    available = len([c for c in conflicts if c["reason"] == "overlap"]) == 0

    logger.info(
        "availability_service: business=%s date=%s start=%s dur=%s team=%s "
        "available=%s conflicts=%d",
        business_id, date_obj, start_obj, duration, team_id, available, len(conflicts),
    )

    return {
        "available": available,
        "scheduled_date": date_obj.isoformat(),
        "scheduled_start": start_obj.strftime("%H:%M"),
        "scheduled_end": end_obj.strftime("%H:%M"),
        "duration_minutes": duration,
        "team_id": str(team_id) if team_id else None,
        "conflicts": conflicts,
    }
