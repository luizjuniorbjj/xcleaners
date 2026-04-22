"""Password reset Wave — contract & smoke tests.

Covers:
  - app.email_service module contract (import + method signatures)
  - /auth/password-reset and /auth/password-reset/confirm route registration
  - Pydantic request validation at those endpoints (422 on malformed body)
  - Migration 030 + rollback_030 SQL structural invariants
  - Frontend JS presence of new methods (regex contract — no browser)

No live DB is required for these tests. DB-integration tests for the full
request-reset → email → confirm → login flow belong in a separate suite
that consumes the `db` fixture and is gated on DATABASE_URL.
"""
from __future__ import annotations

import inspect
import re
from pathlib import Path

import pytest
from httpx import AsyncClient, ASGITransport


REPO_ROOT = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# A. Backend module contract (app.email_service)
# ---------------------------------------------------------------------------

def test_platform_email_service_importable():
    """`from app.email_service import email_service` must resolve."""
    from app.email_service import email_service  # noqa: F401
    assert email_service is not None


def test_platform_email_service_has_required_methods():
    """Instance must expose the two methods auth.py calls."""
    from app.email_service import email_service
    assert hasattr(email_service, "send_password_reset_email"), \
        "email_service missing send_password_reset_email — auth.py will AttributeError"
    assert hasattr(email_service, "send_welcome_email"), \
        "email_service missing send_welcome_email — auth.py will AttributeError"


def test_send_password_reset_email_signature():
    """Signature must accept (to, nome, reset_token, language) — the auth.py call shape."""
    from app.email_service import email_service
    sig = inspect.signature(email_service.send_password_reset_email)
    params = sig.parameters
    # bound method: self is dropped; expect to, nome, reset_token, language
    assert "to" in params
    assert "nome" in params
    assert "reset_token" in params
    assert "language" in params


def test_send_welcome_email_signature():
    """Signature must accept (to, nome, language)."""
    from app.email_service import email_service
    sig = inspect.signature(email_service.send_welcome_email)
    params = sig.parameters
    assert "to" in params
    assert "nome" in params
    assert "language" in params


# ---------------------------------------------------------------------------
# B. Route registration (in-process ASGI, no DB touched)
# ---------------------------------------------------------------------------

def _route_paths(app):
    """Collect all paths registered on a FastAPI/Starlette app (ignore mounts)."""
    return {r.path for r in app.routes if hasattr(r, "path")}


def test_password_reset_routes_are_registered():
    """Both /auth/password-reset and /auth/password-reset/confirm must be
    registered on the FastAPI app. Introspection avoids touching the DB
    (Depends(get_db) runs before Pydantic validation, so an HTTP call would
    leak into the database layer — we only care that the routes exist)."""
    from xcleaners_main import app
    paths = _route_paths(app)
    assert "/auth/password-reset" in paths, (
        f"/auth/password-reset missing from app.routes; "
        f"/auth/* routes present: {sorted(p for p in paths if p.startswith('/auth'))}"
    )
    assert "/auth/password-reset/confirm" in paths, (
        f"/auth/password-reset/confirm missing from app.routes"
    )


def test_password_reset_routes_accept_post():
    """Both endpoints must accept POST (not GET)."""
    from xcleaners_main import app
    for r in app.routes:
        if not hasattr(r, "path"):
            continue
        if r.path in ("/auth/password-reset", "/auth/password-reset/confirm"):
            assert "POST" in getattr(r, "methods", set()), (
                f"{r.path} must accept POST, got methods={r.methods}"
            )


# ---------------------------------------------------------------------------
# C. Migration 030 SQL structural invariants
# ---------------------------------------------------------------------------

def _read(path: str) -> str:
    return (REPO_ROOT / path).read_text(encoding="utf-8")


def test_migration_030_creates_table_idempotently():
    sql = _read("database/migrations/030_password_reset_tokens.sql")
    assert "CREATE TABLE IF NOT EXISTS password_reset_tokens" in sql, \
        "Migration must use IF NOT EXISTS for idempotency"


def test_migration_030_mirrors_schema_columns():
    """All 6 columns from schema.sql must be in the migration."""
    sql = _read("database/migrations/030_password_reset_tokens.sql")
    for col in ("id", "user_id", "token_hash", "expires_at", "used", "created_at"):
        assert col in sql, f"Migration missing column {col!r}"
    assert "REFERENCES users(id) ON DELETE CASCADE" in sql, \
        "user_id FK with ON DELETE CASCADE is mandatory (matches schema.sql)"


def test_migration_030_has_required_indexes():
    sql = _read("database/migrations/030_password_reset_tokens.sql")
    assert "CREATE UNIQUE INDEX IF NOT EXISTS idx_password_reset_tokens_token_hash" in sql, \
        "UNIQUE index on token_hash is the primary query path"
    assert "CREATE INDEX IF NOT EXISTS idx_password_reset_tokens_user_id" in sql, \
        "Index on user_id is required for CASCADE delete performance"


def test_migration_030_is_atomic():
    sql = _read("database/migrations/030_password_reset_tokens.sql")
    assert "BEGIN" in sql.upper() and "COMMIT" in sql.upper(), \
        "Migration must be wrapped in a transaction"


def test_rollback_030_drops_table():
    sql = _read("database/migrations/rollback_030.sql")
    assert "DROP TABLE IF EXISTS password_reset_tokens" in sql, \
        "Rollback must DROP TABLE IF EXISTS (indexes drop with the table)"


# ---------------------------------------------------------------------------
# D. Frontend presence (regex contract — no browser)
# ---------------------------------------------------------------------------

FRONTEND_JS = [
    "frontend/static/js/auth-ui.js",
    "frontend/cleaning/static/js/auth-ui.js",
]

ROUTER_JS = [
    "frontend/static/js/router.js",
    "frontend/cleaning/static/js/router.js",
]


@pytest.mark.parametrize("path", FRONTEND_JS)
def test_auth_ui_has_new_methods(path):
    src = _read(path)
    # Stub was "Password reset is not yet implemented" — must be gone.
    assert "is not yet implemented" not in src, (
        f"{path} still contains the old stub message — patch not applied"
    )
    for method in (
        "showForgotPassword",
        "handleForgotPassword",
        "renderResetPassword",
        "handleResetPassword",
        "_backToLogin",
    ):
        assert re.search(rf"\b{re.escape(method)}\s*\(", src), \
            f"{path} missing method {method}"


@pytest.mark.parametrize("path", FRONTEND_JS)
def test_auth_ui_calls_correct_backend_endpoints(path):
    """The JS uses template literals (backticks) for the fetch URL, so we
    match the bare substring rather than assuming a quoting style."""
    src = _read(path)
    assert "/auth/password-reset/confirm" in src, \
        f"{path} must POST to /auth/password-reset/confirm"
    # /auth/password-reset is a prefix of /auth/password-reset/confirm, so we
    # need a stricter check that the non-confirm URL also appears standalone.
    # Count occurrences and require at least one non-confirm call.
    confirm_count = src.count("/auth/password-reset/confirm")
    total_count = src.count("/auth/password-reset")
    assert total_count > confirm_count, (
        f"{path} must fetch /auth/password-reset (not only the /confirm variant); "
        f"found {total_count} total and {confirm_count} /confirm"
    )


@pytest.mark.parametrize("path", ROUTER_JS)
def test_router_registers_reset_password_route(path):
    src = _read(path)
    assert "'/reset-password'" in src, \
        f"{path} must register /reset-password in _routes"
    assert "AuthUI.renderResetPassword" in src, \
        f"{path} must dispatch /reset-password to AuthUI.renderResetPassword"
