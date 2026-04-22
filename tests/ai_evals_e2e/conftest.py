"""
E2E EVAL conftest — fixtures for ai_evals_e2e suite.

We deliberately keep all fixtures function-scoped so pytest-asyncio uses the
default per-test event loop. Mixing session-scoped async fixtures with
function-scoped tests causes "attached to a different loop" errors.

EVAL_TAG marks every booking row created here so the autouse cleanup_e2e
fixture can purge them deterministically.
"""

from __future__ import annotations

import os
from datetime import date, timedelta

import pytest
import pytest_asyncio

EVAL_TAG = "[AI_EVAL_E2E]"
QATEST_BUSINESS_ID = "af168a02-be55-4714-bbe2-9c979943f89c"
QATEST_SLUG = "qatest-cleaning-co"
LUIZ_CLIENT_NAME = ("luiz", "silva")


@pytest_asyncio.fixture
async def db():
    """Fresh Database instance per test (avoids cross-loop pool reuse).

    We bypass the singleton (get_db_instance) and build a dedicated pool
    for each test, then dispose. This avoids pytest-asyncio's per-test event
    loop closing the singleton's pool and breaking subsequent tests.
    """
    import os as _os
    import asyncpg
    from app.core import db as _db_mod  # type: ignore

    dsn = _os.environ.get("DATABASE_URL")
    if not dsn:
        pytest.skip("DATABASE_URL not set")

    pool = await asyncpg.create_pool(dsn, min_size=1, max_size=3)

    class _Wrapper:
        def __init__(self, p): self.pool = p

    inst = _Wrapper(pool)

    # Some service modules read app.database.get_db_instance() — patch it
    # so they use our test pool instead of the singleton.
    from app import database as _legacy
    original = _legacy.get_db_instance

    async def _stub():
        return inst

    _legacy.get_db_instance = _stub
    try:
        yield inst
    finally:
        _legacy.get_db_instance = original
        await pool.close()


@pytest_asyncio.fixture
async def qatest(db):
    biz = QATEST_BUSINESS_ID

    client_row = await db.pool.fetchrow(
        """SELECT id, user_id, first_name, last_name, phone, email
           FROM cleaning_clients
           WHERE business_id = $1 AND first_name ILIKE $2 AND last_name ILIKE $3
           LIMIT 1""",
        biz, f"%{LUIZ_CLIENT_NAME[0]}%", f"%{LUIZ_CLIENT_NAME[1]}%",
    )
    if not client_row:
        pytest.skip(f"qatest client matching {LUIZ_CLIENT_NAME} not found")

    services = {}
    for row in await db.pool.fetch(
        "SELECT id, name FROM cleaning_services WHERE business_id = $1 AND is_active = true",
        biz,
    ):
        services[row["name"]] = str(row["id"])

    return {
        "business_id": biz,
        "slug": QATEST_SLUG,
        "client_id": str(client_row["id"]),
        "client_user_id": str(client_row["user_id"]) if client_row["user_id"] else None,
        "client_name": f"{client_row['first_name']} {client_row['last_name']}",
        "client_phone": client_row["phone"],
        "client_email": client_row["email"],
        "services": services,
    }


async def _cleanup_e2e_bookings(db):
    """Delete every booking the eval suite could have created.

    Two patterns: (1) rows seeded by _create_booking_direct (carry the
    EVAL_TAG marker), and (2) rows the AI created in this run (any ai_chat
    booking for the qatest client whose scheduled_date falls in the eval
    window of 4-9 days from today). The second pattern catches AI-created
    rows even when the LLM ignored our request to set special_instructions.
    """
    await db.pool.execute(
        "DELETE FROM cleaning_bookings WHERE special_instructions LIKE $1",
        f"{EVAL_TAG}%",
    )
    luiz_row = await db.pool.fetchrow(
        """SELECT id FROM cleaning_clients
           WHERE business_id = $1 AND first_name ILIKE $2 AND last_name ILIKE $3
           LIMIT 1""",
        QATEST_BUSINESS_ID, f"%{LUIZ_CLIENT_NAME[0]}%", f"%{LUIZ_CLIENT_NAME[1]}%",
    )
    if luiz_row:
        await db.pool.execute(
            """DELETE FROM cleaning_bookings
               WHERE business_id = $1 AND client_id = $2
                 AND source = 'ai_chat'
                 AND scheduled_date BETWEEN CURRENT_DATE + INTERVAL '4 days'
                                        AND CURRENT_DATE + INTERVAL '9 days'""",
            QATEST_BUSINESS_ID, luiz_row["id"],
        )


@pytest_asyncio.fixture(autouse=True)
async def cleanup_e2e(db):
    await _cleanup_e2e_bookings(db)
    yield
    await _cleanup_e2e_bookings(db)


@pytest.fixture
def future_slot():
    d = (date.today() + timedelta(days=5)).isoformat()
    return {"date": d, "start": "14:00", "duration_minutes": 120}


@pytest.fixture
def future_slot_alt():
    d = (date.today() + timedelta(days=7)).isoformat()
    return {"date": d, "start": "10:00"}


def pytest_collection_modifyitems(config, items):
    if not os.getenv("OPENAI_API_KEY"):
        skip = pytest.mark.skip(reason="OPENAI_API_KEY required for e2e AI eval")
        for item in items:
            item.add_marker(skip)
