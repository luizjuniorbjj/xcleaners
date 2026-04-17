"""
Tests for Stripe Connect webhook — payment_intent.* event handlers [Smith M3].

Verifies that cleaning_bookings payment_status stays in sync with Stripe's
async PaymentIntent lifecycle (succeeded | failed | processing | requires_action).

Author: @dev (Neo), 2026-04-17 — Smith M3 backlog fix
"""

from __future__ import annotations

import json
import os
import uuid
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException


pytest.importorskip(
    "app.modules.cleaning.routes.stripe_connect_routes",
    reason="stripe_connect_routes not available.",
)

from app.modules.cleaning.routes.stripe_connect_routes import (  # noqa: E402
    stripe_webhook,
)


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
async def biz_webhook(db):
    biz_id = await db.pool.fetchval(
        """
        INSERT INTO businesses (slug, name, stripe_account_id, stripe_charges_enabled)
        VALUES ('whbiz_' || gen_random_uuid()::text, 'Webhook Test Biz',
                'acct_webhook_test', TRUE)
        RETURNING id
        """
    )
    yield biz_id
    await db.pool.execute("DELETE FROM businesses WHERE id = $1", biz_id)


@pytest.fixture
async def client_webhook(db, biz_webhook):
    cid = await db.pool.fetchval(
        """
        INSERT INTO cleaning_clients (business_id, first_name, last_name, email, phone, stripe_customer_id)
        VALUES ($1, 'WH', 'Client', 'wh@test.example', '+15558881111', 'cus_wh_test')
        RETURNING id
        """,
        biz_webhook,
    )
    yield cid
    await db.pool.execute("DELETE FROM cleaning_clients WHERE id = $1", cid)


@pytest.fixture
async def svc_webhook(db, biz_webhook):
    sid = await db.pool.fetchval(
        """
        INSERT INTO cleaning_services (business_id, name, slug, base_price)
        VALUES ($1, 'WH Svc', 'wh-svc-' || gen_random_uuid()::text, 100.00)
        RETURNING id
        """,
        biz_webhook,
    )
    yield sid
    await db.pool.execute("DELETE FROM cleaning_services WHERE id = $1", sid)


async def _make_booking(db, biz_id, client_id, svc_id):
    return await db.pool.fetchval(
        """
        INSERT INTO cleaning_bookings (
            business_id, client_id, service_id, scheduled_date,
            scheduled_start, scheduled_end, final_price, status
        )
        VALUES ($1, $2, $3, CURRENT_DATE, '09:00'::time, '11:00'::time, 100.00, 'scheduled')
        RETURNING id
        """,
        biz_id, client_id, svc_id,
    )


def _make_request(event_payload: dict):
    """Build a fake FastAPI Request that returns `event_payload` via request.body()."""
    req = MagicMock()

    async def _body():
        return json.dumps(event_payload).encode("utf-8")

    req.body = _body
    req.headers = {"stripe-signature": "t=123,v1=fake"}
    return req


# ============================================================================
# payment_intent.succeeded → status='succeeded'
# ============================================================================


@pytest.mark.asyncio
async def test_webhook_payment_intent_succeeded_updates_booking(
    db, biz_webhook, client_webhook, svc_webhook, monkeypatch,
):
    """PI succeeded event → booking.payment_status='succeeded' + pi_id set."""
    booking_id = await _make_booking(db, biz_webhook, client_webhook, svc_webhook)

    monkeypatch.setattr(
        "app.modules.cleaning.routes.stripe_connect_routes.STRIPE_WEBHOOK_SECRET",
        "whsec_test",
    )

    event = {
        "type": "payment_intent.succeeded",
        "data": {"object": {
            "id": "pi_succeeded_abc",
            "metadata": {"xcleaners_booking_id": str(booking_id)},
        }},
    }

    try:
        with patch(
            "stripe.Webhook.construct_event",
            return_value=event,
        ):
            req = _make_request(event)
            result = await stripe_webhook(req, db)

        assert result["processed"] is True
        assert result["type"] == "payment_intent.succeeded"

        row = await db.pool.fetchrow(
            "SELECT payment_status, stripe_payment_intent_id FROM cleaning_bookings WHERE id = $1",
            booking_id,
        )
        assert row["payment_status"] == "succeeded"
        assert row["stripe_payment_intent_id"] == "pi_succeeded_abc"
    finally:
        await db.pool.execute("DELETE FROM cleaning_bookings WHERE id = $1", booking_id)


# ============================================================================
# payment_intent.payment_failed → status='failed'
# ============================================================================


@pytest.mark.asyncio
async def test_webhook_payment_intent_failed_updates_booking(
    db, biz_webhook, client_webhook, svc_webhook, monkeypatch,
):
    booking_id = await _make_booking(db, biz_webhook, client_webhook, svc_webhook)

    monkeypatch.setattr(
        "app.modules.cleaning.routes.stripe_connect_routes.STRIPE_WEBHOOK_SECRET",
        "whsec_test",
    )

    event = {
        "type": "payment_intent.payment_failed",
        "data": {"object": {
            "id": "pi_failed_xyz",
            "metadata": {"xcleaners_booking_id": str(booking_id)},
        }},
    }

    try:
        with patch(
            "stripe.Webhook.construct_event",
            return_value=event,
        ):
            req = _make_request(event)
            result = await stripe_webhook(req, db)

        assert result["processed"] is True

        row = await db.pool.fetchrow(
            "SELECT payment_status FROM cleaning_bookings WHERE id = $1",
            booking_id,
        )
        assert row["payment_status"] == "failed"
    finally:
        await db.pool.execute("DELETE FROM cleaning_bookings WHERE id = $1", booking_id)


# ============================================================================
# payment_intent.processing → status='processing' (Migration 026 enabled)
# ============================================================================


@pytest.mark.asyncio
async def test_webhook_payment_intent_processing_updates_booking(
    db, biz_webhook, client_webhook, svc_webhook, monkeypatch,
):
    """PI processing event → payment_status='processing' (persisted as-is thanks to migration 026)."""
    booking_id = await _make_booking(db, biz_webhook, client_webhook, svc_webhook)

    monkeypatch.setattr(
        "app.modules.cleaning.routes.stripe_connect_routes.STRIPE_WEBHOOK_SECRET",
        "whsec_test",
    )

    event = {
        "type": "payment_intent.processing",
        "data": {"object": {
            "id": "pi_proc_abc",
            "metadata": {"xcleaners_booking_id": str(booking_id)},
        }},
    }

    try:
        with patch(
            "stripe.Webhook.construct_event",
            return_value=event,
        ):
            req = _make_request(event)
            result = await stripe_webhook(req, db)

        assert result["processed"] is True

        row = await db.pool.fetchrow(
            "SELECT payment_status FROM cleaning_bookings WHERE id = $1",
            booking_id,
        )
        assert row["payment_status"] == "processing"
    finally:
        await db.pool.execute("DELETE FROM cleaning_bookings WHERE id = $1", booking_id)


# ============================================================================
# No metadata → graceful noop, NOT error
# ============================================================================


@pytest.mark.asyncio
async def test_webhook_payment_intent_without_metadata_noop(db, monkeypatch):
    """PI event without xcleaners_booking_id → 200 + processed=false, no UPDATE."""
    monkeypatch.setattr(
        "app.modules.cleaning.routes.stripe_connect_routes.STRIPE_WEBHOOK_SECRET",
        "whsec_test",
    )

    event = {
        "type": "payment_intent.succeeded",
        "data": {"object": {
            "id": "pi_orphan",
            "metadata": {},  # no xcleaners_booking_id
        }},
    }

    with patch(
        "stripe.Webhook.construct_event",
        return_value=event,
    ):
        req = _make_request(event)
        result = await stripe_webhook(req, db)

    assert result["received"] is True
    assert result["processed"] is False
    assert result["reason"] == "no_booking_metadata"


# ============================================================================
# Unknown booking id → graceful, logs, no error
# ============================================================================


@pytest.mark.asyncio
async def test_webhook_payment_intent_unknown_booking_id_graceful(db, monkeypatch):
    """PI event for booking_id that doesn't exist in DB → 200 + processed=true, UPDATE 0."""
    monkeypatch.setattr(
        "app.modules.cleaning.routes.stripe_connect_routes.STRIPE_WEBHOOK_SECRET",
        "whsec_test",
    )

    event = {
        "type": "payment_intent.succeeded",
        "data": {"object": {
            "id": "pi_ghost",
            "metadata": {"xcleaners_booking_id": str(uuid.uuid4())},
        }},
    }

    with patch(
        "stripe.Webhook.construct_event",
        return_value=event,
    ):
        req = _make_request(event)
        result = await stripe_webhook(req, db)

    # Still returns success (webhook must be 200 so Stripe doesn't retry indefinitely)
    assert result["received"] is True
    assert result["processed"] is True


# ============================================================================
# Idempotency: UPDATE keeps first pi_id (COALESCE)
# ============================================================================


@pytest.mark.asyncio
async def test_webhook_keeps_first_pi_id_not_overwrites(
    db, biz_webhook, client_webhook, svc_webhook, monkeypatch,
):
    """If booking already has pi_id=X, a later webhook with pi_id=Y keeps X (COALESCE)."""
    booking_id = await _make_booking(db, biz_webhook, client_webhook, svc_webhook)
    await db.pool.execute(
        "UPDATE cleaning_bookings SET stripe_payment_intent_id='pi_original' WHERE id=$1",
        booking_id,
    )

    monkeypatch.setattr(
        "app.modules.cleaning.routes.stripe_connect_routes.STRIPE_WEBHOOK_SECRET",
        "whsec_test",
    )

    event = {
        "type": "payment_intent.succeeded",
        "data": {"object": {
            "id": "pi_later_different",
            "metadata": {"xcleaners_booking_id": str(booking_id)},
        }},
    }

    try:
        with patch(
            "stripe.Webhook.construct_event",
            return_value=event,
        ):
            req = _make_request(event)
            result = await stripe_webhook(req, db)

        row = await db.pool.fetchrow(
            "SELECT payment_status, stripe_payment_intent_id FROM cleaning_bookings WHERE id=$1",
            booking_id,
        )
        # Status updated...
        assert row["payment_status"] == "succeeded"
        # ...but original pi_id preserved (COALESCE keeps first)
        assert row["stripe_payment_intent_id"] == "pi_original"
    finally:
        await db.pool.execute("DELETE FROM cleaning_bookings WHERE id = $1", booking_id)
