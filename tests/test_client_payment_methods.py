"""
Tests for client payment-methods endpoints (Stripe Connect setup-intent flow) [3S-1].

Unit-level with mocked stripe SDK. Integration with DB fixtures.

Covers:
  - POST /setup-intent: happy path returns client_secret + persists customer_id
  - POST /setup-intent: reuses existing stripe_customer_id (no new Customer.create)
  - POST /setup-intent: client not found → 404
  - POST /setup-intent: business without Stripe → 409
  - GET /payment-methods: client without stripe_customer_id → empty list
  - GET /payment-methods: client with stripe_customer_id → returns mocked list
  - DELETE /payment-methods/{pm}: success → 204

Author: @dev (Neo), 2026-04-17 — Feature 3S-1
"""

from __future__ import annotations

import os
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException


pytest.importorskip(
    "app.modules.cleaning.routes.clients",
    reason="cleaning.clients routes not available.",
)

from app.modules.cleaning.routes.clients import (  # noqa: E402
    api_create_client_setup_intent,
    api_list_client_payment_methods,
    api_detach_client_payment_method,
)


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
async def biz_connected(db):
    """Business with a stripe_account_id."""
    biz_id = await db.pool.fetchval(
        """
        INSERT INTO businesses (slug, name, stripe_account_id, stripe_charges_enabled)
        VALUES ('pm_biz_' || gen_random_uuid()::text, 'PM Test Biz', 'acct_test_pm_biz', TRUE)
        RETURNING id
        """
    )
    yield biz_id
    await db.pool.execute("DELETE FROM businesses WHERE id = $1", biz_id)


@pytest.fixture
async def biz_not_connected(db):
    """Business without any Stripe account."""
    biz_id = await db.pool.fetchval(
        """
        INSERT INTO businesses (slug, name)
        VALUES ('pm_biz_noconn_' || gen_random_uuid()::text, 'PM No Stripe')
        RETURNING id
        """
    )
    yield biz_id
    await db.pool.execute("DELETE FROM businesses WHERE id = $1", biz_id)


@pytest.fixture
async def client_without_customer(db, biz_connected):
    """Client without a stripe_customer_id yet."""
    cid = await db.pool.fetchval(
        """
        INSERT INTO cleaning_clients (business_id, first_name, last_name, email, phone)
        VALUES ($1, 'Jane', 'Doe', 'jane.pm@test.example', '+15550000')
        RETURNING id
        """,
        biz_connected,
    )
    yield cid
    await db.pool.execute("DELETE FROM cleaning_clients WHERE id = $1", cid)


@pytest.fixture
async def client_with_customer(db, biz_connected):
    """Client with an existing stripe_customer_id."""
    cid = await db.pool.fetchval(
        """
        INSERT INTO cleaning_clients (business_id, first_name, last_name, email, phone, stripe_customer_id)
        VALUES ($1, 'John', 'Smith', 'john.pm@test.example', '+15550001', 'cus_existing_test')
        RETURNING id
        """,
        biz_connected,
    )
    yield cid
    await db.pool.execute("DELETE FROM cleaning_clients WHERE id = $1", cid)


def _user(business_id):
    return {
        "user_id": str(uuid.uuid4()),
        "email": "owner@test.com",
        "business_id": business_id,
        "business_slug": "pm-test",
        "role": "owner",
    }


# ============================================================================
# POST /setup-intent
# ============================================================================


@pytest.mark.asyncio
async def test_setup_intent_happy_path_persists_customer_id(
    db, biz_connected, client_without_customer, monkeypatch,
):
    """First call: creates new Stripe Customer + SetupIntent, persists customer_id in DB."""
    monkeypatch.setattr(
        "app.modules.cleaning.routes.clients.STRIPE_SECRET_KEY_PRESENT", True
    )

    mock_service = AsyncMock(return_value={
        "customer_id": "cus_new_from_service",
        "setup_intent_id": "seti_abc",
        "client_secret": "seti_abc_secret_xyz",
    })

    with patch(
        "app.modules.cleaning.routes.clients.create_setup_intent_for_client",
        mock_service,
    ):
        result = await api_create_client_setup_intent(
            slug="pm-test",
            client_id=str(client_without_customer),
            user=_user(biz_connected),
            db=db,
        )

    assert result["customer_id"] == "cus_new_from_service"
    assert result["client_secret"] == "seti_abc_secret_xyz"
    assert result["setup_intent_id"] == "seti_abc"

    # DB was updated with the new customer_id
    persisted = await db.pool.fetchval(
        "SELECT stripe_customer_id FROM cleaning_clients WHERE id = $1",
        client_without_customer,
    )
    assert persisted == "cus_new_from_service"

    # Service was called WITHOUT existing_customer_id (it was NULL)
    call_kwargs = mock_service.call_args.kwargs
    assert call_kwargs["existing_customer_id"] is None


@pytest.mark.asyncio
async def test_setup_intent_reuses_existing_customer(
    db, biz_connected, client_with_customer, monkeypatch,
):
    """Second call: reuses the stored stripe_customer_id, no new Customer.create."""
    monkeypatch.setattr(
        "app.modules.cleaning.routes.clients.STRIPE_SECRET_KEY_PRESENT", True
    )

    mock_service = AsyncMock(return_value={
        "customer_id": "cus_existing_test",
        "setup_intent_id": "seti_new",
        "client_secret": "seti_new_secret",
    })

    with patch(
        "app.modules.cleaning.routes.clients.create_setup_intent_for_client",
        mock_service,
    ):
        result = await api_create_client_setup_intent(
            slug="pm-test",
            client_id=str(client_with_customer),
            user=_user(biz_connected),
            db=db,
        )

    assert result["customer_id"] == "cus_existing_test"

    call_kwargs = mock_service.call_args.kwargs
    assert call_kwargs["existing_customer_id"] == "cus_existing_test"


@pytest.mark.asyncio
async def test_setup_intent_client_not_found_returns_404(
    db, biz_connected, monkeypatch,
):
    monkeypatch.setattr(
        "app.modules.cleaning.routes.clients.STRIPE_SECRET_KEY_PRESENT", True
    )

    with pytest.raises(HTTPException) as exc:
        await api_create_client_setup_intent(
            slug="pm-test",
            client_id=str(uuid.uuid4()),
            user=_user(biz_connected),
            db=db,
        )
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_setup_intent_business_not_connected_returns_409(
    db, biz_not_connected, monkeypatch,
):
    """Business without stripe_account_id → 409 Conflict."""
    # Create a client for the unconnected business
    cid = await db.pool.fetchval(
        """
        INSERT INTO cleaning_clients (business_id, first_name, last_name, email)
        VALUES ($1, 'Client', 'Orphan', 'orphan@test.example')
        RETURNING id
        """,
        biz_not_connected,
    )
    try:
        with pytest.raises(HTTPException) as exc:
            await api_create_client_setup_intent(
                slug="pm-test",
                client_id=str(cid),
                user=_user(biz_not_connected),
                db=db,
            )
        assert exc.value.status_code == 409
    finally:
        await db.pool.execute("DELETE FROM cleaning_clients WHERE id = $1", cid)


# ============================================================================
# GET /payment-methods
# ============================================================================


@pytest.mark.asyncio
async def test_list_pms_without_customer_returns_empty(
    db, biz_connected, client_without_customer, monkeypatch,
):
    monkeypatch.setattr(
        "app.modules.cleaning.routes.clients.STRIPE_SECRET_KEY_PRESENT", True
    )

    result = await api_list_client_payment_methods(
        slug="pm-test",
        client_id=str(client_without_customer),
        user=_user(biz_connected),
        db=db,
    )
    assert result == {"payment_methods": []}


@pytest.mark.asyncio
async def test_list_pms_with_customer_returns_cards(
    db, biz_connected, client_with_customer, monkeypatch,
):
    monkeypatch.setattr(
        "app.modules.cleaning.routes.clients.STRIPE_SECRET_KEY_PRESENT", True
    )

    fake_cards = [
        {"id": "pm_1", "brand": "visa", "last4": "4242",
         "exp_month": 12, "exp_year": 2030},
        {"id": "pm_2", "brand": "mastercard", "last4": "5555",
         "exp_month": 6, "exp_year": 2028},
    ]

    with patch(
        "app.modules.cleaning.routes.clients.list_saved_payment_methods",
        AsyncMock(return_value=fake_cards),
    ):
        result = await api_list_client_payment_methods(
            slug="pm-test",
            client_id=str(client_with_customer),
            user=_user(biz_connected),
            db=db,
        )

    assert result == {"payment_methods": fake_cards}


# ============================================================================
# DELETE /payment-methods/{pm_id}
# ============================================================================


@pytest.mark.asyncio
async def test_detach_pm_happy_path(
    db, biz_connected, client_with_customer, monkeypatch,
):
    monkeypatch.setattr(
        "app.modules.cleaning.routes.clients.STRIPE_SECRET_KEY_PRESENT", True
    )

    detach_mock = AsyncMock(return_value=None)
    with patch(
        "app.modules.cleaning.routes.clients.detach_payment_method",
        detach_mock,
    ):
        result = await api_detach_client_payment_method(
            slug="pm-test",
            client_id=str(client_with_customer),
            pm_id="pm_to_remove",
            user=_user(biz_connected),
            db=db,
        )
    assert result is None
    detach_mock.assert_awaited_once_with("acct_test_pm_biz", "pm_to_remove")
