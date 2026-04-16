"""
Xcleaners — Pricing Engine (Story 1.1, ADR-001)

Canonical pricing calculation for cleaning bookings. Implements the hybrid
formula + override model with immutable snapshot output.

Canonical order of operations (ADR-001 Decisions 5/6/7):
    1. service_amount = override_price OR
                        (base + bedrooms*α + bathrooms*β) × tier_multiplier
    2. extras_sum    = Σ(extra.price × extra.qty)           [flat, NOT tiered]
    3. subtotal      = service_amount + extras_sum
    4. discount_amount = ROUND_HALF_UP(subtotal * discount_pct / 100, 2)
    5. amount_before_tax = subtotal - discount_amount + adjustment_amount
    6. tax_amount    = ROUND_HALF_UP(amount_before_tax * tax_pct / 100, 2)
    7. final_amount  = amount_before_tax + tax_amount

Gate AC7: 10 Launch27 3Sisters fixtures match within ±$0.01 tolerance.

Usage (from booking creation flow):

    from app.modules.cleaning.services.pricing_engine import (
        calculate_booking_price,
        PricingConfigError,
    )

    breakdown = await calculate_booking_price(
        business_id=business_uuid,
        service_id=service_uuid,
        tier="basic",                              # 'basic'|'deep'|'premium'
        extras=[{"extra_id": uuid, "qty": 1}],     # from booking form
        frequency_id=frequency_uuid,                # None for no discount
        adjustment_amount=Decimal("-29.58"),        # signed; 0 if none
        adjustment_reason="Complaint refund",       # optional free-text
        location_id=location_uuid,                  # for tax lookup
        db=db,
    )

    # breakdown matches cleaning_bookings.price_snapshot JSONB schema.
    # Persist:
    await db.pool.execute(
        "UPDATE cleaning_bookings SET "
        "  final_price = $1, discount_amount = $2, tax_amount = $3, "
        "  adjustment_amount = $4, adjustment_reason = $5, "
        "  frequency_id = $6, location_id = $7, price_snapshot = $8::jsonb "
        "WHERE id = $9",
        breakdown['final_amount'],
        breakdown['discount_amount'],
        breakdown['tax_amount'],
        breakdown['adjustment_amount'],
        breakdown['adjustment_reason'],
        frequency_id,
        location_id,
        json.dumps(breakdown, default=str),
        booking_id,
    )

References:
    - docs/architecture/adr-001-pricing-engine-hybrid.md
    - docs/stories/1.1.pricing-engine-hybrid.md
    - docs/qa/story-1.1-test-strategy.md
    - database/migrations/021_pricing_engine_hybrid.sql

Tables consumed:
    - cleaning_services (tier, bedrooms, bathrooms)
    - cleaning_service_overrides (tier-specific price overrides)
    - cleaning_pricing_formulas (formula per business + optional location)
    - cleaning_extras (catalog of add-ons, flat prices)
    - cleaning_frequencies (recurring discount catalog)
    - cleaning_sales_taxes (temporal tax rate per location)

Author: @dev (Neo), 2026-04-16
"""

from __future__ import annotations

import json
import logging
from datetime import date as date_cls, datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Literal, TypedDict
from uuid import UUID

from app.database import Database


logger = logging.getLogger("xcleaners.pricing_engine")


# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------

Tier = Literal["basic", "deep", "premium"]


class PricingConfigError(Exception):
    """
    Raised when pricing configuration is missing or invalid.

    Examples:
        - No active formula for business AND no override for (service, tier)
        - Service not found
        - Invalid tier not in ('basic', 'deep', 'premium')
    """


class ExtraSnapshot(TypedDict):
    """One extra as persisted in the booking snapshot."""
    extra_id: str | None      # UUID as string, None if extra deleted later
    name: str
    qty: int
    price: Decimal


class PriceBreakdown(TypedDict, total=False):
    """
    Complete pricing breakdown (ADR-001 Decision 2 schema).

    Total=False: consumers may pick subsets; all keys are set on success.
    """
    formula_id: str | None
    service_id: str
    tier: str
    tier_multiplier: Decimal
    base_amount: Decimal
    bedrooms: int
    bedroom_delta: Decimal
    bathrooms: int
    bathroom_delta: Decimal
    override_applied: bool
    subtotal_service: Decimal
    extras: list[ExtraSnapshot]
    extras_sum: Decimal
    subtotal: Decimal
    frequency_id: str | None
    frequency_name: str | None
    discount_pct: Decimal
    discount_amount: Decimal
    adjustment_amount: Decimal
    adjustment_reason: str | None
    amount_before_tax: Decimal
    tax_pct: Decimal
    tax_amount: Decimal
    final_amount: Decimal
    calculated_at: str  # ISO 8601 UTC


# ---------------------------------------------------------------------------
# Helpers (private)
# ---------------------------------------------------------------------------

_VALID_TIERS: tuple[str, ...] = ("basic", "deep", "premium")


def _round_money(value: Decimal) -> Decimal:
    """Quantize to 2 decimal places with ROUND_HALF_UP (USD money convention)."""
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _to_decimal(value: Any) -> Decimal:
    """Convert any numeric value to Decimal safely (str roundtrip prevents float drift)."""
    if isinstance(value, Decimal):
        return value
    if value is None:
        return Decimal("0")
    return Decimal(str(value))


def _parse_tier_multipliers(raw: Any) -> dict[str, Decimal]:
    """
    Parse tier_multipliers from asyncpg row.

    asyncpg returns JSONB either as dict (most drivers) or as JSON string
    (older versions / specific codec settings). Normalize to dict[str, Decimal].
    """
    if raw is None:
        return {"basic": Decimal("1.0"), "deep": Decimal("1.8"), "premium": Decimal("2.8")}
    if isinstance(raw, str):
        raw = json.loads(raw)
    if not isinstance(raw, dict):
        raise PricingConfigError(
            f"tier_multipliers must be a JSON object; got {type(raw).__name__}"
        )
    return {str(k).lower(): _to_decimal(v) for k, v in raw.items()}


# ---------------------------------------------------------------------------
# Data loaders (private)
# ---------------------------------------------------------------------------

async def _get_service(db: Database, service_id: UUID) -> dict | None:
    """Fetch service basic fields (tier/BR/BA used for formula)."""
    return await db.pool.fetchrow(
        """
        SELECT id, business_id, name, tier, bedrooms, bathrooms, base_price
        FROM cleaning_services
        WHERE id = $1
        """,
        service_id,
    )


async def _get_override(db: Database, service_id: UUID, tier: str) -> dict | None:
    """Fetch active override for (service_id, tier), if exists."""
    return await db.pool.fetchrow(
        """
        SELECT id, price_override, reason
        FROM cleaning_service_overrides
        WHERE service_id = $1 AND tier = $2 AND is_active = TRUE
        LIMIT 1
        """,
        service_id, tier,
    )


async def _get_active_formula(
    db: Database, business_id: UUID, location_id: UUID | None
) -> dict | None:
    """
    Fetch active formula for business.

    Precedence:
      1. Location-specific formula (location_id matches)
      2. Business default (location_id IS NULL)

    Returns None if neither exists.
    """
    if location_id is not None:
        row = await db.pool.fetchrow(
            """
            SELECT id, base_amount, bedroom_delta, bathroom_delta, tier_multipliers
            FROM cleaning_pricing_formulas
            WHERE business_id = $1 AND location_id = $2 AND is_active = TRUE
            ORDER BY updated_at DESC
            LIMIT 1
            """,
            business_id, location_id,
        )
        if row:
            return row

    return await db.pool.fetchrow(
        """
        SELECT id, base_amount, bedroom_delta, bathroom_delta, tier_multipliers
        FROM cleaning_pricing_formulas
        WHERE business_id = $1 AND location_id IS NULL AND is_active = TRUE
        ORDER BY updated_at DESC
        LIMIT 1
        """,
        business_id,
    )


async def _get_frequency(db: Database, frequency_id: UUID | None) -> dict | None:
    """Fetch frequency row by id, or None if no frequency selected."""
    if frequency_id is None:
        return None
    return await db.pool.fetchrow(
        "SELECT id, name, discount_pct FROM cleaning_frequencies WHERE id = $1",
        frequency_id,
    )


async def _get_tax_pct(
    db: Database,
    location_id: UUID | None,
    as_of_date: date_cls | None = None,
) -> Decimal:
    """
    Fetch most recent effective sales tax rate for location as of a given date.

    Fix F-001: the effective_date filter uses `as_of_date` (booking's
    scheduled_date), NOT CURRENT_DATE. This preserves historical correctness
    when a tax rate changed between booking creation and service execution —
    the rate applicable is the one in effect on the date the service is/was
    rendered, per US sales tax rules.

    Args:
      db: Database wrapper.
      location_id: cleaning_areas row; None triggers graceful fallback.
      as_of_date: reference date for tax lookup. Defaults to today (UTC)
                  when None, preserving legacy preview-style behavior.

    Returns:
      Decimal tax percentage. Decimal('0') with warning log if:
        - location_id is None
        - no active tax row exists for location at or before `as_of_date`
    """
    if location_id is None:
        logger.warning("pricing_engine: location_id missing; tax_pct=0")
        return Decimal("0")

    reference_date = as_of_date if as_of_date is not None else datetime.now(timezone.utc).date()

    row = await db.pool.fetchrow(
        """
        SELECT tax_pct
        FROM cleaning_sales_taxes
        WHERE location_id = $1
          AND is_archived = FALSE
          AND effective_date <= $2
        ORDER BY effective_date DESC
        LIMIT 1
        """,
        location_id,
        reference_date,
    )
    if row is None:
        logger.warning(
            "pricing_engine: no sales_tax row for location_id=%s as_of=%s; tax_pct=0",
            location_id,
            reference_date,
        )
        return Decimal("0")
    return _to_decimal(row["tax_pct"])


async def _load_extras_with_prices(
    db: Database, extras_input: list[dict]
) -> list[ExtraSnapshot]:
    """
    Given user-selected extras `[{extra_id, qty}]`, fetch current catalog price
    and return snapshot list (name + price preserved at this calculation time).

    Extras not found in catalog are skipped with warning log (no hard failure —
    cleaning_extras row may have been archived).
    """
    snapshots: list[ExtraSnapshot] = []
    for item in extras_input:
        extra_id = item.get("extra_id")
        try:
            qty = int(item.get("qty", 1))
        except (TypeError, ValueError):
            qty = 1
        if extra_id is None or qty < 1:
            continue
        row = await db.pool.fetchrow(
            "SELECT id, name, price FROM cleaning_extras WHERE id = $1",
            extra_id,
        )
        if row is None:
            logger.warning(
                "pricing_engine: extra_id=%s not found in cleaning_extras; skipping",
                extra_id,
            )
            continue
        snapshots.append({
            "extra_id": str(row["id"]),
            "name": row["name"],
            "qty": qty,
            "price": _to_decimal(row["price"]),
        })
    return snapshots


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def calculate_booking_price(
    business_id: UUID,
    service_id: UUID | None,
    tier: Tier | str,
    extras: list[dict],
    frequency_id: UUID | None,
    adjustment_amount: Decimal | int | float | str = Decimal("0"),
    adjustment_reason: str | None = None,
    location_id: UUID | None = None,
    scheduled_date: date_cls | str | None = None,
    service_metadata: dict | None = None,
    db: Database | None = None,
) -> PriceBreakdown:
    """
    Compute booking price per ADR-001 canonical order of operations.

    Args:
        business_id: tenant scope for formula + frequencies lookup.
        service_id: cleaning_services row; provides BR/BA for formula base.
            Pass `None` together with `service_metadata` to compute a preview
            without a persisted service (e.g., owner creating a new service).
            When None, override lookup is skipped (no service_id to key on).
        tier: 'basic' | 'deep' | 'premium' (controls tier_multiplier OR override lookup).
        extras: list of `{extra_id: UUID, qty: int}` — resolved against cleaning_extras.
        frequency_id: cleaning_frequencies row; None => 0% discount.
        adjustment_amount: signed manual adjustment applied BEFORE tax.
        adjustment_reason: free-text for audit (persisted in breakdown).
        location_id: cleaning_areas row; used for tax lookup + location-specific formula.
        scheduled_date: booking's scheduled service date for historical tax lookup
            (Fix F-001). Accepts date or ISO-8601 str ('YYYY-MM-DD'). Defaults to
            today (UTC) when None — preview-style lookup.
        service_metadata: required when service_id is None. Dict with keys
            `{bedrooms: int, bathrooms: int}`. Used to compute formula base
            without touching cleaning_services. Preview endpoints pass this
            to render prices for services not yet persisted.
        db: Database instance (asyncpg pool wrapper).

    Returns:
        PriceBreakdown dict ready for cleaning_bookings.price_snapshot JSONB.

    Raises:
        PricingConfigError: service missing, invalid tier, OR (no override AND no formula).

    Canonical calculation order:
        subtotal → discount → adjustment → tax → final

    Ref: docs/architecture/adr-001-pricing-engine-hybrid.md
    """
    if db is None:
        raise ValueError("Database instance required (db= kwarg)")

    # Normalize tier
    tier_lower = (tier or "").lower() if isinstance(tier, str) else "basic"
    if tier_lower not in _VALID_TIERS:
        raise PricingConfigError(
            f"Invalid tier '{tier}'. Must be one of {_VALID_TIERS}."
        )

    # Normalize scheduled_date (F-001): accept date, ISO str, or None
    as_of_date: date_cls | None
    if scheduled_date is None:
        as_of_date = None
    elif isinstance(scheduled_date, date_cls) and not isinstance(scheduled_date, datetime):
        as_of_date = scheduled_date
    elif isinstance(scheduled_date, datetime):
        as_of_date = scheduled_date.date()
    elif isinstance(scheduled_date, str):
        try:
            as_of_date = date_cls.fromisoformat(scheduled_date[:10])
        except ValueError as exc:
            raise PricingConfigError(
                f"Invalid scheduled_date '{scheduled_date}'. Expected ISO-8601 YYYY-MM-DD."
            ) from exc
    else:
        raise PricingConfigError(
            f"Invalid scheduled_date type {type(scheduled_date).__name__}; "
            f"expected date, str, or None."
        )

    adjustment = _to_decimal(adjustment_amount)

    # ------- Step 0: resolve service inputs --------------------------------
    # Two paths:
    #   A. service_id provided  → fetch cleaning_services row (canonical path)
    #   B. service_id is None   → require service_metadata (preview mode —
    #      used by the preview endpoint when owner is creating a service
    #      that does not exist in the DB yet). Override lookup is skipped
    #      because there is no service_id to key on.
    override = None
    if service_id is not None:
        service = await _get_service(db, service_id)
        if service is None:
            raise PricingConfigError(
                f"Service not found: service_id={service_id}, business_id={business_id}"
            )
        bedrooms = int(service["bedrooms"] or 0)
        bathrooms = int(service["bathrooms"] or 0)
        override = await _get_override(db, service_id, tier_lower)
    else:
        if not isinstance(service_metadata, dict):
            raise PricingConfigError(
                "service_id is None — service_metadata dict required "
                "with keys {bedrooms, bathrooms} to compute preview."
            )
        try:
            bedrooms = int(service_metadata.get("bedrooms", 0) or 0)
            bathrooms = int(service_metadata.get("bathrooms", 0) or 0)
        except (TypeError, ValueError) as exc:
            raise PricingConfigError(
                f"service_metadata.bedrooms and .bathrooms must be integers; "
                f"got {service_metadata}"
            ) from exc
        # Override lookup skipped — no service_id

    formula_id: str | None = None
    base_amount = Decimal("0")
    bedroom_delta = Decimal("0")
    bathroom_delta = Decimal("0")
    tier_multiplier = Decimal("1.0")

    if override:
        service_amount = _to_decimal(override["price_override"])
        override_applied = True
        # For snapshot transparency, report override as base_amount too
        base_amount = service_amount
    else:
        formula = await _get_active_formula(db, business_id, location_id)
        if formula is None:
            raise PricingConfigError(
                f"No active pricing formula found for business_id={business_id}. "
                f"Cannot compute service_amount without override OR formula. "
                f"(service_id={service_id}, tier={tier_lower})"
            )
        formula_id = str(formula["id"])
        base_amount = _to_decimal(formula["base_amount"])
        bedroom_delta = _to_decimal(formula["bedroom_delta"])
        bathroom_delta = _to_decimal(formula["bathroom_delta"])
        multipliers = _parse_tier_multipliers(formula["tier_multipliers"])
        tier_multiplier = multipliers.get(tier_lower, Decimal("1.0"))
        service_amount = (
            base_amount
            + (Decimal(bedrooms) * bedroom_delta)
            + (Decimal(bathrooms) * bathroom_delta)
        ) * tier_multiplier
        override_applied = False

    # ------- Step 2: extras_sum (flat, NOT affected by tier_multiplier) ----
    extras_snapshots = await _load_extras_with_prices(db, extras)
    extras_sum = Decimal("0")
    for e in extras_snapshots:
        extras_sum += e["price"] * Decimal(e["qty"])

    # ------- Step 3: subtotal ---------------------------------------------
    subtotal = service_amount + extras_sum

    # ------- Step 4: frequency discount -----------------------------------
    freq = await _get_frequency(db, frequency_id)
    if freq:
        discount_pct = _to_decimal(freq["discount_pct"])
        freq_name = freq["name"]
    else:
        discount_pct = Decimal("0")
        freq_name = None

    discount_amount = _round_money(subtotal * discount_pct / Decimal("100"))

    # ------- Step 5: amount_before_tax (adjustment applied BEFORE tax) -----
    amount_before_tax = subtotal - discount_amount + adjustment

    # ------- Step 6: tax (on liquid base — ADR Decision 6) -----------------
    # F-001: use scheduled_date for historical tax lookup (not CURRENT_DATE)
    tax_pct = await _get_tax_pct(db, location_id, as_of_date)
    tax_amount = _round_money(amount_before_tax * tax_pct / Decimal("100"))

    # ------- Step 7: final -----------------------------------------------
    final_amount = amount_before_tax + tax_amount

    breakdown: PriceBreakdown = {
        "formula_id": formula_id,
        "service_id": str(service_id) if service_id is not None else None,
        "tier": tier_lower,
        "tier_multiplier": tier_multiplier,
        "base_amount": base_amount,
        "bedrooms": bedrooms,
        "bedroom_delta": bedroom_delta,
        "bathrooms": bathrooms,
        "bathroom_delta": bathroom_delta,
        "override_applied": override_applied,
        "subtotal_service": service_amount,
        "extras": extras_snapshots,
        "extras_sum": extras_sum,
        "subtotal": subtotal,
        "frequency_id": str(frequency_id) if frequency_id else None,
        "frequency_name": freq_name,
        "discount_pct": discount_pct,
        "discount_amount": discount_amount,
        "adjustment_amount": adjustment,
        "adjustment_reason": adjustment_reason,
        "amount_before_tax": amount_before_tax,
        "tax_pct": tax_pct,
        "tax_amount": tax_amount,
        "final_amount": final_amount,
        "calculated_at": datetime.now(timezone.utc).isoformat(),
    }

    logger.info(
        "pricing_engine: business=%s service=%s tier=%s "
        "subtotal=%s disc=%s adj=%s tax=%s final=%s override=%s",
        business_id, service_id, tier_lower,
        subtotal, discount_amount, adjustment, tax_amount,
        final_amount, override_applied,
    )

    return breakdown


# ---------------------------------------------------------------------------
# Serialization helpers (for JSONB persistence)
# ---------------------------------------------------------------------------

def breakdown_to_jsonb(breakdown: PriceBreakdown) -> str:
    """
    Serialize PriceBreakdown to JSON string for PostgreSQL JSONB storage.

    Decimal values are stringified (preserves exact precision — ADR-001
    Decision 2 immutability requires no float coercion).
    """
    def _encode(o: Any) -> Any:
        if isinstance(o, Decimal):
            return str(o)
        if isinstance(o, UUID):
            return str(o)
        if isinstance(o, datetime):
            return o.isoformat()
        raise TypeError(f"Object of type {type(o).__name__} is not JSON serializable")

    return json.dumps(breakdown, default=_encode)
