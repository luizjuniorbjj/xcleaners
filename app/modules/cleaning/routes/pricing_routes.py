"""
Xcleaners — Pricing Routes (Story 1.1 Task 3).

Endpoints:
  POST /api/v1/clean/{slug}/pricing/preview
      Compute a pricing breakdown for a potential booking. Owner-only.

Rate limiting: the global RateLimitMiddleware (app.modules.cleaning.middleware.security)
already protects all cleaning routes with a sliding-window limit. No per-route
override is added here — Story 1.1 AC3 target of 60 req/min is honored by
the global config. TODO(dedicated-limiter): if preview becomes hot (UI
debouncing failure, etc.), wire a per-endpoint limiter here.

Author: @dev (Neo), 2026-04-16 (Sprint Plan Fase C, Sessão C2)
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException

from app.database import Database, get_db
from app.modules.cleaning.middleware.role_guard import require_role
from app.modules.cleaning.models.pricing import (
    PricingPreviewRequest,
    PricingPreviewResponse,
    format_breakdown,
    stringify_decimals,
)
from app.modules.cleaning.services.pricing_engine import (
    PricingConfigError,
    calculate_booking_price,
)


logger = logging.getLogger("xcleaners.pricing_routes")

router = APIRouter(
    prefix="/api/v1/clean/{slug}",
    tags=["Xcleaners Pricing"],
)


@router.post(
    "/pricing/preview",
    response_model=PricingPreviewResponse,
    summary="Preview pricing breakdown for a potential booking",
    description=(
        "Owner-facing endpoint. Runs pricing_engine.calculate_booking_price "
        "without persisting anything. Accepts either `service_id` (existing "
        "service) or `service_metadata` (new-service preview). Returns raw "
        "breakdown + formatted strings ready for UI."
    ),
)
async def preview_pricing(
    slug: str,
    body: PricingPreviewRequest,
    user: dict = Depends(require_role("owner")),
    db: Database = Depends(get_db),
) -> PricingPreviewResponse:
    """Compute preview per Story 1.1 AC3."""
    business_id = user["business_id"]

    # Resolve tier: explicit field > metadata.tier > fallback 'basic'
    tier = body.tier
    if body.service_metadata is not None:
        # When previewing a new service, the metadata tier is authoritative
        tier = body.service_metadata.tier

    service_metadata_dict = None
    if body.service_metadata is not None:
        service_metadata_dict = {
            "tier": body.service_metadata.tier,
            "bedrooms": body.service_metadata.bedrooms,
            "bathrooms": body.service_metadata.bathrooms,
        }

    extras_input = [
        {"extra_id": e.extra_id, "qty": e.qty} for e in body.extras
    ]

    try:
        breakdown = await calculate_booking_price(
            business_id=business_id,
            service_id=body.service_id,
            tier=tier,
            extras=extras_input,
            frequency_id=body.frequency_id,
            adjustment_amount=body.adjustment_amount,
            adjustment_reason=body.adjustment_reason,
            location_id=body.location_id,
            scheduled_date=body.scheduled_date,
            service_metadata=service_metadata_dict,
            db=db,
        )
    except PricingConfigError as exc:
        # Smith B4: sanitize error detail — log full internally, public msg generic.
        # Raw exc may leak business_id UUID and internal field names.
        logger.warning(
            "pricing/preview PricingConfigError for biz=%s: %s",
            business_id, exc,
        )
        msg = str(exc).lower()
        if "service not found" in msg:
            public = "Service not found."
        elif "no active pricing formula" in msg or "formula" in msg:
            public = "Pricing configuration incomplete for this business."
        elif "invalid tier" in msg:
            public = "Invalid tier value."
        elif "service_metadata" in msg:
            public = "service_id or service_metadata must be provided."
        elif "scheduled_date" in msg:
            public = "Invalid scheduled_date format."
        else:
            public = "Pricing configuration error."
        raise HTTPException(status_code=400, detail=public)

    return PricingPreviewResponse(
        breakdown=stringify_decimals(breakdown),
        formatted=format_breakdown(breakdown),
    )
