"""
Xcleaners v3 — AI Scheduling Assistant Service.

Uses Claude (via existing ClaWtoBusiness Anthropic integration) with tool_use
to provide intelligent schedule optimization, team assignment suggestions,
duration predictions, and pattern detection.

Gated behind Intermediate+ plan.

Functions:
  - optimize_schedule(business_id, date, db) — AI analyzes and suggests improvements
  - suggest_team_assignment(business_id, booking_id, db) — best team for a job
  - predict_duration(business_id, client_id, service_type_id, db) — predict cleaning time
  - detect_patterns(business_id, db) — identify trends and patterns
"""

import json
import logging
from datetime import date, datetime, timedelta
from typing import Optional

from app.config import (
    ANTHROPIC_API_KEY,
    AI_PROVIDER,
    AI_MODEL_PRIMARY,
    PROXY_URL,
    PROXY_MODEL_PRIMARY,
)
from app.database import Database
from app.modules.cleaning.services.ai_tools import AI_TOOLS, execute_tool

logger = logging.getLogger("xcleaners.ai_scheduling")

# Max tool-use iterations to prevent infinite loops
MAX_TOOL_ITERATIONS = 8

# System prompt for the scheduling AI
SCHEDULING_SYSTEM_PROMPT = """\
You are Xcleaners AI, an intelligent scheduling assistant for a residential cleaning business.

Your role is to analyze schedules, teams, and client data to provide actionable optimization suggestions. You have access to tools that let you query the business's scheduling data.

When optimizing schedules:
1. Minimize total travel distance between jobs for each team (cluster geographically)
2. Balance workload across teams (equalize hours and number of jobs)
3. Suggest swaps between teams when it improves proximity
4. Identify gaps in the schedule that could fit additional jobs
5. Consider client preferences (preferred team) and service continuity

When suggesting team assignments:
1. Score teams based on: proximity to other jobs, workload balance, client preference, service history
2. Always explain WHY you recommend a specific team

When predicting durations:
1. Use the client's actual historical data (average duration from past cleanings)
2. Adjust for service type complexity
3. Note if the client tends to take longer or shorter than estimated

When detecting patterns:
1. Look for cancellation trends (day of week, specific clients)
2. Identify peak and slow days
3. Flag underutilized or overloaded teams
4. Suggest actionable improvements

Always respond with structured, actionable suggestions. Use concrete numbers (distances, times, percentages). Be concise but thorough.
"""


def _get_ai_client():
    """
    Get the AI client matching the project's AI_PROVIDER config.
    Returns (client, provider_type) tuple.
    """
    if AI_PROVIDER == "proxy":
        import openai
        client = openai.OpenAI(api_key="any", base_url=PROXY_URL)
        return client, "proxy"
    elif AI_PROVIDER == "openai":
        import openai
        from app.config import OPENAI_API_KEY
        client = openai.OpenAI(api_key=OPENAI_API_KEY)
        return client, "openai"
    else:
        import anthropic
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        return client, "anthropic"


def _convert_tools_to_openai_format(tools: list) -> list:
    """Convert Anthropic tool format to OpenAI function calling format."""
    return [
        {
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t["description"],
                "parameters": t["input_schema"],
            },
        }
        for t in tools
    ]


async def _run_ai_with_tools(
    system_prompt: str,
    user_message: str,
    business_id: str,
    db: Database,
    auth_context: Optional[dict] = None,
) -> str:
    """
    Run the AI with tool_use support. Handles the tool call loop.

    Supports both Anthropic (native tool_use) and OpenAI/proxy (function calling).

    Args:
        auth_context: Optional authenticated context (e.g.
            {"authenticated_client_id": "<uuid>"}) forwarded to tools that
            need ownership enforcement (see ai_tools.TOOLS_REQUIRING_AUTH_CONTEXT).
            Legacy callers (owner-facing optimize_schedule etc.) pass None.

    Returns the final text response from the AI.
    """
    client, provider = _get_ai_client()

    if provider == "anthropic":
        return await _run_anthropic_tools(client, system_prompt, user_message, business_id, db, auth_context)
    else:
        return await _run_openai_tools(client, system_prompt, user_message, business_id, db, provider, auth_context)


async def _run_anthropic_tools(
    client,
    system_prompt: str,
    user_message: str,
    business_id: str,
    db: Database,
    auth_context: Optional[dict] = None,
) -> str:
    """Run tool loop using Anthropic's native tool_use."""
    messages = [{"role": "user", "content": user_message}]

    for iteration in range(MAX_TOOL_ITERATIONS):
        response = client.messages.create(
            model=AI_MODEL_PRIMARY,
            max_tokens=4096,
            system=system_prompt,
            tools=AI_TOOLS,
            messages=messages,
        )

        # Check if we got a final text response (no more tool calls)
        if response.stop_reason == "end_turn":
            # Extract text from content blocks
            text_parts = [
                block.text for block in response.content if block.type == "text"
            ]
            return "\n".join(text_parts) if text_parts else "No suggestions generated."

        # Process tool_use blocks
        tool_results = []
        text_parts = []

        for block in response.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use":
                logger.info(
                    "[AI_SCHED] Tool call [%d]: %s(%s)",
                    iteration + 1,
                    block.name,
                    json.dumps(block.input)[:200],
                )
                result = await execute_tool(block.name, block.input, business_id, db, auth_context)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": result,
                })

        if not tool_results:
            # No tool calls, return whatever text we have
            return "\n".join(text_parts) if text_parts else "No suggestions generated."

        # Add assistant message + tool results to conversation
        messages.append({"role": "assistant", "content": response.content})
        messages.append({"role": "user", "content": tool_results})

    logger.warning("[AI_SCHED] Max tool iterations reached (%d)", MAX_TOOL_ITERATIONS)
    return "Analysis incomplete — too many data lookups required. Please try a more specific request."


async def _run_openai_tools(
    client,
    system_prompt: str,
    user_message: str,
    business_id: str,
    db: Database,
    provider: str,
    auth_context: Optional[dict] = None,
) -> str:
    """Run tool loop using OpenAI function calling (works for proxy too)."""
    # FIX 2026-04-20: remover hardcoded gpt-4o-mini — usar AI_MODEL_PRIMARY do config
    # (default atual: gpt-4.1-mini). Motor do chat em produção via config centralizada.
    model = PROXY_MODEL_PRIMARY if provider == "proxy" else AI_MODEL_PRIMARY
    tools_openai = _convert_tools_to_openai_format(AI_TOOLS)

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]

    for iteration in range(MAX_TOOL_ITERATIONS):
        response = client.chat.completions.create(
            model=model,
            max_tokens=4096,
            messages=messages,
            tools=tools_openai,
            tool_choice="auto",
        )

        choice = response.choices[0]

        # If no tool calls, return the text
        if not choice.message.tool_calls:
            return choice.message.content or "No suggestions generated."

        # Add assistant message with tool calls
        messages.append(choice.message)

        # Process each tool call
        for tool_call in choice.message.tool_calls:
            func = tool_call.function
            logger.info(
                "[AI_SCHED] Tool call [%d]: %s(%s)",
                iteration + 1,
                func.name,
                func.arguments[:200],
            )
            try:
                args = json.loads(func.arguments)
            except json.JSONDecodeError:
                args = {}

            result = await execute_tool(func.name, args, business_id, db, auth_context)

            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": result,
            })

    logger.warning("[AI_SCHED] Max tool iterations reached (%d)", MAX_TOOL_ITERATIONS)
    return "Analysis incomplete — too many data lookups required. Please try a more specific request."


# ============================================
# PUBLIC API
# ============================================

async def optimize_schedule(
    business_id: str,
    target_date: str,
    db: Database,
) -> dict:
    """
    AI analyzes the current schedule for a date and suggests improvements.

    Returns:
        dict with 'suggestions' (AI text), 'date', 'status'
    """
    logger.info("[AI_SCHED] optimize_schedule for %s on %s", business_id, target_date)

    user_message = f"""\
Analyze the schedule for {target_date} and provide optimization suggestions.

Please:
1. First, fetch the schedule for {target_date} and team availability
2. Look at how jobs are distributed across teams
3. Check if jobs are geographically clustered per team (calculate distances between consecutive jobs)
4. Identify any workload imbalances
5. Suggest specific swaps or reassignments that would:
   - Reduce travel distance
   - Better balance workload
   - Fill schedule gaps
6. Identify any open time slots where additional jobs could fit

For each suggestion, provide:
- What to change (specific booking/team)
- Why (quantified benefit: miles saved, better balance)
- Priority (high/medium/low)

Format your response as a clear, structured list of suggestions.
"""

    try:
        result = await _run_ai_with_tools(
            SCHEDULING_SYSTEM_PROMPT,
            user_message,
            business_id,
            db,
        )
        return {
            "status": "success",
            "date": target_date,
            "suggestions": result,
        }
    except Exception as e:
        logger.error("[AI_SCHED] optimize_schedule error: %s", e)
        return {
            "status": "error",
            "date": target_date,
            "suggestions": f"Error generating suggestions: {str(e)}",
        }


async def suggest_team_assignment(
    business_id: str,
    booking_id: str,
    db: Database,
) -> dict:
    """
    AI suggests the best team for a specific booking.

    Returns:
        dict with 'suggestion' (AI text), 'booking_id', 'status'
    """
    logger.info("[AI_SCHED] suggest_team for booking %s", booking_id)

    # Get booking info
    # FIX 2026-04-20: schema real usa cleaning_clients (nao cleaning_client_schedules
    # em joins por client_id) + cleaning_services (nao cleaning_service_types).
    # service_id substitui service_type_id. preferred_team_id vive em
    # cleaning_client_schedules — subquery correlacionada pega o schedule ativo.
    booking = await db.pool.fetchrow(
        """
        SELECT
            b.id, b.scheduled_date, b.client_id, b.service_id,
            b.estimated_duration_minutes, b.team_id,
            (c.first_name || ' ' || COALESCE(c.last_name, '')) AS client_name,
            c.address_line1, c.city, c.zip_code,
            c.latitude, c.longitude,
            (SELECT preferred_team_id
               FROM cleaning_client_schedules
              WHERE client_id = b.client_id AND status = 'active'
              ORDER BY created_at DESC LIMIT 1) AS preferred_team_id,
            s.name AS service_type_name
        FROM cleaning_bookings b
        LEFT JOIN cleaning_clients c ON c.id = b.client_id
        LEFT JOIN cleaning_services s ON s.id = b.service_id
        WHERE b.id = $1 AND b.business_id = $2
        """,
        booking_id,
        business_id,
    )

    if not booking:
        return {
            "status": "error",
            "booking_id": booking_id,
            "suggestion": "Booking not found.",
        }

    sched_date = str(booking["scheduled_date"])
    client_id = str(booking["client_id"]) if booking["client_id"] else "unknown"

    user_message = f"""\
Suggest the best team to assign for this booking:

- Booking ID: {booking_id}
- Date: {sched_date}
- Client: {booking['client_name']} at {booking['address_line1'] or ''}, {booking['city'] or ''}
- Service: {booking['service_type_name'] or 'Standard'}
- Estimated duration: {booking['estimated_duration_minutes'] or 120} minutes
- Client preferred team: {booking['preferred_team_id'] or 'none'}
- Currently assigned team: {booking['team_id'] or 'unassigned'}

Please:
1. Check team availability for {sched_date}
2. Check this client's history (client_id: {client_id})
3. For each available team, calculate distance from their other jobs to this client's location
4. Consider: proximity, workload balance, client preference, and service continuity
5. Recommend the best team with a clear explanation of why

Provide a ranked list of top 2-3 team options with scores/reasoning.
"""

    try:
        result = await _run_ai_with_tools(
            SCHEDULING_SYSTEM_PROMPT,
            user_message,
            business_id,
            db,
        )
        return {
            "status": "success",
            "booking_id": booking_id,
            "suggestion": result,
        }
    except Exception as e:
        logger.error("[AI_SCHED] suggest_team error: %s", e)
        return {
            "status": "error",
            "booking_id": booking_id,
            "suggestion": f"Error generating suggestion: {str(e)}",
        }


async def predict_duration(
    business_id: str,
    client_id: str,
    service_type_id: Optional[str],
    db: Database,
) -> dict:
    """
    Predict cleaning duration based on client history and service type.

    Returns:
        dict with predicted_minutes, confidence, based_on, and reasoning
    """
    logger.info("[AI_SCHED] predict_duration for client %s", client_id)

    # Direct data query — no need for full AI tool loop here
    # Get client's historical durations
    # FIX 2026-04-20: actual_duration_minutes nao existe no schema — computar
    # de actual_end - actual_start. service_id substitui service_type_id.
    # cleaning_services substitui cleaning_service_types (tabela inexistente).
    rows = await db.pool.fetch(
        """
        SELECT
            CAST(EXTRACT(EPOCH FROM (b.actual_end - b.actual_start)) / 60 AS INTEGER) AS actual_duration_minutes,
            b.estimated_duration_minutes,
            b.service_id,
            s.name AS service_type_name,
            b.scheduled_date
        FROM cleaning_bookings b
        LEFT JOIN cleaning_services s ON s.id = b.service_id
        WHERE b.client_id = $1
          AND b.business_id = $2
          AND b.status = 'completed'
          AND b.actual_start IS NOT NULL
          AND b.actual_end IS NOT NULL
        ORDER BY b.scheduled_date DESC
        LIMIT 15
        """,
        client_id,
        business_id,
    )

    if not rows:
        # No history — use service type default or global average
        default_minutes = 120
        if service_type_id:
            # FIX 2026-04-20: tabela real e cleaning_services com coluna
            # estimated_duration_minutes. cleaning_service_types nao existe.
            st_row = await db.pool.fetchrow(
                """
                SELECT estimated_duration_minutes
                FROM cleaning_services
                WHERE id = $1 AND business_id = $2
                """,
                service_type_id,
                business_id,
            )
            if st_row and st_row["estimated_duration_minutes"]:
                default_minutes = st_row["estimated_duration_minutes"]

        return {
            "status": "success",
            "client_id": client_id,
            "predicted_minutes": default_minutes,
            "confidence": "low",
            "based_on": "service_type_default",
            "sample_size": 0,
            "reasoning": (
                f"No historical data for this client. Using service type default "
                f"of {default_minutes} minutes."
            ),
        }

    # Filter by matching service type if provided
    # FIX 2026-04-20: chave da row renomeada de service_type_id para service_id.
    if service_type_id:
        matching = [r for r in rows if str(r["service_id"]) == service_type_id]
        if len(matching) >= 3:
            rows = matching

    actual_durations = [r["actual_duration_minutes"] for r in rows]
    avg_duration = round(sum(actual_durations) / len(actual_durations))
    min_duration = min(actual_durations)
    max_duration = max(actual_durations)

    # Confidence based on sample size and consistency
    spread = max_duration - min_duration
    sample_size = len(actual_durations)

    if sample_size >= 5 and spread <= 30:
        confidence = "high"
    elif sample_size >= 3:
        confidence = "medium"
    else:
        confidence = "low"

    # Weight recent bookings more (simple exponential decay)
    if sample_size >= 3:
        weights = [1.0 / (1 + 0.3 * i) for i in range(sample_size)]
        total_weight = sum(weights)
        weighted_avg = round(
            sum(d * w for d, w in zip(actual_durations, weights)) / total_weight
        )
    else:
        weighted_avg = avg_duration

    return {
        "status": "success",
        "client_id": client_id,
        "predicted_minutes": weighted_avg,
        "confidence": confidence,
        "based_on": "client_history",
        "sample_size": sample_size,
        "avg_minutes": avg_duration,
        "min_minutes": min_duration,
        "max_minutes": max_duration,
        "reasoning": (
            f"Based on {sample_size} past cleanings. "
            f"Average: {avg_duration} min (range: {min_duration}-{max_duration}). "
            f"Weighted prediction (recent jobs weighted higher): {weighted_avg} min. "
            f"Confidence: {confidence}."
        ),
    }


async def detect_patterns(
    business_id: str,
    db: Database,
) -> dict:
    """
    Detect scheduling patterns and generate insights.

    Returns:
        dict with 'insights' (AI text), 'status'
    """
    logger.info("[AI_SCHED] detect_patterns for %s", business_id)

    today = date.today()
    start_30 = (today - timedelta(days=30)).isoformat()
    end = today.isoformat()

    user_message = f"""\
Analyze scheduling patterns for this cleaning business and provide actionable insights.

Please:
1. Get the team workload summary for the last 30 days ({start_30} to {end})
2. Check cancellation patterns (last 30 days)
3. Look at today's schedule and team availability

Based on the data, provide insights on:

**Workload Balance:**
- Are teams evenly loaded? Any consistently overloaded or underutilized teams?
- Recommendation for rebalancing

**Cancellation Trends:**
- Which days have highest cancellation rates?
- Any clients with unusually high cancellation rates?
- Suggestions to reduce cancellations

**Scheduling Efficiency:**
- Peak days vs slow days
- Teams that could take more work
- Geographic clustering opportunities

**Growth Opportunities:**
- Available capacity (unfilled time slots across teams)
- Best days/times to accept new clients

Provide specific, data-driven recommendations. Use numbers and percentages.
"""

    try:
        result = await _run_ai_with_tools(
            SCHEDULING_SYSTEM_PROMPT,
            user_message,
            business_id,
            db,
        )
        return {
            "status": "success",
            "insights": result,
            "generated_at": datetime.utcnow().isoformat(),
        }
    except Exception as e:
        logger.error("[AI_SCHED] detect_patterns error: %s", e)
        return {
            "status": "error",
            "insights": f"Error generating insights: {str(e)}",
        }
