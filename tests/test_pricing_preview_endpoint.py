"""
Pricing Preview Endpoint Tests — Story 1.1 Task 3 (C2).

Tests both the Pydantic validation layer (unit) and the route handler
(integration with real DB, exercising pricing_engine end-to-end).

The route handler is invoked DIRECTLY (not via HTTP TestClient) so we can
reuse the existing `db` fixture and avoid standing up the full FastAPI
app + middleware stack for each test. HTTP-level concerns (auth,
rate-limit) are tested in Playwright/e2e suites later.

Author: @dev (Neo), 2026-04-16 (Sprint Plan Fase C, Sessão C2)
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException
from pydantic import ValidationError


pytest.importorskip(
    "app.modules.cleaning.models.pricing",
    reason="Pricing preview models not yet implemented.",
)
pytest.importorskip(
    "app.modules.cleaning.routes.pricing_routes",
    reason="Pricing preview route not yet implemented.",
)

from app.modules.cleaning.models.pricing import (  # noqa: E402
    ExtraSelection,
    PricingPreviewRequest,
    ServiceMetadata,
    _fmt_money,
    format_breakdown,
    stringify_decimals,
)
from app.modules.cleaning.routes.pricing_routes import preview_pricing  # noqa: E402


# ===========================================================================
# Shared DB fixtures (mirror test_pricing_engine.py)
# ===========================================================================


@pytest.fixture
async def test_business_id(db):
    business_id = await db.pool.fetchval(
        "INSERT INTO businesses (slug, name) "
        "VALUES ('test_preview_biz_' || gen_random_uuid()::text, 'Preview Test Biz') "
        "RETURNING id"
    )
    yield business_id
    await db.pool.execute("DELETE FROM businesses WHERE id = $1", business_id)


@pytest.fixture
async def test_location_id(db, test_business_id):
    return await db.pool.fetchval(
        "INSERT INTO cleaning_areas (business_id, name, zip_codes, is_default) "
        "VALUES ($1, 'Preview NYC', ARRAY['10001'], TRUE) "
        "RETURNING id",
        test_business_id,
    )


@pytest.fixture
async def test_formula(db, test_business_id):
    return await db.pool.fetchval(
        """
        INSERT INTO cleaning_pricing_formulas
            (business_id, name, base_amount, bedroom_delta, bathroom_delta,
             tier_multipliers, is_active)
        VALUES ($1, 'Standard Preview', 115.00, 20.00, 15.00,
                '{"basic": 1.0, "deep": 1.8, "premium": 2.8}'::jsonb, TRUE)
        RETURNING id
        """,
        test_business_id,
    )


# ===========================================================================
# Unit — Pydantic validation
# ===========================================================================


def test_request_requires_service_id_or_metadata():
    """Empty payload (no service_id, no metadata) must fail at validation."""
    with pytest.raises(ValidationError, match=r".*service_id.*service_metadata.*"):
        PricingPreviewRequest(tier="basic", extras=[])


def test_request_accepts_service_id_only():
    """service_id without metadata is valid (canonical path)."""
    req = PricingPreviewRequest(
        service_id=str(uuid4()),
        tier="basic",
        extras=[],
    )
    assert req.service_id is not None
    assert req.service_metadata is None


def test_request_accepts_metadata_only():
    """service_metadata without service_id is valid (preview mode)."""
    req = PricingPreviewRequest(
        service_metadata=ServiceMetadata(tier="deep", bedrooms=2, bathrooms=1),
        tier="deep",
        extras=[],
    )
    assert req.service_id is None
    assert req.service_metadata.tier == "deep"
    assert req.service_metadata.bedrooms == 2


def test_request_rejects_invalid_tier():
    """Tier outside ('basic','deep','premium') is rejected by Literal type."""
    with pytest.raises(ValidationError):
        PricingPreviewRequest(
            service_id=str(uuid4()),
            tier="platinum",  # type: ignore[arg-type]
            extras=[],
        )


def test_request_rejects_bad_scheduled_date():
    """scheduled_date must be ISO-8601 YYYY-MM-DD."""
    with pytest.raises(ValidationError, match=r".*ISO-8601.*"):
        PricingPreviewRequest(
            service_id=str(uuid4()),
            tier="basic",
            scheduled_date="05/15/2026",
        )


def test_request_rejects_bad_extra_qty():
    """qty < 1 rejected by ge=1 constraint."""
    with pytest.raises(ValidationError):
        ExtraSelection(extra_id=str(uuid4()), qty=0)


# ===========================================================================
# Unit — formatting helpers
# ===========================================================================


def test_fmt_money_handles_positive_negative_none():
    assert _fmt_money(Decimal("240.01")) == "$240.01"
    assert _fmt_money(Decimal("-29.58")) == "-$29.58"
    assert _fmt_money(None) == "$--.--"
    assert _fmt_money("1234.5") == "$1,234.50"


def test_format_breakdown_wires_all_fields():
    fake = {
        "subtotal": Decimal("305.00"),
        "discount_amount": Decimal("45.75"),
        "adjustment_amount": Decimal("-29.58"),
        "amount_before_tax": Decimal("229.67"),
        "tax_amount": Decimal("10.34"),
        "final_amount": Decimal("240.01"),
    }
    f = format_breakdown(fake)
    assert f.subtotal == "$305.00"
    assert f.discount == "$45.75"
    assert f.adjustment == "-$29.58"
    assert f.amount_before_tax == "$229.67"
    assert f.tax == "$10.34"
    assert f.final == "$240.01"


def test_stringify_decimals_preserves_ints_strings_booleans():
    raw = {
        "final_amount": Decimal("240.01"),
        "bedrooms": 2,
        "tier": "basic",
        "override_applied": True,
        "extras": [
            {"extra_id": "abc", "price": Decimal("30.00"), "qty": 1, "name": "Stairs"}
        ],
    }
    out = stringify_decimals(raw)
    assert out["final_amount"] == "240.01"
    assert out["bedrooms"] == 2
    assert out["tier"] == "basic"
    assert out["override_applied"] is True
    assert out["extras"][0]["price"] == "30.00"
    assert out["extras"][0]["qty"] == 1


# ===========================================================================
# Integration — route handler with DB
# ===========================================================================


def _make_user(business_id: UUID) -> dict:
    """Build the enriched user dict that require_role would return."""
    return {
        "user_id": str(uuid4()),
        "email": "test-preview@example.com",
        "role": "lead",
        "cleaning_role": "owner",
        "business_id": business_id,
        "business_slug": "test-preview",
    }


@pytest.mark.asyncio
async def test_preview_with_service_id_replays_f1_240_01(
    db, test_business_id, test_location_id, test_formula
):
    """F1 real fixture replay via endpoint: $240.01 final."""
    # Set up: service with override $275, stairs extra $30, Weekly 15%, NYC 4.5%
    service_id = await db.pool.fetchval(
        "INSERT INTO cleaning_services (business_id, name, slug, tier, "
        "bedrooms, bathrooms, base_price) "
        "VALUES ($1, 'Preview F1', 'preview-f1', 'basic', 2, 1, 275.00) "
        "RETURNING id",
        test_business_id,
    )
    await db.pool.execute(
        "INSERT INTO cleaning_service_overrides (service_id, tier, price_override, is_active) "
        "VALUES ($1, 'basic', 275.00, TRUE)",
        service_id,
    )
    extra_id = await db.pool.fetchval(
        "INSERT INTO cleaning_extras (business_id, name, price) "
        "VALUES ($1, 'Preview Stairs', 30.00) RETURNING id",
        test_business_id,
    )
    await db.pool.execute(
        "INSERT INTO cleaning_service_extras (service_id, extra_id) VALUES ($1, $2)",
        service_id, extra_id,
    )
    freq_id = await db.pool.fetchval(
        "INSERT INTO cleaning_frequencies (business_id, name, discount_pct) "
        "VALUES ($1, 'Preview Weekly', 15.00) RETURNING id",
        test_business_id,
    )
    await db.pool.execute(
        "INSERT INTO cleaning_sales_taxes (business_id, location_id, tax_pct, effective_date) "
        "VALUES ($1, $2, 4.50, CURRENT_DATE - INTERVAL '1 day')",
        test_business_id, test_location_id,
    )

    body = PricingPreviewRequest(
        service_id=str(service_id),
        tier="basic",
        extras=[ExtraSelection(extra_id=str(extra_id), qty=1)],
        frequency_id=str(freq_id),
        adjustment_amount=Decimal("-29.58"),
        adjustment_reason="Complaint refund",
        location_id=str(test_location_id),
        scheduled_date="2026-05-15",
    )

    response = await preview_pricing(
        slug="test-preview",
        body=body,
        user=_make_user(test_business_id),
        db=db,
    )

    assert response.formatted.final == "$240.01"
    assert response.formatted.subtotal == "$305.00"
    assert response.formatted.discount == "$45.75"
    assert response.formatted.adjustment == "-$29.58"
    assert response.formatted.amount_before_tax == "$229.67"
    assert response.formatted.tax == "$10.34"
    assert response.breakdown["final_amount"] == "240.01"
    assert response.breakdown["override_applied"] is True
    assert response.breakdown["service_id"] == str(service_id)


@pytest.mark.asyncio
async def test_preview_with_metadata_no_service_id(
    db, test_business_id, test_location_id, test_formula
):
    """
    Preview during service creation: no service_id, metadata drives formula.

    Standard formula: (115 + 2*20 + 1*15) × 1.0 = $170 (basic tier).
    """
    body = PricingPreviewRequest(
        service_metadata=ServiceMetadata(tier="basic", bedrooms=2, bathrooms=1),
        tier="basic",  # redundant but accepted
        extras=[],
        frequency_id=None,
        adjustment_amount=Decimal("0"),
        location_id=str(test_location_id),
    )

    response = await preview_pricing(
        slug="test-preview",
        body=body,
        user=_make_user(test_business_id),
        db=db,
    )

    # Formula path — no override available (no service_id)
    assert response.breakdown["service_id"] is None
    assert response.breakdown["override_applied"] is False
    # Engine keeps Decimal precision on subtotal (no round until discount/tax)
    assert Decimal(response.breakdown["subtotal"]) == Decimal("170.00")
    # Formatted output rounds to 2 decimals for display
    assert response.formatted.subtotal == "$170.00"
    assert response.formatted.final == "$170.00"  # no tax config → 0; no discount


@pytest.mark.asyncio
async def test_preview_missing_formula_returns_400(
    db, test_business_id, test_location_id
):
    """
    Business without active formula AND no override (metadata path) → 400.
    """
    body = PricingPreviewRequest(
        service_metadata=ServiceMetadata(tier="basic", bedrooms=1, bathrooms=1),
        tier="basic",
        extras=[],
        location_id=str(test_location_id),
    )

    with pytest.raises(HTTPException) as excinfo:
        await preview_pricing(
            slug="test-preview",
            body=body,
            user=_make_user(test_business_id),
            db=db,
        )
    assert excinfo.value.status_code == 400
    # Smith B4 sanitized detail — still mentions "configuration" or "formula"
    detail = excinfo.value.detail.lower()
    assert "formula" in detail or "configuration" in detail


@pytest.mark.asyncio
async def test_preview_invalid_service_id_returns_400(
    db, test_business_id, test_location_id, test_formula
):
    """Nonexistent service_id bubbles PricingConfigError → HTTP 400."""
    body = PricingPreviewRequest(
        service_id=str(uuid4()),  # not in DB
        tier="basic",
        extras=[],
        location_id=str(test_location_id),
    )

    with pytest.raises(HTTPException) as excinfo:
        await preview_pricing(
            slug="test-preview",
            body=body,
            user=_make_user(test_business_id),
            db=db,
        )
    assert excinfo.value.status_code == 400
    assert "service not found" in excinfo.value.detail.lower()
