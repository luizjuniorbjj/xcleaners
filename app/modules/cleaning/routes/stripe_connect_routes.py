"""
Xcleaners — Stripe Connect Express Routes

Exposes the stripe_connect_service via HTTP so owners can onboard their
Stripe account, check status, and access the Express Dashboard.

Endpoints:
  POST /api/v1/clean/{slug}/stripe/connect/create-account (owner)
       → creates Express account + returns onboarding_url. Idempotent:
         returns existing onboarding URL if account already exists.
  GET  /api/v1/clean/{slug}/stripe/connect/status (owner)
       → live retrieve from Stripe + sync DB flags
  POST /api/v1/clean/{slug}/stripe/connect/dashboard-link (owner)
       → Express dashboard login URL (5-min TTL)
  POST /api/v1/clean/{slug}/stripe/connect/refresh-link (owner)
       → fresh onboarding AccountLink (old one expired)
  POST /stripe/connect/webhook (public, signature-verified)
       → handles account.updated and syncs DB automatically

Author: @dev (Neo), 2026-04-16 (Sprint E item 1)
"""

from __future__ import annotations

import logging
import os
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

from app.database import get_db, Database
from app.modules.cleaning.middleware.role_guard import require_role
from app.modules.cleaning.services.stripe_connect_service import (
    create_dashboard_link,
    create_express_account,
    refresh_onboarding_link,
    retrieve_account_status,
)

logger = logging.getLogger("xcleaners.stripe_connect_routes")

STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "")


# ============================================================================
# TENANT-SCOPED ROUTER (owner endpoints)
# ============================================================================

router = APIRouter(
    prefix="/api/v1/clean/{slug}/stripe/connect",
    tags=["Xcleaners Stripe Connect"],
)


def _ensure_stripe_configured():
    if not STRIPE_SECRET_KEY:
        raise HTTPException(
            status_code=503,
            detail="Payments are not configured on this server (STRIPE_SECRET_KEY missing).",
        )


async def _get_business_row(db: Database, business_id: str) -> dict:
    row = await db.pool.fetchrow(
        """
        SELECT id, name, slug, stripe_account_id, stripe_account_status,
               stripe_charges_enabled, stripe_payouts_enabled, stripe_connected_at
        FROM businesses
        WHERE id = $1
        """,
        business_id,
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Business not found")
    return dict(row)


async def _get_owner_email(db: Database, business_id: str, fallback: str) -> str:
    """Best-effort: find the business owner's email from cleaning_user_roles → users."""
    row = await db.pool.fetchrow(
        """
        SELECT u.email
        FROM cleaning_user_roles cur
        JOIN users u ON u.id = cur.user_id
        WHERE cur.business_id = $1 AND cur.role = 'owner' AND cur.is_active = TRUE
        ORDER BY cur.created_at ASC
        LIMIT 1
        """,
        business_id,
    )
    if row and row["email"]:
        return row["email"]
    return fallback


@router.post("/create-account")
async def post_create_account(
    slug: str,
    user: dict = Depends(require_role("owner")),
    db: Database = Depends(get_db),
):
    """
    Create or reuse a Stripe Express account for this business, returning
    an onboarding URL. Idempotent: if account exists, returns a fresh link.
    """
    _ensure_stripe_configured()
    biz = await _get_business_row(db, user["business_id"])

    # Already connected: just refresh the onboarding link (for incomplete KYC)
    if biz["stripe_account_id"]:
        try:
            onboarding_url = await refresh_onboarding_link(biz["stripe_account_id"])
        except ValueError as exc:  # pragma: no cover
            raise HTTPException(status_code=400, detail=str(exc))
        return {
            "account_id": biz["stripe_account_id"],
            "onboarding_url": onboarding_url,
            "reused_existing": True,
        }

    owner_email = await _get_owner_email(
        db, user["business_id"], fallback=user.get("email", "owner@example.com"),
    )

    try:
        result = await create_express_account(
            business_id=str(user["business_id"]),
            business_name=biz["name"] or slug,
            owner_email=owner_email,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:  # pragma: no cover — log + 502
        logger.exception("stripe_connect: create_express_account failed")
        raise HTTPException(status_code=502, detail="Upstream payment provider error")

    # Persist account_id on businesses
    await db.pool.execute(
        """
        UPDATE businesses
           SET stripe_account_id = $1,
               stripe_account_status = 'pending',
               stripe_charges_enabled = FALSE,
               stripe_payouts_enabled = FALSE
         WHERE id = $2
        """,
        result["account_id"], user["business_id"],
    )
    return {
        "account_id": result["account_id"],
        "onboarding_url": result["onboarding_url"],
        "reused_existing": False,
    }


@router.get("/status")
async def get_status(
    slug: str,
    user: dict = Depends(require_role("owner")),
    db: Database = Depends(get_db),
):
    """
    Live status from Stripe. Syncs flags to DB so subsequent reads are cheap.
    If no account exists yet, returns disconnected state without calling Stripe.
    """
    biz = await _get_business_row(db, user["business_id"])
    if not biz["stripe_account_id"]:
        return {
            "connected": False,
            "account_id": None,
            "status": "not_connected",
            "charges_enabled": False,
            "payouts_enabled": False,
            "details_submitted": False,
            "requirements_due": [],
        }

    _ensure_stripe_configured()
    try:
        status = await retrieve_account_status(biz["stripe_account_id"])
    except Exception as exc:  # pragma: no cover
        logger.exception("stripe_connect: retrieve_account_status failed")
        raise HTTPException(status_code=502, detail="Upstream payment provider error")

    # Sync DB flags (cheap idempotent update)
    await db.pool.execute(
        """
        UPDATE businesses
           SET stripe_account_status = $1,
               stripe_charges_enabled = $2,
               stripe_payouts_enabled = $3,
               stripe_connected_at = CASE
                   WHEN $2 = TRUE AND stripe_connected_at IS NULL THEN NOW()
                   ELSE stripe_connected_at
               END
         WHERE id = $4
        """,
        status["status"], status["charges_enabled"], status["payouts_enabled"],
        user["business_id"],
    )

    return {
        "connected": True,
        "account_id": biz["stripe_account_id"],
        **status,
    }


@router.post("/dashboard-link")
async def post_dashboard_link(
    slug: str,
    user: dict = Depends(require_role("owner")),
    db: Database = Depends(get_db),
):
    """Generate a single-use Express Dashboard login URL (5-min TTL)."""
    _ensure_stripe_configured()
    biz = await _get_business_row(db, user["business_id"])
    if not biz["stripe_account_id"]:
        raise HTTPException(
            status_code=409,
            detail="Stripe account not connected yet. Call create-account first.",
        )
    try:
        url = await create_dashboard_link(biz["stripe_account_id"])
    except Exception as exc:  # pragma: no cover
        logger.exception("stripe_connect: create_dashboard_link failed")
        raise HTTPException(status_code=502, detail="Upstream payment provider error")
    return {"dashboard_url": url}


@router.post("/refresh-link")
async def post_refresh_link(
    slug: str,
    user: dict = Depends(require_role("owner")),
    db: Database = Depends(get_db),
):
    """Regenerate an onboarding AccountLink (previous one expired)."""
    _ensure_stripe_configured()
    biz = await _get_business_row(db, user["business_id"])
    if not biz["stripe_account_id"]:
        raise HTTPException(
            status_code=409,
            detail="Stripe account not connected yet. Call create-account first.",
        )
    try:
        url = await refresh_onboarding_link(biz["stripe_account_id"])
    except Exception as exc:  # pragma: no cover
        logger.exception("stripe_connect: refresh_onboarding_link failed")
        raise HTTPException(status_code=502, detail="Upstream payment provider error")
    return {"onboarding_url": url}


# ============================================================================
# PUBLIC WEBHOOK (unauthenticated, signature-verified)
# ============================================================================

webhook_router = APIRouter(
    prefix="/stripe/connect",
    tags=["Xcleaners Stripe Connect Webhook"],
)


@webhook_router.post("/webhook")
async def stripe_webhook(request: Request, db: Database = Depends(get_db)):
    """
    Handle Stripe Connect events. We care about `account.updated` to keep
    businesses.stripe_* flags in sync.

    Security: verifies Stripe signature with STRIPE_WEBHOOK_SECRET.
    Returns 200 even on unknown event types (Stripe retries on 4xx/5xx).
    """
    if not STRIPE_WEBHOOK_SECRET:
        # Webhook not configured → log and accept (avoid prod outage from
        # mismatched config). Do NOT process any event.
        logger.warning(
            "stripe_webhook: received event but STRIPE_WEBHOOK_SECRET not set — ignored"
        )
        return {"received": True, "processed": False, "reason": "not_configured"}

    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")

    try:
        import stripe as stripe_sdk
        event = stripe_sdk.Webhook.construct_event(
            payload, sig_header, STRIPE_WEBHOOK_SECRET,
        )
    except ValueError as exc:
        logger.warning("stripe_webhook: invalid payload: %s", exc)
        raise HTTPException(status_code=400, detail="Invalid payload")
    except Exception as exc:
        # Narrow to SignatureVerificationError only — other exceptions
        # (ImportError, AttributeError) are bugs and should surface (Smith #4).
        exc_type = type(exc).__name__
        if exc_type == "SignatureVerificationError":
            logger.warning("stripe_webhook: signature verification failed: %s", exc)
            raise HTTPException(status_code=400, detail="Invalid signature")
        logger.exception("stripe_webhook: unexpected error constructing event")
        raise HTTPException(status_code=500, detail="Webhook processing error")

    event_type = event["type"]

    if event_type == "account.updated":
        account = event["data"]["object"]
        account_id = account.get("id")
        if not account_id:
            return {"received": True, "processed": False}

        charges_enabled = bool(account.get("charges_enabled"))
        payouts_enabled = bool(account.get("payouts_enabled"))
        details_submitted = bool(account.get("details_submitted"))

        reqs = account.get("requirements") or {}
        disabled_reason = reqs.get("disabled_reason") if isinstance(reqs, dict) else None

        if charges_enabled and payouts_enabled:
            status = "active"
        elif disabled_reason == "rejected.fraud":
            status = "rejected"
        elif disabled_reason:
            status = "restricted"
        elif details_submitted:
            status = "pending"
        else:
            status = "pending"

        result = await db.pool.execute(
            """
            UPDATE businesses
               SET stripe_account_status = $1,
                   stripe_charges_enabled = $2,
                   stripe_payouts_enabled = $3,
                   stripe_connected_at = CASE
                       WHEN $2 = TRUE AND stripe_connected_at IS NULL THEN NOW()
                       ELSE stripe_connected_at
                   END
             WHERE stripe_account_id = $4
            """,
            status, charges_enabled, payouts_enabled, account_id,
        )
        # Smith #3: WARN when webhook matches an unknown account (stale env wiring)
        if result == "UPDATE 0":
            logger.warning(
                "stripe_webhook: account.updated for UNKNOWN account_id=%s — not in DB. "
                "Check webhook env wiring.",
                account_id,
            )
        else:
            logger.info(
                "stripe_webhook: account.updated %s status=%s charges=%s payouts=%s",
                account_id, status, charges_enabled, payouts_enabled,
            )
        return {"received": True, "processed": True, "type": event_type}

    # Smith M3: payment_intent lifecycle events — sync cleaning_bookings with
    # Stripe's async payment state. Booking-level PI metadata is set by
    # booking_charge_service.charge_booking_off_session (xcleaners_booking_id).
    _PI_EVENT_TO_STATUS = {
        "payment_intent.succeeded":       "succeeded",
        "payment_intent.payment_failed":  "failed",
        "payment_intent.processing":      "processing",
        "payment_intent.requires_action": "requires_action",
    }
    if event_type in _PI_EVENT_TO_STATUS:
        pi = event["data"]["object"] or {}
        pi_id = pi.get("id")
        metadata = pi.get("metadata") or {}
        booking_id = metadata.get("xcleaners_booking_id")
        target_status = _PI_EVENT_TO_STATUS[event_type]

        if not booking_id or not pi_id:
            logger.debug(
                "stripe_webhook: %s without xcleaners_booking_id metadata — no-op (pi=%s)",
                event_type, pi_id,
            )
            return {
                "received": True,
                "processed": False,
                "type": event_type,
                "reason": "no_booking_metadata",
            }

        # Idempotent state-machine update (Smith N1 fix):
        #   - COALESCE keeps the first pi_id seen — prevents a late webhook
        #     with a different PI (e.g. a retry) from overwriting.
        #   - payment_status CASE prevents regression of terminal states
        #     (succeeded/failed) when Stripe delivers events out-of-order.
        #     Example: '.processing' arriving AFTER '.succeeded' would wrongly
        #     revert the booking to 'processing'. The CASE keeps 'succeeded'.
        #   - Terminal→terminal transitions (succeeded↔failed) DO apply
        #     (refunds, disputes). Non-terminal states always accept the new.
        result = await db.pool.execute(
            """
            UPDATE cleaning_bookings
               SET payment_status = CASE
                   WHEN payment_status IN ('succeeded', 'failed')
                        AND $1 NOT IN ('succeeded', 'failed')
                        THEN payment_status
                   ELSE $1
                   END,
                   stripe_payment_intent_id = COALESCE(stripe_payment_intent_id, $2)
             WHERE id = $3
            """,
            target_status, pi_id, booking_id,
        )
        if result == "UPDATE 0":
            logger.warning(
                "stripe_webhook: %s for unknown booking_id=%s pi=%s — ignored",
                event_type, booking_id, pi_id,
            )
        else:
            logger.info(
                "stripe_webhook: %s booking=%s pi=%s status=%s",
                event_type, booking_id, pi_id, target_status,
            )
        return {"received": True, "processed": True, "type": event_type}

    # Smith #24: checkout.session.completed — mark cleaning_invoices as paid
    # when a Payment Link (one-time invoice charge) is completed. Metadata
    # (invoice_id, business_id) is set by invoice_service.create_payment_link.
    # This event is delivered from Connected accounts (since PaymentLink.create
    # is called with stripe_account=business.stripe_account_id), so the platform
    # webhook endpoint must have "Listen on connected accounts" enabled.
    if event_type == "checkout.session.completed":
        session = event["data"]["object"] or {}
        metadata = session.get("metadata") or {}
        invoice_id = metadata.get("invoice_id")
        business_id = metadata.get("business_id")

        if not invoice_id or not business_id:
            logger.debug(
                "stripe_webhook: checkout.session.completed without invoice_id/business_id "
                "metadata — no-op (session=%s)",
                session.get("id"),
            )
            return {
                "received": True,
                "processed": False,
                "type": event_type,
                "reason": "no_invoice_metadata",
            }

        amount_total = (session.get("amount_total") or 0) / 100.0
        payment_intent_id = session.get("payment_intent") or session.get("id")

        result = await db.pool.execute(
            """
            UPDATE cleaning_invoices
               SET status = 'paid',
                   amount_paid = total,
                   payment_method = 'stripe',
                   payment_reference = $2,
                   stripe_invoice_id = COALESCE(stripe_invoice_id, $3),
                   paid_at = COALESCE(paid_at, NOW()),
                   updated_at = NOW()
             WHERE id = $1
               AND business_id = $4
               AND balance_due > 0
            """,
            invoice_id, payment_intent_id, session.get("id"), business_id,
        )
        if result == "UPDATE 0":
            logger.warning(
                "stripe_webhook: checkout.session.completed for invoice %s "
                "(business=%s) did not match any row with balance_due>0 — "
                "already paid or invoice not found",
                invoice_id, business_id,
            )
        else:
            logger.info(
                "stripe_webhook: invoice %s marked paid ($%.2f) via session %s",
                invoice_id, amount_total, session.get("id"),
            )
        return {"received": True, "processed": True, "type": event_type}

    # Unknown/unhandled event types still return 200 so Stripe doesn't retry
    logger.debug("stripe_webhook: unhandled event type %s", event_type)
    return {"received": True, "processed": False, "type": event_type}
