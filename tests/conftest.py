"""
Xcleaners Test Configuration.

Provides:
    - Environment setup (secrets, DATABASE_URL) before app imports
    - anyio_backend fixture (required by pytest-anyio if used)
    - async `db` fixture (asyncpg pool wrapper) for integration tests
    - Automatic skip if DATABASE_URL unavailable

Integration tests require PostgreSQL running at DATABASE_URL with schema
+ migrations applied. See docs/migrations/migration-021-validation.md
for bootstrap procedure in dev.
"""

from __future__ import annotations

import os

# ---------------------------------------------------------------------------
# Environment MUST be set BEFORE any app import (config.py validates these).
# ---------------------------------------------------------------------------

os.environ.setdefault("SECRET_KEY", "test-secret-key-for-testing-only")
os.environ.setdefault(
    "ENCRYPTION_KEY",
    # Valid Fernet key (32 bytes base64) — NOT for production
    "AcL0G8VR6HgZFKQ81p1NexRgRxNY03cf84MQ4i8XIcg=",
)
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql://xcleaners:xcleaners@localhost:5432/xcleaners_dev",
)
os.environ.setdefault("DEBUG", "true")

import pytest
import pytest_asyncio


# ---------------------------------------------------------------------------
# Backend fixture (anyio compatibility)
# ---------------------------------------------------------------------------

@pytest.fixture
def anyio_backend():
    return "asyncio"


# ---------------------------------------------------------------------------
# DB fixture for integration tests
# ---------------------------------------------------------------------------

class _DBWrapper:
    """
    Minimal wrapper exposing `.pool` attribute.

    Production code uses `app.core.db.Database` which has this same shape.
    Tests use this light wrapper to avoid importing the full Database class
    (which triggers role-setting init that may fail on dev DBs).
    """
    def __init__(self, pool):
        self.pool = pool


@pytest_asyncio.fixture(scope="function")
async def db():
    """
    Async DB fixture — creates asyncpg pool per test.

    Skips the test if DATABASE_URL is empty or connection fails.
    Function-scoped for isolation; each test gets a fresh pool.
    """
    db_url = os.environ.get("DATABASE_URL", "").strip()
    if not db_url:
        pytest.skip("DATABASE_URL not set; skipping DB-integration test")

    try:
        import asyncpg
    except ImportError:
        pytest.skip("asyncpg not installed")

    try:
        pool = await asyncpg.create_pool(
            db_url,
            min_size=1,
            max_size=3,
            # NOTE: no `init=SET ROLE` — dev DB doesn't have xcleaners_app role
        )
    except Exception as e:
        pytest.skip(f"Could not connect to DATABASE_URL: {e}")

    try:
        yield _DBWrapper(pool)
    finally:
        await pool.close()
