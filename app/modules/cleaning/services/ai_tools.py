"""
Xcleaners v3 — AI Scheduling Tool Definitions.

Tool definitions for Claude tool_use integration.
These tools allow the AI scheduling assistant to query and manipulate
schedule data, team availability, client history, and distance calculations.

Each tool is defined as a dict matching Anthropic's tool schema format.
The execute_tool() function dispatches tool calls to the correct handler.
"""

import logging
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional
from uuid import UUID

from app.database import Database
from app.modules.cleaning.services.team_assignment_scorer import haversine
# AI Turbo Sprint 2026-04-20: imports para tools novas (booking flow cliente)
from app.modules.cleaning.services.pricing_engine import (
    calculate_booking_price,
    PricingConfigError,
)
from app.modules.cleaning.services.booking_service import create_booking_with_pricing
from app.modules.cleaning.services.availability_service import is_slot_available

logger = logging.getLogger("xcleaners.ai_tools")


async def _pick_available_team(
    db: Database,
    business_id: str,
    scheduled_date: str,
    scheduled_start: str,
    duration_minutes: Optional[int] = None,
    preferred_team_id: Optional[str] = None,
) -> Optional[str]:
    """Pick a team for an AI-created booking.

    Strategy: rank active teams by (preferred match, no slot conflict, least
    jobs today). Returns team UUID str, or None if no team fits — in which
    case the booking stays unassigned and the owner assigns it manually.
    """
    duration_s = str(duration_minutes or 60)
    rows = await db.pool.fetch(
        """
        SELECT t.id,
               t.max_daily_jobs,
               COALESCE((
                   SELECT COUNT(*) FROM cleaning_bookings b
                   WHERE b.team_id = t.id
                     AND b.scheduled_date = $2::date
                     AND b.status NOT IN ('cancelled','no_show')
               ), 0) AS jobs_today,
               COALESCE((
                   SELECT COUNT(*) FROM cleaning_bookings b
                   WHERE b.team_id = t.id
                     AND b.scheduled_date = $2::date
                     AND b.status NOT IN ('cancelled','no_show')
                     AND b.scheduled_start < ($3::time + ($4 || ' minutes')::interval)
                     AND COALESCE(b.scheduled_end, b.scheduled_start + ($4 || ' minutes')::interval) > $3::time
               ), 0) AS slot_conflicts
        FROM cleaning_teams t
        WHERE t.business_id = $1 AND t.is_active = true
        ORDER BY
            (CASE WHEN $5::uuid IS NOT NULL AND t.id = $5::uuid THEN 0 ELSE 1 END),
            jobs_today ASC,
            t.name
        """,
        business_id,
        scheduled_date,
        scheduled_start,
        duration_s,
        preferred_team_id,
    )
    for r in rows:
        max_jobs = r["max_daily_jobs"] or 6
        if r["slot_conflicts"] == 0 and r["jobs_today"] < max_jobs:
            return str(r["id"])
    return None


# ============================================
# TOOL DEFINITIONS (Anthropic tool_use format)
# ============================================

AI_TOOLS = [
    {
        "name": "get_schedule_for_date",
        "description": (
            "Fetch the full daily schedule for a specific date. "
            "Returns all bookings grouped by team, including client name, "
            "address, service type, time slot, and status."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "date": {
                    "type": "string",
                    "description": "Date in YYYY-MM-DD format.",
                },
            },
            "required": ["date"],
        },
    },
    {
        "name": "get_team_availability",
        "description": (
            "Check team availability for a specific date. "
            "Returns each team's current job count, max capacity, "
            "active members, and available time slots."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "date": {
                    "type": "string",
                    "description": "Date in YYYY-MM-DD format.",
                },
            },
            "required": ["date"],
        },
    },
    {
        "name": "get_client_history",
        "description": (
            "Get a client's booking history including past services, "
            "teams that served them, average duration, cancellation rate, "
            "and preferences."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "client_id": {
                    "type": "string",
                    "description": "UUID of the client.",
                },
            },
            "required": ["client_id"],
        },
    },
    {
        "name": "calculate_distance",
        "description": (
            "Calculate the driving distance in miles between two addresses "
            "using their latitude/longitude coordinates (haversine formula). "
            "Use this to evaluate travel time between jobs."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "from_lat": {"type": "number", "description": "Latitude of origin."},
                "from_lon": {"type": "number", "description": "Longitude of origin."},
                "to_lat": {"type": "number", "description": "Latitude of destination."},
                "to_lon": {"type": "number", "description": "Longitude of destination."},
            },
            "required": ["from_lat", "from_lon", "to_lat", "to_lon"],
        },
    },
    {
        "name": "get_team_workload_summary",
        "description": (
            "Get a workload summary for all teams on a date range. "
            "Returns total jobs, total hours, and average jobs per day "
            "for each team. Useful for workload balancing analysis."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "start_date": {
                    "type": "string",
                    "description": "Start date in YYYY-MM-DD format.",
                },
                "end_date": {
                    "type": "string",
                    "description": "End date in YYYY-MM-DD format.",
                },
            },
            "required": ["start_date", "end_date"],
        },
    },
    {
        "name": "get_cancellation_patterns",
        "description": (
            "Analyze cancellation patterns for the business. "
            "Returns cancellation rate by day of week, by client, "
            "and trends over time."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "days_back": {
                    "type": "integer",
                    "description": "Number of days to look back (default 30).",
                    "default": 30,
                },
            },
            "required": [],
        },
    },
    # ============================================
    # AI Turbo Sprint 2026-04-20 — tools para chat customer (booking flow)
    # ============================================
    {
        "name": "check_availability",
        "description": (
            "Check if a specific date/time slot is available for booking. "
            "Returns whether the slot has any overlapping booking or travel "
            "buffer violation. Use BEFORE proposing a booking to the customer. "
            "Never commit to a time without calling this first."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "scheduled_date": {
                    "type": "string",
                    "description": "Target date in YYYY-MM-DD format.",
                },
                "scheduled_start": {
                    "type": "string",
                    "description": "Target start time in HH:MM format (24h).",
                },
                "duration_minutes": {
                    "type": "integer",
                    "description": "Expected duration in minutes. Default 120.",
                },
                "team_id": {
                    "type": "string",
                    "description": (
                        "Optional UUID of a specific team to check. "
                        "If omitted, checks any team in the business."
                    ),
                },
                "client_zip": {
                    "type": "string",
                    "description": "Optional customer ZIP code for travel-buffer awareness.",
                },
            },
            "required": ["scheduled_date", "scheduled_start"],
        },
    },
    {
        "name": "get_price_quote",
        "description": (
            "Compute an authoritative price quote for a cleaning booking. "
            "Uses the server-side pricing engine (formula + override + extras "
            "+ frequency discount + tax). NEVER estimate prices yourself — "
            "always call this tool. The returned price is exactly what will "
            "be charged if booked. CRITICAL: pick the tier that matches the "
            "service the customer asked for: 'Deep Clean'/'Limpeza Profunda' "
            "-> tier='deep'; 'Standard'/'Basic'/'Limpeza Padrão' -> tier='basic'; "
            "'Premium'/'Move-out'/'Move-in' -> tier='premium'. Mismatched tier "
            "produces wrong price (e.g. Deep Clean quoted at basic tier under-prices "
            "by ~45%)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "service_id": {
                    "type": "string",
                    "description": "UUID of the cleaning_services row.",
                },
                "tier": {
                    "type": "string",
                    "enum": ["basic", "deep", "premium"],
                    "description": (
                        "Service tier — MUST match the service category the customer asked for. "
                        "'basic' = standard/regular clean. 'deep' = deep clean / limpeza profunda. "
                        "'premium' = move-in/move-out / post-construction. NO default — picking "
                        "wrong tier under-charges or over-charges the customer."
                    ),
                },
                "extras": {
                    "type": "array",
                    "description": "List of add-ons selected by the customer.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "extra_id": {"type": "string"},
                            "qty": {"type": "integer", "default": 1},
                        },
                        "required": ["extra_id"],
                    },
                },
                "frequency_id": {
                    "type": "string",
                    "description": "Optional UUID of cleaning_frequencies for recurring discount.",
                },
                "location_id": {
                    "type": "string",
                    "description": "Optional UUID of cleaning_areas for location-specific formula + tax.",
                },
                "scheduled_date": {
                    "type": "string",
                    "description": (
                        "Service date in YYYY-MM-DD for historical tax lookup "
                        "(F-001 correctness)."
                    ),
                },
            },
            "required": ["service_id", "tier"],
        },
    },
    {
        "name": "get_services_catalog",
        "description": (
            "Fetch the business's active services catalog: services, extras, "
            "and frequencies available for booking. Use to show the customer "
            "what they can book and what add-ons exist."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "capture_lead",
        "description": (
            "Save a lead (prospective customer inquiry) with contact info and "
            "service request details. Use this in PUBLIC VISITOR chat ONLY "
            "(visitor is anonymous, no account yet). After collecting at minimum "
            "name + phone, call this tool to persist the lead. The owner will "
            "review and contact them. ALWAYS include the returned Lead ID in your "
            "response text (format: 'Lead ID: <uuid>') so UI can show confirmation. "
            "Do NOT use in authenticated customer chats — those should use "
            "propose_booking_draft instead."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "first_name": {"type": "string", "description": "Visitor first name"},
                "last_name": {"type": "string"},
                "email": {"type": "string"},
                "phone": {"type": "string", "description": "REQUIRED — must be collected before calling"},
                "zip_code": {"type": "string"},
                "service_requested": {
                    "type": "string",
                    "description": "e.g. 'deep clean', 'move-out', 'recurring weekly'",
                },
                "bedrooms": {"type": "integer"},
                "bathrooms": {"type": "number"},
                "preferred_date": {
                    "type": "string",
                    "description": "YYYY-MM-DD or free text like 'next Tuesday'",
                },
                "preferred_time": {
                    "type": "string",
                    "description": "morning | afternoon | evening | specific time",
                },
                "message": {
                    "type": "string",
                    "description": "Free-form notes or context from conversation",
                },
                "estimated_quote": {
                    "type": "number",
                    "description": "If IA calculated via get_price_quote earlier",
                },
            },
            "required": ["phone"],
        },
    },
    {
        "name": "propose_booking_draft",
        "description": (
            "Create a CONFIRMED booking with status='scheduled'. Availability "
            "is re-verified server-side before insert; if slot is free, booking "
            "is auto-confirmed and notifications are sent to both customer and "
            "owner (no manual approval needed). ONLY call after: "
            "(1) check_availability returns available=true, "
            "(2) get_price_quote returns an acceptable total, "
            "(3) customer EXPLICITLY confirmed the booking in conversation. "
            "Returns the booking_id — tell the customer the booking is CONFIRMED "
            "and they will receive a confirmation message."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "client_id": {
                    "type": "string",
                    "description": "UUID of cleaning_clients (the logged-in customer).",
                },
                "service_id": {
                    "type": "string",
                    "description": "UUID of cleaning_services.",
                },
                "scheduled_date": {
                    "type": "string",
                    "description": "YYYY-MM-DD.",
                },
                "scheduled_start": {
                    "type": "string",
                    "description": "HH:MM (24h).",
                },
                "tier": {
                    "type": "string",
                    "enum": ["basic", "deep", "premium"],
                    "description": "Tier matching the quote shown to customer.",
                },
                "extras": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "extra_id": {"type": "string"},
                            "qty": {"type": "integer", "default": 1},
                        },
                        "required": ["extra_id"],
                    },
                },
                "frequency_id": {
                    "type": "string",
                    "description": "Optional — for recurring discount.",
                },
                "location_id": {
                    "type": "string",
                    "description": "Optional — for location-specific formula + tax.",
                },
                "duration_minutes": {
                    "type": "integer",
                    "description": "Expected duration. Default 120.",
                },
                "special_instructions": {
                    "type": "string",
                    "description": "Free-text notes from the customer.",
                },
            },
            "required": ["client_id", "service_id", "scheduled_date", "scheduled_start", "tier"],
        },
    },
]


# ============================================
# TOOL EXECUTORS
# ============================================

# Tools that receive auth_context for ownership enforcement.
# Add tool name here when a handler needs authenticated_client_id or similar
# to block intra-business spoofing via prompt injection.
TOOLS_REQUIRING_AUTH_CONTEXT = {"propose_booking_draft"}


async def execute_tool(
    tool_name: str,
    tool_input: dict,
    business_id: str,
    db: Database,
    auth_context: Optional[dict] = None,
) -> str:
    """
    Execute a tool call and return the result as a JSON string.

    Args:
        tool_name: Name of the tool to execute.
        tool_input: Input parameters for the tool.
        business_id: UUID of the business (scope).
        db: Database instance.
        auth_context: Optional dict with authenticated context (e.g.
            {"authenticated_client_id": "<uuid>"}). Passed only to handlers
            listed in TOOLS_REQUIRING_AUTH_CONTEXT — used to block spoofing
            of ids that should match the authenticated caller.

    Returns:
        JSON string with the tool result.
    """
    import json

    handler = TOOL_HANDLERS.get(tool_name)
    if not handler:
        return json.dumps({"error": f"Unknown tool: {tool_name}"})

    try:
        if tool_name in TOOLS_REQUIRING_AUTH_CONTEXT:
            result = await handler(tool_input, business_id, db, auth_context=auth_context)
        else:
            result = await handler(tool_input, business_id, db)
        return json.dumps(result, default=str)
    except Exception as e:
        logger.error("[AI_TOOLS] Error executing %s: %s", tool_name, e)
        return json.dumps({"error": str(e)})


# ─── get_schedule_for_date ────────────────────

async def _get_schedule_for_date(
    params: dict, business_id: str, db: Database
) -> dict:
    target_date = params["date"]

    rows = await db.pool.fetch(
        """
        SELECT
            b.id AS booking_id,
            b.scheduled_date,
            b.start_time,
            b.end_time,
            b.status,
            b.estimated_duration_minutes,
            b.actual_duration_minutes,
            b.team_id,
            t.name AS team_name,
            cs.id AS client_id,
            cs.client_name,
            cs.address_line1,
            cs.city,
            cs.zip_code,
            cs.latitude,
            cs.longitude,
            st.name AS service_type_name,
            b.notes
        FROM cleaning_bookings b
        LEFT JOIN cleaning_teams t ON t.id = b.team_id
        LEFT JOIN cleaning_client_schedules cs ON cs.id = b.client_id
        LEFT JOIN cleaning_services st ON st.id = b.service_id
        WHERE b.business_id = $1
          AND b.scheduled_date = $2::date
          AND b.status NOT IN ('cancelled')
        ORDER BY t.name NULLS LAST, b.start_time NULLS LAST
        """,
        business_id,
        target_date,
    )

    # Group by team
    teams = {}
    unassigned = []
    for row in rows:
        booking = {
            "booking_id": str(row["booking_id"]),
            "client_name": row["client_name"],
            "address": f"{row['address_line1'] or ''}, {row['city'] or ''}".strip(", "),
            "zip_code": row["zip_code"],
            "latitude": float(row["latitude"]) if row["latitude"] else None,
            "longitude": float(row["longitude"]) if row["longitude"] else None,
            "service_type": row["service_type_name"],
            "start_time": str(row["start_time"]) if row["start_time"] else None,
            "end_time": str(row["end_time"]) if row["end_time"] else None,
            "estimated_minutes": row["estimated_duration_minutes"],
            "actual_minutes": row["actual_duration_minutes"],
            "status": row["status"],
            "notes": row["notes"],
        }
        if row["team_id"]:
            tid = str(row["team_id"])
            if tid not in teams:
                teams[tid] = {
                    "team_id": tid,
                    "team_name": row["team_name"],
                    "bookings": [],
                }
            teams[tid]["bookings"].append(booking)
        else:
            unassigned.append(booking)

    return {
        "date": target_date,
        "teams": list(teams.values()),
        "unassigned": unassigned,
        "total_bookings": len(rows),
    }


# ─── get_team_availability ────────────────────

async def _get_team_availability(
    params: dict, business_id: str, db: Database
) -> dict:
    target_date = params["date"]

    teams = await db.pool.fetch(
        """
        SELECT
            t.id,
            t.name,
            t.max_daily_jobs,
            t.is_active,
            (
                SELECT COUNT(*)
                FROM cleaning_bookings b
                WHERE b.team_id = t.id
                  AND b.scheduled_date = $2::date
                  AND b.status NOT IN ('cancelled')
            ) AS jobs_today,
            (
                SELECT COUNT(*)
                FROM cleaning_team_assignments ta
                WHERE ta.team_id = t.id
                  AND ta.status = 'active'
            ) AS active_members
        FROM cleaning_teams t
        WHERE t.business_id = $1
          AND t.is_active = true
        ORDER BY t.name
        """,
        business_id,
        target_date,
    )

    result = []
    for team in teams:
        max_jobs = team["max_daily_jobs"] or 6
        jobs = team["jobs_today"]
        result.append({
            "team_id": str(team["id"]),
            "team_name": team["name"],
            "status": "active" if team["is_active"] else "inactive",
            "active_members": team["active_members"],
            "jobs_today": jobs,
            "max_daily_jobs": max_jobs,
            "available_slots": max(0, max_jobs - jobs),
            "utilization_percent": round((jobs / max_jobs) * 100, 1) if max_jobs > 0 else 0,
        })

    return {"date": target_date, "teams": result}


# ─── get_client_history ────────────────────

async def _get_client_history(
    params: dict, business_id: str, db: Database
) -> dict:
    client_id = params["client_id"]

    # Client info
    client = await db.pool.fetchrow(
        """
        SELECT client_name, address_line1, city, zip_code,
               frequency, preferred_team_id, special_instructions,
               latitude, longitude
        FROM cleaning_client_schedules
        WHERE id = $1 AND business_id = $2
        """,
        client_id,
        business_id,
    )

    if not client:
        return {"error": f"Client {client_id} not found."}

    # Booking history (last 20)
    bookings = await db.pool.fetch(
        """
        SELECT
            b.scheduled_date,
            b.status,
            b.estimated_duration_minutes,
            b.actual_duration_minutes,
            b.team_id,
            t.name AS team_name,
            st.name AS service_type_name
        FROM cleaning_bookings b
        LEFT JOIN cleaning_teams t ON t.id = b.team_id
        LEFT JOIN cleaning_services st ON st.id = b.service_id
        WHERE b.client_id = $1 AND b.business_id = $2
        ORDER BY b.scheduled_date DESC
        LIMIT 20
        """,
        client_id,
        business_id,
    )

    total = len(bookings)
    cancelled = sum(1 for b in bookings if b["status"] == "cancelled")
    completed = [b for b in bookings if b["actual_duration_minutes"]]
    avg_duration = (
        round(sum(b["actual_duration_minutes"] for b in completed) / len(completed), 0)
        if completed else None
    )

    return {
        "client_id": client_id,
        "client_name": client["client_name"],
        "address": f"{client['address_line1'] or ''}, {client['city'] or ''}".strip(", "),
        "frequency": client["frequency"],
        "preferred_team_id": str(client["preferred_team_id"]) if client["preferred_team_id"] else None,
        "special_instructions": client["special_instructions"],
        "total_bookings": total,
        "cancellation_rate": round(cancelled / total * 100, 1) if total > 0 else 0,
        "avg_actual_duration_minutes": avg_duration,
        "recent_bookings": [
            {
                "date": str(b["scheduled_date"]),
                "status": b["status"],
                "team_name": b["team_name"],
                "service_type": b["service_type_name"],
                "estimated_minutes": b["estimated_duration_minutes"],
                "actual_minutes": b["actual_duration_minutes"],
            }
            for b in bookings[:10]
        ],
    }


# ─── calculate_distance ────────────────────

async def _calculate_distance(
    params: dict, business_id: str, db: Database
) -> dict:
    distance = haversine(
        params["from_lat"],
        params["from_lon"],
        params["to_lat"],
        params["to_lon"],
    )
    # Estimate travel time: ~30 mph average in residential areas
    travel_minutes = round(distance / 30 * 60, 1)

    return {
        "distance_miles": round(distance, 2),
        "estimated_travel_minutes": travel_minutes,
    }


# ─── get_team_workload_summary ────────────────────

async def _get_team_workload_summary(
    params: dict, business_id: str, db: Database
) -> dict:
    start_date = params["start_date"]
    end_date = params["end_date"]

    rows = await db.pool.fetch(
        """
        SELECT
            t.id AS team_id,
            t.name AS team_name,
            COUNT(b.id) AS total_jobs,
            COALESCE(SUM(b.estimated_duration_minutes), 0) AS total_estimated_minutes,
            COALESCE(SUM(b.actual_duration_minutes), 0) AS total_actual_minutes,
            COUNT(DISTINCT b.scheduled_date) AS days_worked
        FROM cleaning_teams t
        LEFT JOIN cleaning_bookings b ON b.team_id = t.id
            AND b.scheduled_date BETWEEN $2::date AND $3::date
            AND b.status NOT IN ('cancelled')
        WHERE t.business_id = $1
          AND t.status = 'active'
        GROUP BY t.id, t.name
        ORDER BY t.name
        """,
        business_id,
        start_date,
        end_date,
    )

    result = []
    for row in rows:
        days = row["days_worked"] or 1
        result.append({
            "team_id": str(row["team_id"]),
            "team_name": row["team_name"],
            "total_jobs": row["total_jobs"],
            "total_estimated_hours": round(row["total_estimated_minutes"] / 60, 1),
            "total_actual_hours": round(row["total_actual_minutes"] / 60, 1),
            "days_worked": days,
            "avg_jobs_per_day": round(row["total_jobs"] / days, 1),
        })

    return {
        "start_date": start_date,
        "end_date": end_date,
        "teams": result,
    }


# ─── get_cancellation_patterns ────────────────────

async def _get_cancellation_patterns(
    params: dict, business_id: str, db: Database
) -> dict:
    days_back = params.get("days_back", 30)

    # Overall stats
    stats = await db.pool.fetchrow(
        """
        SELECT
            COUNT(*) AS total_bookings,
            COUNT(*) FILTER (WHERE status = 'cancelled') AS total_cancelled
        FROM cleaning_bookings
        WHERE business_id = $1
          AND scheduled_date >= CURRENT_DATE - $2::int
        """,
        business_id,
        days_back,
    )

    # By day of week
    by_dow = await db.pool.fetch(
        """
        SELECT
            EXTRACT(DOW FROM scheduled_date)::int AS day_of_week,
            COUNT(*) AS total,
            COUNT(*) FILTER (WHERE status = 'cancelled') AS cancelled
        FROM cleaning_bookings
        WHERE business_id = $1
          AND scheduled_date >= CURRENT_DATE - $2::int
        GROUP BY EXTRACT(DOW FROM scheduled_date)
        ORDER BY EXTRACT(DOW FROM scheduled_date)
        """,
        business_id,
        days_back,
    )

    dow_names = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]

    # Top cancelling clients
    top_cancellers = await db.pool.fetch(
        """
        SELECT
            cs.client_name,
            COUNT(*) FILTER (WHERE b.status = 'cancelled') AS cancellations,
            COUNT(*) AS total_bookings
        FROM cleaning_bookings b
        JOIN cleaning_client_schedules cs ON cs.id = b.client_id
        WHERE b.business_id = $1
          AND b.scheduled_date >= CURRENT_DATE - $2::int
        GROUP BY cs.client_name
        HAVING COUNT(*) FILTER (WHERE b.status = 'cancelled') > 0
        ORDER BY cancellations DESC
        LIMIT 5
        """,
        business_id,
        days_back,
    )

    total = stats["total_bookings"] or 0
    cancelled = stats["total_cancelled"] or 0

    return {
        "period_days": days_back,
        "total_bookings": total,
        "total_cancelled": cancelled,
        "cancellation_rate_percent": round(cancelled / total * 100, 1) if total > 0 else 0,
        "by_day_of_week": [
            {
                "day": dow_names[row["day_of_week"]],
                "total": row["total"],
                "cancelled": row["cancelled"],
                "rate_percent": round(row["cancelled"] / row["total"] * 100, 1) if row["total"] > 0 else 0,
            }
            for row in by_dow
        ],
        "top_cancelling_clients": [
            {
                "client_name": row["client_name"],
                "cancellations": row["cancellations"],
                "total_bookings": row["total_bookings"],
                "rate_percent": round(row["cancellations"] / row["total_bookings"] * 100, 1),
            }
            for row in top_cancellers
        ],
    }


# ─── check_availability (AI Turbo Sprint 2026-04-20) ──────────────────

async def _check_availability(
    params: dict, business_id: str, db: Database
) -> dict:
    return await is_slot_available(
        db,
        business_id=business_id,
        scheduled_date=params["scheduled_date"],
        scheduled_start=params["scheduled_start"],
        duration_minutes=params.get("duration_minutes"),
        team_id=params.get("team_id"),
        client_zip=params.get("client_zip"),
    )


# ─── get_price_quote ────────────────────

async def _get_price_quote(
    params: dict, business_id: str, db: Database
) -> dict:
    try:
        breakdown = await calculate_booking_price(
            business_id=UUID(business_id) if isinstance(business_id, str) else business_id,
            service_id=UUID(params["service_id"]),
            tier=params.get("tier", "basic"),
            extras=params.get("extras", []),
            frequency_id=UUID(params["frequency_id"]) if params.get("frequency_id") else None,
            location_id=UUID(params["location_id"]) if params.get("location_id") else None,
            scheduled_date=params.get("scheduled_date"),
            db=db,
        )
        return {
            "final_amount": float(breakdown["final_amount"]),
            "subtotal": float(breakdown["subtotal"]),
            "subtotal_service": float(breakdown["subtotal_service"]),
            "extras_sum": float(breakdown["extras_sum"]),
            "discount_amount": float(breakdown["discount_amount"]),
            "discount_pct": float(breakdown["discount_pct"]),
            "tax_amount": float(breakdown["tax_amount"]),
            "tax_pct": float(breakdown["tax_pct"]),
            "tier": breakdown["tier"],
            "tier_multiplier": float(breakdown["tier_multiplier"]),
            "override_applied": breakdown["override_applied"],
            "extras": [
                {"name": e["name"], "qty": e["qty"], "price": float(e["price"])}
                for e in breakdown.get("extras", [])
            ],
            "frequency_name": breakdown.get("frequency_name"),
        }
    except PricingConfigError as e:
        return {"error": "pricing_config", "message": str(e)}


# ─── get_services_catalog ────────────────────

async def _get_services_catalog(
    params: dict, business_id: str, db: Database
) -> dict:
    services = await db.pool.fetch(
        """
        SELECT id, name, slug, description, category, tier,
               bedrooms, bathrooms, estimated_duration_minutes, base_price, icon
        FROM cleaning_services
        WHERE business_id = $1 AND is_active = TRUE
        ORDER BY sort_order, name
        """,
        business_id,
    )
    extras = await db.pool.fetch(
        """
        SELECT id, name, price
        FROM cleaning_extras
        WHERE business_id = $1 AND is_active = TRUE
        ORDER BY sort_order, name
        """,
        business_id,
    )
    frequencies = await db.pool.fetch(
        """
        SELECT id, name, interval_weeks, discount_pct, is_default
        FROM cleaning_frequencies
        WHERE business_id = $1 AND is_archived = FALSE
        ORDER BY COALESCE(interval_weeks, 0), name
        """,
        business_id,
    )

    return {
        "services": [
            {
                "service_id": str(s["id"]),
                "name": s["name"],
                "description": s["description"],
                "category": s["category"],
                "tier": s["tier"],
                "bedrooms": s["bedrooms"],
                "bathrooms": s["bathrooms"],
                "estimated_duration_minutes": s["estimated_duration_minutes"],
                "base_price": float(s["base_price"]) if s["base_price"] else None,
                "icon": s["icon"],
            }
            for s in services
        ],
        "extras": [
            {
                "extra_id": str(e["id"]),
                "name": e["name"],
                "price": float(e["price"]),
            }
            for e in extras
        ],
        "frequencies": [
            {
                "frequency_id": str(f["id"]),
                "name": f["name"],
                "interval_weeks": f["interval_weeks"],
                "discount_pct": float(f["discount_pct"]),
                "is_default": f["is_default"],
            }
            for f in frequencies
        ],
    }


# ─── capture_lead (AI Turbo Webchat Publico 2026-04-21) ──────────────────

async def _capture_lead(
    params: dict, business_id: str, db: Database
) -> dict:
    """
    Cria cleaning_leads row com info coletada pelo IA no chat publico.
    NAO cria booking direto — owner revisa manualmente via admin UI.

    Busca match com cleaning_clients.phone (normalized) pra preencher
    client_id se cliente ja existir (lead de cliente existente tambem
    e util pra tracking de engagement).
    """
    phone = (params.get("phone") or "").strip()
    if not phone:
        return {
            "error": "phone_required",
            "message": "Cannot save lead without phone number",
        }

    # Normalize phone (strip non-digits) for dedup match
    phone_normalized = "".join(c for c in phone if c.isdigit())

    # Match existing client by normalized phone (same business scope)
    existing_client = await db.pool.fetchrow(
        """
        SELECT id FROM cleaning_clients
        WHERE business_id = $1
          AND regexp_replace(COALESCE(phone, ''), '[^0-9]', '', 'g') = $2
        LIMIT 1
        """,
        business_id, phone_normalized,
    )
    client_id = existing_client["id"] if existing_client else None

    try:
        lead = await db.pool.fetchrow(
            """
            INSERT INTO cleaning_leads (
                business_id, client_id,
                first_name, last_name, email, phone,
                zip_code, service_requested, bedrooms, bathrooms,
                preferred_date, preferred_time, message, estimated_quote,
                source
            ) VALUES (
                $1, $2, $3, $4, $5, $6, $7, $8, $9, $10,
                $11::date, $12, $13, $14, 'ai_chat'
            )
            RETURNING id
            """,
            business_id,
            client_id,
            params.get("first_name"),
            params.get("last_name"),
            params.get("email"),
            phone,
            params.get("zip_code"),
            params.get("service_requested"),
            params.get("bedrooms"),
            params.get("bathrooms"),
            # preferred_date as DATE: try ISO parse, else NULL (free text goes to message)
            _parse_iso_date(params.get("preferred_date")),
            params.get("preferred_time"),
            params.get("message"),
            params.get("estimated_quote"),
        )
    except Exception as e:
        logger.error("[AI_TOOLS] capture_lead insert failed: %s", e)
        return {"error": "lead_create_failed", "message": str(e)}

    lead_id = str(lead["id"])
    logger.info(
        "[AI_TOOLS] Lead captured: %s business=%s matched_client=%s",
        lead_id, business_id, bool(client_id),
    )

    return {
        "success": True,
        "lead_id": lead_id,
        "matched_existing_client": bool(client_id),
        "message": f"Lead ID: {lead_id} — tell visitor business will contact soon.",
    }


def _parse_iso_date(value):
    """Parse YYYY-MM-DD or return None (IA might send free text)."""
    if not value or not isinstance(value, str):
        return None
    try:
        from datetime import date as _date
        return _date.fromisoformat(value[:10])
    except (ValueError, TypeError):
        return None


# ─── propose_booking_draft ────────────────────

async def _propose_booking_draft(
    params: dict,
    business_id: str,
    db: Database,
    auth_context: Optional[dict] = None,
) -> dict:
    # CRITICAL fix (Smith verify 2026-04-20 C-1):
    # Dois gates de ownership antes de qualquer INSERT — sem isso a IA pode
    # ser manipulada via prompt injection pra criar drafts em nome de outro
    # cliente (cross-business OU intra-business).

    # Gate 1 — cross-business: client_id deve pertencer a este business.
    client_check = await db.pool.fetchrow(
        """
        SELECT id FROM cleaning_clients
        WHERE id = $1 AND business_id = $2 AND status != 'blocked'
        """,
        params["client_id"], business_id,
    )
    if not client_check:
        logger.warning(
            "[AI_TOOLS] propose_booking_draft REJECTED (cross-business): "
            "client_id=%s not owned by business_id=%s",
            params["client_id"], business_id,
        )
        return {
            "error": "client_not_authorized",
            "message": "This customer is not registered with this business.",
        }

    # Gate 2 — intra-business: se temos authenticated_client_id, deve bater
    # com o client_id do tool_input. Bloqueia spoofing dentro do mesmo business.
    if auth_context and auth_context.get("authenticated_client_id"):
        if str(params["client_id"]) != str(auth_context["authenticated_client_id"]):
            logger.warning(
                "[AI_TOOLS] propose_booking_draft REJECTED (spoofing): "
                "auth=%s tool_input=%s",
                auth_context["authenticated_client_id"], params["client_id"],
            )
            return {
                "error": "client_mismatch",
                "message": "You can only book services for your own account.",
            }

    # Defense-in-depth: re-check availability before INSERT
    # (race-safe real via advisory lock fica para backlog pos-sprint)
    avail = await is_slot_available(
        db,
        business_id=business_id,
        scheduled_date=params["scheduled_date"],
        scheduled_start=params["scheduled_start"],
        duration_minutes=params.get("duration_minutes"),
    )
    if not avail["available"]:
        return {
            "error": "slot_unavailable",
            "message": "The requested slot is no longer available.",
            "conflicts": avail["conflicts"],
        }

    # AUTO-ASSIGN TEAM: pick active team with no slot conflict.
    # Falls back to None (unassigned) if no team fits — owner reassigns manually.
    # preferred_team_id lookup from cleaning_client_schedules is backlog.
    auto_team_id = params.get("team_id") or await _pick_available_team(
        db,
        business_id=business_id,
        scheduled_date=params["scheduled_date"],
        scheduled_start=params["scheduled_start"],
        duration_minutes=params.get("duration_minutes"),
        preferred_team_id=None,
    )
    if auto_team_id:
        logger.info(
            "[AI_TOOLS] Auto-assigned team %s to booking (business=%s, slot=%s %s)",
            auto_team_id, business_id, params["scheduled_date"], params["scheduled_start"],
        )
    else:
        logger.warning(
            "[AI_TOOLS] No team auto-assigned (business=%s, slot=%s %s) — booking stays unassigned",
            business_id, params["scheduled_date"], params["scheduled_start"],
        )

    try:
        # AUTO-CONFIRM: availability already verified above (gate at line ~1059).
        # AI cria booking direto como "scheduled" (não draft). Owner não precisa
        # aprovar — slot já está garantido + cliente já viu cotação e confirmou.
        # Owner é notificado via send_notification (mesmo fluxo de bookings manuais).
        result = await create_booking_with_pricing(
            db,
            business_id=business_id,
            client_id=params["client_id"],
            service_id=params["service_id"],
            scheduled_date=params["scheduled_date"],
            scheduled_start=params["scheduled_start"],
            estimated_duration_minutes=params.get("duration_minutes"),
            tier=params.get("tier", "basic"),
            extras=params.get("extras", []),
            frequency_id=params.get("frequency_id"),
            location_id=params.get("location_id"),
            source="ai_chat",
            status="scheduled",
            team_id=auto_team_id,
            special_instructions=params.get("special_instructions"),
        )
        breakdown = result["breakdown"]
        booking_id = result["booking_id"]

        # Multi-channel notify (email + WhatsApp/SMS) — best-effort, never block.
        try:
            from app.modules.cleaning.services.email_service import (
                send_booking_confirmation,
                send_owner_new_booking,
            )
            # Email to client (booking confirmation)
            await send_booking_confirmation(db, str(booking_id))
            # Email to owner (new booking alert)
            await send_owner_new_booking(db, str(booking_id))
        except Exception as e:
            logger.warning("[AI_TOOLS] email notification failed (booking still created): %s", e)

        # Also fire WhatsApp/SMS via channel notification (graceful chains)
        try:
            from app.modules.cleaning.services.notification_service import send_notification
            notify_data = {
                "booking_id": str(booking_id),
                "scheduled_date": params["scheduled_date"],
                "scheduled_start": params["scheduled_start"],
                "duration_minutes": params.get("duration_minutes"),
                "service_id": params["service_id"],
                "tier": params.get("tier", "basic"),
                "final_amount": float(breakdown["final_amount"]),
                "source": "ai_chat",
            }
            await send_notification(
                db=db, business_id=business_id, target_type="client",
                target_id=params["client_id"], template_key="booking_confirmation",
                data=notify_data,
            )
            owner_row = await db.pool.fetchrow(
                """SELECT user_id FROM cleaning_user_roles
                   WHERE business_id = $1 AND role = 'owner' AND is_active = true
                   LIMIT 1""",
                business_id,
            )
            if owner_row:
                await send_notification(
                    db=db, business_id=business_id, target_type="owner",
                    target_id=str(owner_row["user_id"]), template_key="booking_confirmation",
                    data=notify_data,
                )
        except Exception as e:
            logger.warning("[AI_TOOLS] channel notification failed (booking still created): %s", e)

        return {
            "success": True,
            "booking_id": booking_id,
            "status": "scheduled",
            "scheduled_date": params["scheduled_date"],
            "scheduled_start": params["scheduled_start"],
            "final_amount": float(breakdown["final_amount"]),
            "extras_count": result["extras_written"],
            "message": "Booking confirmed and scheduled. Confirmation sent to customer and owner.",
        }
    except PricingConfigError as e:
        return {"error": "pricing_config", "message": str(e)}
    except Exception as e:
        logger.error("[AI_TOOLS] propose_booking_draft error: %s", e)
        return {"error": "draft_create_failed", "message": str(e)}


# ============================================
# HANDLER REGISTRY
# ============================================

TOOL_HANDLERS = {
    "get_schedule_for_date": _get_schedule_for_date,
    "get_team_availability": _get_team_availability,
    "get_client_history": _get_client_history,
    "calculate_distance": _calculate_distance,
    "get_team_workload_summary": _get_team_workload_summary,
    "get_cancellation_patterns": _get_cancellation_patterns,
    # AI Turbo Sprint 2026-04-20: tools limpas, schema atual
    "check_availability": _check_availability,
    "get_price_quote": _get_price_quote,
    "get_services_catalog": _get_services_catalog,
    "propose_booking_draft": _propose_booking_draft,
    # AI Turbo Webchat Publico 2026-04-21: lead capture pra visitante anonimo
    "capture_lead": _capture_lead,
}
