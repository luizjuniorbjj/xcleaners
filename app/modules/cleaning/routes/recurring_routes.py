"""
Xcleaners — Recurring Auto-Generator Internal Routes (Sprint D Track A).

Exposes cron-triggered endpoint for multi-day window generation of recurring
bookings. Isolated from business-slug-scoped routes — internal use only,
HMAC-authenticated.

Endpoints:
  POST /api/v1/clean/internal/recurring/generate-window  — cron entry point

References:
  - ADR-002 Decision 5 (Cron daily 02:00 UTC, 14-day window, HMAC)
  - Sprint Plan Track A AC4
  - Service: app.modules.cleaning.services.recurring_generator.generate_window

Author: @dev (Neo), 2026-04-16 (Sprint D Track A, T5)
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
from datetime import date, timedelta
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, ValidationError

from app.database import Database, get_db
from app.modules.cleaning.services.recurring_generator import generate_window


logger = logging.getLogger("xcleaners.recurring_routes")

router = APIRouter(
    prefix="/api/v1/clean/internal",
    tags=["Xcleaners Recurring (Internal)"],
)


# ============================================
# REQUEST / RESPONSE MODELS
# ============================================

class GenerateWindowRequest(BaseModel):
    """Body payload for POST /recurring/generate-window."""

    business_id: UUID
    days: int = Field(default=14, ge=1, le=90)


class GenerateWindowResponse(BaseModel):
    """Response from POST /recurring/generate-window."""

    generated: int
    skipped_by_skip_table: int
    pricing_failures: list[dict[str, Any]]
    unassigned: int
    conflicts: int
    summary: dict[str, Any]


# ============================================
# AUTH: HMAC-SHA256 on body
# ============================================

async def _verified_body(request: Request) -> bytes:
    """
    Verify X-Internal-Signature header against HMAC-SHA256(body, INTERNAL_CRON_SECRET).

    Returns raw body bytes on success (consumer re-parses via Pydantic).
    Raises HTTPException 401 on missing/invalid signature, 500 on misconfig.
    """
    secret = os.environ.get("INTERNAL_CRON_SECRET")
    if not secret:
        logger.error("INTERNAL_CRON_SECRET env var not configured")
        raise HTTPException(
            status_code=500,
            detail="server misconfigured",
        )

    signature = request.headers.get("X-Internal-Signature")
    if not signature:
        raise HTTPException(status_code=401, detail="missing signature")

    body = await request.body()
    expected = hmac.new(
        secret.encode("utf-8"),
        body,
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(signature, expected):
        logger.warning(
            "[RECURRING] HMAC verify failed (body length=%d)",
            len(body),
        )
        raise HTTPException(status_code=401, detail="invalid signature")

    return body


# ============================================
# ENDPOINTS
# ============================================

@router.post(
    "/recurring/generate-window",
    response_model=GenerateWindowResponse,
    summary="Generate recurring bookings for N-day window (cron entry point)",
)
async def generate_recurring_window(
    body_bytes: bytes = Depends(_verified_body),
    db: Database = Depends(get_db),
) -> GenerateWindowResponse:
    """
    Cron-triggered: generate recurring bookings for [today, today + days - 1].

    Auth: HMAC-SHA256 of request body signed with INTERNAL_CRON_SECRET env var,
    provided in X-Internal-Signature header.

    Default window: 14 days (rolling look-ahead — allows SMS reminders,
    team planning, homeowner calendar visibility).

    Response includes per-schedule pricing_failures list for owner review
    (observability, AC7).
    """
    try:
        data = GenerateWindowRequest.model_validate_json(body_bytes)
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=exc.errors()) from exc
    except Exception as exc:  # noqa: BLE001 — defensive
        raise HTTPException(status_code=400, detail=f"invalid body: {exc}") from exc

    start = date.today()
    end = start + timedelta(days=data.days - 1)

    logger.info(
        "[RECURRING] Cron trigger — business=%s days=%d window=[%s → %s]",
        data.business_id,
        data.days,
        start.isoformat(),
        end.isoformat(),
    )

    result = await generate_window(
        db=db,
        business_id=data.business_id,
        start_date=start,
        end_date=end,
    )

    return GenerateWindowResponse(**result)
