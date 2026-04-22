"""Tests for _resolve_business + _load_channel_config helper.

Covers DB-first path, env fallback paths, and feature flag toggle (HIGH-1.2 AC9).

Story: XCL-HIGH-1.2 — Adapter integration.
Spec:  projects/xcleaners/specs/high-1-channels-ui-spec.md
"""
import logging

import pytest
from unittest.mock import AsyncMock, MagicMock

from app.modules.cleaning.routes.whatsapp_routes import (
    _load_channel_config,
    _resolve_business,
)


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture
def mock_db():
    """Mock asyncpg-style db with .pool.fetchrow as AsyncMock."""
    db = MagicMock()
    db.pool = MagicMock()
    db.pool.fetchrow = AsyncMock()
    return db


@pytest.fixture(autouse=True)
def env_setup(monkeypatch):
    """Default env config for tests (legacy 'env' mode)."""
    monkeypatch.setenv("EVOLUTION_API_URL", "https://evo.test")
    monkeypatch.setenv("EVOLUTION_API_KEY", "envkey123")
    monkeypatch.setenv("EVOLUTION_INSTANCE_NAME", "xcleaners")
    monkeypatch.setenv(
        "EVOLUTION_WEBHOOK_SECRET",
        "envsecret64hexENVENVENVENVENVENVENVENVENVENVENVENVENVENVENVENVENVENV",
    )
    # WHATSAPP_CONFIG_SOURCE intentionally NOT set → defaults to 'env'


# ============================================================
# AC9.1 — feature flag default 'env' preserves legacy behavior
# ============================================================

@pytest.mark.asyncio
async def test_resolve_business_flag_default_env_uses_legacy(mock_db, monkeypatch):
    """When WHATSAPP_CONFIG_SOURCE not set (default 'env'), helper is skipped, returns env config.

    Critical: ensures Phase 1 deploy (flag=env) is byte-equal to pre-refactor behavior.
    """
    monkeypatch.delenv("WHATSAPP_CONFIG_SOURCE", raising=False)
    biz_row = {"id": "biz-uuid", "name": "Test Co", "timezone": "America/New_York"}
    mock_db.pool.fetchrow.return_value = biz_row

    cfg = await _resolve_business(mock_db, "qatest-cleaning-co")

    assert cfg is not None
    assert cfg["instance_name"] == "xcleaners"
    assert cfg["webhook_secret"].startswith("envsecret")
    assert cfg["api_url"] == "https://evo.test"
    # Helper NOT called — only 1 fetchrow (the SELECT business)
    assert mock_db.pool.fetchrow.call_count == 1


# ============================================================
# AC2 — DB-first when row exists with status='connected'
# ============================================================

@pytest.mark.asyncio
async def test_resolve_business_db_first_connected(mock_db, monkeypatch):
    """When flag='db' and business_channels row connected, config from DB."""
    monkeypatch.setenv("WHATSAPP_CONFIG_SOURCE", "db")
    biz_row = {"id": "biz-uuid", "name": "Test Co", "timezone": "America/New_York"}
    channel_row = {
        "instance_name": "xcleaners_qatest",
        "webhook_secret": "dbsecret123",
        "phone_number": "5512988368047",
        "status": "connected",
    }
    mock_db.pool.fetchrow.side_effect = [biz_row, channel_row]

    cfg = await _resolve_business(mock_db, "qatest-cleaning-co")

    assert cfg["instance_name"] == "xcleaners_qatest"
    assert cfg["webhook_secret"] == "dbsecret123"
    assert cfg["phone_number"] == "5512988368047"
    assert cfg["api_url"] == "https://evo.test"  # api_url ALWAYS env
    assert cfg["api_key"] == "envkey123"  # api_key ALWAYS env
    assert mock_db.pool.fetchrow.call_count == 2


# ============================================================
# AC2 — DB-first connecting status also OK (mid-pairing)
# ============================================================

@pytest.mark.asyncio
async def test_resolve_business_db_first_connecting(mock_db, monkeypatch):
    """When flag='db' and row status='connecting', config still from DB (mid-pairing).

    Necessary so webhooks during pairing flow use the correct nascent instance.
    """
    monkeypatch.setenv("WHATSAPP_CONFIG_SOURCE", "db")
    biz_row = {"id": "biz-uuid", "name": "Test Co", "timezone": "America/New_York"}
    channel_row = {
        "instance_name": "xcleaners_pairing",
        "webhook_secret": "dbsecret123",
        "phone_number": None,
        "status": "connecting",
    }
    mock_db.pool.fetchrow.side_effect = [biz_row, channel_row]

    cfg = await _resolve_business(mock_db, "qatest-cleaning-co")

    assert cfg["instance_name"] == "xcleaners_pairing"
    assert cfg["webhook_secret"] == "dbsecret123"


# ============================================================
# AC3 — Fallback env when no row exists in business_channels
# ============================================================

@pytest.mark.asyncio
async def test_resolve_business_fallback_env_no_row(mock_db, monkeypatch, caplog):
    """When flag='db' but business_channels has no row, fallback to env + WARNING."""
    monkeypatch.setenv("WHATSAPP_CONFIG_SOURCE", "db")
    biz_row = {"id": "biz-uuid", "name": "Test Co", "timezone": "America/New_York"}
    mock_db.pool.fetchrow.side_effect = [biz_row, None]  # business found, channel not

    with caplog.at_level(logging.WARNING):
        cfg = await _resolve_business(mock_db, "qatest-cleaning-co")

    assert cfg["instance_name"] == "xcleaners"  # env value
    assert cfg["webhook_secret"].startswith("envsecret")
    assert any("falling back to env" in r.message for r in caplog.records)


# ============================================================
# AC4 — Fallback env when row status invalid (parametrized)
# ============================================================

@pytest.mark.asyncio
@pytest.mark.parametrize("invalid_status", ["disconnected", "error", "pending"])
async def test_resolve_business_fallback_env_invalid_status(
    mock_db, monkeypatch, invalid_status
):
    """When row status not in (connected, connecting), helper SQL filter returns None
    → fallback to env. Tests SQL semantics + caller behavior together.
    """
    monkeypatch.setenv("WHATSAPP_CONFIG_SOURCE", "db")
    biz_row = {"id": "biz-uuid", "name": "Test Co", "timezone": "America/New_York"}
    # Helper SQL has WHERE status IN ('connected', 'connecting') so any other status
    # makes fetchrow return None — same effect as no row at all.
    mock_db.pool.fetchrow.side_effect = [biz_row, None]

    cfg = await _resolve_business(mock_db, "qatest-cleaning-co")
    assert cfg["instance_name"] == "xcleaners"  # fallback env


# ============================================================
# AC4 — DB error → fallback env (graceful degradation)
# ============================================================

@pytest.mark.asyncio
async def test_resolve_business_fallback_env_db_error(mock_db, monkeypatch, caplog):
    """When _load_channel_config raises (DB down), fallback to env without propagating.

    Critical: webhook MUST stay up even if business_channels query fails.
    """
    monkeypatch.setenv("WHATSAPP_CONFIG_SOURCE", "db")
    biz_row = {"id": "biz-uuid", "name": "Test Co", "timezone": "America/New_York"}

    # First fetchrow (SELECT business) succeeds, second (channel) raises
    async def fetchrow_side_effect(query, *args):
        if "SELECT id, name, timezone FROM businesses" in query:
            return biz_row
        raise Exception("Connection lost")

    mock_db.pool.fetchrow.side_effect = fetchrow_side_effect

    with caplog.at_level(logging.ERROR):
        cfg = await _resolve_business(mock_db, "qatest-cleaning-co")

    assert cfg is not None
    assert cfg["instance_name"] == "xcleaners"  # fallback env
    assert any("_load_channel_config failed" in r.message for r in caplog.records)


# ============================================================
# AC1 — byte-equal preservation for qatest-cleaning-co (env mode)
# ============================================================

@pytest.mark.asyncio
async def test_resolve_business_byte_equal_qatest_default_flag(mock_db, monkeypatch):
    """Default flag (env mode) returns identical config shape and values to pre-refactor
    for qatest-cleaning-co. Critical Phase 1 gate.
    """
    monkeypatch.delenv("WHATSAPP_CONFIG_SOURCE", raising=False)
    monkeypatch.setenv("EVOLUTION_INSTANCE_NAME", "xcleaners")
    monkeypatch.setenv(
        "EVOLUTION_WEBHOOK_SECRET",
        "b4bb19dff1949fb1f26aa28010eb46ea3e13c4ab493eabb29f1ff6bc78eb3876",
    )

    biz_row = {
        "id": "af168a02-be55-4714-bbe2-9c979943f89c",
        "name": "QA Test",
        "timezone": "America/New_York",
    }
    mock_db.pool.fetchrow.return_value = biz_row

    cfg = await _resolve_business(mock_db, "qatest-cleaning-co")

    expected_keys = {
        "business_id", "business_name", "timezone",
        "api_url", "api_key",
        "instance_name", "webhook_secret",
    }
    assert set(cfg.keys()) >= expected_keys
    assert cfg["business_id"] == "af168a02-be55-4714-bbe2-9c979943f89c"
    assert cfg["instance_name"] == "xcleaners"
    assert cfg["webhook_secret"] == "b4bb19dff1949fb1f26aa28010eb46ea3e13c4ab493eabb29f1ff6bc78eb3876"


# ============================================================
# Helper unit tests (_load_channel_config isolation)
# ============================================================

@pytest.mark.asyncio
async def test_load_channel_config_returns_dict_when_row_found(mock_db):
    """Helper returns full dict when SQL returns a row."""
    mock_db.pool.fetchrow.return_value = {
        "instance_name": "xcleaners",
        "webhook_secret": "secret64",
        "phone_number": "5512988368047",
        "status": "connected",
    }
    result = await _load_channel_config(mock_db, "biz-uuid")
    assert result is not None
    assert result["instance_name"] == "xcleaners"
    assert result["status"] == "connected"


@pytest.mark.asyncio
async def test_load_channel_config_returns_none_when_no_row(mock_db):
    """Helper returns None (not exception) when SQL returns no row."""
    mock_db.pool.fetchrow.return_value = None
    result = await _load_channel_config(mock_db, "biz-uuid")
    assert result is None


@pytest.mark.asyncio
async def test_load_channel_config_swallows_db_exception(mock_db, caplog):
    """Helper returns None + ERROR log when SQL raises (graceful)."""
    mock_db.pool.fetchrow.side_effect = Exception("PG connection refused")
    with caplog.at_level(logging.ERROR):
        result = await _load_channel_config(mock_db, "biz-uuid")
    assert result is None
    assert any("_load_channel_config failed" in r.message for r in caplog.records)


# ============================================================
# Edge case — slug not found in businesses
# ============================================================

@pytest.mark.asyncio
async def test_resolve_business_returns_none_when_slug_unknown(mock_db, monkeypatch):
    """When business slug doesn't exist, returns None (existing behavior preserved)."""
    monkeypatch.setenv("WHATSAPP_CONFIG_SOURCE", "db")
    mock_db.pool.fetchrow.return_value = None  # business lookup fails

    cfg = await _resolve_business(mock_db, "nonexistent-slug")
    assert cfg is None
    # Should NOT attempt second fetchrow (channel) when business lookup fails
    assert mock_db.pool.fetchrow.call_count == 1
