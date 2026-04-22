"""
Xcleaners — WhatsApp Webhook Routes (AI Turbo Bloco 2.3 — 2026-04-20).

Endpoints:
  POST /api/v1/clean/{slug}/whatsapp/webhook — Evolution API webhook
  GET  /api/v1/clean/{slug}/whatsapp/status  — connection state

Design:
- Webhook responde 200 IMEDIATO apos validacao (Evolution API retry-storma
  em delays > 10s). Processamento IA acontece em BackgroundTasks.
- Pipeline IA DUPLICADO do /ai/chat minimalista — nao tocar ai_routes.py
  pra preservar fixes Smith C-1/H-1/M-3. Dedup via chat_pipeline helper
  fica no backlog.
- Resolve cliente via cleaning_clients.phone. Nao encontrado -> mensagem
  generica de onboarding.
- auth_context enforcing ownership (Smith C-1 fix aplicado aqui tambem).
"""

import logging
import os
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request

from app.database import get_db, Database

logger = logging.getLogger("xcleaners.whatsapp_routes")

router = APIRouter(
    prefix="/api/v1/clean/{slug}/whatsapp",
    tags=["Xcleaners WhatsApp"],
)


# ============================================
# HELPERS
# ============================================

async def _load_channel_config(db: Database, business_id: str) -> Optional[dict]:
    """Load WhatsApp channel config from business_channels for a business.

    Returns dict with instance_name, webhook_secret, phone_number, status if row found
    with status IN ('connected', 'connecting'). Returns None otherwise (caller falls back to env).
    Try/except defensive — DB error → None + ERROR log (graceful degradation).

    Story: XCL-HIGH-1.2 (per-business persistence with backwards-compat fallback).
    """
    try:
        row = await db.pool.fetchrow(
            """
            SELECT instance_name, webhook_secret, phone_number, status
            FROM business_channels
            WHERE business_id = $1
              AND channel_type = 'whatsapp'
              AND status IN ('connected', 'connecting')
            LIMIT 1
            """,
            business_id,
        )
        if not row:
            return None
        return {
            "instance_name": row["instance_name"],
            "webhook_secret": row["webhook_secret"],
            "phone_number": row["phone_number"],
            "status": row["status"],
        }
    except Exception as e:
        logger.error("[CHANNELS] _load_channel_config failed for business_id=%s: %s", business_id, e)
        return None


async def _resolve_business(db: Database, slug: str) -> Optional[dict]:
    """Load business by slug with WhatsApp config.

    Config source controlled by env WHATSAPP_CONFIG_SOURCE (HIGH-1.2 feature flag):
      - 'env' (default, legacy): env vars only (pre-HIGH-1.2 behavior)
      - 'db':                    business_channels DB-first with env fallback

    Fields api_url + api_key always come from env (Evolution server URL is global).
    instance_name + webhook_secret from DB if WHATSAPP_CONFIG_SOURCE='db'
    AND business_channels row exists with status IN ('connected', 'connecting').
    Otherwise fallback to env with WARNING log.

    Rationale (Decisão B Keymaker): two-phase rollout — deploy code with flag='env'
    (zero-impact), then flip to 'db' in controlled window with instant rollback via
    env flip (no redeploy needed).
    """
    biz = await db.pool.fetchrow(
        "SELECT id, name, timezone FROM businesses WHERE slug = $1",
        slug,
    )
    if not biz:
        return None

    business_id = str(biz["id"])

    # Defaults from env (legacy, always-safe path)
    instance_name = os.getenv("EVOLUTION_INSTANCE_NAME", "xcleaners")
    webhook_secret = os.getenv("EVOLUTION_WEBHOOK_SECRET", "")
    phone_number = None  # env-mode does not expose phone (legacy)

    # Feature flag: WHATSAPP_CONFIG_SOURCE controls DB-first vs env-only
    config_source = os.getenv("WHATSAPP_CONFIG_SOURCE", "env").lower()

    if config_source == "db":
        channel_cfg = await _load_channel_config(db, business_id)
        if channel_cfg:
            instance_name = channel_cfg["instance_name"]
            webhook_secret = channel_cfg["webhook_secret"]
            phone_number = channel_cfg["phone_number"]
            logger.info(
                "[CHANNELS] Loaded config from business_channels for slug=%s (instance=%s, status=%s)",
                slug, instance_name, channel_cfg["status"],
            )
        else:
            logger.warning(
                "[CHANNELS] No business_channels row for slug=%s (or status invalid), falling back to env config",
                slug,
            )

    return {
        "business_id": business_id,
        "business_name": biz["name"],
        "timezone": biz["timezone"],
        "api_url": os.getenv("EVOLUTION_API_URL", ""),
        "api_key": os.getenv("EVOLUTION_API_KEY", ""),
        "instance_name": instance_name,
        "webhook_secret": webhook_secret,
        # phone_number só populado em DB-mode; consumers atuais não usam, mas expor para futuro
        "phone_number": phone_number,
    }


def _normalize_phone(raw: str) -> str:
    """Strip WhatsApp JID suffixes + non-digits. Preserves @lid JIDs as-is."""
    if "@lid" in raw:
        return raw  # LID cannot be normalized
    p = raw.replace("@s.whatsapp.net", "").replace("@c.us", "")
    p = p.replace("+", "").replace("-", "").replace(" ", "").replace("(", "").replace(")", "")
    # Strip all non-digits
    return "".join(c for c in p if c.isdigit())


async def _resolve_client(db: Database, business_id: str, phone: str) -> Optional[dict]:
    """Find cleaning_clients row matching this phone within the business."""
    # Compare after normalizing both sides (strip non-digits from db values)
    row = await db.pool.fetchrow(
        """
        SELECT id, user_id, first_name, last_name, zip_code, address_line1
        FROM cleaning_clients
        WHERE business_id = $1
          AND status != 'blocked'
          AND (
              regexp_replace(COALESCE(phone, ''), '[^0-9]', '', 'g') = $2
              OR regexp_replace(COALESCE(phone_secondary, ''), '[^0-9]', '', 'g') = $2
          )
        LIMIT 1
        """,
        business_id, phone,
    )
    return dict(row) if row else None


async def _run_ai_pipeline_whatsapp(
    db: Database,
    config: dict,
    client: dict,
    message_text: str,
) -> str:
    """
    Pipeline IA pra mensagem WhatsApp — duplicado MINIMAL do /ai/chat.
    Nao inclui moderation/rate_limit aqui pra simplificar (backlog: cross-channel
    rate limit via Redis). auth_context preservado pra enforcing Smith C-1.
    """
    from datetime import datetime
    try:
        from zoneinfo import ZoneInfo
        tz_name = config["timezone"] or "America/New_York"
        today_local = datetime.now(ZoneInfo(tz_name)).strftime("%Y-%m-%d (%A)")
    except Exception:
        today_local = datetime.utcnow().strftime("%Y-%m-%d (UTC)")

    from app.prompts.scheduling_customer import SCHEDULING_CUSTOMER_SYSTEM_PROMPT

    client_name = (
        f"{client['first_name'] or ''} {client['last_name'] or ''}".strip()
        or "Customer"
    )
    client_address = client.get("address_line1") or ""

    system_prompt = SCHEDULING_CUSTOMER_SYSTEM_PROMPT.format(
        business_name=config["business_name"],
        business_id=config["business_id"],
        business_timezone=config["timezone"] or "America/New_York",
        client_id=str(client["id"]),
        client_name=client_name,
        client_address=client_address,
        client_zip=client.get("zip_code") or "",
        today_local=today_local,
    )

    # CRITICAL fix Smith C-1: enforcing ownership via auth_context.
    # Mesmo pattern do /ai/chat — bloqueia spoofing via prompt injection.
    auth_context = {"authenticated_client_id": str(client["id"])}

    from app.modules.cleaning.services.ai_scheduling import (
        _get_ai_client,
        _run_openai_tools,
        _run_anthropic_tools,
    )

    ai_client, provider = _get_ai_client()
    if provider == "anthropic":
        response_text = await _run_anthropic_tools(
            ai_client, system_prompt, message_text, config["business_id"], db, auth_context,
        )
    else:
        response_text = await _run_openai_tools(
            ai_client, system_prompt, message_text, config["business_id"], db, provider, auth_context,
        )

    return response_text


async def _persist_conversation(
    db: Database,
    user_id: Optional[str],
    user_message: str,
    assistant_message: str,
):
    """
    MVP: cria nova conversation por mensagem WhatsApp (channel='whatsapp').
    Cross-message conversation threading fica no backlog (exige idle-window
    lookup como em clawtobusiness BusinessChatService._get_recent_conversation).
    """
    if not user_id:
        return  # no linked user — cliente anonimo sem conversation persistente
    try:
        conv = await db.pool.fetchrow(
            """
            INSERT INTO conversations (user_id, channel, last_message_at)
            VALUES ($1, 'whatsapp', NOW())
            RETURNING id
            """,
            user_id,
        )
        if conv:
            await db.pool.execute(
                """
                INSERT INTO messages (conversation_id, role, content_encrypted)
                VALUES ($1, 'user', $2), ($1, 'assistant', $3)
                """,
                conv["id"],
                user_message.encode("utf-8"),
                assistant_message.encode("utf-8"),
            )
    except Exception as e:
        logger.warning("[WHATSAPP] conversation persist failed: %s", e)


# ============================================
# BACKGROUND TASK — processa mensagem e responde
# ============================================

async def _process_incoming(slug: str, payload: dict):
    """
    Background task executado apos webhook 200-OK. Roda o pipeline IA
    e envia response via WhatsAppAdapter.
    """
    from app.database import get_db_instance
    from app.modules.channels.whatsapp import WhatsAppAdapter

    db = await get_db_instance()
    if not db:
        logger.error("[WHATSAPP] No DB instance in background task")
        return

    config = await _resolve_business(db, slug)
    if not config:
        logger.warning("[WHATSAPP] slug not found: %s", slug)
        return
    if not config["api_url"]:
        logger.warning("[WHATSAPP] Evolution API URL not configured — skip")
        return

    adapter = WhatsAppAdapter(config["business_id"], config)
    incoming = adapter.parse_webhook(payload)
    if not incoming:
        return  # ignored (fromMe, group, edit, reaction, etc.)

    phone = _normalize_phone(incoming.sender_id)
    client = await _resolve_client(db, config["business_id"], phone)

    if not client:
        # Cliente fora do sistema — onboarding message
        try:
            await adapter.send_message(
                incoming.sender_id,
                f"Hi! You don't seem to be registered with {config['business_name']}. "
                "Please contact the business directly to set up your account.",
            )
        except Exception as e:
            logger.warning("[WHATSAPP] Failed to send onboarding msg: %s", e)
        return

    # M-2D fix Smith verify 2026-04-21: moderation + rate_limit no canal WhatsApp.
    # Mesmo pattern do /ai/chat (Smith C-1/H-1 Dia 1). Canal exposto sem protecao
    # seria vetor de DDoS/flood + passagem de conteudo toxico.
    from app.config import GATES_FAIL_CLOSED
    from app.moderation_service import get_moderation_service
    from app.rate_limiter import rate_limiter

    # Moderation
    try:
        mod = await get_moderation_service().check(incoming.text)
        if mod.flagged:
            logger.warning(
                "[WHATSAPP] Moderation flagged from %s — dropping",
                incoming.sender_id[:12],
            )
            try:
                await adapter.send_message(
                    incoming.sender_id,
                    "Your message was flagged by our content safety system. Please rephrase.",
                )
            except Exception:
                pass
            return
    except Exception as e:
        logger.exception("[WHATSAPP] moderation gate failed: %s", e)
        if GATES_FAIL_CLOSED:
            # Fail-closed: nao processa nem responde (evita flood se OpenAI API down)
            return

    # Rate limit por phone — 20/60s (mais restritivo que web por higher abuse risk)
    try:
        allowed = await rate_limiter.is_allowed(
            f"whatsapp:{phone}", max_requests=20, window_seconds=60,
        )
        if not allowed:
            logger.warning(
                "[WHATSAPP] Rate limit exceeded for %s",
                incoming.sender_id[:12],
            )
            try:
                await adapter.send_message(
                    incoming.sender_id,
                    "Too many messages. Please wait a moment before sending more.",
                )
            except Exception:
                pass
            return
    except Exception as e:
        logger.exception("[WHATSAPP] rate_limit gate failed: %s", e)
        if GATES_FAIL_CLOSED:
            return

    # Indicador de digitacao (best-effort)
    try:
        await adapter.send_typing(incoming.sender_id)
    except Exception:
        pass

    # Audio message handling — not supported in MVP (transcription backlog)
    if incoming.audio_url and not incoming.text:
        await adapter.send_message(
            incoming.sender_id,
            "I can't process voice messages yet — please send text. "
            "Voice support coming soon!",
        )
        return

    # Pipeline IA
    try:
        response_text = await _run_ai_pipeline_whatsapp(
            db, config, client, incoming.text,
        )
    except Exception as e:
        logger.exception("[WHATSAPP] AI pipeline error: %s", e)
        try:
            await adapter.send_message(
                incoming.sender_id,
                "Sorry, I had trouble processing that. "
                "Please try again in a moment, or contact the business directly.",
            )
        except Exception:
            pass
        return

    # Persist conversation (best-effort)
    await _persist_conversation(db, client.get("user_id"), incoming.text, response_text)

    # Send response
    try:
        sent = await adapter.send_message(incoming.sender_id, response_text)
        if not sent:
            logger.warning("[WHATSAPP] send_message returned False for %s", incoming.sender_id[:12])
    except Exception as e:
        logger.exception("[WHATSAPP] send_message error: %s", e)


# ============================================
# ROUTES
# ============================================

@router.post("/webhook")
async def whatsapp_webhook(
    slug: str,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Database = Depends(get_db),
):
    """
    Evolution API webhook endpoint.
    Responde 200 imediato apos validacao; processamento async via BackgroundTasks.
    """
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    config = await _resolve_business(db, slug)
    if not config:
        raise HTTPException(status_code=404, detail="Business not found")

    # Validar signature se configurado
    from app.modules.channels.whatsapp import WhatsAppAdapter
    adapter = WhatsAppAdapter(config["business_id"], config)
    body = await request.body()
    headers = {k.lower(): v for k, v in request.headers.items()}
    if not adapter.validate_webhook(headers, body):
        logger.warning("[WHATSAPP] Invalid webhook signature for slug=%s", slug)
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    # Enfileirar processamento
    background_tasks.add_task(_process_incoming, slug, payload)
    return {"status": "accepted"}


@router.get("/status")
async def whatsapp_status(
    slug: str,
    db: Database = Depends(get_db),
):
    """Check Evolution API connection status for this business."""
    config = await _resolve_business(db, slug)
    if not config:
        raise HTTPException(status_code=404, detail="Business not found")
    if not config["api_url"]:
        return {"status": "not_configured", "business_id": config["business_id"]}

    from app.modules.channels.whatsapp import WhatsAppAdapter
    adapter = WhatsAppAdapter(config["business_id"], config)
    state = await adapter.get_session_status()
    return {**state, "business_id": config["business_id"]}
