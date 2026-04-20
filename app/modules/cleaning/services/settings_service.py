"""
Xcleaners v3 — Settings Service.

Manages business settings, service areas, and pricing rules
for the owner settings panel.

Tables: businesses (JSONB settings), cleaning_areas, cleaning_pricing_rules.
"""

import json
import logging
from typing import Optional

from app.database import Database
from app.modules.cleaning.services._type_helpers import to_date

logger = logging.getLogger("xcleaners.settings_service")


# ============================================
# DEFAULT SETTINGS (merged with stored settings)
# ============================================

DEFAULT_SETTINGS = {
    "business_hours": {
        "monday": {"start": "08:00", "end": "17:00", "enabled": True},
        "tuesday": {"start": "08:00", "end": "17:00", "enabled": True},
        "wednesday": {"start": "08:00", "end": "17:00", "enabled": True},
        "thursday": {"start": "08:00", "end": "17:00", "enabled": True},
        "friday": {"start": "08:00", "end": "17:00", "enabled": True},
        "saturday": {"start": "09:00", "end": "14:00", "enabled": False},
        "sunday": {"start": "09:00", "end": "14:00", "enabled": False},
    },
    "cancellation_policy": {
        "hours_before": 24,
        "fee_percentage": 50,
        "max_reschedules_per_month": 2,
        "max_reschedules_per_booking": 1,
    },
    "travel_buffer_minutes": 30,
    "auto_generate_schedule": False,
    "auto_generate_time": "06:00",
    "default_service_duration": 120,
    "notification_preferences": {
        "booking_confirmation": True,
        "booking_reminder_24h": True,
        "booking_reminder_1h": False,
        "schedule_change": True,
        "payment_received": True,
        "invoice_sent": True,
        "team_checkin": True,
    },
}


# ============================================
# GET BUSINESS SETTINGS
# ============================================

async def get_business_settings(db: Database, business_id: str) -> dict:
    """
    Retrieve all settings for a cleaning business.
    Settings are stored as JSONB in the businesses table (cleaning_settings column).
    Returns merged defaults + stored settings, plus business profile info.
    """
    row = await db.pool.fetchrow(
        """SELECT
            b.id, b.name, b.slug,
            b.timezone, b.logo_url,
            b.cleaning_settings,
            b.plan, b.status
           FROM businesses b
           WHERE b.id = $1""",
        business_id,
    )

    if not row:
        return None

    # Merge stored settings with defaults
    stored = {}
    if row["cleaning_settings"]:
        if isinstance(row["cleaning_settings"], str):
            stored = json.loads(row["cleaning_settings"])
        else:
            stored = dict(row["cleaning_settings"])

    settings = _deep_merge(DEFAULT_SETTINGS.copy(), stored)

    # Business contact info lives inside cleaning_settings (not in businesses table)
    contact = settings.get("business_info", {})

    return {
        "business_profile": {
            "id": str(row["id"]),
            "name": row["name"],
            "slug": row["slug"],
            "phone": contact.get("phone"),
            "email": contact.get("email"),
            "address": contact.get("address"),
            "city": contact.get("city"),
            "state": contact.get("state"),
            "zip_code": contact.get("zip_code"),
            "timezone": row["timezone"],
            "logo_url": row["logo_url"],
        },
        "settings": settings,
        "plan": row["plan"],
        "status": row["status"],
    }


# ============================================
# CANCELLATION POLICY (fast read — booking flow)
# ============================================

async def get_cancellation_policy(db: Database, business_id: str) -> dict:
    """
    Return the cancellation_policy block merged with defaults, plus the
    business timezone under the key ``timezone`` so callers computing the
    cancellation window (which depends on local booking time) can resolve
    without a second round trip.

    Defaults to ``UTC`` when the business has no timezone configured.
    Always returns a populated dict — defaults cover any missing keys.
    """
    row = await db.pool.fetchrow(
        "SELECT cleaning_settings, timezone FROM businesses WHERE id = $1",
        business_id,
    )

    stored = {}
    if row and row["cleaning_settings"]:
        cs = row["cleaning_settings"]
        if isinstance(cs, str):
            stored = json.loads(cs)
        else:
            stored = dict(cs)

    policy = dict(DEFAULT_SETTINGS["cancellation_policy"])
    policy.update(stored.get("cancellation_policy") or {})
    policy["timezone"] = (row["timezone"] if row else None) or "UTC"
    return policy


# ============================================
# UPDATE BUSINESS SETTINGS
# ============================================

async def update_business_settings(
    db: Database,
    business_id: str,
    settings: dict,
) -> dict:
    """
    Update settings for a cleaning business.
    Accepts partial updates — merges with existing settings.
    Also accepts top-level business profile fields (name, phone, email, etc.).
    """
    # Separate business-table fields from cleaning_settings
    business_table_fields = {}
    settings_update = {}

    # Only these columns exist in the businesses table
    business_table_keys = {"name", "timezone"}
    # Contact info goes into cleaning_settings.business_info
    contact_keys = {"phone", "email", "address", "city", "state", "zip_code"}

    for key, value in settings.items():
        if key in business_table_keys:
            business_table_fields[key] = value
        elif key in contact_keys:
            settings_update.setdefault("business_info", {})[key] = value
        else:
            settings_update[key] = value

    # Update business table fields if any
    if business_table_fields:
        set_parts = []
        values = []
        idx = 1
        for col, val in business_table_fields.items():
            set_parts.append(f"{col} = ${idx}")
            values.append(val)
            idx += 1
        set_parts.append("updated_at = NOW()")
        values.append(business_id)

        await db.pool.execute(
            f"UPDATE businesses SET {', '.join(set_parts)} WHERE id = ${idx}",
            *values,
        )

    # Update cleaning settings (merge with existing)
    if settings_update:
        current = await db.pool.fetchval(
            "SELECT cleaning_settings FROM businesses WHERE id = $1",
            business_id,
        )
        existing = {}
        if current:
            if isinstance(current, str):
                existing = json.loads(current)
            else:
                existing = dict(current)

        merged = _deep_merge(existing, settings_update)

        await db.pool.execute(
            "UPDATE businesses SET cleaning_settings = $1::JSONB, updated_at = NOW() WHERE id = $2",
            json.dumps(merged), business_id,
        )

    return await get_business_settings(db, business_id)


# ============================================
# SERVICE AREAS CRUD
# ============================================

async def list_service_areas(db: Database, business_id: str) -> list:
    """List all service areas for a business."""
    rows = await db.pool.fetch(
        """SELECT * FROM cleaning_areas
           WHERE business_id = $1
           ORDER BY priority DESC, name""",
        business_id,
    )
    return [_area_to_dict(r) for r in rows]


async def create_service_area(db: Database, business_id: str, data: dict) -> dict:
    """Create a new service area."""
    row = await db.pool.fetchrow(
        """INSERT INTO cleaning_areas
           (business_id, name, zip_codes, city, state,
            radius_miles, center_latitude, center_longitude,
            travel_fee, is_active, priority)
           VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
           RETURNING *""",
        business_id,
        data["name"],
        data.get("zip_codes", []),
        data.get("city"),
        data.get("state"),
        data.get("radius_miles"),
        data.get("center_latitude"),
        data.get("center_longitude"),
        data.get("travel_fee", 0),
        data.get("is_active", True),
        data.get("priority", 0),
    )
    return _area_to_dict(row)


async def update_service_area(
    db: Database, business_id: str, area_id: str, data: dict
) -> Optional[dict]:
    """Update an existing service area."""
    allowed = {
        "name", "zip_codes", "city", "state", "radius_miles",
        "center_latitude", "center_longitude", "travel_fee",
        "is_active", "priority",
    }
    update_data = {k: v for k, v in data.items() if k in allowed}
    if not update_data:
        return None

    set_parts = []
    values = []
    idx = 1
    for col, val in update_data.items():
        set_parts.append(f"{col} = ${idx}")
        values.append(val)
        idx += 1
    set_parts.append("updated_at = NOW()")
    values.extend([area_id, business_id])

    row = await db.pool.fetchrow(
        f"""UPDATE cleaning_areas SET {', '.join(set_parts)}
            WHERE id = ${idx} AND business_id = ${idx + 1}
            RETURNING *""",
        *values,
    )
    return _area_to_dict(row) if row else None


async def delete_service_area(
    db: Database, business_id: str, area_id: str
) -> bool:
    """Delete a service area."""
    result = await db.pool.execute(
        "DELETE FROM cleaning_areas WHERE id = $1 AND business_id = $2",
        area_id, business_id,
    )
    return "DELETE 1" in result


# ============================================
# PRICING RULES CRUD
# ============================================

async def list_pricing_rules(db: Database, business_id: str) -> list:
    """List all pricing rules for a business."""
    rows = await db.pool.fetch(
        """SELECT pr.*, s.name AS service_name
           FROM cleaning_pricing_rules pr
           LEFT JOIN cleaning_services s ON s.id = pr.service_id
           WHERE pr.business_id = $1
           ORDER BY pr.priority, pr.name""",
        business_id,
    )
    return [_rule_to_dict(r) for r in rows]


async def create_pricing_rule(db: Database, business_id: str, data: dict) -> dict:
    """Create a new pricing rule."""
    conditions = data.get("conditions", {})
    if isinstance(conditions, str):
        conditions = json.loads(conditions)

    row = await db.pool.fetchrow(
        """INSERT INTO cleaning_pricing_rules
           (business_id, service_id, name, rule_type,
            conditions, amount, percentage,
            priority, is_active, valid_from, valid_until)
           VALUES ($1, $2, $3, $4, $5::JSONB, $6, $7, $8, $9, $10, $11)
           RETURNING *""",
        business_id,
        data.get("service_id"),
        data["name"],
        data["rule_type"],
        json.dumps(conditions),
        data.get("amount"),
        data.get("percentage"),
        data.get("priority", 0),
        data.get("is_active", True),
        to_date(data.get("valid_from")),
        to_date(data.get("valid_until")),
    )

    # Re-fetch with service name
    full = await db.pool.fetchrow(
        """SELECT pr.*, s.name AS service_name
           FROM cleaning_pricing_rules pr
           LEFT JOIN cleaning_services s ON s.id = pr.service_id
           WHERE pr.id = $1""",
        row["id"],
    )
    return _rule_to_dict(full)


async def update_pricing_rule(
    db: Database, business_id: str, rule_id: str, data: dict
) -> Optional[dict]:
    """Update an existing pricing rule."""
    allowed = {
        "service_id", "name", "rule_type", "conditions",
        "amount", "percentage", "priority", "is_active",
        "valid_from", "valid_until",
    }
    update_data = {k: v for k, v in data.items() if k in allowed}
    if not update_data:
        return None

    # Handle conditions serialization
    if "conditions" in update_data:
        cond = update_data["conditions"]
        if isinstance(cond, dict):
            update_data["conditions"] = json.dumps(cond)

    set_parts = []
    values = []
    idx = 1
    for col, val in update_data.items():
        if col == "conditions":
            set_parts.append(f"{col} = ${idx}::JSONB")
        elif col in ("valid_from", "valid_until"):
            set_parts.append(f"{col} = ${idx}")
            val = to_date(val)
        else:
            set_parts.append(f"{col} = ${idx}")
        values.append(val)
        idx += 1
    set_parts.append("updated_at = NOW()")
    values.extend([rule_id, business_id])

    row = await db.pool.fetchrow(
        f"""UPDATE cleaning_pricing_rules SET {', '.join(set_parts)}
            WHERE id = ${idx} AND business_id = ${idx + 1}
            RETURNING *""",
        *values,
    )
    if not row:
        return None

    full = await db.pool.fetchrow(
        """SELECT pr.*, s.name AS service_name
           FROM cleaning_pricing_rules pr
           LEFT JOIN cleaning_services s ON s.id = pr.service_id
           WHERE pr.id = $1""",
        row["id"],
    )
    return _rule_to_dict(full)


async def delete_pricing_rule(
    db: Database, business_id: str, rule_id: str
) -> bool:
    """Delete a pricing rule."""
    result = await db.pool.execute(
        "DELETE FROM cleaning_pricing_rules WHERE id = $1 AND business_id = $2",
        rule_id, business_id,
    )
    return "DELETE 1" in result


# ============================================
# HELPERS
# ============================================

def _deep_merge(base: dict, override: dict) -> dict:
    """Deep merge two dicts. Override values take precedence."""
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _area_to_dict(row) -> dict:
    """Convert a cleaning_areas DB row to a dict."""
    return {
        "id": str(row["id"]),
        "name": row["name"],
        "zip_codes": row["zip_codes"] or [],
        "city": row["city"],
        "state": row["state"],
        "radius_miles": float(row["radius_miles"]) if row["radius_miles"] else None,
        "center_latitude": float(row["center_latitude"]) if row["center_latitude"] else None,
        "center_longitude": float(row["center_longitude"]) if row["center_longitude"] else None,
        "travel_fee": float(row["travel_fee"]) if row["travel_fee"] else 0,
        "is_active": row["is_active"],
        "priority": row["priority"],
        "created_at": str(row["created_at"]),
        "updated_at": str(row["updated_at"]) if row["updated_at"] else None,
    }


def _rule_to_dict(row) -> dict:
    """Convert a cleaning_pricing_rules DB row to a dict."""
    conditions = row["conditions"]
    if isinstance(conditions, str):
        conditions = json.loads(conditions)

    return {
        "id": str(row["id"]),
        "service_id": str(row["service_id"]) if row["service_id"] else None,
        "service_name": row.get("service_name"),
        "name": row["name"],
        "rule_type": row["rule_type"],
        "conditions": conditions or {},
        "amount": float(row["amount"]) if row["amount"] else None,
        "percentage": float(row["percentage"]) if row["percentage"] else None,
        "priority": row["priority"],
        "is_active": row["is_active"],
        "valid_from": str(row["valid_from"]) if row["valid_from"] else None,
        "valid_until": str(row["valid_until"]) if row["valid_until"] else None,
        "created_at": str(row["created_at"]),
        "updated_at": str(row["updated_at"]) if row["updated_at"] else None,
    }
