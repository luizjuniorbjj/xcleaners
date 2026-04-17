"""
Xcleaners v3 — Client Service (S2.3).

CRUD for cleaning_clients with search, filter, pagination,
client stats (LTV, total bookings), property details management,
duplicate detection, and plan-limit enforcement.
"""

import json
import logging
from datetime import datetime, date
from typing import Optional

import asyncpg

from app.database import Database
from app.modules.cleaning.middleware.plan_guard import check_limit
from app.security import encrypt_data, decrypt_data

# H-3 FIX: Access codes that must be encrypted at rest
_SENSITIVE_FIELDS = {"lockbox_code", "alarm_code", "gate_code", "garage_code"}


def _encrypt_sensitive_fields(data: dict, business_id: str) -> dict:
    """Encrypt access codes before storing in DB."""
    for field in _SENSITIVE_FIELDS:
        if field in data and data[field]:
            data[field] = encrypt_data(str(data[field]), business_id).decode("utf-8")
    return data


def _decrypt_sensitive_fields(row_dict: dict, business_id: str) -> dict:
    """Decrypt access codes when reading from DB."""
    for field in _SENSITIVE_FIELDS:
        val = row_dict.get(field)
        if val and isinstance(val, str) and len(val) > 60:
            try:
                row_dict[field] = decrypt_data(val.encode("utf-8"), business_id)
            except Exception:
                pass  # Return as-is if decryption fails (legacy plaintext data)
    return row_dict

logger = logging.getLogger("xcleaners.client_service")


# ============================================
# DURATION ESTIMATOR
# ============================================

def estimate_duration(
    sqft: Optional[int],
    bedrooms: Optional[int],
    bathrooms: Optional[float],
    base_duration: int = 120,
) -> int:
    """
    Estimate cleaning duration in minutes.
    Formula from S2.3 story:
      base = service.estimated_duration_minutes (default 120)
      sqft_factor = max(1.0, sqft / 1500)
      room_factor = 1.0 + (bedrooms + bathrooms - 3) * 0.1
      estimated = int(base * sqft_factor * room_factor)
    """
    sqft = sqft or 1500
    bedrooms = bedrooms or 2
    bathrooms = bathrooms or 1.0

    sqft_factor = max(1.0, sqft / 1500)
    room_factor = 1.0 + (bedrooms + bathrooms - 3) * 0.1
    room_factor = max(0.5, room_factor)  # floor at 0.5x
    estimated = int(base_duration * sqft_factor * room_factor)
    return estimated


# ============================================
# CLIENT CRUD
# ============================================

async def create_client(
    db: Database,
    business_id: str,
    data: dict,
) -> dict:
    """
    Create a new cleaning client.
    - Checks plan limit (Basic 50, Intermediate 200, Maximum unlimited)
    - Duplicate detection by phone or email (returns 409)
    - Returns created client row
    """
    # 1. Check plan limit
    current_count = await db.pool.fetchval(
        "SELECT COUNT(*) FROM cleaning_clients WHERE business_id = $1 AND status != 'blocked'",
        business_id,
    )
    await check_limit(business_id, "clients", current_count, db)

    # 2. Duplicate detection
    if data.get("phone"):
        dup = await db.pool.fetchrow(
            """SELECT id, first_name, last_name, phone, email
               FROM cleaning_clients
               WHERE business_id = $1 AND phone = $2 AND status != 'blocked'""",
            business_id, data["phone"],
        )
        if dup:
            return {"duplicate": True, "existing_client_id": str(dup["id"]), "match_field": "phone"}

    if data.get("email"):
        dup = await db.pool.fetchrow(
            """SELECT id, first_name, last_name, phone, email
               FROM cleaning_clients
               WHERE business_id = $1 AND email = $2 AND status != 'blocked'""",
            business_id, data["email"],
        )
        if dup:
            return {"duplicate": True, "existing_client_id": str(dup["id"]), "match_field": "email"}

    # 3. Build INSERT
    # Filter to valid DB columns only (migration 020 added the extended columns)
    valid_columns = {
        "first_name", "last_name", "email", "phone", "phone_secondary",
        "address_line1", "address_line2", "city", "state", "zip_code",
        "country", "latitude", "longitude", "property_type",
        "bedrooms", "bathrooms", "square_feet", "has_pets", "pet_details",
        "access_instructions", "preferred_day", "preferred_time_start",
        "preferred_time_end", "notes", "source",
        # Migration 020: proper columns (no longer stored in notes __META__)
        "preferred_contact", "billing_address", "tags", "internal_notes",
        "key_location", "lockbox_code", "alarm_code", "gate_code",
        "garage_code", "parking_instructions",
        "pet_type", "pet_name", "pet_temperament", "pet_location_during_cleaning",
        "products_to_use", "products_to_avoid", "rooms_to_skip", "preferred_cleaning_order",
    }

    insert_data = {k: v for k, v in data.items() if k in valid_columns and v is not None}
    insert_data["business_id"] = business_id

    # H-3: Encrypt access codes before storing
    insert_data = _encrypt_sensitive_fields(insert_data, business_id)

    columns = list(insert_data.keys())
    values = list(insert_data.values())
    placeholders = [f"${i+1}" for i in range(len(columns))]

    # Core columns from migration 011 (always safe across all envs).
    _BASIC_COLUMNS = {
        "business_id", "first_name", "last_name", "email", "phone", "phone_secondary",
        "address_line1", "address_line2", "city", "state", "zip_code", "country",
        "latitude", "longitude", "property_type", "bedrooms", "bathrooms", "square_feet",
        "has_pets", "pet_details", "access_instructions", "preferred_day",
        "preferred_time_start", "preferred_time_end", "notes", "source",
    }

    try:
        row = await db.pool.fetchrow(
            f"""INSERT INTO cleaning_clients ({', '.join(columns)})
                VALUES ({', '.join(placeholders)})
                RETURNING *""",
            *values,
        )
    except asyncpg.exceptions.UndefinedColumnError as e:
        # Schema drift: migration 020 extended columns likely not applied yet.
        # Fall back to migration-011 core columns so the create succeeds.
        logger.warning(
            "[CLIENTS] Schema drift detected on cleaning_clients INSERT (%s). "
            "Retrying with migration-011 core columns only.", e
        )
        fallback_data = {k: v for k, v in insert_data.items() if k in _BASIC_COLUMNS}
        fb_columns = list(fallback_data.keys())
        fb_values = list(fallback_data.values())
        fb_placeholders = [f"${i+1}" for i in range(len(fb_columns))]
        row = await db.pool.fetchrow(
            f"""INSERT INTO cleaning_clients ({', '.join(fb_columns)})
                VALUES ({', '.join(fb_placeholders)})
                RETURNING *""",
            *fb_values,
        )
    except asyncpg.exceptions.NotNullViolationError as e:
        return {"error": True, "status": 422,
                "message": f"Missing required field: {e.column_name or 'unknown'}"}
    except asyncpg.exceptions.CheckViolationError as e:
        return {"error": True, "status": 422,
                "message": f"Invalid value for constraint: {e.constraint_name or 'unknown'}"}
    except asyncpg.exceptions.UniqueViolationError as e:
        return {"error": True, "status": 409,
                "message": f"Duplicate: {e.constraint_name or 'already exists'}"}

    result = _row_to_dict(row)
    return _decrypt_sensitive_fields(result, business_id)


async def get_client(
    db: Database,
    business_id: str,
    client_id: str,
    include_schedules: bool = True,
    include_financial: bool = True,
) -> Optional[dict]:
    """Get a single client with optional schedules and financial summary."""
    row = await db.pool.fetchrow(
        """SELECT * FROM cleaning_clients
           WHERE id = $1 AND business_id = $2""",
        client_id, business_id,
    )
    if not row:
        return None

    result = _row_to_dict(row)
    result = _decrypt_sensitive_fields(result, business_id)

    # Active schedules count
    sched_count = await db.pool.fetchval(
        """SELECT COUNT(*) FROM cleaning_client_schedules
           WHERE client_id = $1 AND business_id = $2 AND status = 'active'""",
        client_id, business_id,
    )
    result["active_schedules_count"] = sched_count or 0

    # Financial summary
    if include_financial:
        result["financial_summary"] = await _get_financial_summary(db, business_id, client_id)

    return result


async def update_client(
    db: Database,
    business_id: str,
    client_id: str,
    data: dict,
) -> Optional[dict]:
    """Update client fields. Returns updated row or None if not found."""
    # Handle status change: paused -> suspend schedules
    new_status = data.get("status")

    valid_columns = {
        "first_name", "last_name", "email", "phone", "phone_secondary",
        "address_line1", "address_line2", "city", "state", "zip_code",
        "country", "latitude", "longitude", "property_type",
        "bedrooms", "bathrooms", "square_feet", "has_pets", "pet_details",
        "access_instructions", "preferred_day", "preferred_time_start",
        "preferred_time_end", "notes", "status",
        # Migration 020: proper columns (no longer stored in notes __META__)
        "preferred_contact", "billing_address", "tags", "internal_notes",
        "key_location", "lockbox_code", "alarm_code", "gate_code",
        "garage_code", "parking_instructions",
        "pet_type", "pet_name", "pet_temperament", "pet_location_during_cleaning",
        "products_to_use", "products_to_avoid", "rooms_to_skip", "preferred_cleaning_order",
    }

    update_data = {k: v for k, v in data.items() if k in valid_columns and v is not None}

    if not update_data:
        # Nothing to update, just return current
        return await get_client(db, business_id, client_id)

    # H-3: Encrypt access codes before storing
    update_data = _encrypt_sensitive_fields(update_data, business_id)

    # NOTE: 'paused' and 'former' are now valid DB statuses (migration 018).
    # No mapping needed — values pass through directly.

    set_clauses = [f"{col} = ${i+1}" for i, col in enumerate(update_data.keys())]
    values = list(update_data.values())
    values.extend([client_id, business_id])

    row = await db.pool.fetchrow(
        f"""UPDATE cleaning_clients
            SET {', '.join(set_clauses)}, updated_at = NOW()
            WHERE id = ${len(values) - 1} AND business_id = ${len(values)}
            RETURNING *""",
        *values,
    )

    if not row:
        return None

    # If paused, suspend all active schedules
    if new_status == "paused":
        await db.pool.execute(
            """UPDATE cleaning_client_schedules
               SET status = 'paused', updated_at = NOW()
               WHERE client_id = $1 AND business_id = $2 AND status = 'active'""",
            client_id, business_id,
        )

    result = _row_to_dict(row)
    result["active_schedules_count"] = 0 if new_status == "paused" else await db.pool.fetchval(
        "SELECT COUNT(*) FROM cleaning_client_schedules WHERE client_id = $1 AND business_id = $2 AND status = 'active'",
        client_id, business_id,
    ) or 0

    return result


async def delete_client(
    db: Database,
    business_id: str,
    client_id: str,
) -> bool:
    """Soft delete: set status to 'blocked' and cancel schedules."""
    result = await db.pool.execute(
        """UPDATE cleaning_clients
           SET status = 'blocked', updated_at = NOW()
           WHERE id = $1 AND business_id = $2 AND status != 'blocked'""",
        client_id, business_id,
    )

    if result == "UPDATE 0":
        return False

    # Cancel all active schedules
    await db.pool.execute(
        """UPDATE cleaning_client_schedules
           SET status = 'cancelled', updated_at = NOW()
           WHERE client_id = $1 AND business_id = $2 AND status IN ('active', 'paused')""",
        client_id, business_id,
    )

    return True


async def list_clients(
    db: Database,
    business_id: str,
    search: Optional[str] = None,
    status: Optional[str] = None,
    frequency: Optional[str] = None,
    team_id: Optional[str] = None,
    tag: Optional[str] = None,
    has_balance: Optional[bool] = None,
    sort_by: str = "last_name",
    sort_order: str = "asc",
    page: int = 1,
    per_page: int = 25,
) -> dict:
    """
    List clients with search, filter, sort, and pagination.
    Returns {clients: [...], total: N, page, per_page}.
    """
    conditions = ["c.business_id = $1", "c.status != 'blocked'"]
    params = [business_id]
    param_idx = 2

    # Status filter
    if status:
        # Map API status to DB status
        if status == "paused":
            conditions.append(f"c.status = ${param_idx}")
            params.append("inactive")
        elif status == "former":
            conditions.append(f"c.status = ${param_idx}")
            params.append("inactive")
        else:
            conditions.append(f"c.status = ${param_idx}")
            params.append(status)
        param_idx += 1

    # Search (name, email, phone, address)
    if search:
        conditions.append(f"""(
            c.first_name ILIKE ${param_idx}
            OR c.last_name ILIKE ${param_idx}
            OR c.email ILIKE ${param_idx}
            OR c.phone ILIKE ${param_idx}
            OR c.address_line1 ILIKE ${param_idx}
            OR c.city ILIKE ${param_idx}
        )""")
        params.append(f"%{search}%")
        param_idx += 1

    # Tag filter (stored in notes JSON meta)
    if tag:
        conditions.append(f"c.notes ILIKE ${param_idx}")
        params.append(f"%{tag}%")
        param_idx += 1

    # Frequency filter (via client_schedules join)
    frequency_join = ""
    if frequency:
        frequency_join = f"""
            INNER JOIN cleaning_client_schedules cs
            ON cs.client_id = c.id AND cs.business_id = c.business_id
            AND cs.status = 'active' AND cs.frequency = ${param_idx}
        """
        params.append(frequency)
        param_idx += 1

    # Team filter (via client_schedules join)
    team_join = ""
    if team_id and not frequency:
        team_join = f"""
            INNER JOIN cleaning_client_schedules cs
            ON cs.client_id = c.id AND cs.business_id = c.business_id
            AND cs.status = 'active' AND cs.preferred_team_id = ${param_idx}
        """
        params.append(team_id)
        param_idx += 1
    elif team_id and frequency:
        conditions.append(f"cs.preferred_team_id = ${param_idx}")
        params.append(team_id)
        param_idx += 1

    where_clause = " AND ".join(conditions)

    # Validate sort column
    allowed_sorts = {
        "first_name": "c.first_name",
        "last_name": "c.last_name",
        "email": "c.email",
        "status": "c.status",
        "lifetime_value": "c.lifetime_value",
        "total_bookings": "c.total_bookings",
        "last_service_date": "c.last_service_date",
        "created_at": "c.created_at",
    }
    sort_col = allowed_sorts.get(sort_by, "c.last_name")
    sort_dir = "DESC" if sort_order.lower() == "desc" else "ASC"

    # Count
    count_sql = f"""
        SELECT COUNT(DISTINCT c.id)
        FROM cleaning_clients c
        {frequency_join}
        {team_join}
        WHERE {where_clause}
    """
    total = await db.pool.fetchval(count_sql, *params)

    # Fetch
    offset = (page - 1) * per_page
    fetch_sql = f"""
        SELECT DISTINCT c.*
        FROM cleaning_clients c
        {frequency_join}
        {team_join}
        WHERE {where_clause}
        ORDER BY {sort_col} {sort_dir}
        LIMIT {per_page} OFFSET {offset}
    """
    rows = await db.pool.fetch(fetch_sql, *params)

    clients = []
    for row in rows:
        client = _row_to_dict(row)
        # Get active schedule count
        sched_count = await db.pool.fetchval(
            "SELECT COUNT(*) FROM cleaning_client_schedules WHERE client_id = $1 AND business_id = $2 AND status = 'active'",
            str(row["id"]), business_id,
        )
        client["active_schedules_count"] = sched_count or 0
        clients.append(client)

    return {
        "clients": clients,
        "total": total or 0,
        "page": page,
        "per_page": per_page,
    }


async def search_clients(
    db: Database,
    business_id: str,
    query: str,
    limit: int = 10,
) -> list[dict]:
    """Quick search for autocomplete / typeahead."""
    rows = await db.pool.fetch(
        """SELECT id, first_name, last_name, phone, email, address_line1, city, status
           FROM cleaning_clients
           WHERE business_id = $1
             AND status != 'blocked'
             AND (
               first_name ILIKE $2
               OR last_name ILIKE $2
               OR email ILIKE $2
               OR phone ILIKE $2
               OR address_line1 ILIKE $2
             )
           ORDER BY last_name ASC, first_name ASC
           LIMIT $3""",
        business_id, f"%{query}%", limit,
    )
    return [dict(r) for r in rows]


# ============================================
# FINANCIAL SUMMARY
# ============================================

async def _get_financial_summary(db: Database, business_id: str, client_id: str) -> dict:
    """Compute financial summary for a client."""
    row = await db.pool.fetchrow(
        """SELECT
            COALESCE(SUM(CASE WHEN status = 'paid' THEN total ELSE 0 END), 0) AS total_spent,
            COALESCE(SUM(CASE WHEN status IN ('sent', 'overdue') THEN total ELSE 0 END), 0) AS outstanding_balance,
            COUNT(*) AS total_invoices,
            COUNT(CASE WHEN status = 'overdue' THEN 1 END) AS overdue_invoices
           FROM cleaning_invoices
           WHERE client_id = $1 AND business_id = $2""",
        client_id, business_id,
    )
    if row:
        return {
            "total_spent": float(row["total_spent"]),
            "outstanding_balance": float(row["outstanding_balance"]),
            "total_invoices": row["total_invoices"],
            "overdue_invoices": row["overdue_invoices"],
        }
    return {"total_spent": 0.0, "outstanding_balance": 0.0, "total_invoices": 0, "overdue_invoices": 0}


# ============================================
# HELPERS
# ============================================

def _parse_meta(notes: str) -> tuple[dict, str]:
    """Parse __META__{json}__META__ prefix from notes field."""
    if notes and notes.startswith("__META__"):
        parts = notes.split("__META__", 2)
        if len(parts) >= 3:
            try:
                meta = json.loads(parts[1])
                clean_notes = parts[2] if len(parts) > 2 else ""
                return meta, clean_notes
            except (json.JSONDecodeError, IndexError):
                pass
    return {}, notes or ""


def _row_to_dict(row) -> dict:
    """Convert asyncpg Record to dict with proper serialization."""
    if not row:
        return {}

    d = dict(row)

    # Parse __META__ from notes for backward compat (rows written before migration 020)
    notes_raw = d.get("notes", "") or ""
    meta, clean_notes = _parse_meta(notes_raw)

    # UUID to str
    for key in ["id", "business_id", "user_id"]:
        if d.get(key):
            d[key] = str(d[key])

    # Dates/times to str
    for key in ["created_at", "updated_at", "last_service_date"]:
        val = d.get(key)
        if val is not None:
            d[key] = str(val)

    for key in ["preferred_time_start", "preferred_time_end"]:
        val = d.get(key)
        if val is not None:
            d[key] = str(val)

    # Numeric conversions
    for key in ["lifetime_value"]:
        val = d.get(key)
        if val is not None:
            d[key] = float(val)

    for key in ["bathrooms"]:
        val = d.get(key)
        if val is not None:
            d[key] = float(val)

    for key in ["latitude", "longitude"]:
        val = d.get(key)
        if val is not None:
            d[key] = float(val)

    # Extract extended fields — prefer real DB columns (migration 020),
    # fall back to __META__ for rows written before migration 020.
    if d.get("tags") is None:
        d["tags"] = meta.get("tags", [])
    if d.get("internal_notes") is None:
        d["internal_notes"] = meta.get("internal_notes")
    if d.get("preferred_contact") is None:
        d["preferred_contact"] = meta.get("preferred_contact")
    if d.get("billing_address") is None:
        d["billing_address"] = meta.get("billing_address")
    # Ensure tags is always a list
    if not isinstance(d["tags"], list):
        d["tags"] = []
    d["notes"] = clean_notes if clean_notes else None

    # Defaults
    d.setdefault("active_schedules_count", 0)
    d.setdefault("financial_summary", None)
    d.setdefault("source", "manual")
    d.setdefault("status", "active")

    return d
