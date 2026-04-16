"""
Xcleaners — Test Fixtures for Recurring Auto-Generator (Sprint D Track A).

Helper builders for setting up schedules + pricing inputs in test DB.
Used by tests/test_recurring_generator.py.

Provides:
    - create_test_business + tear_down_business
    - create_test_client
    - create_test_service (with tier, bedrooms, bathrooms)
    - create_test_frequency (or use 021-seeded one via LOOKUP)
    - create_test_extra
    - create_test_location
    - create_schedule (with full pricing inputs)
    - add_schedule_extra
    - add_schedule_skip

Cleanup: tear_down_business cascades via FK deletes to clean entire tree.
"""

from __future__ import annotations

import uuid
from datetime import date as date_cls, time
from decimal import Decimal
from typing import Any


# ============================================
# BUSINESS + USER
# ============================================

async def create_test_business(db, slug: str = "test-biz") -> str:
    """Create a minimal business + owner for isolation. Returns business_id."""
    owner_id = uuid.uuid4()
    await db.pool.execute(
        """
        INSERT INTO users (id, email, password_hash, name, role, status, created_at, updated_at)
        VALUES ($1, $2, 'test', 'Test Owner', 'user', 'active', NOW(), NOW())
        """,
        owner_id,
        f"owner-{owner_id}@test.local",
    )

    biz_id = uuid.uuid4()
    await db.pool.execute(
        """
        INSERT INTO businesses (
            id, user_id, name, slug, whatsapp_phone, phone,
            business_type, primary_color, welcome_message, status, plan,
            created_at, updated_at
        )
        VALUES (
            $1, $2, $3, $4, '+15551234567', '+15551234567',
            'cleaning', '#4285F4', 'hi', 'active', 'basic',
            NOW(), NOW()
        )
        """,
        biz_id,
        owner_id,
        f"Test Biz {slug}",
        f"{slug}-{uuid.uuid4().hex[:8]}",
    )

    # Seed default frequencies + formula + default area (mimics migration 021)
    await _seed_defaults(db, biz_id)

    return str(biz_id)


async def _seed_defaults(db, biz_id: uuid.UUID) -> None:
    """Seed 4 frequencies, default formula, default area for this business."""
    # Frequencies: One Time (0%), Weekly (15%), Biweekly (10%), Monthly (5%)
    freq_data = [
        ("One Time", None, Decimal("0.00"), True),
        ("Weekly", 1, Decimal("15.00"), False),
        ("Biweekly", 2, Decimal("10.00"), False),
        ("Monthly", 4, Decimal("5.00"), False),
    ]
    for name, interval, pct, is_default in freq_data:
        await db.pool.execute(
            """
            INSERT INTO cleaning_frequencies (
                business_id, name, interval_weeks, discount_pct, is_default
            ) VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT DO NOTHING
            """,
            biz_id, name, interval, pct, is_default,
        )

    # Default formula
    import json
    await db.pool.execute(
        """
        INSERT INTO cleaning_pricing_formulas (
            business_id, name, base_amount, bedroom_delta, bathroom_delta,
            tier_multipliers, is_active
        ) VALUES ($1, 'Standard', 115.00, 20.00, 15.00, $2::jsonb, TRUE)
        """,
        biz_id,
        json.dumps({"basic": 1.0, "deep": 1.8, "premium": 2.8}),
    )

    # Default area
    area_id = uuid.uuid4()
    await db.pool.execute(
        """
        INSERT INTO cleaning_areas (
            id, business_id, name, zip_codes, is_default, is_archived, created_at
        ) VALUES ($1, $2, 'NYC', ARRAY['10001','10002'], TRUE, FALSE, NOW())
        """,
        area_id, biz_id,
    )

    # Tax rate for NYC (4.5% per 3Sisters F1)
    await db.pool.execute(
        """
        INSERT INTO cleaning_sales_taxes (
            business_id, location_id, tax_pct, effective_date
        ) VALUES ($1, $2, 4.50, '2020-01-01')
        """,
        biz_id, area_id,
    )


async def tear_down_business(db, business_id: str) -> None:
    """Delete business — CASCADE removes all linked rows."""
    # Also remove the owner user(s)
    await db.pool.execute(
        """
        DELETE FROM users WHERE id IN (
            SELECT user_id FROM businesses WHERE id = $1
        )
        """,
        uuid.UUID(business_id),
    )
    await db.pool.execute(
        "DELETE FROM businesses WHERE id = $1",
        uuid.UUID(business_id),
    )


# ============================================
# CLIENT
# ============================================

async def create_test_client(db, business_id: str, first_name: str = "Test") -> str:
    cid = uuid.uuid4()
    await db.pool.execute(
        """
        INSERT INTO cleaning_clients (
            id, business_id, first_name, last_name,
            address_line1, city, state, zip_code,
            created_at, updated_at
        ) VALUES ($1, $2, $3, 'Client',
                  '123 Test St', 'NYC', 'NY', '10001',
                  NOW(), NOW())
        """,
        cid, uuid.UUID(business_id), first_name,
    )
    return str(cid)


# ============================================
# SERVICE
# ============================================

async def create_test_service(
    db,
    business_id: str,
    name: str = "Basic 2BR/1BA",
    tier: str = "basic",
    bedrooms: int = 2,
    bathrooms: int = 1,
) -> str:
    sid = uuid.uuid4()
    await db.pool.execute(
        """
        INSERT INTO cleaning_services (
            id, business_id, name, tier, bedrooms, bathrooms,
            is_active, created_at, updated_at
        ) VALUES ($1, $2, $3, $4, $5, $6, TRUE, NOW(), NOW())
        """,
        sid, uuid.UUID(business_id), name, tier, bedrooms, bathrooms,
    )
    return str(sid)


# ============================================
# FREQUENCY / EXTRA LOOKUPS
# ============================================

async def get_frequency_id(db, business_id: str, name: str) -> str:
    row = await db.pool.fetchrow(
        "SELECT id FROM cleaning_frequencies WHERE business_id = $1 AND name = $2",
        uuid.UUID(business_id), name,
    )
    if not row:
        raise ValueError(f"Frequency '{name}' not found for business {business_id}")
    return str(row["id"])


async def get_default_location_id(db, business_id: str) -> str:
    row = await db.pool.fetchrow(
        """
        SELECT id FROM cleaning_areas
        WHERE business_id = $1 AND is_default = TRUE AND is_archived = FALSE
        """,
        uuid.UUID(business_id),
    )
    if not row:
        raise ValueError(f"No default area for business {business_id}")
    return str(row["id"])


async def create_test_extra(
    db, business_id: str, name: str = "Stairs", price: str = "30.00",
) -> str:
    eid = uuid.uuid4()
    await db.pool.execute(
        """
        INSERT INTO cleaning_extras (
            id, business_id, name, price, is_active, sort_order, created_at
        ) VALUES ($1, $2, $3, $4, TRUE, 0, NOW())
        """,
        eid, uuid.UUID(business_id), name, Decimal(price),
    )
    return str(eid)


# ============================================
# SCHEDULE
# ============================================

async def create_schedule(
    db,
    business_id: str,
    client_id: str,
    service_id: str,
    frequency: str = "weekly",
    frequency_id: str | None = None,
    preferred_day_of_week: int = 1,  # Monday in DB convention (0=Sunday)
    next_occurrence: date_cls | None = None,
    adjustment_amount: str = "0",
    adjustment_reason: str | None = None,
    location_id: str | None = None,
    agreed_price: str = "100.00",
    estimated_duration_minutes: int = 120,
    status: str = "active",
    created_at: date_cls | None = None,
) -> str:
    """
    Create recurring schedule with pricing inputs.
    Auto-fills frequency_id from name if not supplied (Sprint D Track A pattern).
    """
    sid = uuid.uuid4()
    if frequency_id is None:
        # Convert 'weekly' → 'Weekly' matching for lookup
        freq_title = frequency.title() if frequency != "sporadic" else None
        if freq_title:
            try:
                frequency_id = await get_frequency_id(db, business_id, freq_title)
            except ValueError:
                frequency_id = None

    if location_id is None:
        try:
            location_id = await get_default_location_id(db, business_id)
        except ValueError:
            location_id = None

    if next_occurrence is None:
        next_occurrence = date_cls.today()

    from datetime import datetime as _dt
    created_ts = _dt.combine(created_at or next_occurrence, time(0, 0))

    await db.pool.execute(
        """
        INSERT INTO cleaning_client_schedules (
            id, business_id, client_id, service_id,
            frequency, preferred_day_of_week, preferred_time_start,
            agreed_price, estimated_duration_minutes, min_team_size,
            next_occurrence, status,
            frequency_id, adjustment_amount, adjustment_reason, location_id,
            created_at, updated_at
        ) VALUES ($1, $2, $3, $4,
                  $5, $6, '09:00',
                  $7, $8, 1,
                  $9, $10,
                  $11, $12, $13, $14,
                  $15, NOW())
        """,
        sid, uuid.UUID(business_id), uuid.UUID(client_id), uuid.UUID(service_id),
        frequency, preferred_day_of_week,
        Decimal(agreed_price), estimated_duration_minutes,
        next_occurrence, status,
        uuid.UUID(frequency_id) if frequency_id else None,
        Decimal(adjustment_amount),
        adjustment_reason,
        uuid.UUID(location_id) if location_id else None,
        created_ts,
    )
    return str(sid)


async def add_schedule_extra(
    db, schedule_id: str, extra_id: str, qty: int = 1,
) -> None:
    await db.pool.execute(
        """
        INSERT INTO cleaning_client_schedule_extras (schedule_id, extra_id, qty)
        VALUES ($1, $2, $3)
        """,
        uuid.UUID(schedule_id), uuid.UUID(extra_id), qty,
    )


async def add_schedule_skip(
    db, schedule_id: str, skip_date: date_cls, reason: str = "test skip",
) -> None:
    await db.pool.execute(
        """
        INSERT INTO cleaning_schedule_skips (schedule_id, skip_date, reason)
        VALUES ($1, $2, $3)
        """,
        uuid.UUID(schedule_id), skip_date, reason,
    )


# ============================================
# TEAM (minimal — required for daily_generator assignment)
# ============================================

async def create_test_team(
    db, business_id: str, name: str = "Test Team",
) -> dict[str, Any]:
    """Create team + 1 member + 1 assignment (active all week)."""
    tid = uuid.uuid4()
    await db.pool.execute(
        """
        INSERT INTO cleaning_teams (
            id, business_id, name, color, is_active, max_daily_jobs,
            created_at, updated_at
        ) VALUES ($1, $2, $3, '#4285F4', TRUE, 10, NOW(), NOW())
        """,
        tid, uuid.UUID(business_id), name,
    )

    mid = uuid.uuid4()
    await db.pool.execute(
        """
        INSERT INTO cleaning_team_members (
            id, business_id, first_name, last_name, status, created_at
        ) VALUES ($1, $2, 'Test', 'Member', 'active', NOW())
        """,
        mid, uuid.UUID(business_id),
    )

    await db.pool.execute(
        """
        INSERT INTO cleaning_team_assignments (
            team_id, member_id, effective_from, is_active
        ) VALUES ($1, $2, '2020-01-01', TRUE)
        """,
        tid, mid,
    )

    # Availability all days of week
    for dow in range(7):
        await db.pool.execute(
            """
            INSERT INTO cleaning_team_availability (
                team_member_id, business_id, day_of_week,
                start_time, end_time, is_available, effective_from
            ) VALUES ($1, $2, $3, '08:00', '17:00', TRUE, '2020-01-01')
            """,
            mid, uuid.UUID(business_id), dow,
        )

    return {"team_id": str(tid), "member_id": str(mid)}
