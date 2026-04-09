"""
Xcleaners v3 — Push Notification Routes (Sprint 4).

Endpoints for Web Push subscription management.
The frontend push-manager.js calls these to register/unregister
push subscriptions and retrieve the VAPID public key.

Endpoints:
  POST /api/v1/clean/{slug}/push/subscribe     — store push subscription
  POST /api/v1/clean/{slug}/push/unsubscribe   — remove push subscription
  GET  /api/v1/clean/{slug}/push/vapid-key     — get VAPID public key
"""

import json
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.config import VAPID_PUBLIC_KEY
from app.database import get_db, Database
from app.modules.cleaning.middleware.role_guard import require_role

logger = logging.getLogger("xcleaners.push_routes")

router = APIRouter(
    prefix="/api/v1/clean/{slug}",
    tags=["Xcleaners Push Notifications"],
)


# ============================================
# REQUEST MODELS
# ============================================

class PushSubscription(BaseModel):
    endpoint: str = Field(..., description="Push service endpoint URL")
    keys: dict = Field(..., description="Subscription keys: {p256dh, auth}")


# ============================================
# SUBSCRIBE
# ============================================

@router.post("/push/subscribe")
async def push_subscribe(
    slug: str,
    body: PushSubscription,
    user: dict = Depends(require_role("owner", "homeowner", "team_lead", "cleaner")),
    db: Database = Depends(get_db),
):
    """
    Store a push notification subscription for the current user.
    Creates or updates the subscription in cleaning_push_subscriptions.
    """
    user_id = user.get("user_id")
    business_id = user.get("business_id")

    if not user_id:
        raise HTTPException(status_code=401, detail="User ID not found")

    subscription_json = {
        "endpoint": body.endpoint,
        "keys": body.keys,
    }

    try:
        # Upsert: update if same endpoint exists, otherwise insert
        await db.pool.execute(
            """INSERT INTO cleaning_push_subscriptions
               (user_id, business_id, subscription_json, is_active)
               VALUES ($1, $2, $3::JSONB, true)
               ON CONFLICT (user_id, business_id)
               WHERE (subscription_json->>'endpoint') = $4
               DO UPDATE SET
                   subscription_json = $3::JSONB,
                   is_active = true,
                   updated_at = NOW()""",
            user_id, business_id, json.dumps(subscription_json), body.endpoint,
        )
    except Exception:
        # If ON CONFLICT fails (no unique constraint on endpoint),
        # fall back to simple insert/dedup approach
        logger.debug("[PUSH] Upsert not supported, using dedup approach")

        # Deactivate existing subscription with same endpoint
        await db.pool.execute(
            """UPDATE cleaning_push_subscriptions
               SET is_active = false, updated_at = NOW()
               WHERE user_id = $1 AND business_id = $2
                 AND subscription_json->>'endpoint' = $3""",
            user_id, business_id, body.endpoint,
        )

        # Insert new subscription
        await db.pool.execute(
            """INSERT INTO cleaning_push_subscriptions
               (user_id, business_id, subscription_json, is_active)
               VALUES ($1, $2, $3::JSONB, true)""",
            user_id, business_id, json.dumps(subscription_json),
        )

    logger.info("[PUSH] Subscription stored for user %s in business %s", user_id, business_id)
    return {"status": "subscribed"}


# ============================================
# UNSUBSCRIBE
# ============================================

@router.post("/push/unsubscribe")
async def push_unsubscribe(
    slug: str,
    body: PushSubscription,
    user: dict = Depends(require_role("owner", "homeowner", "team_lead", "cleaner")),
    db: Database = Depends(get_db),
):
    """
    Remove (deactivate) a push notification subscription for the current user.
    """
    user_id = user.get("user_id")
    business_id = user.get("business_id")

    if not user_id:
        raise HTTPException(status_code=401, detail="User ID not found")

    result = await db.pool.execute(
        """UPDATE cleaning_push_subscriptions
           SET is_active = false, updated_at = NOW()
           WHERE user_id = $1 AND business_id = $2
             AND subscription_json->>'endpoint' = $3""",
        user_id, business_id, body.endpoint,
    )

    logger.info("[PUSH] Subscription removed for user %s in business %s", user_id, business_id)
    return {"status": "unsubscribed"}


# ============================================
# VAPID PUBLIC KEY
# ============================================

@router.get("/push/vapid-key")
async def get_vapid_key(
    slug: str,
    user: dict = Depends(require_role("owner", "homeowner", "team_lead", "cleaner")),
):
    """
    Return the VAPID public key for the client to use when subscribing
    to push notifications via the Push API.
    """
    if not VAPID_PUBLIC_KEY:
        raise HTTPException(
            status_code=503,
            detail="Push notifications not configured (VAPID key missing)",
        )

    return {"vapid_public_key": VAPID_PUBLIC_KEY}
