"""
Payroll Service Tests — Sprint D Track B.

Validates cleaner earnings materialization, immutability of snapshots, and
idempotent mark-paid flow.

Integration-style tests against real PostgreSQL (same pattern as
test_pricing_engine.py). Each test seeds its own business/member/booking
in fixtures and tears them down after.

Author: @dev (Neo), 2026-04-16
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

import pytest


pytest.importorskip(
    "app.modules.cleaning.services.payroll_service",
    reason="payroll_service not yet implemented.",
)

from app.modules.cleaning.services.payroll_service import (  # noqa: E402
    PayrollError,
    calculate_cleaner_earnings,
    get_cleaner_summary,
    list_earnings,
    mark_paid,
    void_earning,
)


# ===========================================================================
# Fixtures
# ===========================================================================


@pytest.fixture
async def biz(db):
    biz_id = await db.pool.fetchval(
        "INSERT INTO businesses (slug, name) "
        "VALUES ('payroll_biz_' || gen_random_uuid()::text, 'Payroll Test Biz') "
        "RETURNING id"
    )
    yield biz_id
    await db.pool.execute("DELETE FROM businesses WHERE id = $1", biz_id)


@pytest.fixture
async def cleaner_member(db, biz):
    """Team member with default 60% wage."""
    member_id = await db.pool.fetchval(
        """
        INSERT INTO cleaning_team_members
            (business_id, first_name, last_name, email, role, wage_pct, status)
        VALUES ($1, 'Test', 'Cleaner', 'cleaner@test.com', 'cleaner', 60.00, 'active')
        RETURNING id
        """,
        biz,
    )
    return member_id


@pytest.fixture
async def completed_booking(db, biz, cleaner_member):
    """Completed booking with final_price=$311.10."""
    client_id = await db.pool.fetchval(
        """
        INSERT INTO cleaning_clients (business_id, first_name, last_name, email)
        VALUES ($1, 'Test', 'Client', 'client@test.com')
        RETURNING id
        """,
        biz,
    )
    service_id = await db.pool.fetchval(
        """
        INSERT INTO cleaning_services (business_id, name, slug, tier, base_price)
        VALUES ($1, 'Test Service', 'test-svc', 'basic', 100.00)
        RETURNING id
        """,
        biz,
    )
    booking_id = await db.pool.fetchval(
        """
        INSERT INTO cleaning_bookings
            (business_id, client_id, service_id, lead_cleaner_id,
             scheduled_date, scheduled_start, estimated_duration_minutes,
             final_price, status)
        VALUES ($1, $2, $3, $4, CURRENT_DATE, '09:00', 120, 311.10, 'completed')
        RETURNING id
        """,
        biz, client_id, service_id, cleaner_member,
    )
    return booking_id


# ===========================================================================
# calculate_cleaner_earnings
# ===========================================================================


@pytest.mark.asyncio
async def test_calculate_creates_earnings_row(db, biz, cleaner_member, completed_booking):
    """Happy path: $311.10 × 60% = $186.66 net."""
    result = await calculate_cleaner_earnings(db, completed_booking)
    assert result is not None
    assert Decimal(str(result["gross_amount"])) == Decimal("311.10")
    assert Decimal(str(result["commission_pct"])) == Decimal("60.00")
    assert Decimal(str(result["net_amount"])) == Decimal("186.66")
    assert result["status"] == "pending"
    assert result["paid_at"] is None
    assert result["booking_id"] == completed_booking
    assert result["cleaner_id"] == cleaner_member


@pytest.mark.asyncio
async def test_calculate_is_idempotent(db, biz, cleaner_member, completed_booking):
    """Calling twice returns the same row, does not duplicate."""
    first = await calculate_cleaner_earnings(db, completed_booking)
    second = await calculate_cleaner_earnings(db, completed_booking)
    assert first["id"] == second["id"]
    count = await db.pool.fetchval(
        "SELECT COUNT(*) FROM cleaning_cleaner_earnings WHERE booking_id = $1",
        completed_booking,
    )
    assert count == 1


@pytest.mark.asyncio
async def test_calculate_skips_non_completed_booking(db, biz, cleaner_member):
    """status != 'completed' → None, no row created."""
    client_id = await db.pool.fetchval(
        "INSERT INTO cleaning_clients (business_id, first_name, email) "
        "VALUES ($1, 'A', 'a@b.c') RETURNING id", biz,
    )
    service_id = await db.pool.fetchval(
        "INSERT INTO cleaning_services (business_id, name, slug, tier, base_price) "
        "VALUES ($1, 'Svc', 'svc', 'basic', 100) RETURNING id", biz,
    )
    b = await db.pool.fetchval(
        """
        INSERT INTO cleaning_bookings
            (business_id, client_id, service_id, lead_cleaner_id,
             scheduled_date, scheduled_start, estimated_duration_minutes,
             final_price, status)
        VALUES ($1, $2, $3, $4, CURRENT_DATE, '09:00', 120, 200.00, 'scheduled')
        RETURNING id
        """,
        biz, client_id, service_id, cleaner_member,
    )
    result = await calculate_cleaner_earnings(db, b)
    assert result is None
    count = await db.pool.fetchval(
        "SELECT COUNT(*) FROM cleaning_cleaner_earnings WHERE booking_id = $1", b,
    )
    assert count == 0


@pytest.mark.asyncio
async def test_calculate_skips_no_lead_cleaner(db, biz):
    """No lead_cleaner_id → None (e.g. unassigned booking)."""
    client_id = await db.pool.fetchval(
        "INSERT INTO cleaning_clients (business_id, first_name, email) "
        "VALUES ($1, 'X', 'x@y.z') RETURNING id", biz,
    )
    service_id = await db.pool.fetchval(
        "INSERT INTO cleaning_services (business_id, name, slug, tier, base_price) "
        "VALUES ($1, 'S', 's', 'basic', 100) RETURNING id", biz,
    )
    b = await db.pool.fetchval(
        """
        INSERT INTO cleaning_bookings
            (business_id, client_id, service_id, scheduled_date,
             scheduled_start, estimated_duration_minutes, final_price, status)
        VALUES ($1, $2, $3, CURRENT_DATE, '09:00', 120, 150.00, 'completed')
        RETURNING id
        """,
        biz, client_id, service_id,
    )
    result = await calculate_cleaner_earnings(db, b)
    assert result is None


@pytest.mark.asyncio
async def test_calculate_snapshot_immutable_vs_wage_change(
    db, biz, cleaner_member, completed_booking,
):
    """After earnings exist, changing wage_pct on the member does NOT alter row."""
    await calculate_cleaner_earnings(db, completed_booking)

    # Owner bumps cleaner's wage to 80% AFTER booking is paid
    await db.pool.execute(
        "UPDATE cleaning_team_members SET wage_pct = 80.00 WHERE id = $1",
        cleaner_member,
    )

    # Recalc must return EXISTING row (still 60%)
    row = await calculate_cleaner_earnings(db, completed_booking)
    assert Decimal(str(row["commission_pct"])) == Decimal("60.00")
    assert Decimal(str(row["net_amount"])) == Decimal("186.66")


@pytest.mark.asyncio
async def test_calculate_raises_on_null_final_price(db, biz, cleaner_member):
    """NULL final_price → PayrollError (data bug, must not silently return)."""
    client_id = await db.pool.fetchval(
        "INSERT INTO cleaning_clients (business_id, first_name, email) "
        "VALUES ($1, 'X', 'x@y.z') RETURNING id", biz,
    )
    service_id = await db.pool.fetchval(
        "INSERT INTO cleaning_services (business_id, name, slug, tier, base_price) "
        "VALUES ($1, 'S', 's', 'basic', 100) RETURNING id", biz,
    )
    b = await db.pool.fetchval(
        """
        INSERT INTO cleaning_bookings
            (business_id, client_id, service_id, lead_cleaner_id,
             scheduled_date, scheduled_start, estimated_duration_minutes, status)
        VALUES ($1, $2, $3, $4, CURRENT_DATE, '09:00', 120, 'completed')
        RETURNING id
        """,
        biz, client_id, service_id, cleaner_member,
    )
    with pytest.raises(PayrollError, match=r"NULL final_price"):
        await calculate_cleaner_earnings(db, b)


@pytest.mark.asyncio
async def test_calculate_raises_on_missing_booking(db, biz):
    from uuid import uuid4
    with pytest.raises(PayrollError, match=r"not found"):
        await calculate_cleaner_earnings(db, uuid4())


# ===========================================================================
# list_earnings / summary
# ===========================================================================


@pytest.mark.asyncio
async def test_list_earnings_filters_by_cleaner(db, biz, cleaner_member, completed_booking):
    await calculate_cleaner_earnings(db, completed_booking)
    rows = await list_earnings(db, biz, cleaner_id=cleaner_member)
    assert len(rows) == 1
    assert rows[0]["cleaner_id"] == cleaner_member


@pytest.mark.asyncio
async def test_list_earnings_filters_by_status(db, biz, cleaner_member, completed_booking):
    await calculate_cleaner_earnings(db, completed_booking)
    pending = await list_earnings(db, biz, status="pending")
    paid = await list_earnings(db, biz, status="paid")
    assert len(pending) == 1
    assert len(paid) == 0


@pytest.mark.asyncio
async def test_list_earnings_rejects_bad_status(db, biz):
    with pytest.raises(PayrollError, match=r"invalid status"):
        await list_earnings(db, biz, status="wat")


@pytest.mark.asyncio
async def test_summary_aggregates_correctly(db, biz, cleaner_member, completed_booking):
    await calculate_cleaner_earnings(db, completed_booking)
    summary = await get_cleaner_summary(db, biz)
    assert len(summary) == 1
    row = summary[0]
    assert row["cleaner_id"] == cleaner_member
    assert row["bookings_count"] == 1
    assert Decimal(str(row["gross_total"])) == Decimal("311.10")
    assert Decimal(str(row["net_total"])) == Decimal("186.66")
    assert Decimal(str(row["pending_net"])) == Decimal("186.66")
    assert Decimal(str(row["paid_net"])) == Decimal("0.00")


# ===========================================================================
# mark_paid
# ===========================================================================


@pytest.mark.asyncio
async def test_mark_paid_happy_path(db, biz, cleaner_member, completed_booking):
    row = await calculate_cleaner_earnings(db, completed_booking)
    result = await mark_paid(db, biz, [row["id"]], "CHK-12345")
    assert result["updated"] == 1
    assert result["skipped_already_paid"] == 0

    # Verify DB state
    after = await db.pool.fetchrow(
        "SELECT status, paid_at, payout_ref FROM cleaning_cleaner_earnings WHERE id = $1",
        row["id"],
    )
    assert after["status"] == "paid"
    assert after["paid_at"] is not None
    assert after["payout_ref"] == "CHK-12345"


@pytest.mark.asyncio
async def test_mark_paid_idempotent_same_ref(db, biz, cleaner_member, completed_booking):
    """Calling twice with same payout_ref → second call is a no-op."""
    row = await calculate_cleaner_earnings(db, completed_booking)
    r1 = await mark_paid(db, biz, [row["id"]], "CHK-999")
    r2 = await mark_paid(db, biz, [row["id"]], "CHK-999")
    assert r1["updated"] == 1
    assert r2["updated"] == 0
    assert r2["skipped_already_paid"] == 1


@pytest.mark.asyncio
async def test_mark_paid_conflicts_on_different_ref(db, biz, cleaner_member, completed_booking):
    row = await calculate_cleaner_earnings(db, completed_booking)
    await mark_paid(db, biz, [row["id"]], "CHK-001")
    with pytest.raises(PayrollError, match=r"already paid"):
        await mark_paid(db, biz, [row["id"]], "CHK-002")


@pytest.mark.asyncio
async def test_mark_paid_rejects_wrong_business(db, biz, cleaner_member, completed_booking):
    row = await calculate_cleaner_earnings(db, completed_booking)
    other_biz = await db.pool.fetchval(
        "INSERT INTO businesses (slug, name) "
        "VALUES ('payroll_other_' || gen_random_uuid()::text, 'Other') RETURNING id"
    )
    try:
        with pytest.raises(PayrollError, match=r"not found"):
            await mark_paid(db, other_biz, [row["id"]], "X")
    finally:
        await db.pool.execute("DELETE FROM businesses WHERE id = $1", other_biz)


@pytest.mark.asyncio
async def test_mark_paid_empty_list_rejected(db, biz):
    with pytest.raises(PayrollError, match=r"must not be empty"):
        await mark_paid(db, biz, [], "X")


@pytest.mark.asyncio
async def test_mark_paid_blank_ref_rejected(db, biz, cleaner_member, completed_booking):
    row = await calculate_cleaner_earnings(db, completed_booking)
    with pytest.raises(PayrollError, match=r"required"):
        await mark_paid(db, biz, [row["id"]], "   ")


# ===========================================================================
# void_earning
# ===========================================================================


@pytest.mark.asyncio
async def test_void_pending_earning(db, biz, cleaner_member, completed_booking):
    row = await calculate_cleaner_earnings(db, completed_booking)
    ok = await void_earning(db, biz, row["id"], reason="booking refunded")
    assert ok is True
    after = await db.pool.fetchrow(
        "SELECT status FROM cleaning_cleaner_earnings WHERE id = $1", row["id"],
    )
    assert after["status"] == "void"


@pytest.mark.asyncio
async def test_void_already_paid_returns_false(db, biz, cleaner_member, completed_booking):
    row = await calculate_cleaner_earnings(db, completed_booking)
    await mark_paid(db, biz, [row["id"]], "CHK-X")
    ok = await void_earning(db, biz, row["id"])
    assert ok is False
