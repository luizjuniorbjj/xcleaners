"""
Stripe Connect Routes Tests — Sprint E item 1.

Unit-level: mocks stripe SDK to avoid real API calls. Integration with DB.

Covers:
  - create-account creates row + returns onboarding_url
  - create-account is idempotent (reused_existing=True when account exists)
  - status endpoint for disconnected vs connected account
  - dashboard-link + refresh-link require existing account (409 if not)
  - webhook signature verification (400 on bad sig)
  - webhook account.updated syncs DB flags
  - webhook returns 200 for unknown event types

Author: @dev (Neo), 2026-04-16
"""

from __future__ import annotations

import os
from uuid import UUID

import pytest
from unittest.mock import AsyncMock, patch


pytest.importorskip(
    "app.modules.cleaning.routes.stripe_connect_routes",
    reason="stripe_connect_routes not yet implemented.",
)

from app.modules.cleaning.routes.stripe_connect_routes import (  # noqa: E402
    post_create_account,
    get_status,
    post_dashboard_link,
    post_refresh_link,
    stripe_webhook,
)
from fastapi import HTTPException


# ===========================================================================
# Fixtures
# ===========================================================================


@pytest.fixture
async def biz_unconnected(db):
    """Business row without a Stripe account yet."""
    biz_id = await db.pool.fetchval(
        "INSERT INTO businesses (slug, name) "
        "VALUES ('stripe_biz_' || gen_random_uuid()::text, 'Stripe Test Biz') "
        "RETURNING id"
    )
    yield biz_id
    await db.pool.execute("DELETE FROM businesses WHERE id = $1", biz_id)


@pytest.fixture
async def biz_connected(db):
    """Business row with an existing stripe_account_id."""
    biz_id = await db.pool.fetchval(
        """
        INSERT INTO businesses
            (slug, name, stripe_account_id, stripe_account_status)
        VALUES ('stripe_connbiz_' || gen_random_uuid()::text,
                'Connected Biz', 'acct_test123', 'pending')
        RETURNING id
        """
    )
    yield biz_id
    await db.pool.execute("DELETE FROM businesses WHERE id = $1", biz_id)


def _user(business_id):
    return {
        "user_id": str(business_id),  # placeholder
        "email": "owner@test.com",
        "business_id": business_id,
        "business_slug": "stripe-test",
        "role": "lead",
        "cleaning_role": "owner",
    }


# ===========================================================================
# /create-account
# ===========================================================================


@pytest.mark.asyncio
async def test_create_account_requires_stripe_configured(db, biz_unconnected, monkeypatch):
    """503 when STRIPE_SECRET_KEY not set."""
    monkeypatch.setattr(
        "app.modules.cleaning.routes.stripe_connect_routes.STRIPE_SECRET_KEY", ""
    )
    with pytest.raises(HTTPException) as exc:
        await post_create_account(
            slug="x", user=_user(biz_unconnected), db=db,
        )
    assert exc.value.status_code == 503
    assert "not configured" in exc.value.detail.lower()


@pytest.mark.asyncio
async def test_create_account_new_business(db, biz_unconnected, monkeypatch):
    """Fresh account → calls service → persists DB → returns onboarding_url."""
    monkeypatch.setattr(
        "app.modules.cleaning.routes.stripe_connect_routes.STRIPE_SECRET_KEY", "sk_test_x"
    )
    mock_create = AsyncMock(return_value={
        "account_id": "acct_new_abc",
        "onboarding_url": "https://connect.stripe.com/setup/e/abc",
    })
    with patch(
        "app.modules.cleaning.routes.stripe_connect_routes.create_express_account",
        mock_create,
    ):
        resp = await post_create_account(
            slug="x", user=_user(biz_unconnected), db=db,
        )

    assert resp["account_id"] == "acct_new_abc"
    assert resp["onboarding_url"].startswith("https://")
    assert resp["reused_existing"] is False

    # DB persisted
    row = await db.pool.fetchrow(
        "SELECT stripe_account_id, stripe_account_status FROM businesses WHERE id = $1",
        biz_unconnected,
    )
    assert row["stripe_account_id"] == "acct_new_abc"
    assert row["stripe_account_status"] == "pending"


@pytest.mark.asyncio
async def test_create_account_idempotent(db, biz_connected, monkeypatch):
    """Second call returns reused_existing=True + fresh onboarding link."""
    monkeypatch.setattr(
        "app.modules.cleaning.routes.stripe_connect_routes.STRIPE_SECRET_KEY", "sk_test_x"
    )
    mock_refresh = AsyncMock(return_value="https://connect.stripe.com/setup/e/refreshed")
    with patch(
        "app.modules.cleaning.routes.stripe_connect_routes.refresh_onboarding_link",
        mock_refresh,
    ):
        resp = await post_create_account(
            slug="x", user=_user(biz_connected), db=db,
        )

    assert resp["account_id"] == "acct_test123"
    assert resp["reused_existing"] is True
    assert "refreshed" in resp["onboarding_url"]
    mock_refresh.assert_awaited_once()


# ===========================================================================
# /status
# ===========================================================================


@pytest.mark.asyncio
async def test_status_disconnected(db, biz_unconnected, monkeypatch):
    """No account → returns disconnected state without calling Stripe."""
    monkeypatch.setattr(
        "app.modules.cleaning.routes.stripe_connect_routes.STRIPE_SECRET_KEY", ""
    )
    resp = await get_status(slug="x", user=_user(biz_unconnected), db=db)
    assert resp["connected"] is False
    assert resp["account_id"] is None
    assert resp["status"] == "not_connected"
    assert resp["charges_enabled"] is False


@pytest.mark.asyncio
async def test_status_connected_syncs_db(db, biz_connected, monkeypatch):
    """Connected account → live retrieve + sync flags."""
    monkeypatch.setattr(
        "app.modules.cleaning.routes.stripe_connect_routes.STRIPE_SECRET_KEY", "sk_test_x"
    )
    mock_retrieve = AsyncMock(return_value={
        "charges_enabled": True,
        "payouts_enabled": True,
        "details_submitted": True,
        "requirements_due": [],
        "disabled_reason": None,
        "status": "active",
    })
    with patch(
        "app.modules.cleaning.routes.stripe_connect_routes.retrieve_account_status",
        mock_retrieve,
    ):
        resp = await get_status(slug="x", user=_user(biz_connected), db=db)

    assert resp["connected"] is True
    assert resp["charges_enabled"] is True
    assert resp["status"] == "active"

    # DB synced
    row = await db.pool.fetchrow(
        """SELECT stripe_account_status, stripe_charges_enabled, stripe_payouts_enabled,
                  stripe_connected_at
             FROM businesses WHERE id = $1""",
        biz_connected,
    )
    assert row["stripe_account_status"] == "active"
    assert row["stripe_charges_enabled"] is True
    assert row["stripe_payouts_enabled"] is True
    assert row["stripe_connected_at"] is not None  # timestamp set because charges_enabled


# ===========================================================================
# /dashboard-link & /refresh-link
# ===========================================================================


@pytest.mark.asyncio
async def test_dashboard_link_requires_connected_account(db, biz_unconnected, monkeypatch):
    monkeypatch.setattr(
        "app.modules.cleaning.routes.stripe_connect_routes.STRIPE_SECRET_KEY", "sk_test_x"
    )
    with pytest.raises(HTTPException) as exc:
        await post_dashboard_link(slug="x", user=_user(biz_unconnected), db=db)
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_dashboard_link_ok(db, biz_connected, monkeypatch):
    monkeypatch.setattr(
        "app.modules.cleaning.routes.stripe_connect_routes.STRIPE_SECRET_KEY", "sk_test_x"
    )
    mock_link = AsyncMock(return_value="https://connect.stripe.com/express/acct_test123/login")
    with patch(
        "app.modules.cleaning.routes.stripe_connect_routes.create_dashboard_link",
        mock_link,
    ):
        resp = await post_dashboard_link(slug="x", user=_user(biz_connected), db=db)
    assert resp["dashboard_url"].startswith("https://")


@pytest.mark.asyncio
async def test_refresh_link_requires_connected_account(db, biz_unconnected, monkeypatch):
    monkeypatch.setattr(
        "app.modules.cleaning.routes.stripe_connect_routes.STRIPE_SECRET_KEY", "sk_test_x"
    )
    with pytest.raises(HTTPException) as exc:
        await post_refresh_link(slug="x", user=_user(biz_unconnected), db=db)
    assert exc.value.status_code == 409


# ===========================================================================
# Webhook
# ===========================================================================


class _FakeRequest:
    """Minimal Request stub for the webhook handler."""
    def __init__(self, body: bytes, headers: dict):
        self._body = body
        self.headers = headers

    async def body(self):
        return self._body


@pytest.mark.asyncio
async def test_webhook_ignores_when_secret_missing(db, monkeypatch):
    """Without STRIPE_WEBHOOK_SECRET → return 200 but processed=False."""
    monkeypatch.setattr(
        "app.modules.cleaning.routes.stripe_connect_routes.STRIPE_WEBHOOK_SECRET", ""
    )
    req = _FakeRequest(b'{"type":"account.updated"}', {"stripe-signature": "x"})
    resp = await stripe_webhook(req, db)
    assert resp["received"] is True
    assert resp["processed"] is False
    assert resp["reason"] == "not_configured"


@pytest.mark.asyncio
async def test_webhook_rejects_bad_signature(db, monkeypatch):
    """With secret configured but bad signature → 400."""
    monkeypatch.setattr(
        "app.modules.cleaning.routes.stripe_connect_routes.STRIPE_WEBHOOK_SECRET",
        "whsec_test",
    )
    req = _FakeRequest(b'{"type":"account.updated"}', {"stripe-signature": "bad"})
    with pytest.raises(HTTPException) as exc:
        await stripe_webhook(req, db)
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_webhook_account_updated_syncs_db(db, biz_connected, monkeypatch):
    """Simulated account.updated event → business flags synced."""
    monkeypatch.setattr(
        "app.modules.cleaning.routes.stripe_connect_routes.STRIPE_WEBHOOK_SECRET",
        "whsec_test",
    )

    fake_event = {
        "type": "account.updated",
        "data": {
            "object": {
                "id": "acct_test123",
                "charges_enabled": True,
                "payouts_enabled": True,
                "details_submitted": True,
                "requirements": {"disabled_reason": None},
            }
        },
    }

    class _FakeWebhook:
        @staticmethod
        def construct_event(payload, sig, secret):
            return fake_event

    class _FakeStripe:
        Webhook = _FakeWebhook

    req = _FakeRequest(b"{}", {"stripe-signature": "t=1,v1=x"})
    with patch.dict("sys.modules", {"stripe": _FakeStripe}):
        resp = await stripe_webhook(req, db)

    assert resp["processed"] is True
    row = await db.pool.fetchrow(
        """SELECT stripe_account_status, stripe_charges_enabled, stripe_payouts_enabled
             FROM businesses WHERE stripe_account_id = 'acct_test123'""",
    )
    assert row is not None
    assert row["stripe_account_status"] == "active"
    assert row["stripe_charges_enabled"] is True


@pytest.mark.asyncio
async def test_webhook_unknown_event_returns_200(db, monkeypatch):
    """Unknown event types still return 200 (Stripe doesn't retry)."""
    monkeypatch.setattr(
        "app.modules.cleaning.routes.stripe_connect_routes.STRIPE_WEBHOOK_SECRET",
        "whsec_test",
    )

    class _FakeWebhook:
        @staticmethod
        def construct_event(payload, sig, secret):
            return {"type": "customer.created", "data": {"object": {}}}

    class _FakeStripe:
        Webhook = _FakeWebhook

    req = _FakeRequest(b"{}", {"stripe-signature": "t=1,v1=x"})
    with patch.dict("sys.modules", {"stripe": _FakeStripe}):
        resp = await stripe_webhook(req, db)

    assert resp["received"] is True
    assert resp["processed"] is False
    assert resp["type"] == "customer.created"
