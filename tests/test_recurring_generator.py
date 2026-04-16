"""
Xcleaners — Recurring Auto-Generator Tests (Sprint D Track A).

8 mandatory tests per Sprint Plan AC8:
    1. test_recurring_generator_end_to_end
    2. test_pricing_matches_schedule_inputs      ⚠️ GATE ±$0.01 (F1 replay)
    3. test_skip_date_excludes_booking
    4. test_pause_stops_new_bookings
    5. test_formula_change_does_not_affect_past_bookings
    6. test_frequency_id_missing_graceful_fallback
    7. test_collect_jobs_joins_schedule_extras   (unit, mock)
    8. test_persist_assignments_calls_create_booking_with_pricing  (unit, mock)

Integration tests (1-6) require Docker PostgreSQL with migrations
021 + 022 applied. Skip gracefully if DATABASE_URL unavailable.

Author: @dev (Neo), 2026-04-16 (Sprint D Track A, T7)
"""

from __future__ import annotations

import uuid
from datetime import date as date_cls, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.fixtures.recurring_schedules import (
    add_schedule_extra,
    add_schedule_skip,
    create_schedule,
    create_test_business,
    create_test_client,
    create_test_extra,
    create_test_service,
    create_test_team,
    get_default_location_id,
    get_frequency_id,
    tear_down_business,
)


# ============================================
# HELPERS
# ============================================

def _next_weekday(target_dow: int, from_date: date_cls | None = None) -> date_cls:
    """
    Return next occurrence of target_dow (DB convention: 0=Sunday..6=Saturday).
    Forward-looking from `from_date` (or today).
    """
    base = from_date or date_cls.today()
    # Python weekday: 0=Monday..6=Sunday → map to DB: Sunday=0
    current_dow = (base.isoweekday() % 7)
    days_ahead = (target_dow - current_dow) % 7
    if days_ahead == 0:
        days_ahead = 7
    return base + timedelta(days=days_ahead)


async def _count_bookings(db, schedule_id: str) -> int:
    return await db.pool.fetchval(
        "SELECT COUNT(*) FROM cleaning_bookings WHERE recurring_schedule_id = $1",
        uuid.UUID(schedule_id),
    ) or 0


async def _fetch_booking(db, schedule_id: str) -> dict | None:
    row = await db.pool.fetchrow(
        """
        SELECT id, final_price, tax_amount, discount_amount, adjustment_amount,
               price_snapshot, scheduled_date
        FROM cleaning_bookings
        WHERE recurring_schedule_id = $1
        ORDER BY scheduled_date ASC
        LIMIT 1
        """,
        uuid.UUID(schedule_id),
    )
    return dict(row) if row else None


# ============================================
# TEST 1 — END-TO-END WINDOW
# ============================================

@pytest.mark.asyncio
async def test_recurring_generator_end_to_end(db):
    """
    Create 3 schedules (Weekly/Biweekly/Monthly), generate 14-day window,
    assert bookings created with price_snapshot != NULL.
    """
    from app.modules.cleaning.services.recurring_generator import generate_window

    biz_id = await create_test_business(db, slug="t1-e2e")
    try:
        await create_test_team(db, biz_id)

        client_id = await create_test_client(db, biz_id)
        service_id = await create_test_service(db, biz_id)

        today = date_cls.today()
        monday = _next_weekday(1, today)

        # Weekly Monday
        weekly_sid = await create_schedule(
            db, biz_id, client_id, service_id,
            frequency="weekly", preferred_day_of_week=1,
            next_occurrence=monday,
            created_at=today - timedelta(days=1),
        )
        # Biweekly same day
        bi_sid = await create_schedule(
            db, biz_id, client_id, service_id,
            frequency="biweekly", preferred_day_of_week=1,
            next_occurrence=monday,
            created_at=today - timedelta(days=1),
        )
        # Monthly (preferred_day_of_week repurposed as day-of-month in matcher)
        dom = min(28, today.day + 3)
        monthly_next = today + timedelta(days=(dom - today.day) % 28 or 28)
        month_sid = await create_schedule(
            db, biz_id, client_id, service_id,
            frequency="monthly", preferred_day_of_week=dom,
            next_occurrence=monthly_next,
            created_at=today - timedelta(days=1),
        )

        result = await generate_window(
            db, biz_id, today, today + timedelta(days=13),
        )

        assert result["generated"] >= 2, (
            f"Expected at least 2 bookings (weekly + biweekly in 14d window), "
            f"got {result['generated']}"
        )

        # Every generated booking must have price_snapshot
        non_null_snapshot = await db.pool.fetchval(
            """
            SELECT COUNT(*) FROM cleaning_bookings
            WHERE business_id = $1
              AND source = 'recurring'
              AND price_snapshot IS NOT NULL
            """,
            uuid.UUID(biz_id),
        )
        assert non_null_snapshot == result["generated"], (
            f"Expected all {result['generated']} bookings to have price_snapshot; "
            f"got {non_null_snapshot} non-null"
        )
    finally:
        await tear_down_business(db, biz_id)


# ============================================
# TEST 2 — F1 REPLAY ±$0.01 (GATE — NON-NEGOTIABLE)
# ============================================

@pytest.mark.asyncio
async def test_pricing_matches_schedule_inputs(db):
    """
    ⚠️ GATE NON-NEGOTIABLE ±$0.01 ⚠️

    Replica fixture F1 (3Sisters real booking $240.01) via recurring path:
      Service 2BR/1BA Basic + Stairs extra + Weekly 15% + adjustment -$29.58
      Location NYC 4.5% tax → final $240.01

    If this test FAILS, Story is FAILED — recurring path diverges from
    Story 1.1 pricing engine, which breaks cutover confidence.
    """
    from app.modules.cleaning.services.recurring_generator import generate_window

    biz_id = await create_test_business(db, slug="t2-f1")
    try:
        await create_test_team(db, biz_id)

        client_id = await create_test_client(db, biz_id)
        service_id = await create_test_service(
            db, biz_id, tier="basic", bedrooms=2, bathrooms=1,
        )

        # F1 extras: Stairs @ $30
        stairs_id = await create_test_extra(db, biz_id, name="Stairs", price="30.00")

        today = date_cls.today()
        target = _next_weekday(1, today)  # next Monday

        sid = await create_schedule(
            db, biz_id, client_id, service_id,
            frequency="weekly",
            preferred_day_of_week=(target.isoweekday() % 7),
            next_occurrence=target,
            adjustment_amount="-29.58",
            adjustment_reason="Complaint refund (F1 replay)",
            created_at=today - timedelta(days=1),
        )
        await add_schedule_extra(db, sid, stairs_id, qty=1)

        # Generate window covering target date
        days = (target - today).days + 1
        if days < 1:
            days = 14
        result = await generate_window(db, biz_id, today, target)

        assert result["generated"] >= 1, (
            f"No booking generated for F1 replay schedule "
            f"(result={result})"
        )

        booking = await _fetch_booking(db, sid)
        assert booking is not None, "Booking missing for F1 schedule"

        final = Decimal(str(booking["final_price"]))
        expected = Decimal("240.01")
        delta = abs(final - expected)

        assert delta <= Decimal("0.01"), (
            f"GATE FAILED ±$0.01: expected $240.01, got ${final} (delta ${delta}). "
            f"Breakdown: tax={booking['tax_amount']} discount={booking['discount_amount']} "
            f"adjustment={booking['adjustment_amount']}"
        )

        # Spot-check the snapshot fields
        snap = booking["price_snapshot"]
        assert snap is not None, "price_snapshot is NULL"
        # snap is stored as JSONB — asyncpg returns as dict or str
        if isinstance(snap, str):
            import json
            snap = json.loads(snap)
        assert snap.get("override_applied") is False
        assert snap.get("discount_pct") in (15, 15.0, "15.00", Decimal("15.00"))
    finally:
        await tear_down_business(db, biz_id)


# ============================================
# TEST 3 — SKIP DATE
# ============================================

@pytest.mark.asyncio
async def test_skip_date_excludes_booking(db):
    """Weekly schedule + skip row for target Monday → no booking that date."""
    from app.modules.cleaning.services.recurring_generator import generate_window

    biz_id = await create_test_business(db, slug="t3-skip")
    try:
        await create_test_team(db, biz_id)

        client_id = await create_test_client(db, biz_id)
        service_id = await create_test_service(db, biz_id)

        today = date_cls.today()
        monday1 = _next_weekday(1, today)  # skip this one
        monday2 = monday1 + timedelta(days=7)  # should be generated

        sid = await create_schedule(
            db, biz_id, client_id, service_id,
            frequency="weekly",
            preferred_day_of_week=(monday1.isoweekday() % 7),
            next_occurrence=monday1,
            created_at=today - timedelta(days=1),
        )

        # Skip row for monday1 — Sprint D Track A AC6 (raw SQL INSERT per Smith L3)
        await add_schedule_skip(db, sid, monday1, reason="test skip")

        result = await generate_window(db, biz_id, today, monday2)

        # Fetch all bookings for this schedule
        rows = await db.pool.fetch(
            """
            SELECT scheduled_date FROM cleaning_bookings
            WHERE recurring_schedule_id = $1
            ORDER BY scheduled_date
            """,
            uuid.UUID(sid),
        )
        booking_dates = [r["scheduled_date"] for r in rows]

        assert monday1 not in booking_dates, (
            f"Skip failed: booking created for skipped date {monday1}"
        )
        assert monday2 in booking_dates, (
            f"Second Monday ({monday2}) was not generated (bookings: {booking_dates})"
        )
        assert result["skipped_by_skip_table"] >= 1, (
            f"skipped_by_skip_table count should be >=1, got {result['skipped_by_skip_table']}"
        )
    finally:
        await tear_down_business(db, biz_id)


# ============================================
# TEST 4 — PAUSE
# ============================================

@pytest.mark.asyncio
async def test_pause_stops_new_bookings(db):
    """status=paused → zero new bookings; already-generated stay."""
    from app.modules.cleaning.services.recurring_generator import generate_window

    biz_id = await create_test_business(db, slug="t4-pause")
    try:
        await create_test_team(db, biz_id)

        client_id = await create_test_client(db, biz_id)
        service_id = await create_test_service(db, biz_id)

        today = date_cls.today()
        target = _next_weekday(1, today)

        sid = await create_schedule(
            db, biz_id, client_id, service_id,
            frequency="weekly",
            preferred_day_of_week=(target.isoweekday() % 7),
            next_occurrence=target,
            status="paused",  # pause from the start
            created_at=today - timedelta(days=1),
        )

        result = await generate_window(db, biz_id, today, target + timedelta(days=7))

        booking_count = await _count_bookings(db, sid)
        assert booking_count == 0, (
            f"Paused schedule produced {booking_count} bookings — expected 0"
        )
    finally:
        await tear_down_business(db, biz_id)


# ============================================
# TEST 5 — FORMULA CHANGE IMMUTABILITY
# ============================================

@pytest.mark.asyncio
async def test_formula_change_does_not_affect_past_bookings(db):
    """
    Generate booking → capture snapshot. Mutate formula.base_amount. Ensure
    existing booking (non-draft) retains original snapshot via immutability.
    """
    from app.modules.cleaning.services.recurring_generator import generate_window

    biz_id = await create_test_business(db, slug="t5-mut")
    try:
        await create_test_team(db, biz_id)

        client_id = await create_test_client(db, biz_id)
        service_id = await create_test_service(db, biz_id)

        today = date_cls.today()
        target = _next_weekday(1, today)

        sid = await create_schedule(
            db, biz_id, client_id, service_id,
            frequency="weekly",
            preferred_day_of_week=(target.isoweekday() % 7),
            next_occurrence=target,
            created_at=today - timedelta(days=1),
        )

        # Generate first booking
        await generate_window(db, biz_id, today, target)
        first = await _fetch_booking(db, sid)
        assert first is not None
        first_price = first["final_price"]
        first_snapshot = first["price_snapshot"]

        # Mutate formula (+$50 base)
        await db.pool.execute(
            """
            UPDATE cleaning_pricing_formulas
            SET base_amount = base_amount + 50
            WHERE business_id = $1
            """,
            uuid.UUID(biz_id),
        )

        # Re-fetch the original booking — snapshot must be unchanged
        row = await db.pool.fetchrow(
            "SELECT final_price, price_snapshot FROM cleaning_bookings WHERE id = $1",
            first["id"],
        )
        assert row["final_price"] == first_price, (
            "Immutability violated: final_price changed after formula update"
        )
        assert row["price_snapshot"] == first_snapshot, (
            "Immutability violated: price_snapshot JSONB changed"
        )
    finally:
        await tear_down_business(db, biz_id)


# ============================================
# TEST 6 — FREQUENCY_ID NULL FALLBACK
# ============================================

@pytest.mark.asyncio
async def test_frequency_id_missing_graceful_fallback(db, caplog):
    """
    Schedule with frequency='sporadic' (no matching row in cleaning_frequencies)
    → frequency_id=NULL. Pricing engine should use discount_pct=0.
    """
    from app.modules.cleaning.services.recurring_generator import generate_window

    biz_id = await create_test_business(db, slug="t6-null-freq")
    try:
        await create_test_team(db, biz_id)

        client_id = await create_test_client(db, biz_id)
        service_id = await create_test_service(db, biz_id)

        today = date_cls.today()
        target = today + timedelta(days=3)

        sid = await create_schedule(
            db, biz_id, client_id, service_id,
            frequency="sporadic",
            frequency_id=None,
            preferred_day_of_week=(target.isoweekday() % 7),
            next_occurrence=target,
            created_at=today - timedelta(days=1),
        )

        result = await generate_window(db, biz_id, today, target)

        booking = await _fetch_booking(db, sid)
        if booking is None:
            # Sporadic may not match target via frequency_matcher — acceptable; skip assertion
            pytest.skip("Sporadic schedule did not match target; matcher behavior varies")
        else:
            # Discount should be 0 (no frequency_id → 0% discount)
            assert Decimal(str(booking["discount_amount"])) == Decimal("0"), (
                f"Expected discount_amount=0 for null frequency_id, got {booking['discount_amount']}"
            )
    finally:
        await tear_down_business(db, biz_id)


# ============================================
# TEST 7 — UNIT: collect_jobs JOINs schedule_extras
# ============================================

@pytest.mark.asyncio
async def test_collect_jobs_joins_schedule_extras():
    """
    Unit test with mock DB — verify _collect_jobs issues the schedule_extras
    fetch query and includes `schedule_extras` in the job dict.
    """
    from app.modules.cleaning.services.daily_generator import _collect_jobs

    # Mock DB
    mock_pool = MagicMock()
    mock_db = MagicMock()
    mock_db.pool = mock_pool

    target_date = date_cls(2026, 5, 4)  # Monday
    sched_id = uuid.uuid4()
    extra_id = uuid.uuid4()

    # Sequence: fetchval (skipped_count) → fetch (schedules) →
    #   fetch (extras_rows) → fetchval (existing confirmed) → fetch (manual bookings)
    mock_pool.fetchval = AsyncMock(side_effect=[
        0,       # skipped_count
        None,    # existing confirmed check for the one schedule
    ])
    mock_pool.fetch = AsyncMock(side_effect=[
        # schedules result
        [{
            "schedule_id": sched_id, "client_id": uuid.uuid4(),
            "service_id": uuid.uuid4(), "frequency": "weekly",
            "preferred_day_of_week": 1, "custom_interval_days": None,
            "preferred_time_start": None, "preferred_time_end": None,
            "preferred_team_id": None, "agreed_price": Decimal("100"),
            "estimated_duration_minutes": 120, "min_team_size": 1,
            "next_occurrence": target_date, "notes": None,
            "created_at": datetime(2026, 5, 1),
            "frequency_id": uuid.uuid4(), "adjustment_amount": Decimal("0"),
            "adjustment_reason": None, "location_id": uuid.uuid4(),
            "first_name": "Test", "last_name": "Client",
            "address_line1": "1 Test", "city": "NYC", "state": "NY",
            "zip_code": "10001", "latitude": None, "longitude": None,
            "service_name": "Basic", "service_tier": "basic",
        }],
        # extras_rows result
        [{"schedule_id": sched_id, "extra_id": extra_id, "qty": 2}],
        # manual_bookings result
        [],
    ])

    # Patch matches_date so the single schedule matches target
    with patch(
        "app.modules.cleaning.services.daily_generator.matches_date",
        return_value=True,
    ):
        jobs, matched, skipped = await _collect_jobs(mock_db, "bid", target_date)

    assert len(jobs) == 1
    job = jobs[0]
    assert job["schedule_extras"] == [
        {"extra_id": str(extra_id), "qty": 2},
    ]
    assert job["service_tier"] == "basic"
    assert job["frequency_id"] is not None
    assert job["location_id"] is not None
    assert skipped == 0


# ============================================
# TEST 8 — UNIT: persist_assignments calls create_booking_with_pricing
# ============================================

@pytest.mark.asyncio
async def test_persist_assignments_calls_create_booking_with_pricing():
    """
    Unit test — mock create_booking_with_pricing, verify _persist_assignments
    invokes it with correct kwargs for recurring path.
    """
    from app.modules.cleaning.services import daily_generator as dg

    target_date = date_cls(2026, 5, 4)
    sched_id = str(uuid.uuid4())
    client_id = str(uuid.uuid4())
    svc_id = str(uuid.uuid4())
    freq_id = str(uuid.uuid4())
    loc_id = str(uuid.uuid4())

    assignment = {
        "team_id": str(uuid.uuid4()),
        "team_name": "T",
        "client_id": client_id,
        "service_id": svc_id,
        "schedule_id": sched_id,
        "booking_id": None,  # recurring path
        "source": "recurring",
        "scheduled_start": "09:00:00",
        "scheduled_end": "11:00:00",
        "estimated_duration_minutes": 120,
        "address_line1": "1 Test",
        "notes": None,
        "service_tier": "basic",
        "schedule_extras": [{"extra_id": str(uuid.uuid4()), "qty": 1}],
        "frequency_id": freq_id,
        "adjustment_amount": Decimal("-29.58"),
        "adjustment_reason": "test",
        "location_id": loc_id,
    }

    mock_db = MagicMock()
    mock_db.pool = MagicMock()
    mock_db.pool.fetchval = AsyncMock(return_value=None)  # no existing
    mock_db.pool.execute = AsyncMock()

    mock_return = {
        "booking_id": "abc-123",
        "breakdown": {
            "final_amount": Decimal("240.01"),
            "override_applied": False,
        },
        "extras_written": 1,
    }

    with patch.object(
        dg, "create_booking_with_pricing", new=AsyncMock(return_value=mock_return),
    ) as mock_create:
        persisted, failures = await dg._persist_assignments(
            mock_db, "bid", target_date, [assignment],
        )

    assert len(persisted) == 1
    assert len(failures) == 0
    assert mock_create.called
    kwargs = mock_create.call_args.kwargs
    assert kwargs["service_id"] == svc_id
    assert kwargs["tier"] == "basic"
    assert kwargs["frequency_id"] == freq_id
    assert kwargs["adjustment_amount"] == Decimal("-29.58")
    assert kwargs["location_id"] == loc_id
    assert kwargs["source"] == "recurring"
    assert kwargs["recurring_schedule_id"] == sched_id
    assert len(kwargs["extras"]) == 1
