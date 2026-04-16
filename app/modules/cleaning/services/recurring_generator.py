"""
Xcleaners — Recurring Generator (Sprint D Track A).

Orchestrates a multi-day window of daily schedule generation for recurring
bookings. Iterates daily_generator.generate_daily_schedule for each date in
[start_date, end_date] and aggregates results.

Used by:
  - Cron-triggered endpoint POST /api/v1/clean/internal/recurring/generate-window
  - Manual admin trigger scripts (scripts/trigger_recurring.sh)

References:
  - ADR-002 Decision 5 (Cron daily 02:00 UTC, 14-day look-ahead window)
  - Sprint Plan Track A AC5

Author: @dev (Neo), 2026-04-16 (Sprint D Track A, T4)
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any
from uuid import UUID

from app.database import Database
from app.modules.cleaning.services.daily_generator import (
    generate_daily_schedule,
)


logger = logging.getLogger("xcleaners.recurring_generator")


async def generate_window(
    db: Database,
    business_id: UUID | str,
    start_date: date,
    end_date: date,
) -> dict[str, Any]:
    """
    Generate recurring bookings across a date window.

    Iterates daily_generator.generate_daily_schedule for each date in
    [start_date, end_date] inclusive. Each daily call:
      - Collects recurring schedules matching that date (respecting skip rows)
      - Delegates booking creation to booking_service.create_booking_with_pricing
        via daily_generator._persist_assignments (Track A AC2)
      - Returns per-day summary with pricing_failures list

    Aggregates window-level totals for caller (endpoint response, cron log).

    Args:
        db: Database instance
        business_id: UUID of business to process
        start_date: inclusive window start (today)
        end_date: inclusive window end (today + 13 for 14-day window)

    Returns:
        {
            "generated": int,                    # total bookings created across window
            "skipped_by_skip_table": int,        # sum of schedules filtered by cleaning_schedule_skips
            "pricing_failures": [                # schedules where pricing_engine raised error
                {"schedule_id": str, "date": str, "reason": str},
                ...
            ],
            "unassigned": int,                   # schedules matched but no team available
            "conflicts": int,                    # travel/overlap conflicts detected
            "summary": {
                "window_days": int,
                "business_id": str,
                "start_date": str,
                "end_date": str,
                "total_schedules_scanned": int,  # across all days (may double-count)
            }
        }
    """
    if end_date < start_date:
        raise ValueError(
            f"end_date ({end_date}) must be >= start_date ({start_date})"
        )

    bid = str(business_id)
    window_days = (end_date - start_date).days + 1

    logger.info(
        "[RECURRING] Starting window %s → %s (%d days) for business=%s",
        start_date.isoformat(),
        end_date.isoformat(),
        window_days,
        bid,
    )

    generated = 0
    skipped_by_skip_table = 0
    pricing_failures: list[dict[str, Any]] = []
    unassigned_total = 0
    conflict_total = 0
    schedules_scanned = 0

    current = start_date
    while current <= end_date:
        try:
            day_result = await generate_daily_schedule(db, bid, current)
        except Exception as exc:
            logger.exception(
                "[RECURRING] generate_daily_schedule failed for business=%s date=%s: %s",
                bid,
                current.isoformat(),
                exc,
            )
            pricing_failures.append({
                "schedule_id": None,
                "date": current.isoformat(),
                "reason": f"daily_generator exception: {exc}",
            })
            current += timedelta(days=1)
            continue

        # generate_daily_schedule may return {"error": True, "message": "..."}
        # when Redis lock cannot be acquired (concurrent run) — record as skip-like
        if day_result.get("error"):
            logger.warning(
                "[RECURRING] Day %s skipped by daily_generator: %s",
                current.isoformat(),
                day_result.get("message"),
            )
            current += timedelta(days=1)
            continue

        summary = day_result.get("summary", {})
        day_assigned = summary.get("assigned_count", 0) or 0
        day_unassigned = summary.get("unassigned_count", 0) or 0
        day_conflicts = summary.get("conflict_count", 0) or 0
        day_total_jobs = summary.get("total_jobs", 0) or 0

        # Track A AC3/AC6/AC7: daily_generator exposes these via summary
        day_skipped = summary.get("skipped_by_skip_table", 0) or 0
        day_failures = day_result.get("pricing_failures", []) or []

        generated += day_assigned
        unassigned_total += day_unassigned
        conflict_total += day_conflicts
        skipped_by_skip_table += day_skipped
        schedules_scanned += day_total_jobs

        # Tag each pricing_failure with the date for window-level traceability
        for fail in day_failures:
            pricing_failures.append({
                "schedule_id": fail.get("schedule_id"),
                "date": current.isoformat(),
                "reason": fail.get("reason", "unknown"),
            })

        logger.debug(
            "[RECURRING] Day %s: generated=%d unassigned=%d conflicts=%d skipped=%d failures=%d",
            current.isoformat(),
            day_assigned,
            day_unassigned,
            day_conflicts,
            day_skipped,
            len(day_failures),
        )

        current += timedelta(days=1)

    result = {
        "generated": generated,
        "skipped_by_skip_table": skipped_by_skip_table,
        "pricing_failures": pricing_failures,
        "unassigned": unassigned_total,
        "conflicts": conflict_total,
        "summary": {
            "window_days": window_days,
            "business_id": bid,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "total_schedules_scanned": schedules_scanned,
        },
    }

    logger.info(
        "[RECURRING] Window complete: generated=%d unassigned=%d conflicts=%d skipped=%d failures=%d (scanned=%d)",
        generated,
        unassigned_total,
        conflict_total,
        skipped_by_skip_table,
        len(pricing_failures),
        schedules_scanned,
    )

    return result
