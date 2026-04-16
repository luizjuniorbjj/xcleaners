"""
Xcleaners — Booking Service (pricing integration)

Thin helper that bridges pricing_engine (Task 2) with booking creation
(Task 6). When a booking moves from draft to scheduled/confirmed, we:

  1. Fetch service metadata (tier/BR/BA — carries formula inputs).
  2. Invoke pricing_engine.calculate_booking_price passing booking's
     scheduled_date (F-001: historical tax correctness).
  3. Insert cleaning_bookings with full pricing columns + price_snapshot JSONB.
  4. Insert cleaning_booking_extras rows (flat, snapshotted prices).

Consumers:
  - POST /schedule/generate (recurring bookings) — schedule.py
  - Tests/integration harness — tests/test_pricing_engine.py

Decisions captured (ADR-001):
  - D2: price_snapshot is immutable after write — owner must explicitly
    click "Recalculate" in UI to overwrite it.
  - D6/D7: canonical order + tax on liquid base — delegated to engine.

Author: @dev (Neo), 2026-04-16 (Sprint Plan Fase C, Sessão C1)
"""

from __future__ import annotations

import json
import logging
from datetime import date as date_cls, datetime, time as time_cls, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

from app.database import Database
from app.modules.cleaning.services._type_helpers import to_date, to_time
from app.modules.cleaning.services.pricing_engine import (
    PriceBreakdown,
    PricingConfigError,
    breakdown_to_jsonb,
    calculate_booking_price,
)


logger = logging.getLogger("xcleaners.booking_service")


_DEFAULT_TIER = "basic"
_DEFAULT_DURATION_MIN = 120


async def _fetch_service_tier(db: Database, service_id: UUID | str) -> str:
    """Read service.tier; fallback to 'basic' when NULL (pre-migration 021 services)."""
    row = await db.pool.fetchrow(
        "SELECT tier FROM cleaning_services WHERE id = $1",
        service_id,
    )
    if row is None or not row["tier"]:
        return _DEFAULT_TIER
    return row["tier"]


def _coerce_date(value: date_cls | str) -> date_cls:
    if isinstance(value, date_cls) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    return date_cls.fromisoformat(str(value)[:10])


def _coerce_time(value: time_cls | str | None) -> time_cls | None:
    if value is None:
        return None
    if isinstance(value, time_cls):
        return value
    s = str(value)
    if len(s) == 5:
        s += ":00"
    return time_cls.fromisoformat(s)


def _compute_scheduled_end(
    scheduled_date: date_cls,
    start: time_cls | None,
    duration_minutes: int | None,
) -> time_cls | None:
    if start is None:
        return None
    duration = duration_minutes or _DEFAULT_DURATION_MIN
    anchor = datetime.combine(scheduled_date, start)
    return (anchor + timedelta(minutes=duration)).time()


async def create_booking_with_pricing(
    db: Database,
    *,
    business_id: UUID | str,
    client_id: UUID | str,
    service_id: UUID | str,
    scheduled_date: date_cls | str,
    scheduled_start: time_cls | str,
    scheduled_end: time_cls | str | None = None,
    estimated_duration_minutes: int | None = None,
    team_id: UUID | str | None = None,
    recurring_schedule_id: UUID | str | None = None,
    tier: str | None = None,
    extras: list[dict[str, Any]] | None = None,
    frequency_id: UUID | str | None = None,
    adjustment_amount: Decimal | int | float | str = Decimal("0"),
    adjustment_reason: str | None = None,
    location_id: UUID | str | None = None,
    source: str = "manual",
    status: str = "scheduled",
    address_line1: str | None = None,
    special_instructions: str | None = None,
    access_instructions: str | None = None,
) -> dict[str, Any]:
    """
    Create a booking with pricing engine integration.

    Runs pricing_engine.calculate_booking_price() first (passing
    scheduled_date for F-001 tax correctness), then inserts the booking
    with full pricing columns + price_snapshot JSONB + extras.

    Returns:
        {
            "booking_id": str,
            "breakdown": PriceBreakdown,
            "extras_written": int,
        }

    Raises:
        PricingConfigError: pricing engine cannot resolve formula/service.
    """
    sched_date = _coerce_date(scheduled_date)
    sched_start = _coerce_time(scheduled_start)
    sched_end = _coerce_time(scheduled_end) or _compute_scheduled_end(
        sched_date, sched_start, estimated_duration_minutes
    )
    extras_input = extras or []

    resolved_tier = tier or await _fetch_service_tier(db, service_id)

    breakdown: PriceBreakdown = await calculate_booking_price(
        business_id=business_id,
        service_id=service_id,
        tier=resolved_tier,
        extras=extras_input,
        frequency_id=frequency_id,
        adjustment_amount=adjustment_amount,
        adjustment_reason=adjustment_reason,
        location_id=location_id,
        scheduled_date=sched_date,
        db=db,
    )

    booking_id = await db.pool.fetchval(
        """
        INSERT INTO cleaning_bookings (
            business_id, client_id, service_id, recurring_schedule_id,
            scheduled_date, scheduled_start, scheduled_end,
            estimated_duration_minutes, team_id,
            quoted_price, final_price,
            discount_amount, tax_amount,
            adjustment_amount, adjustment_reason,
            frequency_id, location_id,
            price_snapshot,
            address_line1, access_instructions, special_instructions,
            status, source
        )
        VALUES ($1, $2, $3, $4,
                $5, $6, $7,
                $8, $9,
                $10, $11,
                $12, $13,
                $14, $15,
                $16, $17,
                $18::jsonb,
                $19, $20, $21,
                $22, $23)
        RETURNING id
        """,
        business_id, client_id, service_id, recurring_schedule_id,
        sched_date, sched_start, sched_end,
        estimated_duration_minutes or _DEFAULT_DURATION_MIN, team_id,
        breakdown["final_amount"], breakdown["final_amount"],
        breakdown["discount_amount"], breakdown["tax_amount"],
        breakdown["adjustment_amount"], breakdown["adjustment_reason"],
        frequency_id, location_id,
        breakdown_to_jsonb(breakdown),
        address_line1, access_instructions, special_instructions,
        status, source,
    )

    extras_written = 0
    for e in breakdown.get("extras", []):
        await db.pool.execute(
            """
            INSERT INTO cleaning_booking_extras
                (booking_id, extra_id, name_snapshot, price_snapshot, qty)
            VALUES ($1, $2, $3, $4, $5)
            """,
            booking_id,
            UUID(e["extra_id"]) if e.get("extra_id") else None,
            e["name"],
            e["price"],
            e["qty"],
        )
        extras_written += 1

    logger.info(
        "booking_service: created booking=%s final=%s extras=%d tier=%s override=%s",
        booking_id,
        breakdown["final_amount"],
        extras_written,
        resolved_tier,
        breakdown["override_applied"],
    )

    return {
        "booking_id": str(booking_id),
        "breakdown": breakdown,
        "extras_written": extras_written,
    }


async def recalculate_booking_snapshot(
    db: Database,
    *,
    booking_id: UUID | str,
    recalculated_by: UUID | str | None = None,
) -> dict[str, Any]:
    """
    Explicit recalculate — overrides immutable snapshot (ADR-001 D2).

    Fetches booking inputs, re-runs pricing_engine using the booking's
    persisted scheduled_date, frequency_id, location_id, adjustment_amount,
    and current extras (from cleaning_booking_extras). Overwrites
    price_snapshot + final_price + tax/discount columns.

    UI MUST warn owner before invoking this — snapshot is designed to be
    immutable for audit purposes.

    Returns:
        {"booking_id": str, "breakdown": PriceBreakdown, "previous_final": Decimal}
    """
    row = await db.pool.fetchrow(
        """
        SELECT id, business_id, service_id, scheduled_date,
               frequency_id, location_id,
               adjustment_amount, adjustment_reason,
               final_price, status
        FROM cleaning_bookings
        WHERE id = $1
        """,
        booking_id,
    )
    if row is None:
        raise PricingConfigError(f"Booking not found: {booking_id}")
    if row["status"] in ("completed", "cancelled", "no_show"):
        raise PricingConfigError(
            f"Cannot recalculate booking in terminal status '{row['status']}'."
        )

    extra_rows = await db.pool.fetch(
        """
        SELECT extra_id, qty
        FROM cleaning_booking_extras
        WHERE booking_id = $1 AND extra_id IS NOT NULL
        """,
        booking_id,
    )
    extras_input = [
        {"extra_id": r["extra_id"], "qty": r["qty"]} for r in extra_rows
    ]

    tier = await _fetch_service_tier(db, row["service_id"])

    breakdown = await calculate_booking_price(
        business_id=row["business_id"],
        service_id=row["service_id"],
        tier=tier,
        extras=extras_input,
        frequency_id=row["frequency_id"],
        adjustment_amount=row["adjustment_amount"] or Decimal("0"),
        adjustment_reason=row["adjustment_reason"],
        location_id=row["location_id"],
        scheduled_date=row["scheduled_date"],
        db=db,
    )

    await db.pool.execute(
        """
        UPDATE cleaning_bookings
        SET final_price = $2,
            quoted_price = $2,
            discount_amount = $3,
            tax_amount = $4,
            price_snapshot = $5::jsonb,
            updated_at = NOW()
        WHERE id = $1
        """,
        booking_id,
        breakdown["final_amount"],
        breakdown["discount_amount"],
        breakdown["tax_amount"],
        breakdown_to_jsonb(breakdown),
    )

    logger.info(
        "booking_service: recalculated booking=%s prev=%s new=%s by=%s",
        booking_id, row["final_price"], breakdown["final_amount"], recalculated_by,
    )

    return {
        "booking_id": str(booking_id),
        "breakdown": breakdown,
        "previous_final": row["final_price"],
    }
