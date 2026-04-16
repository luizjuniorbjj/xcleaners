"""
Pricing Engine Regression & Edge Case Tests — Story 1.1 AC7 Gate

Authority: @qa (Oracle) — 2026-04-16
Scope: Gate non-negotiable do merge da Story 1.1 (Pricing Engine Hybrid)

Structure:
  1. test_pricing_matches_launch27  — parametrized regression, 10 fixtures, tol ±$0.01
  2. Seven edge case tests            — ADR-001 Decisions 1/2/3/5/6/7 + happy path
  3. One integration test              — booking creation writes price_snapshot

Gate criteria (DoD):
  - 10/10 regression PASS (tolerance ±$0.01)
  - 7/7 edge cases PASS
  - 1/1 integration test PASS
  - pytest --cov=app.modules.cleaning.services.pricing_engine ≥ 90%

References:
  - docs/architecture/adr-001-pricing-engine-hybrid.md
  - docs/stories/1.1.pricing-engine-hybrid.md
  - docs/qa/story-1.1-test-strategy.md
  - tests/fixtures/launch27_3sisters_bookings.py

Status: AGUARDA IMPLEMENTAÇÃO de app/modules/cleaning/services/pricing_engine.py
  This file is a TDD contract. @dev implements against these tests.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest

from tests.fixtures.launch27_3sisters_bookings import (
    LAUNCH27_3SISTERS_BOOKINGS,
    PricingFixture,
)

# ---------------------------------------------------------------------------
# Module under test — import WILL FAIL until @dev implements it.
# This is intentional (TDD): failing import = not started.
# ---------------------------------------------------------------------------

pytest.importorskip(
    "app.modules.cleaning.services.pricing_engine",
    reason=(
        "Story 1.1 not yet implemented. This test file is a TDD contract. "
        "@dev must create app/modules/cleaning/services/pricing_engine.py with "
        "calculate_booking_price() matching ADR-001 canonical order."
    ),
)

from app.modules.cleaning.services.pricing_engine import (  # noqa: E402
    calculate_booking_price,
    PricingConfigError,
)


# ===========================================================================
# Test fixtures (pytest setup)
# ===========================================================================

@pytest.fixture
async def test_business_id(db):
    """Create isolated test business; cleanup after test."""
    business_id = await db.pool.fetchval(
        "INSERT INTO businesses (slug, name) "
        "VALUES ('test_pricing_biz_' || gen_random_uuid()::text, 'Pricing Test Business') "
        "RETURNING id"
    )
    yield business_id
    # Cascade cleanup via ON DELETE CASCADE on business_id FKs
    await db.pool.execute("DELETE FROM businesses WHERE id = $1", business_id)


@pytest.fixture
async def test_location_id(db, test_business_id):
    """Default location for pricing tests."""
    return await db.pool.fetchval(
        "INSERT INTO cleaning_areas (business_id, name, zip_codes, is_default) "
        "VALUES ($1, 'Test Location NYC', ARRAY['10001'], TRUE) "
        "RETURNING id",
        test_business_id,
    )


@pytest.fixture
async def test_formula(db, test_business_id):
    """Default formula (matches ADR-001 seed values)."""
    return await db.pool.fetchval(
        """
        INSERT INTO cleaning_pricing_formulas
            (business_id, name, base_amount, bedroom_delta, bathroom_delta,
             tier_multipliers, is_active)
        VALUES ($1, 'Standard', 115.00, 20.00, 15.00,
                '{"basic": 1.0, "deep": 1.8, "premium": 2.8}'::jsonb, TRUE)
        RETURNING id
        """,
        test_business_id,
    )


async def _create_service_with_override(
    db, business_id: UUID, fixture: PricingFixture
) -> UUID:
    """
    Helper: insert service with override matching fixture.base_price.

    Since most fixtures use observed prices (not pure formula-computed),
    we install an override per tier to force the pricing engine to return
    the expected service_amount. This isolates the test from formula drift.
    """
    service_id = await db.pool.fetchval(
        """
        INSERT INTO cleaning_services
            (business_id, name, slug, tier, bedrooms, bathrooms,
             base_price, is_active)
        VALUES ($1, $2, $3, $4, $5, $6, $7, TRUE)
        RETURNING id
        """,
        business_id,
        fixture.name,
        f"svc_{fixture.name}_{uuid4().hex[:6]}",
        fixture.service_config.tier,
        fixture.service_config.bedrooms,
        fixture.service_config.bathrooms,
        fixture.service_config.base_price,
    )
    # Install override so base_price flows through as-is (no formula recompute)
    await db.pool.execute(
        """
        INSERT INTO cleaning_service_overrides
            (service_id, tier, price_override, reason, is_active)
        VALUES ($1, $2, $3, 'Fixture-driven override (test harness)', TRUE)
        """,
        service_id,
        fixture.service_config.tier,
        fixture.service_config.base_price,
    )
    return service_id


async def _create_extras_from_fixture(
    db, business_id: UUID, service_id: UUID, fixture: PricingFixture
) -> list[dict]:
    """Create cleaning_extras rows + whitelist + return engine-ready list."""
    ready: list[dict] = []
    for e in fixture.extras:
        extra_id = await db.pool.fetchval(
            "INSERT INTO cleaning_extras (business_id, name, price, is_active) "
            "VALUES ($1, $2, $3, TRUE) RETURNING id",
            business_id, e.name, e.price,
        )
        await db.pool.execute(
            "INSERT INTO cleaning_service_extras (service_id, extra_id) VALUES ($1, $2)",
            service_id, extra_id,
        )
        ready.append({"extra_id": extra_id, "qty": e.qty})
    return ready


async def _create_frequency(db, business_id: UUID, fixture: PricingFixture) -> UUID:
    """Upsert a frequency matching fixture."""
    return await db.pool.fetchval(
        """
        INSERT INTO cleaning_frequencies
            (business_id, name, interval_weeks, discount_pct, is_default)
        VALUES ($1, $2, $3, $4, FALSE)
        ON CONFLICT (business_id, name)
        DO UPDATE SET discount_pct = EXCLUDED.discount_pct
        RETURNING id
        """,
        business_id,
        fixture.frequency.name,
        None if fixture.frequency.name == "One Time" else 1,
        fixture.frequency.discount_pct,
    )


async def _install_tax(
    db, business_id: UUID, location_id: UUID, tax_pct: Decimal
) -> None:
    """Install sales tax row if non-zero."""
    if tax_pct == Decimal("0"):
        return
    await db.pool.execute(
        """
        INSERT INTO cleaning_sales_taxes
            (business_id, location_id, tax_pct, effective_date, is_archived)
        VALUES ($1, $2, $3, CURRENT_DATE - INTERVAL '1 day', FALSE)
        """,
        business_id, location_id, tax_pct,
    )


# ===========================================================================
# AC7 PART 1 — Parametrized Launch27 regression (10 fixtures, ±$0.01)
# ===========================================================================

@pytest.mark.asyncio
@pytest.mark.parametrize(
    "fixture",
    LAUNCH27_3SISTERS_BOOKINGS,
    ids=lambda f: f.name,
)
async def test_pricing_matches_launch27(
    fixture: PricingFixture,
    db,
    test_business_id: UUID,
    test_location_id: UUID,
    test_formula: UUID,
):
    """
    Regression: pricing engine output MUST match Launch27 captured/derived
    values within ±$0.01 tolerance (ADR-001 + Story 1.1 AC7 gate).

    Validates ONE of the 10 fixtures per parametrized run. All 10 must pass.
    """
    # Arrange: set up DB with fixture inputs
    service_id = await _create_service_with_override(
        db, test_business_id, fixture
    )
    engine_extras = await _create_extras_from_fixture(
        db, test_business_id, service_id, fixture
    )
    frequency_id = await _create_frequency(db, test_business_id, fixture)
    await _install_tax(db, test_business_id, test_location_id, fixture.tax_pct)

    # Act: call pricing engine
    result = await calculate_booking_price(
        business_id=test_business_id,
        service_id=service_id,
        tier=fixture.service_config.tier,
        extras=engine_extras,
        frequency_id=frequency_id,
        adjustment_amount=fixture.adjustment,
        location_id=test_location_id,
        db=db,
    )

    # Assert: final_amount within tolerance
    got = Decimal(str(result["final_amount"]))
    expected = fixture.expected.final_amount
    diff = abs(got - expected)
    assert diff <= Decimal("0.01"), (
        f"\nPricing mismatch for {fixture.name}:\n"
        f"  Expected final: {expected}\n"
        f"  Got final:      {got}\n"
        f"  Diff:           {diff} (tolerance: $0.01)\n"
        f"  Subtotal:       expected={fixture.expected.subtotal}, got={result.get('subtotal')}\n"
        f"  Discount:       expected={fixture.expected.discount_amount}, got={result.get('discount_amount')}\n"
        f"  Before tax:     expected={fixture.expected.amount_before_tax}, got={result.get('amount_before_tax')}\n"
        f"  Tax:            expected={fixture.expected.tax_amount}, got={result.get('tax_amount')}\n"
        f"  Source:         {fixture.source_note}"
    )

    # Additional: verify breakdown components also match (not just final)
    assert Decimal(str(result["subtotal"])) == fixture.expected.subtotal
    assert Decimal(str(result["discount_amount"])) == fixture.expected.discount_amount
    assert Decimal(str(result["adjustment_amount"])) == fixture.expected.adjustment_amount
    assert Decimal(str(result["amount_before_tax"])) == fixture.expected.amount_before_tax
    assert Decimal(str(result["tax_amount"])) == fixture.expected.tax_amount


# ===========================================================================
# AC7 PART 2 — Seven Edge Case Tests (ADR-001 Decisions)
# ===========================================================================

@pytest.mark.asyncio
async def test_formula_change_keeps_overrides_stale(
    db, test_business_id, test_location_id, test_formula
):
    """
    ADR-001 Decision 1: When owner edits formula, existing overrides remain STALE.

    Scenario: create service with override $200, change formula base +$50,
    verify override still returns $200 (not 250).
    """
    # Create service with override $200
    service_id = await db.pool.fetchval(
        "INSERT INTO cleaning_services (business_id, name, slug, tier, "
        "bedrooms, bathrooms, base_price) "
        "VALUES ($1, 'Test Svc', 'test-svc-stale', 'basic', 1, 1, 200.00) "
        "RETURNING id",
        test_business_id,
    )
    await db.pool.execute(
        "INSERT INTO cleaning_service_overrides (service_id, tier, price_override, is_active) "
        "VALUES ($1, 'basic', 200.00, TRUE)",
        service_id,
    )
    freq_id = await db.pool.fetchval(
        "INSERT INTO cleaning_frequencies (business_id, name, discount_pct) "
        "VALUES ($1, 'One Time Stale', 0) RETURNING id",
        test_business_id,
    )

    # Mutate formula (base_amount +$50)
    await db.pool.execute(
        "UPDATE cleaning_pricing_formulas SET base_amount = base_amount + 50 "
        "WHERE id = $1",
        test_formula,
    )

    # Act: calculate — override should still apply
    result = await calculate_booking_price(
        business_id=test_business_id,
        service_id=service_id,
        tier="basic",
        extras=[],
        frequency_id=freq_id,
        adjustment_amount=Decimal("0"),
        location_id=test_location_id,
        db=db,
    )

    # Assert: service_amount is $200 (override), not $250 (would be if formula recomputed)
    assert Decimal(str(result["subtotal"])) == Decimal("200.00"), (
        f"Override should be STALE after formula change. Got subtotal={result['subtotal']}"
    )
    assert result["override_applied"] is True


@pytest.mark.asyncio
async def test_snapshot_immutable_after_booking(
    db, test_business_id, test_location_id, test_formula
):
    """
    ADR-001 Decision 2: price_snapshot in cleaning_bookings is immutable.

    Scenario: create booking → snapshot written. Mutate formula + extras.
    Re-read booking → snapshot unchanged.
    """
    # This test requires booking creation endpoint OR direct SQL with calc
    # Simplified: write snapshot directly, mutate, verify unchanged
    snapshot = {
        "final_amount": "225.50",
        "subtotal": "250.00",
        "tax_amount": "0.00",
        "calculated_at": "2026-04-16T12:00:00Z",
    }
    booking_id = await db.pool.fetchval(
        """
        INSERT INTO cleaning_bookings
            (business_id, client_id, service_id, scheduled_date, scheduled_start,
             quoted_price, final_price, price_snapshot)
        VALUES ($1,
                (SELECT id FROM cleaning_clients WHERE business_id = $1 LIMIT 1),
                (SELECT id FROM cleaning_services WHERE business_id = $1 LIMIT 1),
                CURRENT_DATE, '10:00:00', 225.50, 225.50, $2::jsonb)
        RETURNING id
        """,
        test_business_id,
        # NOTE: test setup depends on existence of client + service. Integration
        # variant of this test sets those up; here we skip if not present.
    ) if False else None
    pytest.skip(
        "Snapshot immutability test requires booking integration harness. "
        "Will be enabled once @dev completes booking creation flow."
    )


@pytest.mark.asyncio
async def test_override_precedence_wins(
    db, test_business_id, test_location_id, test_formula
):
    """
    ADR-001 Decision 3: IF override exists AND is_active → override wins over formula.

    Scenario: formula would compute $200, override says $150. Expect $150.
    """
    service_id = await db.pool.fetchval(
        "INSERT INTO cleaning_services (business_id, name, slug, tier, "
        "bedrooms, bathrooms, base_price) "
        "VALUES ($1, 'Precedence Test', 'precedence-test', 'basic', 2, 1, 155.00) "
        "RETURNING id",
        test_business_id,
    )
    # Formula would give (115 + 2*20 + 1*15) * 1.0 = $170; we override with $150
    await db.pool.execute(
        "INSERT INTO cleaning_service_overrides (service_id, tier, price_override, is_active) "
        "VALUES ($1, 'basic', 150.00, TRUE)",
        service_id,
    )
    freq_id = await db.pool.fetchval(
        "INSERT INTO cleaning_frequencies (business_id, name, discount_pct) "
        "VALUES ($1, 'One Time Prec', 0) RETURNING id",
        test_business_id,
    )

    result = await calculate_booking_price(
        business_id=test_business_id,
        service_id=service_id,
        tier="basic",
        extras=[],
        frequency_id=freq_id,
        adjustment_amount=Decimal("0"),
        location_id=test_location_id,
        db=db,
    )

    assert Decimal(str(result["subtotal"])) == Decimal("150.00")
    assert result["override_applied"] is True


@pytest.mark.asyncio
async def test_tier_multiplier_only_on_base(
    db, test_business_id, test_location_id, test_formula
):
    """
    ADR-001 Decision 5: Tier multiplier applies ONLY to (base + BR + BA).
    Extras remain flat regardless of tier.

    Scenario: same service + same $25 extra, computed for Basic (mult 1.0) vs
    Premium (mult 2.8). Extra should contribute $25 to BOTH totals.
    """
    # Two services: same BR/BA, different tiers
    svc_basic = await db.pool.fetchval(
        "INSERT INTO cleaning_services (business_id, name, slug, tier, "
        "bedrooms, bathrooms, base_price) "
        "VALUES ($1, 'Tier Basic', 'tier-basic', 'basic', 1, 1, 150.00) "
        "RETURNING id",
        test_business_id,
    )
    svc_premium = await db.pool.fetchval(
        "INSERT INTO cleaning_services (business_id, name, slug, tier, "
        "bedrooms, bathrooms, base_price) "
        "VALUES ($1, 'Tier Premium', 'tier-premium', 'premium', 1, 1, 420.00) "
        "RETURNING id",
        test_business_id,
    )
    # Overrides (isolate from formula)
    for sid, tier, price in [(svc_basic, "basic", "150.00"),
                              (svc_premium, "premium", "420.00")]:
        await db.pool.execute(
            "INSERT INTO cleaning_service_overrides (service_id, tier, price_override, is_active) "
            "VALUES ($1, $2, $3, TRUE)",
            sid, tier, Decimal(price),
        )
    # One extra $25
    extra_id = await db.pool.fetchval(
        "INSERT INTO cleaning_extras (business_id, name, price) "
        "VALUES ($1, 'Test Extra Flat', 25.00) RETURNING id",
        test_business_id,
    )
    for sid in (svc_basic, svc_premium):
        await db.pool.execute(
            "INSERT INTO cleaning_service_extras (service_id, extra_id) VALUES ($1, $2)",
            sid, extra_id,
        )
    freq_id = await db.pool.fetchval(
        "INSERT INTO cleaning_frequencies (business_id, name, discount_pct) "
        "VALUES ($1, 'One Time Tier', 0) RETURNING id",
        test_business_id,
    )

    args_common = dict(
        business_id=test_business_id,
        extras=[{"extra_id": extra_id, "qty": 1}],
        frequency_id=freq_id,
        adjustment_amount=Decimal("0"),
        location_id=test_location_id,
        db=db,
    )
    r_basic = await calculate_booking_price(
        service_id=svc_basic, tier="basic", **args_common
    )
    r_premium = await calculate_booking_price(
        service_id=svc_premium, tier="premium", **args_common
    )

    # Assert: extras_sum is $25 in BOTH — flat regardless of tier
    assert Decimal(str(r_basic["extras_sum"])) == Decimal("25.00")
    assert Decimal(str(r_premium["extras_sum"])) == Decimal("25.00")
    # Subtotal = service + $25 flat extra
    assert Decimal(str(r_basic["subtotal"])) == Decimal("175.00")    # 150 + 25
    assert Decimal(str(r_premium["subtotal"])) == Decimal("445.00")  # 420 + 25


@pytest.mark.asyncio
async def test_tax_base_is_liquid(
    db, test_business_id, test_location_id, test_formula
):
    """
    ADR-001 Decision 6: tax = (subtotal − discount − adjustment) × tax_pct, NOT
    on the gross subtotal.

    Validates against the captured $229.67 scenario.
    """
    # Replicate F1 conditions minimally
    svc = await db.pool.fetchval(
        "INSERT INTO cleaning_services (business_id, name, slug, tier, "
        "bedrooms, bathrooms, base_price) "
        "VALUES ($1, 'Tax Liquid', 'tax-liquid', 'basic', 2, 1, 275.00) "
        "RETURNING id",
        test_business_id,
    )
    await db.pool.execute(
        "INSERT INTO cleaning_service_overrides (service_id, tier, price_override, is_active) "
        "VALUES ($1, 'basic', 275.00, TRUE)",
        svc,
    )
    extra_id = await db.pool.fetchval(
        "INSERT INTO cleaning_extras (business_id, name, price) "
        "VALUES ($1, 'Stairs', 30.00) RETURNING id",
        test_business_id,
    )
    await db.pool.execute(
        "INSERT INTO cleaning_service_extras (service_id, extra_id) VALUES ($1, $2)",
        svc, extra_id,
    )
    freq_id = await db.pool.fetchval(
        "INSERT INTO cleaning_frequencies (business_id, name, discount_pct) "
        "VALUES ($1, 'Weekly TaxLiquid', 15.00) RETURNING id",
        test_business_id,
    )
    await db.pool.execute(
        "INSERT INTO cleaning_sales_taxes (business_id, location_id, tax_pct, effective_date) "
        "VALUES ($1, $2, 4.50, CURRENT_DATE - INTERVAL '1 day')",
        test_business_id, test_location_id,
    )

    result = await calculate_booking_price(
        business_id=test_business_id,
        service_id=svc,
        tier="basic",
        extras=[{"extra_id": extra_id, "qty": 1}],
        frequency_id=freq_id,
        adjustment_amount=Decimal("-29.58"),
        location_id=test_location_id,
        db=db,
    )

    # Tax should be applied to $229.67 (LIQUID), not $305.00 (gross)
    assert Decimal(str(result["amount_before_tax"])) == Decimal("229.67")
    assert Decimal(str(result["tax_amount"])) == Decimal("10.34")
    # Verify tax on gross would be $13.73 — NOT what we expect
    tax_on_gross = Decimal("305.00") * Decimal("0.045")
    assert Decimal(str(result["tax_amount"])) != tax_on_gross.quantize(Decimal("0.01"))


@pytest.mark.asyncio
async def test_adjustment_before_tax(
    db, test_business_id, test_location_id, test_formula
):
    """
    ADR-001 Decision 7: adjustment is applied BEFORE tax.

    Scenario: positive and negative adjustment both reduce/increase
    amount_before_tax; tax is computed on the resulting value.
    """
    # Setup: $200 service, no extras, no discount, $0 and -$50 adjustments
    svc = await db.pool.fetchval(
        "INSERT INTO cleaning_services (business_id, name, slug, tier, "
        "bedrooms, bathrooms, base_price) "
        "VALUES ($1, 'Adj Test', 'adj-test', 'basic', 1, 1, 200.00) "
        "RETURNING id",
        test_business_id,
    )
    await db.pool.execute(
        "INSERT INTO cleaning_service_overrides (service_id, tier, price_override, is_active) "
        "VALUES ($1, 'basic', 200.00, TRUE)",
        svc,
    )
    freq_id = await db.pool.fetchval(
        "INSERT INTO cleaning_frequencies (business_id, name, discount_pct) "
        "VALUES ($1, 'One Time Adj', 0) RETURNING id",
        test_business_id,
    )
    await db.pool.execute(
        "INSERT INTO cleaning_sales_taxes (business_id, location_id, tax_pct, effective_date) "
        "VALUES ($1, $2, 10.00, CURRENT_DATE - INTERVAL '1 day')",
        test_business_id, test_location_id,
    )

    # Zero adjustment: tax = 10% of $200 = $20; final = $220
    r_zero = await calculate_booking_price(
        business_id=test_business_id, service_id=svc, tier="basic",
        extras=[], frequency_id=freq_id,
        adjustment_amount=Decimal("0"),
        location_id=test_location_id, db=db,
    )
    # Negative adjustment -$50: amount_before_tax = 200 - 50 = $150;
    # tax = 10% of $150 = $15; final = $165
    r_neg = await calculate_booking_price(
        business_id=test_business_id, service_id=svc, tier="basic",
        extras=[], frequency_id=freq_id,
        adjustment_amount=Decimal("-50"),
        location_id=test_location_id, db=db,
    )

    assert Decimal(str(r_zero["tax_amount"])) == Decimal("20.00")
    assert Decimal(str(r_zero["final_amount"])) == Decimal("220.00")
    assert Decimal(str(r_neg["amount_before_tax"])) == Decimal("150.00")
    assert Decimal(str(r_neg["tax_amount"])) == Decimal("15.00")
    assert Decimal(str(r_neg["final_amount"])) == Decimal("165.00")


@pytest.mark.asyncio
async def test_happy_path_zero_extras_zero_discount_no_tax(
    db, test_business_id, test_location_id, test_formula
):
    """
    Happy path: minimal case exercises full engine without optional components.
    Studio Basic, One Time, no extras, no adjustment, no tax → final == service_amount.
    """
    svc = await db.pool.fetchval(
        "INSERT INTO cleaning_services (business_id, name, slug, tier, "
        "bedrooms, bathrooms, base_price) "
        "VALUES ($1, 'Happy Path', 'happy-path', 'basic', 0, 0, 135.00) "
        "RETURNING id",
        test_business_id,
    )
    await db.pool.execute(
        "INSERT INTO cleaning_service_overrides (service_id, tier, price_override, is_active) "
        "VALUES ($1, 'basic', 135.00, TRUE)",
        svc,
    )
    freq_id = await db.pool.fetchval(
        "INSERT INTO cleaning_frequencies (business_id, name, discount_pct) "
        "VALUES ($1, 'One Time Happy', 0) RETURNING id",
        test_business_id,
    )
    # NO sales tax row for location

    result = await calculate_booking_price(
        business_id=test_business_id, service_id=svc, tier="basic",
        extras=[], frequency_id=freq_id,
        adjustment_amount=Decimal("0"),
        location_id=test_location_id, db=db,
    )

    assert Decimal(str(result["final_amount"])) == Decimal("135.00")
    assert Decimal(str(result["tax_amount"])) == Decimal("0.00")
    assert Decimal(str(result["discount_amount"])) == Decimal("0.00")
    assert Decimal(str(result["adjustment_amount"])) == Decimal("0.00")


# ===========================================================================
# AC7 PART 3 — Integration Test (booking creation flow)
# ===========================================================================

@pytest.mark.asyncio
async def test_booking_creation_writes_immutable_snapshot(
    db, test_business_id, test_location_id, test_formula
):
    """
    Integration: when booking is confirmed (draft → scheduled), the pricing
    engine result is persisted to cleaning_bookings.price_snapshot JSONB.

    Validates Story 1.1 AC6 (snapshot immutable).
    """
    pytest.skip(
        "Booking creation endpoint required. Enable after @dev completes "
        "Task 6 (Snapshot + Booking Confirmation). "
        "Expected: POST /api/v1/clean/{slug}/bookings → cleaning_bookings "
        "row with price_snapshot JSONB populated matching pricing_engine output."
    )


# ===========================================================================
# Error handling tests (graceful fallbacks)
# ===========================================================================

@pytest.mark.asyncio
async def test_missing_formula_raises_pricing_config_error(
    db, test_business_id, test_location_id
):
    """
    ADR-001: missing formula for business raises PricingConfigError.
    """
    # Don't create formula; business has none
    svc = await db.pool.fetchval(
        "INSERT INTO cleaning_services (business_id, name, slug, tier, "
        "bedrooms, bathrooms, base_price) "
        "VALUES ($1, 'No Formula', 'no-formula', 'basic', 1, 1, 100.00) "
        "RETURNING id",
        test_business_id,
    )
    # No override either — engine must rely on formula
    freq_id = await db.pool.fetchval(
        "INSERT INTO cleaning_frequencies (business_id, name, discount_pct) "
        "VALUES ($1, 'One Time NoFormula', 0) RETURNING id",
        test_business_id,
    )

    with pytest.raises(PricingConfigError, match=r".*formula.*"):
        await calculate_booking_price(
            business_id=test_business_id, service_id=svc, tier="basic",
            extras=[], frequency_id=freq_id,
            adjustment_amount=Decimal("0"),
            location_id=test_location_id, db=db,
        )


@pytest.mark.asyncio
async def test_missing_tax_config_defaults_to_zero(
    db, test_business_id, test_location_id, test_formula
):
    """
    ADR-001 Error handling: missing sales tax config → tax_pct = 0 (fallback).
    """
    svc = await db.pool.fetchval(
        "INSERT INTO cleaning_services (business_id, name, slug, tier, "
        "bedrooms, bathrooms, base_price) "
        "VALUES ($1, 'No Tax', 'no-tax', 'basic', 0, 0, 100.00) "
        "RETURNING id",
        test_business_id,
    )
    await db.pool.execute(
        "INSERT INTO cleaning_service_overrides (service_id, tier, price_override, is_active) "
        "VALUES ($1, 'basic', 100.00, TRUE)",
        svc,
    )
    freq_id = await db.pool.fetchval(
        "INSERT INTO cleaning_frequencies (business_id, name, discount_pct) "
        "VALUES ($1, 'One Time NoTax', 0) RETURNING id",
        test_business_id,
    )
    # NO cleaning_sales_taxes row

    result = await calculate_booking_price(
        business_id=test_business_id, service_id=svc, tier="basic",
        extras=[], frequency_id=freq_id,
        adjustment_amount=Decimal("0"),
        location_id=test_location_id, db=db,
    )

    assert Decimal(str(result["tax_pct"])) == Decimal("0")
    assert Decimal(str(result["tax_amount"])) == Decimal("0")
    assert Decimal(str(result["final_amount"])) == Decimal("100")


# ===========================================================================
# Helper tests (no DB — raise coverage of defensive branches)
# ===========================================================================

def test_breakdown_to_jsonb_serializes_decimals_and_uuids():
    """`breakdown_to_jsonb` must stringify Decimals and UUIDs losslessly."""
    from app.modules.cleaning.services.pricing_engine import breakdown_to_jsonb
    import json
    from uuid import uuid4

    u = uuid4()
    sample = {
        "formula_id": str(u),
        "service_id": str(u),
        "tier": "basic",
        "tier_multiplier": Decimal("1.0"),
        "base_amount": Decimal("115.00"),
        "bedrooms": 2,
        "bedroom_delta": Decimal("20.00"),
        "bathrooms": 1,
        "bathroom_delta": Decimal("15.00"),
        "override_applied": False,
        "subtotal_service": Decimal("170.00"),
        "extras": [{"extra_id": str(u), "name": "Stairs", "qty": 1, "price": Decimal("30.00")}],
        "extras_sum": Decimal("30.00"),
        "subtotal": Decimal("200.00"),
        "frequency_id": None,
        "frequency_name": None,
        "discount_pct": Decimal("0"),
        "discount_amount": Decimal("0"),
        "adjustment_amount": Decimal("0"),
        "adjustment_reason": None,
        "amount_before_tax": Decimal("200.00"),
        "tax_pct": Decimal("0"),
        "tax_amount": Decimal("0"),
        "final_amount": Decimal("200.00"),
        "calculated_at": "2026-04-16T12:00:00+00:00",
    }
    serialized = breakdown_to_jsonb(sample)
    parsed = json.loads(serialized)
    # Decimals must be strings (lossless); UUIDs must be strings
    assert parsed["final_amount"] == "200.00"
    assert parsed["extras"][0]["price"] == "30.00"


def test_parse_tier_multipliers_handles_string_input():
    """asyncpg may return JSONB as str; parser should handle both dict and str."""
    from app.modules.cleaning.services.pricing_engine import _parse_tier_multipliers
    parsed = _parse_tier_multipliers('{"basic": 1.0, "deep": 1.8, "premium": 2.8}')
    assert parsed["basic"] == Decimal("1.0")
    assert parsed["deep"] == Decimal("1.8")
    assert parsed["premium"] == Decimal("2.8")


def test_parse_tier_multipliers_none_returns_defaults():
    """None input returns sensible defaults (Basic 1.0, Deep 1.8, Premium 2.8)."""
    from app.modules.cleaning.services.pricing_engine import _parse_tier_multipliers
    defaults = _parse_tier_multipliers(None)
    assert defaults["basic"] == Decimal("1.0")
    assert defaults["deep"] == Decimal("1.8")
    assert defaults["premium"] == Decimal("2.8")


def test_parse_tier_multipliers_invalid_type_raises():
    """Non-dict / non-JSON-str input raises PricingConfigError."""
    from app.modules.cleaning.services.pricing_engine import (
        _parse_tier_multipliers, PricingConfigError,
    )
    with pytest.raises(PricingConfigError, match=r".*JSON object.*"):
        _parse_tier_multipliers(123)  # int — not valid


def test_to_decimal_handles_none_and_decimals():
    """`_to_decimal` must handle None, Decimal, int, float, str uniformly."""
    from app.modules.cleaning.services.pricing_engine import _to_decimal
    assert _to_decimal(None) == Decimal("0")
    assert _to_decimal(Decimal("3.14")) == Decimal("3.14")
    assert _to_decimal(10) == Decimal("10")
    assert _to_decimal("5.50") == Decimal("5.50")
    # float: string-roundtrip prevents float drift
    assert _to_decimal(0.1) == Decimal("0.1")


def test_round_money_rounds_half_up():
    """Money rounding must use ROUND_HALF_UP (not banker's rounding)."""
    from app.modules.cleaning.services.pricing_engine import _round_money
    # 0.005 rounds up (HALF_UP) — banker's rounding would round to even (0.00)
    assert _round_money(Decimal("0.005")) == Decimal("0.01")
    assert _round_money(Decimal("10.575")) == Decimal("10.58")
    assert _round_money(Decimal("20.3625")) == Decimal("20.36")  # under half
    assert _round_money(Decimal("25.245")) == Decimal("25.25")   # exact half rounds up


@pytest.mark.asyncio
async def test_invalid_tier_raises_pricing_config_error(
    db, test_business_id, test_location_id, test_formula
):
    """Tier outside ('basic','deep','premium') → PricingConfigError."""
    from app.modules.cleaning.services.pricing_engine import (
        calculate_booking_price, PricingConfigError,
    )
    with pytest.raises(PricingConfigError, match=r".*Invalid tier.*"):
        await calculate_booking_price(
            business_id=test_business_id,
            service_id=test_business_id,  # any UUID; won't reach service fetch
            tier="platinum",  # invalid
            extras=[], frequency_id=None,
            adjustment_amount=Decimal("0"),
            location_id=test_location_id, db=db,
        )


@pytest.mark.asyncio
async def test_service_not_found_raises(
    db, test_business_id, test_location_id, test_formula
):
    """Service_id that doesn't exist → PricingConfigError."""
    from app.modules.cleaning.services.pricing_engine import (
        calculate_booking_price, PricingConfigError,
    )
    from uuid import uuid4
    with pytest.raises(PricingConfigError, match=r".*Service not found.*"):
        await calculate_booking_price(
            business_id=test_business_id,
            service_id=uuid4(),  # doesn't exist
            tier="basic",
            extras=[], frequency_id=None,
            adjustment_amount=Decimal("0"),
            location_id=test_location_id, db=db,
        )


@pytest.mark.asyncio
async def test_location_specific_formula_preferred_over_default(
    db, test_business_id, test_location_id, test_formula
):
    """When location-specific formula exists, engine uses it over business default."""
    from app.modules.cleaning.services.pricing_engine import calculate_booking_price

    # Insert location-specific formula with DIFFERENT base than default
    await db.pool.execute(
        """
        INSERT INTO cleaning_pricing_formulas
            (business_id, location_id, name, base_amount, bedroom_delta, bathroom_delta,
             tier_multipliers, is_active)
        VALUES ($1, $2, 'NYC Premium Formula', 200.00, 30.00, 20.00,
                '{"basic": 1.0, "deep": 2.0, "premium": 3.0}'::jsonb, TRUE)
        """,
        test_business_id, test_location_id,
    )
    # Create service WITHOUT override → formula path is exercised
    svc = await db.pool.fetchval(
        "INSERT INTO cleaning_services (business_id, name, slug, tier, "
        "bedrooms, bathrooms, base_price) "
        "VALUES ($1, 'LocSpec Test', 'locspec-test', 'basic', 1, 1, 0) "
        "RETURNING id",
        test_business_id,
    )
    freq_id = await db.pool.fetchval(
        "INSERT INTO cleaning_frequencies (business_id, name, discount_pct) "
        "VALUES ($1, 'One Time LocSpec', 0) RETURNING id",
        test_business_id,
    )

    result = await calculate_booking_price(
        business_id=test_business_id,
        service_id=svc,
        tier="basic",
        extras=[],
        frequency_id=freq_id,
        adjustment_amount=Decimal("0"),
        location_id=test_location_id,  # passes location_id → triggers location-specific lookup
        db=db,
    )

    # Expected: location-specific formula applied
    # service_amount = (200 + 1*30 + 1*20) * 1.0 = $250 (location formula)
    # Business default would have been: (115 + 1*20 + 1*15) * 1.0 = $150
    assert Decimal(str(result["subtotal"])) == Decimal("250.00"), (
        f"Location-specific formula not applied. Got subtotal={result['subtotal']}, "
        f"expected $250 (200 + 30 + 20). If got $150, location_id lookup failed."
    )


@pytest.mark.asyncio
async def test_extras_with_invalid_qty_skipped(
    db, test_business_id, test_location_id, test_formula
):
    """Extras with qty < 1 or missing extra_id are skipped gracefully."""
    from app.modules.cleaning.services.pricing_engine import calculate_booking_price

    svc = await db.pool.fetchval(
        "INSERT INTO cleaning_services (business_id, name, slug, tier, "
        "bedrooms, bathrooms, base_price) "
        "VALUES ($1, 'Invalid Qty Test', 'invalid-qty-test', 'basic', 0, 0, 135.00) "
        "RETURNING id",
        test_business_id,
    )
    await db.pool.execute(
        "INSERT INTO cleaning_service_overrides (service_id, tier, price_override, is_active) "
        "VALUES ($1, 'basic', 135.00, TRUE)",
        svc,
    )
    freq_id = await db.pool.fetchval(
        "INSERT INTO cleaning_frequencies (business_id, name, discount_pct) "
        "VALUES ($1, 'One Time InvalidQty', 0) RETURNING id",
        test_business_id,
    )

    from uuid import uuid4
    nonexistent_extra = uuid4()  # valid UUID format, not in DB

    # Pass extras with invalid qty (0) and missing extra_id and nonexistent
    result = await calculate_booking_price(
        business_id=test_business_id,
        service_id=svc,
        tier="basic",
        extras=[
            {"extra_id": None, "qty": 1},            # missing extra_id
            {"qty": 0},                               # qty 0 (no extra_id)
            {"extra_id": nonexistent_extra, "qty": 1},  # valid UUID but not in DB
        ],
        frequency_id=freq_id,
        adjustment_amount=Decimal("0"),
        location_id=test_location_id, db=db,
    )
    # All 3 bad extras skipped; subtotal is just the service
    assert Decimal(str(result["extras_sum"])) == Decimal("0")
    assert Decimal(str(result["subtotal"])) == Decimal("135.00")


# ===========================================================================
# Meta test — fixture file self-validation
# ===========================================================================

def test_all_fixtures_satisfy_canonical_equation():
    """
    Verify the 10 fixtures in launch27_3sisters_bookings.py are
    mathematically self-consistent with the canonical pricing equation.

    This test is the first line of defense: if a fixture violates the
    equation, no pricing engine implementation can pass it.
    """
    from decimal import ROUND_HALF_UP

    failures: list[str] = []
    for f in LAUNCH27_3SISTERS_BOOKINGS:
        # Recompute expected values per canonical equation
        subtotal = f.service_config.base_price + sum(
            (e.price * Decimal(e.qty) for e in f.extras), Decimal("0")
        )
        discount = (subtotal * f.frequency.discount_pct / Decimal("100")).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        before_tax = subtotal - discount + f.adjustment
        tax = (before_tax * f.tax_pct / Decimal("100")).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        final = before_tax + tax

        mismatches = []
        if subtotal != f.expected.subtotal:
            mismatches.append(f"subtotal exp={f.expected.subtotal} got={subtotal}")
        if discount != f.expected.discount_amount:
            mismatches.append(f"discount exp={f.expected.discount_amount} got={discount}")
        if before_tax != f.expected.amount_before_tax:
            mismatches.append(f"before_tax exp={f.expected.amount_before_tax} got={before_tax}")
        if tax != f.expected.tax_amount:
            mismatches.append(f"tax exp={f.expected.tax_amount} got={tax}")
        if final != f.expected.final_amount:
            mismatches.append(f"final exp={f.expected.final_amount} got={final}")

        if mismatches:
            failures.append(f"{f.name}: {'; '.join(mismatches)}")

    assert not failures, (
        "Fixtures file has internal inconsistencies:\n  " + "\n  ".join(failures)
    )
