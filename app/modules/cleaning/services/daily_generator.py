"""
Xcleaners v3 — Daily Schedule Generator (S2.4).

THE CORE OF XCLEANERS.

Orchestrates the 5-step schedule generation algorithm:
  1. COLLECT eligible jobs for target_date
  2. COMPUTE team availability
  3. SCORE and ASSIGN teams to jobs
  4. APPLY travel buffers and detect conflicts
  5. PERSIST bookings and cache results

Uses distributed Redis lock to prevent concurrent generation.
Idempotent: re-running replaces unconfirmed bookings, preserves confirmed ones.
"""

import json
import logging
import os
from datetime import date, time, timedelta
from decimal import Decimal
from typing import Optional

from app.database import Database
from app.redis_client import get_redis
from app.modules.cleaning.services.frequency_matcher import matches_date
from app.modules.cleaning.services.team_assignment_scorer import (
    score_team_for_job,
    get_last_team_for_client,
)
from app.modules.cleaning.services.conflict_resolver import (
    detect_all_conflicts,
)
from app.modules.cleaning.services.recurrence_engine import bulk_advance
from app.modules.cleaning.services._type_helpers import to_time
# Sprint D Track A (AC2): delegate booking persistence to booking_service so
# recurring bookings pass through pricing_engine (formula + extras + discount
# + adjustment + tax + snapshot). Closes Smith C1 M2 + R9.
from app.modules.cleaning.services.booking_charge_service import (
    try_auto_charge_booking,
)
from app.modules.cleaning.services.booking_service import (
    create_booking_with_pricing,
)
from app.modules.cleaning.services.pricing_engine import PricingConfigError

logger = logging.getLogger("xcleaners.daily_generator")

# Configurable travel buffer (minutes)
TRAVEL_BUFFER_DIFF_ZIP = int(os.environ.get("CLEANING_TRAVEL_BUFFER_MINUTES", "30"))
TRAVEL_BUFFER_SAME_ZIP = 15

# Redis keys and TTLs
LOCK_TTL_SECONDS = 60
SCHEDULE_CACHE_TTL = 86400  # 24 hours


# ============================================
# DISTRIBUTED LOCK
# ============================================

async def _acquire_lock(business_id: str, target_date: date) -> bool:
    """Acquire Redis distributed lock for schedule generation."""
    redis = get_redis()
    if not redis:
        return True  # No Redis -> proceed without lock (dev/fallback)
    key = f"clean:{business_id}:lock:schedule:{target_date.isoformat()}"
    acquired = await redis.set(key, "1", ex=LOCK_TTL_SECONDS, nx=True)
    return bool(acquired)


async def _release_lock(business_id: str, target_date: date):
    """Release Redis distributed lock."""
    redis = get_redis()
    if not redis:
        return
    key = f"clean:{business_id}:lock:schedule:{target_date.isoformat()}"
    await redis.delete(key)


# ============================================
# STEP 1: COLLECT JOBS
# ============================================

async def _collect_jobs(
    db: Database,
    business_id: str,
    target_date: date,
) -> tuple[list[dict], list[dict], int]:
    """
    Collect all jobs to assign for target_date:
      a. Recurring schedules whose frequency matches target_date (SKIP filtered)
      b. Manual one-off bookings already created for target_date
    Excludes bookings already confirmed/in_progress for the date.

    Sprint D Track A (AC3 + AC6):
      - Exposes pricing inputs from schedule (frequency_id, adjustment_amount,
        adjustment_reason, location_id, service_tier, schedule_extras[]) so
        _persist_assignments can delegate to booking_service.create_booking_with_pricing
      - Filters out schedules with matching cleaning_schedule_skips row

    Returns:
        Tuple of (jobs, matched_schedules, skipped_by_skip_table_count)
    """
    jobs = []

    # Track A AC6: count schedules that WOULD match but have a skip for this date.
    # Observability — reported in summary + endpoint response.
    skipped_count = await db.pool.fetchval(
        """
        SELECT COUNT(*)
        FROM cleaning_client_schedules cs
        WHERE cs.business_id = $1
          AND cs.status = 'active'
          AND cs.next_occurrence IS NOT NULL
          AND cs.next_occurrence <= $2
          AND EXISTS (
              SELECT 1 FROM cleaning_schedule_skips ss
              WHERE ss.schedule_id = cs.id AND ss.skip_date = $2
          )
        """,
        business_id,
        target_date,
    ) or 0

    # a. Recurring schedules due on target_date (NOT filtered by skip)
    # Track A AC3: SELECT expanded to include pricing inputs (frequency_id,
    # adjustment_amount, adjustment_reason, location_id, service_tier).
    # Track A AC6: WHERE NOT EXISTS filters out skip dates.
    schedules = await db.pool.fetch(
        """
        SELECT
            cs.id AS schedule_id, cs.client_id, cs.service_id,
            cs.frequency, cs.preferred_day_of_week, cs.custom_interval_days,
            cs.preferred_time_start, cs.preferred_time_end,
            cs.preferred_team_id, cs.agreed_price,
            cs.estimated_duration_minutes, cs.min_team_size,
            cs.next_occurrence, cs.notes, cs.created_at,
            cs.frequency_id, cs.adjustment_amount, cs.adjustment_reason,
            cs.location_id,
            c.first_name, c.last_name,
            c.address_line1, c.city, c.state, c.zip_code,
            c.latitude, c.longitude,
            s.name AS service_name,
            s.tier AS service_tier
        FROM cleaning_client_schedules cs
        JOIN cleaning_clients c ON c.id = cs.client_id
        LEFT JOIN cleaning_services s ON s.id = cs.service_id
        WHERE cs.business_id = $1
          AND cs.status = 'active'
          AND cs.next_occurrence IS NOT NULL
          AND cs.next_occurrence <= $2
          AND NOT EXISTS (
              SELECT 1 FROM cleaning_schedule_skips ss
              WHERE ss.schedule_id = cs.id AND ss.skip_date = $2
          )
        ORDER BY cs.preferred_time_start ASC NULLS LAST
        """,
        business_id,
        target_date,
    )

    # Track A AC3: fetch schedule-level extras (template) in one query,
    # group by schedule_id in Python. Pricing_engine will snapshot these
    # into cleaning_booking_extras at booking creation time.
    schedule_ids = [str(row["schedule_id"]) for row in schedules]
    extras_by_schedule: dict[str, list[dict]] = {}
    if schedule_ids:
        extras_rows = await db.pool.fetch(
            """
            SELECT schedule_id, extra_id, qty
            FROM cleaning_client_schedule_extras
            WHERE schedule_id = ANY($1::uuid[])
            """,
            schedule_ids,
        )
        for row in extras_rows:
            sid = str(row["schedule_id"])
            extras_by_schedule.setdefault(sid, []).append({
                "extra_id": str(row["extra_id"]),
                "qty": row["qty"] or 1,
            })

    matched_schedules = []
    for row in schedules:
        sched = dict(row)
        # Run frequency matcher to double-check (next_occurrence advanced
        # prematurely can cause false positives; matcher is source of truth)
        if matches_date(sched, target_date):
            # Check if a booking already exists for this schedule + date (confirmed)
            existing = await db.pool.fetchval(
                """
                SELECT id FROM cleaning_bookings
                WHERE business_id = $1
                  AND client_id = $2
                  AND scheduled_date = $3
                  AND recurring_schedule_id = $4
                  AND status IN ('confirmed', 'in_progress', 'completed')
                """,
                business_id,
                str(sched["client_id"]),
                target_date,
                str(sched["schedule_id"]),
            )
            if existing:
                continue  # Already confirmed, skip

            schedule_id_str = str(sched["schedule_id"])

            jobs.append({
                "source": "recurring",
                "schedule_id": schedule_id_str,
                "client_id": str(sched["client_id"]),
                "service_id": str(sched["service_id"]),
                "client_name": f"{sched['first_name'] or ''} {sched['last_name'] or ''}".strip(),
                "service_name": sched["service_name"],
                "preferred_time_start": str(sched["preferred_time_start"]) if sched["preferred_time_start"] else None,
                "preferred_time_end": str(sched["preferred_time_end"]) if sched["preferred_time_end"] else None,
                "preferred_team_id": str(sched["preferred_team_id"]) if sched["preferred_team_id"] else None,
                "estimated_duration_minutes": sched["estimated_duration_minutes"] or 120,
                "min_team_size": sched["min_team_size"] or 1,
                "agreed_price": float(sched["agreed_price"]) if sched["agreed_price"] else None,
                "address_line1": sched["address_line1"],
                "city": sched["city"],
                "state": sched["state"],
                "zip_code": sched["zip_code"],
                "latitude": float(sched["latitude"]) if sched["latitude"] else None,
                "longitude": float(sched["longitude"]) if sched["longitude"] else None,
                "notes": sched["notes"],
                "priority": 1,  # Recurring = higher priority
                # Sprint D Track A — pricing inputs from schedule (AC3)
                "frequency_id": str(sched["frequency_id"]) if sched.get("frequency_id") else None,
                "adjustment_amount": sched.get("adjustment_amount") or 0,
                "adjustment_reason": sched.get("adjustment_reason"),
                "location_id": str(sched["location_id"]) if sched.get("location_id") else None,
                "service_tier": sched.get("service_tier"),
                "schedule_extras": extras_by_schedule.get(schedule_id_str, []),
            })
            matched_schedules.append(sched)

    # b. Manual one-off bookings for target_date (not yet team-assigned)
    manual_bookings = await db.pool.fetch(
        """
        SELECT
            b.id AS booking_id, b.client_id, b.service_id,
            b.scheduled_start, b.scheduled_end,
            b.estimated_duration_minutes, b.quoted_price,
            b.special_instructions, b.team_id,
            b.address_line1, b.city, b.state, b.zip_code,
            b.latitude, b.longitude,
            c.first_name, c.last_name,
            s.name AS service_name
        FROM cleaning_bookings b
        JOIN cleaning_clients c ON c.id = b.client_id
        LEFT JOIN cleaning_services s ON s.id = b.service_id
        WHERE b.business_id = $1
          AND b.scheduled_date = $2
          AND b.source = 'manual'
          AND b.team_id IS NULL
          AND b.status NOT IN ('cancelled', 'no_show', 'completed')
        ORDER BY b.scheduled_start ASC NULLS LAST
        """,
        business_id,
        target_date,
    )

    for row in manual_bookings:
        b = dict(row)
        jobs.append({
            "source": "manual",
            "booking_id": str(b["booking_id"]),
            "client_id": str(b["client_id"]),
            "service_id": str(b["service_id"]),
            "client_name": f"{b['first_name'] or ''} {b['last_name'] or ''}".strip(),
            "service_name": b["service_name"],
            "preferred_time_start": str(b["scheduled_start"]) if b["scheduled_start"] else None,
            "preferred_time_end": str(b["scheduled_end"]) if b["scheduled_end"] else None,
            "preferred_team_id": None,
            "estimated_duration_minutes": b["estimated_duration_minutes"] or 120,
            "min_team_size": 1,
            "agreed_price": float(b["quoted_price"]) if b["quoted_price"] else None,
            "address_line1": b["address_line1"],
            "city": b["city"],
            "state": b["state"],
            "zip_code": b["zip_code"],
            "latitude": float(b["latitude"]) if b["latitude"] else None,
            "longitude": float(b["longitude"]) if b["longitude"] else None,
            "notes": b["special_instructions"],
            "priority": 0,  # One-off = lower priority
        })

    # Sort: recurring first, then by preferred_time_start
    jobs.sort(key=lambda j: (
        -j["priority"],
        j["preferred_time_start"] or "99:99",
    ))

    logger.info(
        "[SCHEDULE] Collected %d jobs for %s (recurring: %d, manual: %d)",
        len(jobs), target_date, len(matched_schedules), len(manual_bookings),
    )
    # Sprint D Track A AC7: observability for skip table usage
    if skipped_count:
        logger.info(
            "[RECURRING] Scanned schedules for %s — %d filtered by cleaning_schedule_skips",
            target_date, skipped_count,
        )

    return jobs, matched_schedules, skipped_count


# ============================================
# STEP 2: COMPUTE TEAM AVAILABILITY
# ============================================

async def _compute_team_availability(
    db: Database,
    business_id: str,
    target_date: date,
) -> list[dict]:
    """
    For each active team, compute available members and time slots.

    Returns:
        List of team dicts with availability info
    """
    # DB convention: 0=Sunday..6=Saturday
    target_dow = target_date.isoweekday() % 7

    teams = await db.pool.fetch(
        """
        SELECT id, name, color, team_lead_id, max_daily_jobs,
               service_area_ids, is_active
        FROM cleaning_teams
        WHERE business_id = $1 AND is_active = true
        ORDER BY name
        """,
        business_id,
    )

    team_availability = []

    for team_row in teams:
        team = dict(team_row)
        team_id = str(team["id"])

        # Get active team assignments for this date
        members = await db.pool.fetch(
            """
            SELECT
                a.member_id, m.first_name, m.last_name, m.status, m.home_zip
            FROM cleaning_team_assignments a
            JOIN cleaning_team_members m ON m.id = a.member_id
            WHERE a.team_id = $1
              AND a.is_active = true
              AND a.effective_from <= $2
              AND (a.effective_until IS NULL OR a.effective_until >= $2)
              AND m.status = 'active'
            """,
            team["id"],
            target_date,
        )

        available_members = []

        for member_row in members:
            member_id = str(member_row["member_id"])

            # Check weekly availability for this day of week
            avail = await db.pool.fetchrow(
                """
                SELECT start_time, end_time, is_available
                FROM cleaning_team_availability
                WHERE team_member_id = $1
                  AND business_id = $2
                  AND day_of_week = $3
                  AND (effective_until IS NULL OR effective_until >= $4)
                  AND effective_from <= $4
                ORDER BY effective_from DESC
                LIMIT 1
                """,
                member_row["member_id"],
                business_id,
                target_dow,
                target_date,
            )

            # Check for exceptions on this specific date
            exception = await db.pool.fetchrow(
                """
                SELECT is_available
                FROM cleaning_team_availability
                WHERE team_member_id = $1
                  AND business_id = $2
                  AND effective_from = $3
                  AND effective_until = $3
                  AND is_available = false
                """,
                member_row["member_id"],
                business_id,
                target_date,
            )

            if exception:
                continue  # Member has PTO/sick/exception

            if avail and not avail["is_available"]:
                continue  # Member not available on this day of week

            available_members.append({
                "member_id": member_id,
                "name": f"{member_row['first_name'] or ''} {member_row['last_name'] or ''}".strip(),
                "start_time": str(avail["start_time"]) if avail and avail["start_time"] else "08:00",
                "end_time": str(avail["end_time"]) if avail and avail["end_time"] else "17:00",
            })

        # Resolve service area zip codes
        service_area_zips = []
        if team.get("service_area_ids"):
            area_rows = await db.pool.fetch(
                """
                SELECT zip_codes FROM cleaning_areas
                WHERE id = ANY($1) AND business_id = $2
                """,
                team["service_area_ids"],
                business_id,
            )
            for ar in area_rows:
                if ar["zip_codes"]:
                    service_area_zips.extend(ar["zip_codes"])

        # Get currently assigned jobs for this team on this date
        current_jobs = await db.pool.fetchval(
            """
            SELECT COUNT(*) FROM cleaning_bookings
            WHERE team_id = $1
              AND business_id = $2
              AND scheduled_date = $3
              AND status NOT IN ('cancelled', 'no_show')
            """,
            team["id"],
            business_id,
            target_date,
        )

        team_availability.append({
            "id": team_id,
            "name": team["name"],
            "color": team["color"],
            "max_daily_jobs": team["max_daily_jobs"],
            "service_area_ids": [str(x) for x in team["service_area_ids"]] if team["service_area_ids"] else [],
            "service_area_zips": service_area_zips,
            "available_members": available_members,
            "available_member_count": len(available_members),
            "total_member_count": len(members),
            "current_job_count": current_jobs or 0,
            "team_slots_start": "08:00",  # Default if no member-specific data
            "team_slots_end": "17:00",
        })

        # Compute intersection of available member time slots
        if available_members:
            starts = []
            ends = []
            for m in available_members:
                starts.append(m["start_time"])
                ends.append(m["end_time"])
            team_availability[-1]["team_slots_start"] = max(starts)  # Latest start
            team_availability[-1]["team_slots_end"] = min(ends)  # Earliest end

    logger.info(
        "[SCHEDULE] %d active teams with availability for %s",
        len(team_availability), target_date,
    )
    return team_availability


# ============================================
# STEP 3: SCORE AND ASSIGN
# ============================================

async def _score_and_assign(
    db: Database,
    business_id: str,
    target_date: date,
    jobs: list[dict],
    teams: list[dict],
) -> tuple[list[dict], list[dict]]:
    """
    For each job, score every team and assign the best fit.

    Returns:
        (assigned_jobs, unassigned_jobs)
    """
    assigned = []
    unassigned = []

    # Track assignments per team for workload and proximity
    team_assignments: dict[str, list[dict]] = {t["id"]: [] for t in teams}
    team_job_counts: dict[str, int] = {t["id"]: t["current_job_count"] for t in teams}

    # Pre-fetch existing assignments with coordinates for proximity scoring
    existing = await db.pool.fetch(
        """
        SELECT team_id, latitude, longitude, zip_code, scheduled_start,
               estimated_duration_minutes
        FROM cleaning_bookings
        WHERE business_id = $1
          AND scheduled_date = $2
          AND team_id IS NOT NULL
          AND status NOT IN ('cancelled', 'no_show')
        """,
        business_id,
        target_date,
    )
    for e in existing:
        tid = str(e["team_id"])
        if tid in team_assignments:
            team_assignments[tid].append({
                "latitude": float(e["latitude"]) if e["latitude"] else None,
                "longitude": float(e["longitude"]) if e["longitude"] else None,
                "zip_code": e["zip_code"],
                "scheduled_start": str(e["scheduled_start"]) if e["scheduled_start"] else None,
                "estimated_duration_minutes": e["estimated_duration_minutes"],
            })

    for job in jobs:
        # Get continuity data (which team last served this client)
        last_team_id = await get_last_team_for_client(
            db, business_id, job["client_id"],
        )

        # Score every team
        scores = []
        for team in teams:
            # Skip teams at capacity
            if team_job_counts.get(team["id"], 0) >= team["max_daily_jobs"]:
                continue

            # Skip teams with no available members
            if team["available_member_count"] == 0:
                continue

            result = score_team_for_job(
                team=team,
                job=job,
                existing_assignments=team_assignments.get(team["id"], []),
                existing_job_count=team_job_counts.get(team["id"], 0),
                last_team_id=last_team_id,
            )
            scores.append(result)

        # Sort by score descending
        scores.sort(key=lambda s: s["total_score"], reverse=True)

        # Try to assign to the best team
        assigned_team = None
        for score_result in scores:
            team_id = score_result["team_id"]
            team = next((t for t in teams if t["id"] == team_id), None)
            if not team:
                continue

            # Check if team has available time slot
            # (simplified: just check capacity, detailed slot checking is for future)
            if team_job_counts.get(team_id, 0) < team["max_daily_jobs"]:
                assigned_team = team
                assigned_score = score_result
                break

        if assigned_team:
            # Compute time slot
            time_start = job.get("preferred_time_start") or assigned_team["team_slots_start"]
            duration = job.get("estimated_duration_minutes", 120)

            # Parse start time and compute end
            parts = str(time_start).split(":")
            start_minutes = int(parts[0]) * 60 + int(parts[1]) if len(parts) >= 2 else 480
            end_minutes = start_minutes + duration
            time_end = f"{min(23, end_minutes // 60):02d}:{end_minutes % 60:02d}"

            assignment = {
                "team_id": assigned_team["id"],
                "team_name": assigned_team["name"],
                "team_color": assigned_team["color"],
                "client_id": job["client_id"],
                "client_name": job.get("client_name", ""),
                "service_id": job["service_id"],
                "service_name": job.get("service_name", ""),
                "schedule_id": job.get("schedule_id"),
                "booking_id": job.get("booking_id"),
                "source": job["source"],
                "scheduled_start": time_start,
                "scheduled_end": time_end,
                "estimated_duration_minutes": duration,
                "zip_code": job.get("zip_code"),
                "latitude": job.get("latitude"),
                "longitude": job.get("longitude"),
                "address_line1": job.get("address_line1"),
                "city": job.get("city"),
                "score": assigned_score["total_score"],
                "score_breakdown": assigned_score["breakdown"],
            }

            assigned.append(assignment)
            team_job_counts[assigned_team["id"]] = team_job_counts.get(assigned_team["id"], 0) + 1
            team_assignments[assigned_team["id"]].append({
                "latitude": job.get("latitude"),
                "longitude": job.get("longitude"),
                "zip_code": job.get("zip_code"),
                "scheduled_start": time_start,
                "estimated_duration_minutes": duration,
            })
        else:
            # Could not assign
            reasons = []
            if not scores:
                reasons.append("No teams available (all at capacity or no members)")
            else:
                reasons.append("No team with available time slot")
            unassigned.append({
                "client_id": job["client_id"],
                "client_name": job.get("client_name", ""),
                "service_id": job["service_id"],
                "service_name": job.get("service_name", ""),
                "schedule_id": job.get("schedule_id"),
                "booking_id": job.get("booking_id"),
                "source": job["source"],
                "reason": "; ".join(reasons),
                "preferred_time_start": job.get("preferred_time_start"),
                "estimated_duration_minutes": job.get("estimated_duration_minutes"),
            })

    logger.info(
        "[SCHEDULE] Assigned %d jobs, %d unassigned for %s",
        len(assigned), len(unassigned), target_date,
    )
    return assigned, unassigned


# ============================================
# STEP 4: TRAVEL BUFFERS + CONFLICT DETECTION
# ============================================

def _apply_travel_buffers_and_detect_conflicts(
    assigned: list[dict],
    teams: list[dict],
) -> list[dict]:
    """
    For each team's assignments, check travel buffers and detect conflicts.

    Returns:
        List of all conflicts found
    """
    all_conflicts = []

    # Group assignments by team
    by_team: dict[str, list[dict]] = {}
    for a in assigned:
        tid = a["team_id"]
        if tid not in by_team:
            by_team[tid] = []
        by_team[tid].append(a)

    for team in teams:
        tid = team["id"]
        team_assignments = by_team.get(tid, [])
        if not team_assignments:
            continue

        conflicts = detect_all_conflicts(
            team=team,
            assignments=team_assignments,
            available_members=team["available_member_count"],
            travel_buffer_same_zip=TRAVEL_BUFFER_SAME_ZIP,
            travel_buffer_diff_zip=TRAVEL_BUFFER_DIFF_ZIP,
        )
        all_conflicts.extend(conflicts)

    return all_conflicts


# ============================================
# STEP 5: PERSIST BOOKINGS
# ============================================

async def _persist_assignments(
    db: Database,
    business_id: str,
    target_date: date,
    assigned: list[dict],
) -> tuple[list[dict], list[dict]]:
    """
    Create or update cleaning_bookings for all assignments.
    Idempotent: replaces unconfirmed bookings, preserves confirmed ones.

    Sprint D Track A (AC2): recurring path delegates to
    booking_service.create_booking_with_pricing so every recurring booking
    passes through pricing_engine — price_snapshot + tax + discount + extras
    snapshot are all materialized correctly. Closes Smith C1 M2 + R9.

    Manual (one-off) path unchanged — manual bookings are created elsewhere
    (POST /bookings endpoint) which already integrates pricing.

    For recurring path with existing unconfirmed booking: DELETE + recreate
    (Smith L2) — guarantees fresh pricing snapshot if schedule extras/
    adjustment/frequency changed since last generation. Booking id changes,
    but no external FK references recurring-generated unconfirmed bookings.

    Returns:
        Tuple of (persisted, pricing_failures):
          - persisted: list of booking assignment dicts with booking_id set
          - pricing_failures: [{schedule_id, reason}] for schedules skipped
            due to PricingConfigError (e.g. service missing tier/BR/BA)
    """
    persisted = []
    pricing_failures: list[dict] = []

    for assignment in assigned:
        booking_id = assignment.get("booking_id")

        if booking_id:
            # Manual booking — already has pricing snapshot (created via
            # POST /bookings with booking_service). Just update team assignment.
            await db.pool.execute(
                """
                UPDATE cleaning_bookings
                SET team_id = $2, scheduled_start = $3,
                    scheduled_end = $4, status = 'scheduled',
                    updated_at = NOW()
                WHERE id = $1
                  AND status NOT IN ('confirmed', 'in_progress', 'completed')
                """,
                booking_id,
                assignment["team_id"],
                to_time(assignment["scheduled_start"]),
                to_time(assignment["scheduled_end"]),
            )
            assignment["booking_id"] = booking_id
            persisted.append(assignment)
            continue

        # Recurring schedule — delegate to booking_service (Track A AC2)
        schedule_id = assignment.get("schedule_id")

        # Check for existing unconfirmed booking for this (schedule, date)
        existing = await db.pool.fetchval(
            """
            SELECT id FROM cleaning_bookings
            WHERE business_id = $1
              AND client_id = $2
              AND scheduled_date = $3
              AND recurring_schedule_id = $4
              AND status NOT IN ('confirmed', 'in_progress', 'completed')
            """,
            business_id,
            assignment["client_id"],
            target_date,
            schedule_id,
        )

        # Smith L2: delete+recreate ensures fresh pricing snapshot
        # (extras/adjustment/frequency may have changed since last generation).
        # Booking_id changes but no external FK references unconfirmed recurring
        # bookings — verified 2026-04-16 during Track A audit.
        if existing:
            await db.pool.execute(
                "DELETE FROM cleaning_bookings WHERE id = $1",
                existing,
            )

        # Convert adjustment_amount to Decimal for pricing_engine
        raw_adj = assignment.get("adjustment_amount", 0) or 0
        try:
            adj_decimal = Decimal(str(raw_adj))
        except Exception:  # noqa: BLE001 — defensive cast
            adj_decimal = Decimal("0")

        try:
            result = await create_booking_with_pricing(
                db=db,
                business_id=business_id,
                client_id=assignment["client_id"],
                service_id=assignment["service_id"],
                scheduled_date=target_date,
                scheduled_start=to_time(assignment["scheduled_start"]),
                scheduled_end=to_time(assignment["scheduled_end"]),
                estimated_duration_minutes=assignment.get("estimated_duration_minutes"),
                team_id=assignment.get("team_id"),
                recurring_schedule_id=schedule_id,
                # Track A AC2 — pricing inputs from schedule
                tier=assignment.get("service_tier"),  # None → booking_service fetches from service
                extras=assignment.get("schedule_extras", []),
                frequency_id=assignment.get("frequency_id"),
                adjustment_amount=adj_decimal,
                adjustment_reason=assignment.get("adjustment_reason"),
                location_id=assignment.get("location_id"),
                source="recurring",
                status="scheduled",
                address_line1=assignment.get("address_line1"),
                special_instructions=assignment.get("notes"),
            )
        except PricingConfigError as exc:
            # Track A AC7: log warning, skip schedule, continue with others
            logger.warning(
                "[RECURRING] Pricing failure for schedule=%s client=%s: %s. Booking SKIPPED.",
                schedule_id,
                assignment.get("client_id"),
                exc,
            )
            pricing_failures.append({
                "schedule_id": str(schedule_id) if schedule_id else None,
                "reason": str(exc),
            })
            continue

        assignment["booking_id"] = result["booking_id"]
        # Track A AC7: observability per successful generation
        breakdown = result["breakdown"]
        logger.info(
            "[RECURRING] Generated booking=%s schedule=%s client=%s final=$%s tier=%s override=%s extras=%d",
            result["booking_id"],
            schedule_id,
            assignment["client_id"],
            breakdown["final_amount"],
            assignment.get("service_tier") or "basic",
            breakdown["override_applied"],
            result["extras_written"],
        )

        # [3S-2] Best-effort auto-charge. Never raises; gates inside the helper.
        try:
            await try_auto_charge_booking(db, result["booking_id"])
        except Exception as exc:  # noqa: BLE001 — defensive: never break booking flow
            logger.warning(
                "[RECURRING] auto-charge unexpected error for booking=%s: %s",
                result["booking_id"], exc,
            )

        persisted.append(assignment)

    logger.info(
        "[SCHEDULE] Persisted %d bookings for %s (pricing_failures: %d)",
        len(persisted), target_date, len(pricing_failures),
    )
    return persisted, pricing_failures


async def _cache_schedule(
    business_id: str,
    target_date: date,
    result: dict,
):
    """Cache generated schedule in Redis."""
    redis = get_redis()
    if not redis:
        return

    key = f"clean:{business_id}:schedule:{target_date.isoformat()}"
    try:
        await redis.set(key, json.dumps(result, default=str), ex=SCHEDULE_CACHE_TTL)
        logger.info("[SCHEDULE] Cached schedule for %s", target_date)
    except Exception as e:
        logger.warning("[SCHEDULE] Failed to cache schedule: %s", e)


async def _get_cached_schedule(
    business_id: str,
    target_date: date,
) -> Optional[dict]:
    """Get cached schedule from Redis."""
    redis = get_redis()
    if not redis:
        return None

    key = f"clean:{business_id}:schedule:{target_date.isoformat()}"
    try:
        data = await redis.get(key)
        if data:
            return json.loads(data)
    except Exception as e:
        logger.warning("[SCHEDULE] Failed to read cache: %s", e)
    return None


async def _invalidate_cache(business_id: str, target_date: date):
    """Invalidate cached schedule."""
    redis = get_redis()
    if not redis:
        return
    key = f"clean:{business_id}:schedule:{target_date.isoformat()}"
    await redis.delete(key)


# ============================================
# MAIN ORCHESTRATOR
# ============================================

async def generate_daily_schedule(
    db: Database,
    business_id: str,
    target_date: date,
) -> dict:
    """
    Generate the full daily schedule for a business.

    This is THE core algorithm of Xcleaners.

    Steps:
      1. Collect eligible jobs
      2. Compute team availability
      3. Score and assign teams
      4. Apply travel buffers and detect conflicts
      5. Persist bookings and cache results

    Returns:
        {
            assigned: [{booking_id, team_id, team_name, time_slot, ...}],
            conflicts: [{type, detail, suggestions}],
            unassigned: [{client_id, reason}],
            summary: {total_jobs, assigned_count, unassigned_count, conflict_count}
        }
    """
    # Acquire distributed lock
    if not await _acquire_lock(business_id, target_date):
        return {
            "error": True,
            "message": (
                f"Schedule generation already in progress for {target_date}. "
                "Please wait and try again."
            ),
        }

    try:
        logger.info(
            "[SCHEDULE] ========== GENERATING SCHEDULE for %s ==========",
            target_date,
        )

        # STEP 1: Collect jobs
        # Sprint D Track A: _collect_jobs now returns (jobs, matched_schedules, skipped_count)
        jobs, matched_schedules, skipped_by_skip_table = await _collect_jobs(
            db, business_id, target_date,
        )
        if not jobs:
            result = {
                "assigned": [],
                "conflicts": [],
                "unassigned": [],
                "pricing_failures": [],
                "summary": {
                    "date": target_date.isoformat(),
                    "total_jobs": 0,
                    "assigned_count": 0,
                    "unassigned_count": 0,
                    "conflict_count": 0,
                    "skipped_by_skip_table": skipped_by_skip_table,
                },
            }
            await _cache_schedule(business_id, target_date, result)
            return result

        # STEP 2: Compute team availability
        teams = await _compute_team_availability(db, business_id, target_date)
        if not teams:
            # No teams -> all jobs unassigned
            unassigned = [{
                "client_id": j["client_id"],
                "client_name": j.get("client_name", ""),
                "service_name": j.get("service_name", ""),
                "source": j["source"],
                "reason": "No active teams configured",
            } for j in jobs]
            result = {
                "assigned": [],
                "conflicts": [],
                "unassigned": unassigned,
                "pricing_failures": [],
                "summary": {
                    "date": target_date.isoformat(),
                    "total_jobs": len(jobs),
                    "assigned_count": 0,
                    "unassigned_count": len(jobs),
                    "conflict_count": 0,
                    "skipped_by_skip_table": skipped_by_skip_table,
                },
            }
            await _cache_schedule(business_id, target_date, result)
            return result

        # STEP 3: Score and assign
        assigned, unassigned = await _score_and_assign(
            db, business_id, target_date, jobs, teams,
        )

        # STEP 4: Travel buffers and conflict detection
        conflicts = _apply_travel_buffers_and_detect_conflicts(assigned, teams)

        # STEP 5a: Persist bookings
        # Sprint D Track A: returns (persisted, pricing_failures)
        persisted, pricing_failures = await _persist_assignments(
            db, business_id, target_date, assigned,
        )

        # STEP 5b: Advance next_occurrence for matched recurring schedules
        # Only advance for schedules that actually produced a booking (not
        # those that failed pricing). Otherwise a schedule with persistent
        # pricing error would silently skip all occurrences.
        successful_schedule_ids = {
            a.get("schedule_id") for a in persisted if a.get("schedule_id")
        }
        successful_matched = [
            s for s in matched_schedules
            if str(s["schedule_id"]) in successful_schedule_ids
        ]
        if successful_matched:
            await bulk_advance(db, business_id, [
                {"id": str(s["schedule_id"])} for s in successful_matched
            ], target_date)

        # Build result
        result = {
            "assigned": [{
                "booking_id": a["booking_id"],
                "team_id": a["team_id"],
                "team_name": a["team_name"],
                "team_color": a.get("team_color"),
                "client_id": a["client_id"],
                "client_name": a.get("client_name", ""),
                "service_name": a.get("service_name", ""),
                "source": a["source"],
                "time_slot": {
                    "start": a["scheduled_start"],
                    "end": a["scheduled_end"],
                    "duration_minutes": a["estimated_duration_minutes"],
                },
                "score": a.get("score"),
                "score_breakdown": a.get("score_breakdown"),
                "address": a.get("address_line1"),
                "city": a.get("city"),
                "zip_code": a.get("zip_code"),
            } for a in persisted],
            "conflicts": conflicts,
            "unassigned": unassigned,
            "pricing_failures": pricing_failures,
            "summary": {
                "date": target_date.isoformat(),
                "total_jobs": len(jobs),
                "assigned_count": len(persisted),
                "unassigned_count": len(unassigned),
                "conflict_count": len(conflicts),
                "skipped_by_skip_table": skipped_by_skip_table,
            },
        }

        # STEP 5c: Cache result
        await _cache_schedule(business_id, target_date, result)

        logger.info(
            "[SCHEDULE] ========== COMPLETE: %d assigned, %d unassigned, %d conflicts ==========",
            len(persisted), len(unassigned), len(conflicts),
        )

        return result

    finally:
        await _release_lock(business_id, target_date)


async def regenerate_daily_schedule(
    db: Database,
    business_id: str,
    target_date: date,
) -> dict:
    """
    Clear unconfirmed bookings and regenerate the schedule.
    Preserves confirmed/in_progress/completed bookings.
    """
    # Delete unconfirmed schedule-generated bookings for this date
    deleted = await db.pool.execute(
        """
        DELETE FROM cleaning_bookings
        WHERE business_id = $1
          AND scheduled_date = $2
          AND source = 'recurring'
          AND status IN ('draft', 'scheduled')
        """,
        business_id,
        target_date,
    )

    logger.info(
        "[SCHEDULE] Cleared unconfirmed bookings for %s: %s",
        target_date, deleted,
    )

    # Invalidate cache
    await _invalidate_cache(business_id, target_date)

    # Regenerate
    return await generate_daily_schedule(db, business_id, target_date)


async def get_daily_schedule(
    db: Database,
    business_id: str,
    target_date: date,
    team_id: Optional[str] = None,
) -> dict:
    """
    Get the daily schedule, grouped by team.
    Returns from cache if available, otherwise queries DB.
    """
    # Try cache first
    cached = await _get_cached_schedule(business_id, target_date)
    if cached and not team_id:
        return cached

    # Query from DB
    conditions = [
        "b.business_id = $1",
        "b.scheduled_date = $2",
        "b.status NOT IN ('cancelled', 'no_show')",
    ]
    params = [business_id, target_date]

    if team_id:
        conditions.append("b.team_id = $3")
        params.append(team_id)

    where = " AND ".join(conditions)

    rows = await db.pool.fetch(
        f"""
        SELECT
            b.id, b.client_id, b.service_id, b.team_id,
            b.scheduled_start, b.scheduled_end,
            b.estimated_duration_minutes, b.status, b.source,
            b.address_line1, b.city, b.state, b.zip_code,
            b.latitude, b.longitude, b.quoted_price,
            b.special_instructions, b.recurring_schedule_id,
            c.first_name AS client_first, c.last_name AS client_last,
            s.name AS service_name,
            t.name AS team_name, t.color AS team_color
        FROM cleaning_bookings b
        JOIN cleaning_clients c ON c.id = b.client_id
        LEFT JOIN cleaning_services s ON s.id = b.service_id
        LEFT JOIN cleaning_teams t ON t.id = b.team_id
        WHERE {where}
        ORDER BY t.name, b.scheduled_start ASC NULLS LAST
        """,
        *params,
    )

    # Group by team
    by_team: dict[str, dict] = {}
    unassigned_list = []

    for row in rows:
        booking = {
            "booking_id": str(row["id"]),
            "client_id": str(row["client_id"]),
            "client_name": f"{row['client_first'] or ''} {row['client_last'] or ''}".strip(),
            "service_id": str(row["service_id"]) if row["service_id"] else None,
            "service_name": row["service_name"],
            "scheduled_start": str(row["scheduled_start"]) if row["scheduled_start"] else None,
            "scheduled_end": str(row["scheduled_end"]) if row["scheduled_end"] else None,
            "estimated_duration_minutes": row["estimated_duration_minutes"],
            "status": row["status"],
            "source": row["source"],
            "address": row["address_line1"],
            "city": row["city"],
            "zip_code": row["zip_code"],
            "quoted_price": float(row["quoted_price"]) if row["quoted_price"] else None,
            "special_instructions": row["special_instructions"],
        }

        tid = str(row["team_id"]) if row["team_id"] else None
        if tid:
            if tid not in by_team:
                by_team[tid] = {
                    "team_id": tid,
                    "team_name": row["team_name"],
                    "team_color": row["team_color"],
                    "bookings": [],
                }
            by_team[tid]["bookings"].append(booking)
        else:
            unassigned_list.append(booking)

    return {
        "date": target_date.isoformat(),
        "teams": list(by_team.values()),
        "unassigned": unassigned_list,
        "total_bookings": len(rows),
    }


async def get_unassigned_jobs(
    db: Database,
    business_id: str,
    target_date: date,
) -> dict:
    """Get bookings without team assignment for a date."""
    rows = await db.pool.fetch(
        """
        SELECT
            b.id, b.client_id, b.service_id,
            b.scheduled_start, b.scheduled_end,
            b.estimated_duration_minutes, b.status, b.source,
            b.address_line1, b.city, b.zip_code,
            c.first_name, c.last_name,
            s.name AS service_name
        FROM cleaning_bookings b
        JOIN cleaning_clients c ON c.id = b.client_id
        LEFT JOIN cleaning_services s ON s.id = b.service_id
        WHERE b.business_id = $1
          AND b.scheduled_date = $2
          AND b.team_id IS NULL
          AND b.status NOT IN ('cancelled', 'no_show')
        ORDER BY b.scheduled_start ASC NULLS LAST
        """,
        business_id,
        target_date,
    )

    jobs = []
    for row in rows:
        jobs.append({
            "booking_id": str(row["id"]),
            "client_id": str(row["client_id"]),
            "client_name": f"{row['first_name'] or ''} {row['last_name'] or ''}".strip(),
            "service_name": row["service_name"],
            "scheduled_start": str(row["scheduled_start"]) if row["scheduled_start"] else None,
            "estimated_duration_minutes": row["estimated_duration_minutes"],
            "status": row["status"],
            "source": row["source"],
            "address": row["address_line1"],
            "city": row["city"],
            "zip_code": row["zip_code"],
        })

    return {"jobs": jobs, "total": len(jobs), "date": target_date.isoformat()}


async def assign_job_to_team(
    db: Database,
    business_id: str,
    booking_id: str,
    team_id: str,
) -> dict:
    """Manually assign a booking to a team."""
    # Verify booking exists
    booking = await db.pool.fetchrow(
        "SELECT id, scheduled_date FROM cleaning_bookings WHERE id = $1 AND business_id = $2",
        booking_id, business_id,
    )
    if not booking:
        return {"error": True, "message": "Booking not found", "status_code": 404}

    # Verify team exists
    team = await db.pool.fetchrow(
        "SELECT id, name FROM cleaning_teams WHERE id = $1 AND business_id = $2 AND is_active = true",
        team_id, business_id,
    )
    if not team:
        return {"error": True, "message": "Team not found or inactive", "status_code": 404}

    await db.pool.execute(
        """
        UPDATE cleaning_bookings
        SET team_id = $2, updated_at = NOW()
        WHERE id = $1
        """,
        booking_id,
        team_id,
    )

    # Invalidate cache for that date
    scheduled_date = booking["scheduled_date"]
    if scheduled_date:
        await _invalidate_cache(business_id, scheduled_date)

    logger.info("[SCHEDULE] Assigned booking %s to team %s", booking_id[:8], team["name"])
    return {
        "booking_id": booking_id,
        "team_id": team_id,
        "team_name": team["name"],
        "success": True,
    }


async def move_job_between_teams(
    db: Database,
    business_id: str,
    booking_id: str,
    from_team_id: str,
    to_team_id: str,
) -> dict:
    """Move a booking from one team to another (drag-and-drop support)."""
    # Verify booking
    booking = await db.pool.fetchrow(
        """
        SELECT id, team_id, scheduled_date
        FROM cleaning_bookings
        WHERE id = $1 AND business_id = $2
        """,
        booking_id, business_id,
    )
    if not booking:
        return {"error": True, "message": "Booking not found", "status_code": 404}

    current_team = str(booking["team_id"]) if booking["team_id"] else None
    if current_team != from_team_id:
        return {
            "error": True,
            "message": f"Booking is not assigned to team {from_team_id}",
            "status_code": 400,
        }

    # Verify target team
    target_team = await db.pool.fetchrow(
        "SELECT id, name FROM cleaning_teams WHERE id = $1 AND business_id = $2 AND is_active = true",
        to_team_id, business_id,
    )
    if not target_team:
        return {"error": True, "message": "Target team not found or inactive", "status_code": 404}

    await db.pool.execute(
        """
        UPDATE cleaning_bookings
        SET team_id = $2, updated_at = NOW()
        WHERE id = $1
        """,
        booking_id,
        to_team_id,
    )

    # Invalidate cache
    scheduled_date = booking["scheduled_date"]
    if scheduled_date:
        await _invalidate_cache(business_id, scheduled_date)

    logger.info(
        "[SCHEDULE] Moved booking %s from team %s to team %s",
        booking_id[:8], from_team_id[:8], target_team["name"],
    )
    return {
        "booking_id": booking_id,
        "from_team_id": from_team_id,
        "to_team_id": to_team_id,
        "to_team_name": target_team["name"],
        "success": True,
    }
