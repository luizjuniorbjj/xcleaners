"""
Xcleaners v3 — AI Scheduling Routes.

Endpoints for AI-powered schedule optimization, team suggestions,
duration predictions, and business insights.

All endpoints gated behind Intermediate+ plan via require_minimum_plan.

Endpoints:
  POST /api/v1/clean/{slug}/ai/optimize-schedule/{date}  — optimize schedule
  POST /api/v1/clean/{slug}/ai/suggest-team/{booking_id}  — suggest team
  POST /api/v1/clean/{slug}/ai/predict-duration            — predict duration
  GET  /api/v1/clean/{slug}/ai/insights                    — patterns & insights
"""

import logging
import re
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.database import get_db, Database
from app.modules.cleaning.middleware.plan_guard import require_minimum_plan
from app.modules.cleaning.middleware.role_guard import require_role
# AI Turbo Sprint 2026-04-20: imports para endpoint /ai/chat (homeowner)
from app.moderation_service import get_moderation_service
from app.rate_limiter import rate_limiter
from app.prompts.scheduling_customer import SCHEDULING_CUSTOMER_SYSTEM_PROMPT
from app.config import GATES_FAIL_CLOSED

logger = logging.getLogger("xcleaners.ai_routes")

router = APIRouter(
    prefix="/api/v1/clean/{slug}/ai",
    tags=["Xcleaners AI Scheduling"],
)


# ============================================
# REQUEST MODELS
# ============================================

class PredictDurationRequest(BaseModel):
    """Request body for duration prediction."""
    client_id: str = Field(..., description="UUID of the client.")
    service_type_id: Optional[str] = Field(
        None, description="UUID of the service type (optional, improves accuracy)."
    )


class ChatRequest(BaseModel):
    """Request body for AI chat (AI Turbo Sprint 2026-04-20)."""
    message: str = Field(..., min_length=1, max_length=5000)
    conversation_id: Optional[str] = Field(None, description="UUID of existing conversation, or omit to start new.")


class ChatResponse(BaseModel):
    response: str
    conversation_id: str
    proposed_draft_id: Optional[str] = None
    model_used: Optional[str] = None


# ============================================
# POST /ai/optimize-schedule/{date}
# ============================================

@router.post("/optimize-schedule/{date}")
async def optimize_schedule(
    slug: str,
    date: str,
    user: dict = Depends(require_minimum_plan("intermediate")),
    db: Database = Depends(get_db),
):
    """
    AI analyzes the schedule for a specific date and suggests optimizations.

    Suggestions include:
    - Travel distance reduction (geographic clustering)
    - Workload rebalancing across teams
    - Team swap recommendations
    - Gap identification for additional jobs

    Requires: Intermediate or Maximum plan.
    Requires: Owner role.
    """
    # Verify owner role (require_minimum_plan already authenticated the user)
    business_id = user["business_id"]

    # Verify the user is an owner in this cleaning business
    role = await _get_user_cleaning_role(user, business_id, db)
    if role != "owner":
        raise HTTPException(
            status_code=403,
            detail="Only the business owner can use AI scheduling features.",
        )

    # Validate date format
    _validate_date(date)

    from app.modules.cleaning.services.ai_scheduling import optimize_schedule as _optimize
    result = await _optimize(business_id, date, db)

    return result


# ============================================
# POST /ai/suggest-team/{booking_id}
# ============================================

@router.post("/suggest-team/{booking_id}")
async def suggest_team(
    slug: str,
    booking_id: str,
    user: dict = Depends(require_minimum_plan("intermediate")),
    db: Database = Depends(get_db),
):
    """
    AI suggests the best team to assign for a specific booking.

    Considers proximity, workload balance, client preference,
    and service continuity (same team as last time).

    Requires: Intermediate or Maximum plan.
    Requires: Owner role.
    """
    business_id = user["business_id"]

    role = await _get_user_cleaning_role(user, business_id, db)
    if role != "owner":
        raise HTTPException(
            status_code=403,
            detail="Only the business owner can use AI scheduling features.",
        )

    from app.modules.cleaning.services.ai_scheduling import suggest_team_assignment
    result = await suggest_team_assignment(business_id, booking_id, db)

    return result


# ============================================
# POST /ai/predict-duration
# ============================================

@router.post("/predict-duration")
async def predict_duration(
    slug: str,
    body: PredictDurationRequest,
    user: dict = Depends(require_minimum_plan("intermediate")),
    db: Database = Depends(get_db),
):
    """
    Predict cleaning duration for a client based on history.

    Uses historical actual durations, weighted by recency,
    to predict how long the next cleaning will take.

    Requires: Intermediate or Maximum plan.
    Requires: Owner role.
    """
    business_id = user["business_id"]

    role = await _get_user_cleaning_role(user, business_id, db)
    if role != "owner":
        raise HTTPException(
            status_code=403,
            detail="Only the business owner can use AI scheduling features.",
        )

    from app.modules.cleaning.services.ai_scheduling import predict_duration as _predict
    result = await _predict(business_id, body.client_id, body.service_type_id, db)

    return result


# ============================================
# GET /ai/insights
# ============================================

@router.get("/insights")
async def get_insights(
    slug: str,
    user: dict = Depends(require_minimum_plan("intermediate")),
    db: Database = Depends(get_db),
):
    """
    AI detects scheduling patterns and generates business insights.

    Analyzes: cancellation trends, peak days, underutilized teams,
    workload imbalances, and growth opportunities.

    Requires: Intermediate or Maximum plan.
    Requires: Owner role.
    """
    business_id = user["business_id"]

    role = await _get_user_cleaning_role(user, business_id, db)
    if role != "owner":
        raise HTTPException(
            status_code=403,
            detail="Only the business owner can use AI scheduling features.",
        )

    from app.modules.cleaning.services.ai_scheduling import detect_patterns
    result = await detect_patterns(business_id, db)

    return result


# ============================================
# POST /ai/chat — AI Turbo Sprint 2026-04-20
# Customer conversational chat endpoint.
# Auth: require_role("homeowner") — cliente logado no portal.
# ============================================

@router.post("/chat", response_model=ChatResponse)
async def ai_chat(
    slug: str,
    body: ChatRequest,
    user: dict = Depends(require_role("homeowner")),
    db: Database = Depends(get_db),
):
    """
    Conversational AI scheduling assistant for the customer (homeowner).

    Pipeline:
      1. Moderation check (OpenAI Moderation API — graceful degrade if disabled).
      2. Rate limit (30 req / 60s por user_id).
      3. Resolve cleaning_clients row for this homeowner.
      4. Load or create conversation (scoped to user_id).
      5. Save user message (plaintext bytes — Fernet encryption backlog).
      6. Run OpenAI function calling loop via ai_scheduling._run_openai_tools.
      7. Save assistant message.
      8. Detect proposed_draft_id by regex on response.
      9. Return response + conversation_id + draft_id (if any).

    Tools allowed (system prompt enforces): check_availability, get_price_quote,
    get_services_catalog, calculate_distance, propose_booking_draft.
    """
    business_id = user["business_id"]
    user_id = user["user_id"]
    message = body.message.strip()

    # 1. Moderation (HIGH fix Smith H-1 2026-04-20: fail-closed em producao)
    try:
        moderation = get_moderation_service()
        mod = await moderation.check(message)
        if mod.flagged:
            raise HTTPException(
                status_code=400,
                detail="Your message was flagged by our content safety system. Please rephrase.",
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("[ai/chat] moderation gate failed: %s", e)
        if GATES_FAIL_CLOSED:
            raise HTTPException(
                status_code=503,
                detail="Content safety service temporarily unavailable. Please try again shortly.",
            )
        # fail-open (dev/staging): log e continua

    # 2. Rate limit 30/60s per user (HIGH fix Smith H-1: fail-closed em producao)
    try:
        allowed = await rate_limiter.is_allowed(
            f"chat:{user_id}", max_requests=30, window_seconds=60,
        )
        if not allowed:
            raise HTTPException(
                status_code=429,
                detail="Too many messages. Please wait a moment before sending another.",
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("[ai/chat] rate_limit gate failed: %s", e)
        if GATES_FAIL_CLOSED:
            raise HTTPException(
                status_code=503,
                detail="Rate limiting service temporarily unavailable. Please try again shortly.",
            )
        # fail-open (dev/staging): log e continua

    # 3. Resolve client
    client = await db.pool.fetchrow(
        """
        SELECT id, first_name, last_name, address_line1, city, zip_code
        FROM cleaning_clients
        WHERE user_id = $1 AND business_id = $2 AND status != 'blocked'
        LIMIT 1
        """,
        user_id, business_id,
    )
    if not client:
        raise HTTPException(
            status_code=403,
            detail="Your client profile was not found. Contact your cleaning service.",
        )

    # 4. Load or create conversation
    # MEDIUM fix Smith M-3: conversation reuse exige client_id ativo no business.
    # Bloqueia usuario multi-business cruzar conversas entre tenants.
    conv_id: Optional[str] = body.conversation_id
    if conv_id:
        row = await db.pool.fetchrow(
            """
            SELECT c.id FROM conversations c
            WHERE c.id = $1 AND c.user_id = $2
              AND EXISTS (
                  SELECT 1 FROM cleaning_clients cc
                  WHERE cc.user_id = c.user_id
                    AND cc.business_id = $3
                    AND cc.status != 'blocked'
              )
            """,
            conv_id, user_id, business_id,
        )
        if not row:
            raise HTTPException(status_code=404, detail="Conversation not found.")
        conv_id = str(row["id"])
    else:
        row = await db.pool.fetchrow(
            """
            INSERT INTO conversations (user_id, channel)
            VALUES ($1, 'web')
            RETURNING id
            """,
            user_id,
        )
        conv_id = str(row["id"])

    # 5. Save user message
    # NOTE: content_encrypted BYTEA armazenando plaintext UTF-8 por ora.
    # Fernet encryption via app.security.encrypt_data vai para backlog pos-sprint.
    await db.pool.execute(
        """
        INSERT INTO messages (conversation_id, role, content_encrypted)
        VALUES ($1, 'user', $2)
        """,
        conv_id, message.encode("utf-8"),
    )

    # 6. Build system prompt with business + customer context
    biz = await db.pool.fetchrow(
        "SELECT name, timezone FROM businesses WHERE id = $1",
        business_id,
    )
    tz_name = (biz["timezone"] if biz and biz["timezone"] else None) or "America/New_York"

    try:
        from zoneinfo import ZoneInfo
        today_local = datetime.now(ZoneInfo(tz_name)).strftime("%Y-%m-%d (%A)")
    except Exception:
        today_local = datetime.utcnow().strftime("%Y-%m-%d (UTC)")

    client_name = f"{client['first_name']} {client['last_name'] or ''}".strip()
    client_address = ", ".join(
        [p for p in (client["address_line1"], client["city"]) if p]
    ) or "unknown"

    system_prompt = SCHEDULING_CUSTOMER_SYSTEM_PROMPT.format(
        business_name=biz["name"] if biz else "your cleaning service",
        business_id=business_id,
        business_timezone=tz_name,
        client_id=str(client["id"]),
        client_name=client_name,
        client_address=client_address,
        client_zip=client["zip_code"] or "",
        today_local=today_local,
    )

    # 7. Run AI tool loop (OpenAI function calling — GPT-4.1 Mini por default)
    from app.modules.cleaning.services.ai_scheduling import (
        _get_ai_client,
        _run_openai_tools,
        _run_anthropic_tools,
    )
    from app.config import AI_MODEL_PRIMARY

    # CRITICAL fix Smith C-1 2026-04-20: auth_context enforcing ownership
    # no handler propose_booking_draft — bloqueia client_id spoofing via prompt.
    auth_context = {"authenticated_client_id": str(client["id"])}

    try:
        ai_client, provider = _get_ai_client()
        if provider == "anthropic":
            response_text = await _run_anthropic_tools(
                ai_client, system_prompt, message, business_id, db, auth_context,
            )
        else:
            response_text = await _run_openai_tools(
                ai_client, system_prompt, message, business_id, db, provider, auth_context,
            )
    except Exception as e:
        logger.exception("[ai/chat] AI tool loop error: %s", e)
        raise HTTPException(
            status_code=503,
            detail="AI service temporarily unavailable. Please try again in a moment.",
        )

    # 8. Save assistant message
    await db.pool.execute(
        """
        INSERT INTO messages (conversation_id, role, content_encrypted)
        VALUES ($1, 'assistant', $2)
        """,
        conv_id, response_text.encode("utf-8"),
    )

    # Update conversation timestamp
    await db.pool.execute(
        "UPDATE conversations SET last_message_at = NOW() WHERE id = $1",
        conv_id,
    )

    # 9. Detect if AI mentioned a draft booking_id (system prompt asks it to)
    draft_match = re.search(
        r"Booking ID:\s*([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})",
        response_text,
        re.IGNORECASE,
    )
    proposed_draft_id = draft_match.group(1) if draft_match else None

    return ChatResponse(
        response=response_text,
        conversation_id=conv_id,
        proposed_draft_id=proposed_draft_id,
        model_used=AI_MODEL_PRIMARY,
    )


# ============================================
# HELPERS
# ============================================

async def _get_user_cleaning_role(user: dict, business_id: str, db: Database) -> Optional[str]:
    """Get the user's cleaning role in this business."""
    user_id = user.get("user_id") or user.get("sub")
    if not user_id:
        return None

    row = await db.pool.fetchrow(
        """
        SELECT role FROM cleaning_user_roles
        WHERE user_id = $1 AND business_id = $2 AND is_active = true
        """,
        user_id,
        business_id,
    )
    return row["role"] if row else None


def _validate_date(date_str: str):
    """Validate YYYY-MM-DD format."""
    try:
        from datetime import datetime
        datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid date format: '{date_str}'. Expected YYYY-MM-DD.",
        )
