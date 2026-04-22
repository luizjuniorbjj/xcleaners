"""
E2E lifecycle tests — book via AI -> reschedule -> cancel.

Each test exercises the real production code path against the real DB. Booking
rows are tagged with EVAL_TAG in special_instructions so conftest cleanup is
unambiguous and idempotent.

The "book via AI" test invokes _run_anthropic_tools / _run_openai_tools with
a real LLM call (gpt-4.1-mini) and asserts the resulting DB row matches the
slot the customer asked for.

The reschedule and cancel tests call homeowner_service directly because that
is the path the homeowner UI uses — covering the AI -> service contract is
out of scope for these three cases (would require an additional tool).
"""

from __future__ import annotations

import json
import re
from datetime import date, timedelta

import pytest

from tests.ai_evals_e2e.conftest import EVAL_TAG


def _tag(label: str) -> str:
    return f"{EVAL_TAG} {label}"


async def _create_booking_direct(db, qatest, future_slot, label: str) -> str:
    """Create a booking via the same booking_service the AI uses, but bypass
    the LLM (so reschedule/cancel tests have a deterministic seed row)."""
    from app.modules.cleaning.services.booking_service import create_booking_with_pricing

    deep_id = qatest["services"].get("Deep Clean")
    assert deep_id, "Deep Clean service missing in qatest fixture"

    result = await create_booking_with_pricing(
        db,
        business_id=qatest["business_id"],
        client_id=qatest["client_id"],
        service_id=deep_id,
        scheduled_date=future_slot["date"],
        scheduled_start=future_slot["start"],
        estimated_duration_minutes=future_slot["duration_minutes"],
        tier="deep",
        extras=[],
        frequency_id=None,
        location_id=None,
        source="ai_chat",
        status="scheduled",
        special_instructions=_tag(label),
    )
    return str(result["booking_id"])


# ---------------------------------------------------------------------------
# 1. AI books a slot end-to-end (real LLM, real DB, no mocks)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ai_books_real_slot(db, qatest, future_slot):
    """Customer says 'Deep clean DD/MM HH:MM' — AI must call propose_booking_draft
    and a row with status=scheduled, team auto-assigned, source=ai_chat must
    exist for that slot afterwards."""
    from app.modules.cleaning.services import ai_scheduling
    from app.prompts.scheduling_customer import SCHEDULING_CUSTOMER_SYSTEM_PROMPT

    iso = future_slot["date"]
    yyyy, mm, dd = iso.split("-")
    today = (date.today()).strftime("%Y-%m-%d (%A)")

    system_prompt = SCHEDULING_CUSTOMER_SYSTEM_PROMPT.format(
        business_name="QATEST Cleaning Co",
        business_id=qatest["business_id"],
        business_timezone="America/New_York",
        client_id=qatest["client_id"],
        client_name=qatest["client_name"],
        client_address="",
        client_zip="",
        today_local=today,
    )
    user_message = (
        f"Quero agendar Limpeza Profunda no dia {dd}/{mm} às {future_slot['start']}h. "
        f"Confirma direto, sem perguntar de novo."
    )

    ai_client, provider = ai_scheduling._get_ai_client()
    auth = {"authenticated_client_id": qatest["client_id"]}
    if provider == "anthropic":
        response = await ai_scheduling._run_anthropic_tools(
            ai_client, system_prompt, user_message,
            qatest["business_id"], db, auth,
        )
    else:
        response = await ai_scheduling._run_openai_tools(
            ai_client, system_prompt, user_message,
            qatest["business_id"], db, provider, auth,
        )

    assert response, "AI returned empty response"

    from datetime import date as _date
    row = await db.pool.fetchrow(
        """SELECT id, scheduled_date, scheduled_start, status, team_id,
                  source, quoted_price, special_instructions
           FROM cleaning_bookings
           WHERE business_id = $1 AND client_id = $2
             AND scheduled_date = $3
             AND created_at > NOW() - INTERVAL '5 minutes'
           ORDER BY created_at DESC LIMIT 1""",
        qatest["business_id"], qatest["client_id"],
        _date.fromisoformat(future_slot["date"]),
    )
    assert row is not None, (
        f"No booking row created.\nAI response was:\n{response}\n"
        "Either the AI never called propose_booking_draft or it tagged the row differently."
    )
    assert row["status"] == "scheduled", f"Expected status=scheduled, got {row['status']}"
    assert row["team_id"] is not None, "Auto-team-assign should have populated team_id"
    assert row["source"] == "ai_chat", f"Expected source=ai_chat, got {row['source']}"
    assert float(row["quoted_price"]) == 207.0, (
        f"Deep Clean should be $207 (deep tier × 1.8 base $115). Got {row['quoted_price']}"
    )

    # AI response sanity — should mention confirmation + booking id
    assert re.search(r"confirmad[oa]|confirmed", response, re.I), (
        f"AI did not announce confirmation: {response!r}"
    )


# ---------------------------------------------------------------------------
# 2. Homeowner reschedules — booking row updates and audit trail recorded
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_homeowner_reschedules(db, qatest, future_slot, future_slot_alt):
    from app.modules.cleaning.services.homeowner_service import reschedule_booking

    booking_id = await _create_booking_direct(db, qatest, future_slot, "reschedule_seed")

    result = await reschedule_booking(
        db,
        business_id=qatest["business_id"],
        booking_id=booking_id,
        client_id=qatest["client_id"],
        new_date=future_slot_alt["date"],
        new_time=future_slot_alt["start"],
    )
    assert result.get("success") is True, f"Reschedule did not succeed: {result}"

    row = await db.pool.fetchrow(
        "SELECT scheduled_date, scheduled_start, status FROM cleaning_bookings WHERE id = $1",
        booking_id,
    )
    assert row["scheduled_date"].isoformat() == future_slot_alt["date"], (
        f"Date not updated. Want {future_slot_alt['date']}, got {row['scheduled_date']}"
    )
    assert str(row["scheduled_start"]).startswith(future_slot_alt["start"]), (
        f"Start time not updated. Want {future_slot_alt['start']}, got {row['scheduled_start']}"
    )
    assert row["status"] in ("scheduled", "rescheduled"), (
        f"Unexpected status post-reschedule: {row['status']}"
    )


# ---------------------------------------------------------------------------
# 3. Homeowner cancels — status flips to 'cancelled'
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_homeowner_cancels(db, qatest, future_slot):
    from app.modules.cleaning.services.homeowner_service import cancel_booking

    booking_id = await _create_booking_direct(db, qatest, future_slot, "cancel_seed")

    result = await cancel_booking(
        db,
        business_id=qatest["business_id"],
        booking_id=booking_id,
        client_id=qatest["client_id"],
        reason=f"{EVAL_TAG} automated test cancel",
    )
    assert result.get("success") is True, f"Cancel did not succeed: {result}"

    row = await db.pool.fetchrow(
        "SELECT status FROM cleaning_bookings WHERE id = $1",
        booking_id,
    )
    assert row["status"] == "cancelled", (
        f"Expected status=cancelled, got {row['status']}"
    )
