"""
Xcleaners — Booking Auto-Charge Service [3S-2]

Best-effort orchestration of off_session PaymentIntent charges for bookings
created via daily_generator (recurring path) and future manual path.

Gates (all must be TRUE to attempt charge):
  1. Business has Stripe Connect connected (stripe_account_id NOT NULL)
  2. Business has stripe_charges_enabled = TRUE (payouts/KYC complete)
  3. Client has stripe_customer_id NOT NULL
  4. Booking has final_price > 0
  5. Booking has NO existing payment_intent_id (idempotence — don't re-charge)
  6. Booking has NO terminal payment_status (Smith M2: prevents double-charge
     after Stripe's 24h idempotency window expires; pi_id may have been NULL
     on a prior declined attempt)

On charge attempt:
  - Updates cleaning_bookings with stripe_payment_intent_id + payment_status
  - Logs success/failure but NEVER raises — auto-charge is best-effort;
    booking must survive even if payment fails

Called from:
  - daily_generator._persist_assignments after booking created successfully
  - Manual bookings (future): could be wired into booking_service.create_booking

Author: @dev (Neo), 2026-04-17 — Feature 3S-2
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any

from app.database import Database
from app.modules.cleaning.services.stripe_connect_service import (
    charge_booking_off_session,
)

logger = logging.getLogger("xcleaners.booking_auto_charge")


async def try_auto_charge_booking(db: Database, booking_id: str) -> dict:
    """
    Best-effort attempt to charge a booking via off_session PaymentIntent.

    Returns a dict describing the outcome. NEVER raises.

    Outcomes:
      {"attempted": False, "reason": "<gate>"} when a gate fails
      {"attempted": True, "success": True,  "payment_status": "succeeded" | "processing"}
      {"attempted": True, "success": False, "payment_status": "requires_action" | "declined" | "failed"}
    """
    try:
        row = await db.pool.fetchrow(
            """
            SELECT b.id,
                   b.business_id,
                   b.client_id,
                   b.final_price,
                   b.stripe_payment_intent_id AS existing_pi,
                   b.payment_status AS existing_status,
                   c.stripe_customer_id,
                   biz.stripe_account_id,
                   biz.stripe_charges_enabled
              FROM cleaning_bookings b
              JOIN cleaning_clients  c   ON c.id   = b.client_id
              JOIN businesses        biz ON biz.id = b.business_id
             WHERE b.id = $1
            """,
            booking_id,
        )
    except Exception as exc:
        logger.warning("[AUTO_CHARGE] lookup failed for booking %s: %s", booking_id, exc)
        return {"attempted": False, "reason": "lookup_failed"}

    if not row:
        return {"attempted": False, "reason": "booking_not_found"}

    # Gate: already charged (idempotence)
    if row["existing_pi"]:
        return {"attempted": False, "reason": "already_charged"}

    # Gate: terminal prior status (Smith M2) — a previous attempt ended in a
    # state that should NOT be silently retried. Examples:
    #   - 'succeeded' (defense-in-depth; covered by existing_pi but explicit here)
    #   - 'declined'  (card issuer refused — needs owner intervention)
    #   - 'failed'    (stripe config or network error; treat as terminal until fixed)
    # 'pending' and 'processing' (in-flight) and 'requires_action' (needs SCA —
    # owner should retry after client authenticates) DO pass this gate.
    existing_status = row.get("existing_status")
    if existing_status in ("succeeded", "declined", "failed"):
        return {
            "attempted": False,
            "reason": f"terminal_status_{existing_status}",
        }

    # Gate: business not connected / charges not enabled
    if not row["stripe_account_id"] or not row["stripe_charges_enabled"]:
        return {"attempted": False, "reason": "business_not_stripe_ready"}

    # Gate: client has no saved customer (no card on file)
    if not row["stripe_customer_id"]:
        return {"attempted": False, "reason": "client_no_stripe_customer"}

    # Gate: no amount to charge
    final_price = row["final_price"]
    if final_price is None:
        return {"attempted": False, "reason": "no_final_price"}
    try:
        amount_cents = int((Decimal(str(final_price)) * Decimal("100")).to_integral_value())
    except Exception as exc:
        logger.warning("[AUTO_CHARGE] price coercion failed for booking %s: %s", booking_id, exc)
        return {"attempted": False, "reason": "price_coercion_failed"}
    if amount_cents <= 0:
        return {"attempted": False, "reason": "zero_or_negative_amount"}

    # Attempt charge (never raises)
    result = await charge_booking_off_session(
        connected_account_id=row["stripe_account_id"],
        customer_id=row["stripe_customer_id"],
        amount_cents=amount_cents,
        booking_id=str(booking_id),
    )

    # Persist outcome to booking row.
    # Migration 026 added 'processing' to the CHECK constraint, so Stripe's
    # real async state can now be stored without remapping (Smith M1 fix).
    payment_intent_id = result.get("payment_intent_id")
    payment_status = result.get("status") or ("succeeded" if result.get("success") else "failed")

    try:
        await db.pool.execute(
            """
            UPDATE cleaning_bookings
               SET stripe_payment_intent_id = $1,
                   payment_status = $2
             WHERE id = $3
            """,
            payment_intent_id,
            payment_status,
            booking_id,
        )
    except Exception as exc:
        logger.warning(
            "[AUTO_CHARGE] persistence failed for booking %s (status=%s): %s",
            booking_id, payment_status, exc,
        )

    if result.get("success"):
        logger.info(
            "[AUTO_CHARGE] booking=%s charged OK amount=%d pi=%s status=%s",
            booking_id, amount_cents, payment_intent_id, payment_status,
        )
    else:
        logger.warning(
            "[AUTO_CHARGE] booking=%s charge FAILED status=%s error=%s",
            booking_id, payment_status, result.get("error"),
        )

    return {
        "attempted": True,
        "success": bool(result.get("success")),
        "payment_status": payment_status,
        "payment_intent_id": payment_intent_id,
    }
