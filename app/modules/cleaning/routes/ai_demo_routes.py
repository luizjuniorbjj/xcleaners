"""
Xcleaners — Public Visitor Chat Routes (AI Turbo Webchat Publico 2026-04-21).

POST /api/v1/clean/{slug}/ai/demo-chat — SEM auth, rate-limited por IP.
Visitante anonimo conversa com IA. Ao final IA cria lead em cleaning_leads
via tool capture_lead.

Rate limit: 10 msg/60s por IP hash. Moderation + GATES_FAIL_CLOSED preservados.
Pipeline: moderation -> rate limit per IP -> resolve business -> conversation
(user_id=NULL, channel='web_public') -> AI tool loop com SCHEDULING_PUBLIC_SYSTEM_PROMPT
-> save messages -> return lead_captured_id se IA criou lead.

Smith C-1 nao aplica (sem auth_context authenticated_client_id — visitante anonimo).
IA e instruida via system prompt a NAO usar propose_booking_draft/check_availability.
"""

import hashlib
import logging
import re
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.database import get_db, Database
from app.moderation_service import get_moderation_service
from app.rate_limiter import rate_limiter
from app.config import GATES_FAIL_CLOSED
from app.prompts.scheduling_public_visitor import SCHEDULING_PUBLIC_SYSTEM_PROMPT

logger = logging.getLogger("xcleaners.ai_demo_routes")

router = APIRouter(
    prefix="/api/v1/clean/{slug}/ai",
    tags=["Xcleaners Public Chat"],
)


class DemoChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)
    conversation_id: Optional[str] = Field(None)
    visitor_name: Optional[str] = Field(None, max_length=100)


class DemoChatResponse(BaseModel):
    response: str
    conversation_id: str
    lead_captured_id: Optional[str] = None


def _get_visitor_ip(request: Request) -> str:
    """Respect X-Forwarded-For em production atras de proxy (Railway, Cloudflare)."""
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


@router.post("/demo-chat", response_model=DemoChatResponse)
async def demo_chat(
    slug: str,
    body: DemoChatRequest,
    request: Request,
    db: Database = Depends(get_db),
):
    """
    Public visitor chat — no auth required.
    IA pipeline: moderation -> rate_limit (IP) -> business resolve ->
    conversation (anonymous) -> AI tool loop -> lead capture (if IA calls).
    """
    message = body.message.strip()
    visitor_ip = _get_visitor_ip(request)
    visitor_ip_hash = hashlib.sha256(visitor_ip.encode()).hexdigest()[:16]

    # 1. Moderation (fail-closed em producao — Smith H-1 pattern)
    try:
        mod = await get_moderation_service().check(message)
        if mod.flagged:
            raise HTTPException(
                status_code=400,
                detail="Message flagged by content safety. Please rephrase.",
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("[demo-chat] moderation gate failed: %s", e)
        if GATES_FAIL_CLOSED:
            raise HTTPException(
                status_code=503,
                detail="Content safety service unavailable. Please try again.",
            )

    # 2. Rate limit per IP hash (10/60s — visitante = higher abuse risk)
    try:
        allowed = await rate_limiter.is_allowed(
            f"demo_chat:{visitor_ip_hash}", max_requests=10, window_seconds=60,
        )
        if not allowed:
            raise HTTPException(
                status_code=429,
                detail="Too many messages. Please wait a moment.",
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("[demo-chat] rate_limit gate failed: %s", e)
        if GATES_FAIL_CLOSED:
            raise HTTPException(
                status_code=503,
                detail="Rate limiting service unavailable.",
            )

    # 3. Resolve business via slug
    biz = await db.pool.fetchrow(
        "SELECT id, name, timezone FROM businesses WHERE slug = $1",
        slug,
    )
    if not biz:
        raise HTTPException(status_code=404, detail="Business not found.")

    business_id = str(biz["id"])
    tz_name = biz["timezone"] or "America/New_York"

    # 4. Load or create conversation — user_id=NULL (visitante anonimo)
    conv_id: Optional[str] = body.conversation_id
    if conv_id:
        row = await db.pool.fetchrow(
            "SELECT id FROM conversations WHERE id = $1 AND channel = 'web_public'",
            conv_id,
        )
        if not row:
            raise HTTPException(status_code=404, detail="Conversation not found.")
        conv_id = str(row["id"])
    else:
        row = await db.pool.fetchrow(
            """
            INSERT INTO conversations (user_id, channel)
            VALUES (NULL, 'web_public')
            RETURNING id
            """,
        )
        conv_id = str(row["id"])

    # 5. Save user message (plaintext bytes — Fernet encryption backlog)
    await db.pool.execute(
        """
        INSERT INTO messages (conversation_id, role, content_encrypted)
        VALUES ($1, 'user', $2)
        """,
        conv_id, message.encode("utf-8"),
    )

    # 6. Build system prompt
    try:
        from zoneinfo import ZoneInfo
        today_local = datetime.now(ZoneInfo(tz_name)).strftime("%Y-%m-%d (%A)")
    except Exception:
        today_local = datetime.utcnow().strftime("%Y-%m-%d (UTC)")

    from app.config import APP_URL
    login_url = f"{APP_URL}/cleaning/app" if APP_URL else "/cleaning/app"

    system_prompt = SCHEDULING_PUBLIC_SYSTEM_PROMPT.format(
        business_name=biz["name"] or "this cleaning service",
        business_id=business_id,
        business_timezone=tz_name,
        today_local=today_local,
        visitor_ip_hash=visitor_ip_hash,
        login_url=login_url,
    )

    # 7. Run AI tool loop (auth_context marca is_public_visitor=True)
    # IA nao tem authenticated_client_id entao propose_booking_draft vai rejeitar
    # se tentada (Smith C-1 Gate 1 client ownership bloqueia cross-business).
    # System prompt instrui IA a usar apenas capture_lead + get_price_quote +
    # get_services_catalog.
    auth_context = {
        "is_public_visitor": True,
        "conversation_id": conv_id,
        "visitor_ip_hash": visitor_ip_hash,
    }

    try:
        from app.modules.cleaning.services.ai_scheduling import (
            _get_ai_client, _run_openai_tools, _run_anthropic_tools,
        )
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
        logger.exception("[demo-chat] AI tool loop error: %s", e)
        raise HTTPException(
            status_code=503,
            detail="AI service temporarily unavailable. Please try again.",
        )

    # 8. Save assistant message + update conversation timestamp
    await db.pool.execute(
        """
        INSERT INTO messages (conversation_id, role, content_encrypted)
        VALUES ($1, 'assistant', $2)
        """,
        conv_id, response_text.encode("utf-8"),
    )
    await db.pool.execute(
        "UPDATE conversations SET last_message_at = NOW() WHERE id = $1",
        conv_id,
    )

    # 9. Detect lead captured via regex UUID in response text
    # System prompt instrui IA a incluir "Lead ID: <uuid>" quando capture_lead succeeds
    lead_match = re.search(
        r"Lead ID:\s*([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})",
        response_text,
        re.IGNORECASE,
    )
    lead_captured_id = lead_match.group(1) if lead_match else None

    return DemoChatResponse(
        response=response_text,
        conversation_id=conv_id,
        lead_captured_id=lead_captured_id,
    )
