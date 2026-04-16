"""
Xcleaners — Pricing Pydantic Models (Story 1.1 Task 3).

Request/response schemas for the preview endpoint
    POST /api/v1/clean/{slug}/pricing/preview

Accepts two modes:
  A. service_id provided      → pricing_engine fetches service from DB
                                 (applies override if configured)
  B. service_id is None +     → pricing_engine uses service_metadata
     service_metadata passed    (no override; used during service creation
                                 flow — service does not exist in DB yet)

The endpoint keeps all compute in pricing_engine.calculate_booking_price;
this file only defines shapes + light validation.

Author: @dev (Neo), 2026-04-16 (Sprint Plan Fase C, Sessão C2)
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


# ---------------------------------------------------------------------------
# Request
# ---------------------------------------------------------------------------


class ExtraSelection(BaseModel):
    """One selected extra for preview."""

    extra_id: str = Field(..., description="cleaning_extras.id UUID")
    qty: int = Field(default=1, ge=1, description="Qty (must be >= 1)")


class ServiceMetadata(BaseModel):
    """
    Minimal service shape for preview when no service_id exists yet.

    Used when owner is creating a new service and wants to see the price
    before saving. All fields required.
    """

    tier: Literal["basic", "deep", "premium"]
    bedrooms: int = Field(..., ge=0, le=20)
    bathrooms: int = Field(..., ge=0, le=20)


class PricingPreviewRequest(BaseModel):
    """
    Preview pricing for a potential booking.

    Either `service_id` (referencing a persisted cleaning_services row)
    OR `service_metadata` (shape-only) must be provided — validated in
    `_require_service_source`.
    """

    service_id: Optional[str] = Field(
        default=None, description="Existing cleaning_services.id UUID"
    )
    service_metadata: Optional[ServiceMetadata] = Field(
        default=None,
        description="Required when service_id is None (new-service preview).",
    )
    tier: Literal["basic", "deep", "premium"] = Field(
        default="basic",
        description=(
            "Tier for pricing. Required even with service_metadata "
            "(service_metadata.tier may override). When service_id is "
            "provided, tier here drives the override lookup key."
        ),
    )
    extras: list[ExtraSelection] = Field(default_factory=list)
    frequency_id: Optional[str] = Field(
        default=None, description="cleaning_frequencies.id; None = 0% discount."
    )
    adjustment_amount: Decimal = Field(
        default=Decimal("0"),
        description="Signed manual adjustment applied BEFORE tax.",
    )
    adjustment_reason: Optional[str] = Field(default=None, max_length=255)
    location_id: Optional[str] = Field(
        default=None,
        description="cleaning_areas.id — drives tax lookup (F-001) and location-specific formula.",
    )
    scheduled_date: Optional[str] = Field(
        default=None,
        description=(
            "ISO-8601 YYYY-MM-DD. Drives historical tax lookup (F-001). "
            "Defaults to today UTC when omitted — preview-style."
        ),
    )

    @model_validator(mode="after")
    def _require_service_source(self) -> "PricingPreviewRequest":
        if self.service_id is None and self.service_metadata is None:
            raise ValueError(
                "Either service_id or service_metadata must be provided."
            )
        return self

    @field_validator("scheduled_date")
    @classmethod
    def _validate_scheduled_date(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        # Light sanity check; engine does the real parsing
        from datetime import date

        try:
            date.fromisoformat(v[:10])
        except ValueError as exc:
            raise ValueError(
                f"scheduled_date must be ISO-8601 YYYY-MM-DD; got '{v}'"
            ) from exc
        return v


# ---------------------------------------------------------------------------
# Response
# ---------------------------------------------------------------------------


class PricingPreviewFormatted(BaseModel):
    """Display-ready strings for UI rendering (US locale)."""

    subtotal: str
    discount: str
    adjustment: str
    amount_before_tax: str
    tax: str
    final: str


class PricingPreviewResponse(BaseModel):
    """
    Preview result.

    - `breakdown` is the full `PriceBreakdown` dict from pricing_engine
      with Decimal values stringified for JSON transport (e.g. "240.01").
    - `formatted` is pre-rendered for the UI (e.g. "$240.01").
    """

    breakdown: dict[str, Any]
    formatted: PricingPreviewFormatted


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------


def _fmt_money(value: Any) -> str:
    """
    Format a Decimal/number as US currency string.

    Negative values preserve the sign for UI clarity ("-$29.58").
    """
    if value is None:
        return "$--.--"
    try:
        decimal_value = Decimal(str(value))
    except (ValueError, ArithmeticError):
        return "$--.--"
    if decimal_value < 0:
        return f"-${abs(decimal_value):,.2f}"
    return f"${decimal_value:,.2f}"


def format_breakdown(breakdown: dict[str, Any]) -> PricingPreviewFormatted:
    """Build the `formatted` payload from a raw PriceBreakdown."""
    return PricingPreviewFormatted(
        subtotal=_fmt_money(breakdown.get("subtotal")),
        discount=_fmt_money(breakdown.get("discount_amount")),
        adjustment=_fmt_money(breakdown.get("adjustment_amount")),
        amount_before_tax=_fmt_money(breakdown.get("amount_before_tax")),
        tax=_fmt_money(breakdown.get("tax_amount")),
        final=_fmt_money(breakdown.get("final_amount")),
    )


def stringify_decimals(breakdown: dict[str, Any]) -> dict[str, Any]:
    """
    Recursively convert Decimals (and UUIDs) in breakdown to str for JSON.

    Keeps integers (bedrooms/bathrooms/qty) and booleans intact.
    """
    from uuid import UUID

    def _encode(obj: Any) -> Any:
        if isinstance(obj, Decimal):
            return str(obj)
        if isinstance(obj, UUID):
            return str(obj)
        if isinstance(obj, dict):
            return {k: _encode(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [_encode(v) for v in obj]
        return obj

    return _encode(breakdown)
