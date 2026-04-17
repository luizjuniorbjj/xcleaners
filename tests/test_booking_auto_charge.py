"""
Tests for booking auto-charge flow [3S-2].

Covers:
  - charge_booking_off_session happy path (mocked Stripe SDK)
  - charge_booking_off_session card declined (CardError)
  - try_auto_charge_booking gates: no stripe_customer_id, not connected, zero price
  - try_auto_charge_booking persists payment_status on success (integration with DB)

Author: @dev (Neo), 2026-04-17 — Feature 3S-2
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


pytest.importorskip(
    "app.modules.cleaning.services.booking_charge_service",
    reason="booking_charge_service not yet available.",
)

from app.modules.cleaning.services.booking_charge_service import (  # noqa: E402
    try_auto_charge_booking,
)
from app.modules.cleaning.services.stripe_connect_service import (  # noqa: E402
    charge_booking_off_session,
)


# ============================================================================
# Unit tests: charge_booking_off_session (mocked Stripe SDK)
# ============================================================================


@pytest.mark.asyncio
async def test_charge_off_session_happy(monkeypatch):
    """PaymentIntent.create returns succeeded → success dict."""
    monkeypatch.setattr(
        "app.modules.cleaning.services.stripe_connect_service.STRIPE_SECRET_KEY",
        "sk_test_mock",
    )

    fake_intent = MagicMock()
    fake_intent.id = "pi_ok_123"
    fake_intent.status = "succeeded"

    with patch(
        "app.modules.cleaning.services.stripe_connect_service.stripe.PaymentIntent.create",
        return_value=fake_intent,
    ) as create_mock:
        result = await charge_booking_off_session(
            connected_account_id="acct_x",
            customer_id="cus_x",
            amount_cents=12500,
            booking_id="book_abc",
        )

    assert result == {
        "success": True,
        "payment_intent_id": "pi_ok_123",
        "status": "succeeded",
    }
    # Idempotency key includes booking id
    call_kwargs = create_mock.call_args.kwargs
    assert call_kwargs["idempotency_key"] == "booking-book_abc"
    assert call_kwargs["off_session"] is True
    assert call_kwargs["confirm"] is True


@pytest.mark.asyncio
async def test_charge_off_session_card_declined(monkeypatch):
    """stripe.error.CardError → success=False, status=declined."""
    import stripe as stripe_mod

    monkeypatch.setattr(
        "app.modules.cleaning.services.stripe_connect_service.STRIPE_SECRET_KEY",
        "sk_test_mock",
    )

    # Build a minimal CardError
    err_obj = MagicMock()
    err_obj.code = "card_declined"
    err_obj.payment_intent = None
    card_error = stripe_mod.error.CardError(
        message="Your card was declined.",
        param="payment_method",
        code="card_declined",
    )
    card_error.error = err_obj

    with patch(
        "app.modules.cleaning.services.stripe_connect_service.stripe.PaymentIntent.create",
        side_effect=card_error,
    ):
        result = await charge_booking_off_session(
            connected_account_id="acct_x",
            customer_id="cus_x",
            amount_cents=5000,
            booking_id="book_fail",
        )

    assert result["success"] is False
    assert result["status"] == "declined"
    assert isinstance(result["error"], str) and result["error"]


@pytest.mark.asyncio
async def test_charge_off_session_sca_required(monkeypatch):
    """CardError with code=authentication_required → status=requires_action."""
    import stripe as stripe_mod

    monkeypatch.setattr(
        "app.modules.cleaning.services.stripe_connect_service.STRIPE_SECRET_KEY",
        "sk_test_mock",
    )

    err_obj = MagicMock()
    err_obj.code = "authentication_required"
    fake_pi = MagicMock()
    fake_pi.id = "pi_sca_123"
    err_obj.payment_intent = fake_pi

    card_error = stripe_mod.error.CardError(
        message="Authentication required",
        param="payment_method",
        code="authentication_required",
    )
    card_error.error = err_obj

    with patch(
        "app.modules.cleaning.services.stripe_connect_service.stripe.PaymentIntent.create",
        side_effect=card_error,
    ):
        result = await charge_booking_off_session(
            connected_account_id="acct_x",
            customer_id="cus_x",
            amount_cents=5000,
            booking_id="book_sca",
        )

    assert result["success"] is False
    assert result["status"] == "requires_action"
    assert result["payment_intent_id"] == "pi_sca_123"


# ============================================================================
# Integration tests: try_auto_charge_booking (DB + gates)
# ============================================================================


@pytest.fixture
async def biz_ready(db):
    """Business ready to charge: Stripe connected, charges enabled."""
    biz_id = await db.pool.fetchval(
        """
        INSERT INTO businesses (slug, name, stripe_account_id, stripe_charges_enabled)
        VALUES ('chargebiz_' || gen_random_uuid()::text, 'Charge Biz', 'acct_ready', TRUE)
        RETURNING id
        """
    )
    yield biz_id
    await db.pool.execute("DELETE FROM businesses WHERE id = $1", biz_id)


@pytest.fixture
async def biz_not_connected(db):
    biz_id = await db.pool.fetchval(
        """
        INSERT INTO businesses (slug, name)
        VALUES ('chargenoconn_' || gen_random_uuid()::text, 'No Stripe')
        RETURNING id
        """
    )
    yield biz_id
    await db.pool.execute("DELETE FROM businesses WHERE id = $1", biz_id)


async def _make_booking(db, business_id, client_id, service_id, final_price=Decimal("100.00")):
    """Insert a booking row with minimum required columns."""
    return await db.pool.fetchval(
        """
        INSERT INTO cleaning_bookings (
            business_id, client_id, service_id, scheduled_date,
            scheduled_start, scheduled_end, final_price, status
        )
        VALUES ($1, $2, $3, CURRENT_DATE, '09:00'::time, '11:00'::time, $4, 'scheduled')
        RETURNING id
        """,
        business_id, client_id, service_id, final_price,
    )


async def _make_client(db, business_id, stripe_customer_id=None):
    return await db.pool.fetchval(
        """
        INSERT INTO cleaning_clients (business_id, first_name, last_name, email, phone, stripe_customer_id)
        VALUES ($1, 'Charge', 'Client', 'charge.client@test.example', '+15557777777', $2)
        RETURNING id
        """,
        business_id, stripe_customer_id,
    )


async def _make_service(db, business_id):
    return await db.pool.fetchval(
        """
        INSERT INTO cleaning_services (business_id, name, slug, base_price)
        VALUES ($1, 'Std Clean', 'std-clean-' || gen_random_uuid()::text, 100.00)
        RETURNING id
        """,
        business_id,
    )


@pytest.mark.asyncio
async def test_auto_charge_skips_client_without_stripe_customer(db, biz_ready):
    """Client without stripe_customer_id → {attempted: False, reason: client_no_stripe_customer}."""
    svc_id = await _make_service(db, biz_ready)
    client_id = await _make_client(db, biz_ready, stripe_customer_id=None)
    booking_id = await _make_booking(db, biz_ready, client_id, svc_id)

    try:
        result = await try_auto_charge_booking(db, booking_id)
        assert result == {"attempted": False, "reason": "client_no_stripe_customer"}
    finally:
        await db.pool.execute("DELETE FROM cleaning_bookings WHERE id = $1", booking_id)
        await db.pool.execute("DELETE FROM cleaning_clients WHERE id = $1", client_id)
        await db.pool.execute("DELETE FROM cleaning_services WHERE id = $1", svc_id)


@pytest.mark.asyncio
async def test_auto_charge_skips_business_not_connected(db, biz_not_connected):
    """Business without stripe_account_id → gate blocks."""
    svc_id = await _make_service(db, biz_not_connected)
    client_id = await _make_client(db, biz_not_connected, stripe_customer_id="cus_x")
    booking_id = await _make_booking(db, biz_not_connected, client_id, svc_id)

    try:
        result = await try_auto_charge_booking(db, booking_id)
        assert result == {"attempted": False, "reason": "business_not_stripe_ready"}
    finally:
        await db.pool.execute("DELETE FROM cleaning_bookings WHERE id = $1", booking_id)
        await db.pool.execute("DELETE FROM cleaning_clients WHERE id = $1", client_id)
        await db.pool.execute("DELETE FROM cleaning_services WHERE id = $1", svc_id)


@pytest.mark.asyncio
async def test_auto_charge_skips_already_charged_booking(db, biz_ready):
    """Booking with existing stripe_payment_intent_id is idempotent — not re-charged."""
    svc_id = await _make_service(db, biz_ready)
    client_id = await _make_client(db, biz_ready, stripe_customer_id="cus_abc")
    booking_id = await _make_booking(db, biz_ready, client_id, svc_id)
    await db.pool.execute(
        "UPDATE cleaning_bookings SET stripe_payment_intent_id = 'pi_already' WHERE id = $1",
        booking_id,
    )

    try:
        result = await try_auto_charge_booking(db, booking_id)
        assert result == {"attempted": False, "reason": "already_charged"}
    finally:
        await db.pool.execute("DELETE FROM cleaning_bookings WHERE id = $1", booking_id)
        await db.pool.execute("DELETE FROM cleaning_clients WHERE id = $1", client_id)
        await db.pool.execute("DELETE FROM cleaning_services WHERE id = $1", svc_id)


@pytest.mark.asyncio
@pytest.mark.parametrize("terminal_status", ["declined", "failed", "succeeded"])
async def test_auto_charge_skips_terminal_status_prior(db, biz_ready, terminal_status):
    """Smith M2: booking with terminal payment_status is NOT retried even if pi_id is NULL."""
    svc_id = await _make_service(db, biz_ready)
    client_id = await _make_client(db, biz_ready, stripe_customer_id="cus_terminal")
    booking_id = await _make_booking(db, biz_ready, client_id, svc_id)
    # Terminal status set by prior attempt — pi_id intentionally NULL
    await db.pool.execute(
        "UPDATE cleaning_bookings SET payment_status = $1 WHERE id = $2",
        terminal_status, booking_id,
    )

    try:
        result = await try_auto_charge_booking(db, booking_id)
        assert result == {
            "attempted": False,
            "reason": f"terminal_status_{terminal_status}",
        }
    finally:
        await db.pool.execute("DELETE FROM cleaning_bookings WHERE id = $1", booking_id)
        await db.pool.execute("DELETE FROM cleaning_clients WHERE id = $1", client_id)
        await db.pool.execute("DELETE FROM cleaning_services WHERE id = $1", svc_id)


@pytest.mark.asyncio
@pytest.mark.parametrize("non_terminal_status", ["pending", "processing", "requires_action"])
async def test_auto_charge_retries_non_terminal_status(db, biz_ready, non_terminal_status):
    """Smith M2: in-flight / requires_action states MUST still allow retry attempt."""
    svc_id = await _make_service(db, biz_ready)
    client_id = await _make_client(db, biz_ready, stripe_customer_id="cus_retry")
    booking_id = await _make_booking(db, biz_ready, client_id, svc_id)
    await db.pool.execute(
        "UPDATE cleaning_bookings SET payment_status = $1 WHERE id = $2",
        non_terminal_status, booking_id,
    )

    fake_result = {
        "success": True,
        "payment_intent_id": "pi_retry_ok",
        "status": "succeeded",
    }

    try:
        with patch(
            "app.modules.cleaning.services.booking_charge_service.charge_booking_off_session",
            AsyncMock(return_value=fake_result),
        ):
            result = await try_auto_charge_booking(db, booking_id)

        # Gate must NOT block — charge attempted
        assert result["attempted"] is True
        assert result["success"] is True
    finally:
        await db.pool.execute("DELETE FROM cleaning_bookings WHERE id = $1", booking_id)
        await db.pool.execute("DELETE FROM cleaning_clients WHERE id = $1", client_id)
        await db.pool.execute("DELETE FROM cleaning_services WHERE id = $1", svc_id)


@pytest.mark.asyncio
async def test_auto_charge_persists_processing_status_without_remap(db, biz_ready):
    """Smith M1: Stripe's 'processing' is persisted as-is (not remapped to 'pending')."""
    svc_id = await _make_service(db, biz_ready)
    client_id = await _make_client(db, biz_ready, stripe_customer_id="cus_proc")
    booking_id = await _make_booking(db, biz_ready, client_id, svc_id)

    fake_result = {
        "success": True,
        "payment_intent_id": "pi_processing_async",
        "status": "processing",
    }

    try:
        with patch(
            "app.modules.cleaning.services.booking_charge_service.charge_booking_off_session",
            AsyncMock(return_value=fake_result),
        ):
            result = await try_auto_charge_booking(db, booking_id)

        assert result["attempted"] is True
        assert result["success"] is True
        assert result["payment_status"] == "processing"  # NOT remapped to 'pending'

        row = await db.pool.fetchrow(
            "SELECT payment_status FROM cleaning_bookings WHERE id = $1",
            booking_id,
        )
        assert row["payment_status"] == "processing"
    finally:
        await db.pool.execute("DELETE FROM cleaning_bookings WHERE id = $1", booking_id)
        await db.pool.execute("DELETE FROM cleaning_clients WHERE id = $1", client_id)
        await db.pool.execute("DELETE FROM cleaning_services WHERE id = $1", svc_id)


@pytest.mark.asyncio
async def test_auto_charge_happy_updates_booking_status(db, biz_ready):
    """All gates pass → charges via mocked Stripe → booking updated with PI id + status."""
    svc_id = await _make_service(db, biz_ready)
    client_id = await _make_client(db, biz_ready, stripe_customer_id="cus_happy")
    booking_id = await _make_booking(db, biz_ready, client_id, svc_id, final_price=Decimal("125.00"))

    fake_result = {
        "success": True,
        "payment_intent_id": "pi_integration_ok",
        "status": "succeeded",
    }

    try:
        with patch(
            "app.modules.cleaning.services.booking_charge_service.charge_booking_off_session",
            AsyncMock(return_value=fake_result),
        ) as mock_charge:
            result = await try_auto_charge_booking(db, booking_id)

        assert result["attempted"] is True
        assert result["success"] is True
        assert result["payment_status"] == "succeeded"
        assert result["payment_intent_id"] == "pi_integration_ok"

        # Verify DB was updated
        row = await db.pool.fetchrow(
            "SELECT stripe_payment_intent_id, payment_status FROM cleaning_bookings WHERE id = $1",
            booking_id,
        )
        assert row["stripe_payment_intent_id"] == "pi_integration_ok"
        assert row["payment_status"] == "succeeded"

        # Verify amount was converted to cents correctly
        call_kwargs = mock_charge.call_args.kwargs
        assert call_kwargs["amount_cents"] == 12500  # 125.00 × 100
    finally:
        await db.pool.execute("DELETE FROM cleaning_bookings WHERE id = $1", booking_id)
        await db.pool.execute("DELETE FROM cleaning_clients WHERE id = $1", client_id)
        await db.pool.execute("DELETE FROM cleaning_services WHERE id = $1", svc_id)


@pytest.mark.asyncio
async def test_auto_charge_declined_persists_failure_status(db, biz_ready):
    """Card declined → booking updated with status='declined', success=False."""
    svc_id = await _make_service(db, biz_ready)
    client_id = await _make_client(db, biz_ready, stripe_customer_id="cus_fail")
    booking_id = await _make_booking(db, biz_ready, client_id, svc_id)

    fake_result = {
        "success": False,
        "payment_intent_id": None,
        "status": "declined",
        "error": "Your card was declined.",
    }

    try:
        with patch(
            "app.modules.cleaning.services.booking_charge_service.charge_booking_off_session",
            AsyncMock(return_value=fake_result),
        ):
            result = await try_auto_charge_booking(db, booking_id)

        assert result["attempted"] is True
        assert result["success"] is False
        assert result["payment_status"] == "declined"

        row = await db.pool.fetchrow(
            "SELECT stripe_payment_intent_id, payment_status FROM cleaning_bookings WHERE id = $1",
            booking_id,
        )
        assert row["stripe_payment_intent_id"] is None
        assert row["payment_status"] == "declined"
    finally:
        await db.pool.execute("DELETE FROM cleaning_bookings WHERE id = $1", booking_id)
        await db.pool.execute("DELETE FROM cleaning_clients WHERE id = $1", client_id)
        await db.pool.execute("DELETE FROM cleaning_services WHERE id = $1", svc_id)
