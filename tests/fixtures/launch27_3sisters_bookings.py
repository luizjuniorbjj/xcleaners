"""
Launch27 3Sisters Regression Fixtures — Pricing Engine Tests

Purpose: Ground-truth fixtures for the AC7 regression gate in Story 1.1.
  Tests must pass with tolerance ±$0.01 (Decimal) against these expected values.

Source of truth (2026-04-16):
  - 1 REAL fixture: captured booking #5792 from 3sistersnyc.launch27.com
  - 9 DERIVED fixtures: pricing ladder + standard Launch27 order of operations

Pricing ladder observed in 3Sisters admin (FASE2 analysis):
  Studio:         Basic $135  / Deep $260  / Premium $410
  1 Room × 1 BA:  Basic $155  / Deep $300  / Premium $450
  2 Rooms × 1 BA: Basic $175* / Deep $350  / Premium $500
  2 Rooms × 2 BA: Basic $195  / Deep $380  / Premium $530
  3 Rooms × 1 BA: Basic $215  / Deep $420  / Premium $580

* KNOWN UNKNOWN: Real booking #5792 has service = $275 for "2R×1BA Basic",
  not the ladder's $175. Root cause undetermined (owner override, tier
  mislabel, or sampling issue in Fase 2). F1 honors the observed $275 —
  reality wins over model. See story-1.1-test-strategy.md Section 4.

Canonical order of operations (ADR-001 Decisions 5/6/7):
  1. service_amount = (base + BR*α + BA*β) × tier_multiplier
  2. extras_sum    = Σ(extra.price × extra.qty)           [flat, NOT tiered]
  3. subtotal      = service_amount + extras_sum
  4. discount      = round(subtotal × discount_pct / 100, 2, ROUND_HALF_UP)
  5. before_tax    = subtotal − discount + adjustment      [adjustment is signed]
  6. tax           = round(before_tax × tax_pct / 100, 2, ROUND_HALF_UP)
  7. final         = before_tax + tax

All 10 fixtures below were validated via canonical equation:
    F{N}: subtotal=X, discount=Y, before_tax=Z, tax=T, final=F
before check-in (see qa validation script).

Authored by: @qa (Oracle), 2026-04-16
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Literal

# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

Tier = Literal["basic", "deep", "premium"]


@dataclass(frozen=True)
class ServiceConfig:
    """Service-level inputs to the pricing engine."""
    tier: Tier
    bedrooms: int
    bathrooms: int
    base_price: Decimal  # Price resolved by formula OR override at booking time


@dataclass(frozen=True)
class ExtraInput:
    """One add-on applied to a booking."""
    name: str
    price: Decimal
    qty: int = 1


@dataclass(frozen=True)
class FrequencyInput:
    """Selected frequency (may be one-time or recurring)."""
    name: str
    discount_pct: Decimal


@dataclass(frozen=True)
class ExpectedPricing:
    """Ground-truth outputs — match with ±$0.01 tolerance."""
    subtotal: Decimal
    discount_amount: Decimal
    adjustment_amount: Decimal
    amount_before_tax: Decimal
    tax_amount: Decimal
    final_amount: Decimal


@dataclass(frozen=True)
class PricingFixture:
    """
    One regression fixture for pricing engine AC7 gate.

    Compose: service_config + extras + frequency + adjustment + tax_pct
    Expect:  expected (Decimal values that MUST match ±$0.01)
    """
    name: str
    service_config: ServiceConfig
    extras: tuple[ExtraInput, ...]
    frequency: FrequencyInput
    adjustment: Decimal
    tax_pct: Decimal
    expected: ExpectedPricing
    source_note: str


# ---------------------------------------------------------------------------
# Fixture 1 — REAL (captured from 3sistersnyc.launch27.com booking #5792)
# ---------------------------------------------------------------------------

F1_REAL_240_01 = PricingFixture(
    name="real_booking_5792_2r1ba_basic_stairs_weekly15_adj_negative",
    service_config=ServiceConfig(
        tier="basic",
        bedrooms=2,
        bathrooms=1,
        # Observed $275 service row (not ladder $175). See "KNOWN UNKNOWN"
        # in module docstring. Reality wins — fixture honors captured value.
        base_price=Decimal("275.00"),
    ),
    extras=(
        ExtraInput(name="Stairs", price=Decimal("30.00"), qty=1),
    ),
    frequency=FrequencyInput(name="Weekly", discount_pct=Decimal("15.00")),
    adjustment=Decimal("-29.58"),
    tax_pct=Decimal("4.50"),
    expected=ExpectedPricing(
        subtotal=Decimal("305.00"),
        discount_amount=Decimal("45.75"),
        adjustment_amount=Decimal("-29.58"),
        amount_before_tax=Decimal("229.67"),
        tax_amount=Decimal("10.34"),
        final_amount=Decimal("240.01"),
    ),
    source_note=(
        "REAL. Captured from 3sistersnyc.launch27.com admin booking #5792 on "
        "2026-04-16 (Launch27 competitive analysis Fase 2, anonymized). "
        "Observed service amount $275 exceeds the observed ladder $175 for "
        "'2R×1BA Basic' — likely owner override in Launch27. Fixture uses the "
        "observed $275 (reality over model). Discrepancy is a pre-cutover "
        "investigation item — see story-1.1-test-strategy.md §4."
    ),
)


# ---------------------------------------------------------------------------
# Fixtures 2-10 — DERIVED (ladder + canonical operations, validated)
# ---------------------------------------------------------------------------

F2_STUDIO_BASIC_ONETIME_TAX = PricingFixture(
    name="derived_studio_basic_onetime_no_extras_tax45",
    service_config=ServiceConfig(
        tier="basic", bedrooms=0, bathrooms=0,
        base_price=Decimal("135.00"),
    ),
    extras=(),
    frequency=FrequencyInput(name="One Time", discount_pct=Decimal("0.00")),
    adjustment=Decimal("0.00"),
    tax_pct=Decimal("4.50"),
    expected=ExpectedPricing(
        subtotal=Decimal("135.00"),
        discount_amount=Decimal("0.00"),
        adjustment_amount=Decimal("0.00"),
        amount_before_tax=Decimal("135.00"),
        tax_amount=Decimal("6.08"),
        final_amount=Decimal("141.08"),
    ),
    source_note=(
        "DERIVED. Studio Basic from ladder ($135). One Time frequency (0% "
        "discount). No extras, no adjustment. NYC 4.5% tax. "
        "Round-half-up: 135 × 0.045 = 6.075 → 6.08."
    ),
)


F3_STUDIO_PREMIUM_OVEN_WEEKLY_TAX = PricingFixture(
    name="derived_studio_premium_oven_weekly15_tax45",
    service_config=ServiceConfig(
        tier="premium", bedrooms=0, bathrooms=0,
        base_price=Decimal("410.00"),
    ),
    extras=(
        ExtraInput(name="Inside the oven", price=Decimal("25.00"), qty=1),
    ),
    frequency=FrequencyInput(name="Weekly", discount_pct=Decimal("15.00")),
    adjustment=Decimal("0.00"),
    tax_pct=Decimal("4.50"),
    expected=ExpectedPricing(
        subtotal=Decimal("435.00"),
        discount_amount=Decimal("65.25"),
        adjustment_amount=Decimal("0.00"),
        amount_before_tax=Decimal("369.75"),
        tax_amount=Decimal("16.64"),
        final_amount=Decimal("386.39"),
    ),
    source_note=(
        "DERIVED. Studio Premium ($410) + Oven ($25 flat, not tiered) = $435. "
        "Weekly 15% discount = $65.25. Tax 4.5% on $369.75 = $16.6388 → $16.64. "
        "Validates ADR-001 Decision 5 (tier multiplier NOT applied to extras)."
    ),
)


F4_1R1BA_DEEP_2EXTRAS_BIWEEKLY_TAX = PricingFixture(
    name="derived_1r1ba_deep_windows_oven_biweekly10_tax45",
    service_config=ServiceConfig(
        tier="deep", bedrooms=1, bathrooms=1,
        base_price=Decimal("300.00"),
    ),
    extras=(
        ExtraInput(name="Inside windows", price=Decimal("25.00"), qty=1),
        ExtraInput(name="Inside the oven", price=Decimal("25.00"), qty=1),
    ),
    frequency=FrequencyInput(name="Biweekly", discount_pct=Decimal("10.00")),
    adjustment=Decimal("0.00"),
    tax_pct=Decimal("4.50"),
    expected=ExpectedPricing(
        subtotal=Decimal("350.00"),
        discount_amount=Decimal("35.00"),
        adjustment_amount=Decimal("0.00"),
        amount_before_tax=Decimal("315.00"),
        tax_amount=Decimal("14.18"),
        final_amount=Decimal("329.18"),
    ),
    source_note=(
        "DERIVED. 1R×1BA Deep ($300) + Windows ($25) + Oven ($25) = $350. "
        "Biweekly 10% = $35 discount. Tax 4.5% on $315 = $14.175 → $14.18."
    ),
)


F5_2R2BA_BASIC_MONTHLY_ADJ_POS_TAX = PricingFixture(
    name="derived_2r2ba_basic_monthly5_adj_positive_tax45",
    service_config=ServiceConfig(
        tier="basic", bedrooms=2, bathrooms=2,
        base_price=Decimal("195.00"),
    ),
    extras=(),
    frequency=FrequencyInput(name="Monthly", discount_pct=Decimal("5.00")),
    adjustment=Decimal("50.00"),  # positive = surcharge
    tax_pct=Decimal("4.50"),
    expected=ExpectedPricing(
        subtotal=Decimal("195.00"),
        discount_amount=Decimal("9.75"),
        adjustment_amount=Decimal("50.00"),
        amount_before_tax=Decimal("235.25"),
        tax_amount=Decimal("10.59"),
        final_amount=Decimal("245.84"),
    ),
    source_note=(
        "DERIVED. 2R×2BA Basic ($195). Monthly 5% discount = $9.75. "
        "Positive adjustment +$50 (e.g. surcharge for last-minute booking). "
        "Tax on (195 − 9.75 + 50) = $235.25 × 4.5% = $10.58625 → $10.59. "
        "Validates adjustment applied BEFORE tax (ADR-001 Decision 7)."
    ),
)


F6_3R1BA_PREMIUM_3EXTRAS_WEEKLY_TAX = PricingFixture(
    name="derived_3r1ba_premium_stairs_office_cabinets_weekly15_tax45",
    service_config=ServiceConfig(
        tier="premium", bedrooms=3, bathrooms=1,
        base_price=Decimal("580.00"),
    ),
    extras=(
        ExtraInput(name="Stairs", price=Decimal("30.00"), qty=1),
        ExtraInput(name="Office", price=Decimal("25.00"), qty=1),
        ExtraInput(name="Inside cabinets", price=Decimal("25.00"), qty=1),
    ),
    frequency=FrequencyInput(name="Weekly", discount_pct=Decimal("15.00")),
    adjustment=Decimal("0.00"),
    tax_pct=Decimal("4.50"),
    expected=ExpectedPricing(
        subtotal=Decimal("660.00"),
        discount_amount=Decimal("99.00"),
        adjustment_amount=Decimal("0.00"),
        amount_before_tax=Decimal("561.00"),
        tax_amount=Decimal("25.25"),
        final_amount=Decimal("586.25"),
    ),
    source_note=(
        "DERIVED. 3R×1BA Premium ($580) + Stairs ($30) + Office ($25) + "
        "Cabinets ($25) = $660. Weekly 15% = $99 discount. Tax 4.5% on $561 "
        "= $25.245 → $25.25 (ROUND_HALF_UP, 0.245 rounds to 0.25)."
    ),
)


F7_STUDIO_DEEP_WALLS_ONETIME_TAX = PricingFixture(
    name="derived_studio_deep_walls_onetime_tax45",
    service_config=ServiceConfig(
        tier="deep", bedrooms=0, bathrooms=0,
        base_price=Decimal("260.00"),
    ),
    extras=(
        ExtraInput(name="Walls", price=Decimal("25.00"), qty=1),
    ),
    frequency=FrequencyInput(name="One Time", discount_pct=Decimal("0.00")),
    adjustment=Decimal("0.00"),
    tax_pct=Decimal("4.50"),
    expected=ExpectedPricing(
        subtotal=Decimal("285.00"),
        discount_amount=Decimal("0.00"),
        adjustment_amount=Decimal("0.00"),
        amount_before_tax=Decimal("285.00"),
        tax_amount=Decimal("12.83"),
        final_amount=Decimal("297.83"),
    ),
    source_note=(
        "DERIVED. Studio Deep ($260) + Walls ($25) = $285. One Time (no "
        "discount, no adjustment). Tax 4.5% on $285 = $12.825 → $12.83 "
        "(ROUND_HALF_UP on exact half, rounds up)."
    ),
)


F8_2R1BA_PREMIUM_LAUNDRY_BIWEEKLY_ADJ_NEG_TAX = PricingFixture(
    name="derived_2r1ba_premium_laundry_biweekly10_adj_negative_tax45",
    service_config=ServiceConfig(
        tier="premium", bedrooms=2, bathrooms=1,
        base_price=Decimal("500.00"),
    ),
    extras=(
        ExtraInput(name="Load of laundry", price=Decimal("25.00"), qty=1),
    ),
    frequency=FrequencyInput(name="Biweekly", discount_pct=Decimal("10.00")),
    adjustment=Decimal("-20.00"),
    tax_pct=Decimal("4.50"),
    expected=ExpectedPricing(
        subtotal=Decimal("525.00"),
        discount_amount=Decimal("52.50"),
        adjustment_amount=Decimal("-20.00"),
        amount_before_tax=Decimal("452.50"),
        tax_amount=Decimal("20.36"),
        final_amount=Decimal("472.86"),
    ),
    source_note=(
        "DERIVED. 2R×1BA Premium ($500) + Laundry ($25) = $525. Biweekly 10% "
        "= $52.50 discount. Negative adjustment -$20 (e.g. goodwill refund). "
        "Tax on $452.50 × 4.5% = $20.3625 → $20.36 (0.3625 < 0.5 rounds down)."
    ),
)


F9_1R1BA_BASIC_ONETIME_NOTAX_DALLAS = PricingFixture(
    name="derived_1r1ba_basic_onetime_no_tax_dallas",
    service_config=ServiceConfig(
        tier="basic", bedrooms=1, bathrooms=1,
        base_price=Decimal("155.00"),
    ),
    extras=(),
    frequency=FrequencyInput(name="One Time", discount_pct=Decimal("0.00")),
    adjustment=Decimal("0.00"),
    tax_pct=Decimal("0.00"),  # Dallas has no cleaning_sales_taxes row yet
    expected=ExpectedPricing(
        subtotal=Decimal("155.00"),
        discount_amount=Decimal("0.00"),
        adjustment_amount=Decimal("0.00"),
        amount_before_tax=Decimal("155.00"),
        tax_amount=Decimal("0.00"),
        final_amount=Decimal("155.00"),
    ),
    source_note=(
        "DERIVED. 1R×1BA Basic ($155). One Time + no extras + no adjustment. "
        "Tax 0% (Dallas location — no sales tax row configured yet in "
        "cleaning_sales_taxes). Validates tax fallback behavior: missing tax "
        "config → 0% with warning (ADR-001 Error handling)."
    ),
)


F10_3R1BA_DEEP_2EXTRAS_MONTHLY_ADJ_POS_TAX = PricingFixture(
    name="derived_3r1ba_deep_fridge_movein_monthly5_adj_positive_tax45",
    service_config=ServiceConfig(
        tier="deep", bedrooms=3, bathrooms=1,
        base_price=Decimal("420.00"),
    ),
    extras=(
        ExtraInput(name="Inside the fridge", price=Decimal("25.00"), qty=1),
        ExtraInput(name="Move in move out", price=Decimal("25.00"), qty=1),
    ),
    frequency=FrequencyInput(name="Monthly", discount_pct=Decimal("5.00")),
    adjustment=Decimal("15.00"),
    tax_pct=Decimal("4.50"),
    expected=ExpectedPricing(
        subtotal=Decimal("470.00"),
        discount_amount=Decimal("23.50"),
        adjustment_amount=Decimal("15.00"),
        amount_before_tax=Decimal("461.50"),
        tax_amount=Decimal("20.77"),
        final_amount=Decimal("482.27"),
    ),
    source_note=(
        "DERIVED. 3R×1BA Deep ($420) + Fridge ($25) + Move in/out ($25) = "
        "$470. Monthly 5% = $23.50 discount. Positive adjustment +$15 (small "
        "surcharge). Tax on (470 − 23.50 + 15) = $461.50 × 4.5% = $20.7675 "
        "→ $20.77."
    ),
)


# ---------------------------------------------------------------------------
# Exported list (consumed by test_pricing_engine.py parametrize)
# ---------------------------------------------------------------------------

LAUNCH27_3SISTERS_BOOKINGS: tuple[PricingFixture, ...] = (
    F1_REAL_240_01,
    F2_STUDIO_BASIC_ONETIME_TAX,
    F3_STUDIO_PREMIUM_OVEN_WEEKLY_TAX,
    F4_1R1BA_DEEP_2EXTRAS_BIWEEKLY_TAX,
    F5_2R2BA_BASIC_MONTHLY_ADJ_POS_TAX,
    F6_3R1BA_PREMIUM_3EXTRAS_WEEKLY_TAX,
    F7_STUDIO_DEEP_WALLS_ONETIME_TAX,
    F8_2R1BA_PREMIUM_LAUNDRY_BIWEEKLY_ADJ_NEG_TAX,
    F9_1R1BA_BASIC_ONETIME_NOTAX_DALLAS,
    F10_3R1BA_DEEP_2EXTRAS_MONTHLY_ADJ_POS_TAX,
)


# ---------------------------------------------------------------------------
# Coverage matrix (for strategy doc reference)
# ---------------------------------------------------------------------------
# Tier       : Basic=4, Deep=3, Premium=3  (all tiers ≥2)
# Frequency  : One Time=3, Weekly=3, Biweekly=2, Monthly=2  (all ≥2)
# Extras     : 0 extras=3, 1 extra=4, 2+ extras=3
# Adjustment : negative=2, zero=6, positive=2
# Tax        : 4.5% NYC=9, 0% Dallas=1
# Service    : Studio=3, 1R×1BA=2, 2R×1BA=2, 2R×2BA=1, 3R×1BA=2
# Provenance : REAL=1, DERIVED=9
# ---------------------------------------------------------------------------


if __name__ == "__main__":
    """Self-validation: recompute expected values and compare."""
    from decimal import ROUND_HALF_UP

    def verify(f: PricingFixture) -> tuple[bool, str]:
        # Canonical computation (ADR-001)
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

        checks = [
            ("subtotal", f.expected.subtotal, subtotal),
            ("discount", f.expected.discount_amount, discount),
            ("before_tax", f.expected.amount_before_tax, before_tax),
            ("tax", f.expected.tax_amount, tax),
            ("final", f.expected.final_amount, final),
        ]
        errors = [f"{name}: expected={exp} got={got}"
                  for name, exp, got in checks if exp != got]
        return (not errors), "; ".join(errors) or "OK"

    print(f"Validating {len(LAUNCH27_3SISTERS_BOOKINGS)} fixtures...")
    all_pass = True
    for fix in LAUNCH27_3SISTERS_BOOKINGS:
        ok, msg = verify(fix)
        status = "✓" if ok else "✗"
        print(f"  {status} {fix.name}: {msg}")
        all_pass &= ok

    if all_pass:
        print("\nAll 10 fixtures pass canonical validation.")
    else:
        print("\n⚠️  Fixture validation FAILED — review ORDER OF OPERATIONS.")
        raise SystemExit(1)
