"""
Seed script for Sprint 100% Xcleaners — synthetic demo data.

Populates the `owner.demo@xcleaners.app` business with realistic clients,
services, extras, bookings and job assignments so Oracle can run the
exhaustive smoke suite across all 5 portals.

Guarantees:
    - Idempotent: second run = no new rows (uuid5 deterministic + ON CONFLICT)
    - Reversible: `--revert` flag deletes exactly what this script inserted
    - Atomic: everything commits or everything rolls back (single transaction)
    - Cross-tenant safe: every INSERT/WHERE filters by business_id
    - Zero-touch: never calls pricing_engine / booking_service / recurring_generator

Usage:
    python scripts/seed_sprint100_demo.py            # seed
    python scripts/seed_sprint100_demo.py --revert   # undo

Requires:
    - Migrations 011..023 applied
    - DATABASE_URL or XCLEANERS_DATABASE_URL env var set
    - asyncpg installed
"""

import argparse
import asyncio
import json
import os
import sys
import uuid
from datetime import date, time, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncpg

DATABASE_URL = os.getenv("XCLEANERS_DATABASE_URL", os.getenv("DATABASE_URL"))

OWNER_EMAIL = "owner.demo@xcleaners.app"
TEAMLEAD_EMAIL = "teamlead.demo@xcleaners.app"
CLEANER_EMAIL = "cleaner.demo@xcleaners.app"
TEAM_A_ID = uuid.UUID("5cc614f9-be6b-4eb5-aecd-c8c3c3230537")

SEED_NS = uuid.NAMESPACE_DNS
SEED_MARKER = "sprint100_seed"


def ns(label: str) -> uuid.UUID:
    return uuid.uuid5(SEED_NS, f"sprint100.{label}")


# ── Static catalogs ──────────────────────────────────────────────

CLIENTS = [
    ("Sarah",    "Mitchell",   "sarah.mitchell@example.com",    "+1-718-555-0101", "412 Atlantic Ave",        "Brooklyn",  "NY", "11201", "apartment",  2, 1.5, 900),
    ("James",    "Chen",       "james.chen@example.com",        "+1-347-555-0102", "88 Bedford Ave",          "Brooklyn",  "NY", "11211", "apartment",  1, 1.0, 650),
    ("Olivia",   "Rodriguez",  "olivia.r@example.com",          "+1-646-555-0103", "230 W 15th St 4B",        "New York",  "NY", "10011", "condo",      2, 2.0, 1100),
    ("Daniel",   "Park",       "daniel.park@example.com",       "+1-718-555-0104", "55 Prospect Park W",      "Brooklyn",  "NY", "11215", "house",      3, 2.5, 1800),
    ("Emma",     "Walker",     "emma.walker@example.com",       "+1-347-555-0105", "17 Irving Pl",            "New York",  "NY", "10003", "townhouse",  4, 3.0, 2400),
    ("Michael",  "Nguyen",     "michael.n@example.com",         "+1-646-555-0106", "301 Mott St",             "New York",  "NY", "10012", "condo",      1, 1.0, 550),
    ("Sophia",   "Patel",      "sophia.patel@example.com",      "+1-718-555-0107", "140 Bergen St",           "Brooklyn",  "NY", "11217", "apartment",  2, 1.5, 950),
    ("Jacob",    "Thompson",   "jacob.t@example.com",           "+1-347-555-0108", "50-15 44th Ave",          "Long Island City", "NY", "11101", "condo", 2, 2.0, 1200),
    ("Ava",      "Silva",      "ava.silva@example.com",         "+1-646-555-0109", "69 74th St",              "Jackson Heights", "NY", "11372", "house", 3, 2.0, 1600),
    ("William",  "Brown",      "will.brown@example.com",        "+1-718-555-0110", "256 E 14th St",           "New York",  "NY", "10003", "apartment",  1, 1.0, 700),
    ("Isabella", "Garcia",     "isabella.g@example.com",        "+1-347-555-0111", "1200 5th Ave",            "New York",  "NY", "10029", "condo",      3, 2.5, 1500),
    ("Ethan",    "Kim",        "ethan.kim@example.com",         "+1-646-555-0112", "87 Eastern Pkwy",         "Brooklyn",  "NY", "11238", "townhouse",  4, 2.5, 2000),
    ("Mia",      "Johnson",    "mia.johnson@example.com",       "+1-718-555-0113", "35-10 30th Ave",          "Astoria",   "NY", "11103", "apartment",  2, 1.0, 850),
    ("Lucas",    "Martinez",   "lucas.m@example.com",           "+1-347-555-0114", "560 Lincoln Pl",          "Brooklyn",  "NY", "11238", "house",      5, 3.0, 2800),
    ("Charlotte","Davis",      "charlotte.davis@example.com",   "+1-646-555-0115", "444 W 37th St",           "New York",  "NY", "10018", "condo",      2, 2.0, 1050),
]

SERVICES = [
    # (name, slug, description, category, base_price, tier, bedrooms, bathrooms, duration_min)
    ("Quick Tidy 1BR",         "s100-quick-tidy-1br",    "Light cleaning for 1-bedroom apartments", "residential", 85.00,  "basic",   1, 1, 90),
    ("Standard Clean 2BR",     "s100-standard-2br",      "Standard residential clean, 2BR/1.5BA",   "residential", 140.00, "basic",   2, 2, 120),
    ("Standard Clean 3BR",     "s100-standard-3br",      "Standard residential clean, 3BR/2BA",     "residential", 175.00, "basic",   3, 2, 150),
    ("Deep Clean 2BR",         "s100-deep-2br",          "Deep clean incl. baseboards, inside appliances", "residential", 220.00, "deep", 2, 2, 180),
    ("Deep Clean 3BR",         "s100-deep-3br",          "Deep clean, 3BR/2.5BA",                   "residential", 265.00, "deep",    3, 3, 210),
    ("Premium Move-In 2BR",    "s100-premium-movein-2br","Move-in/out premium clean",              "residential", 260.00, "premium", 2, 2, 210),
    ("Premium Move-Out 3BR",   "s100-premium-moveout-3br","Move-out premium clean 3BR",            "residential", 320.00, "premium", 3, 3, 240),
    ("Studio Express",         "s100-studio-express",    "Fast clean for studios",                  "residential", 80.00,  "basic",   0, 1, 75),
]

EXTRAS = [
    ("[S100] Inside Fridge",   25.00, 10),
    ("[S100] Inside Oven",     30.00, 20),
    ("[S100] Inside Cabinets", 40.00, 30),
    ("[S100] Laundry Load",    20.00, 40),
]


# ── Deterministic IDs ────────────────────────────────────────────

CLIENT_IDS  = [ns(f"client.{i}")  for i in range(len(CLIENTS))]
SERVICE_IDS = [ns(f"service.{i}") for i in range(len(SERVICES))]
EXTRA_IDS   = [ns(f"extra.{i}")   for i in range(len(EXTRAS))]
BOOKING_IDS = [ns(f"booking.{i}") for i in range(30)]
TM_TEAMLEAD_ID = ns("tm.teamlead")
TM_CLEANER_ID  = ns("tm.cleaner")
LOCATION_ID    = ns("location.default")


# ── Business + users lookup ──────────────────────────────────────

async def resolve_business_id(conn) -> uuid.UUID:
    row = await conn.fetchrow(
        """
        SELECT ur.business_id
        FROM cleaning_user_roles ur
        JOIN users u ON u.id = ur.user_id
        WHERE u.email = $1
          AND ur.role = 'owner'
          AND ur.is_active = TRUE
        LIMIT 1
        """,
        OWNER_EMAIL,
    )
    if not row:
        raise RuntimeError(f"Business for {OWNER_EMAIL} not found — aborting.")
    return row["business_id"]


async def resolve_user_id(conn, email: str) -> uuid.UUID | None:
    return await conn.fetchval("SELECT id FROM users WHERE email = $1", email)


# ── Seed helpers ─────────────────────────────────────────────────

async def ensure_default_location(conn, business_id: uuid.UUID) -> uuid.UUID:
    existing = await conn.fetchval(
        "SELECT id FROM cleaning_areas WHERE business_id = $1 AND is_default = TRUE AND is_archived = FALSE LIMIT 1",
        business_id,
    )
    if existing:
        return existing

    await conn.execute(
        """
        INSERT INTO cleaning_areas (id, business_id, name, zip_codes, city, state, is_active, priority, is_default)
        VALUES ($1, $2, 'NYC Metro (seed default)', ARRAY['11201','11215','10003','10011','11101']::text[], 'New York', 'NY', TRUE, 1, TRUE)
        ON CONFLICT (id) DO NOTHING
        """,
        LOCATION_ID, business_id,
    )
    return LOCATION_ID


async def ensure_team_members(conn, business_id: uuid.UUID) -> tuple[uuid.UUID, uuid.UUID]:
    """Return (teamlead_tm_id, cleaner_tm_id). Reuse existing if user_id linked, else create."""
    teamlead_uid = await resolve_user_id(conn, TEAMLEAD_EMAIL)
    cleaner_uid  = await resolve_user_id(conn, CLEANER_EMAIL)
    if not teamlead_uid or not cleaner_uid:
        raise RuntimeError("teamlead.demo or cleaner.demo user missing — aborting.")

    # Try to find existing team_members linked to these users
    existing_lead = await conn.fetchval(
        "SELECT id FROM cleaning_team_members WHERE business_id = $1 AND user_id = $2 LIMIT 1",
        business_id, teamlead_uid,
    )
    existing_cleaner = await conn.fetchval(
        "SELECT id FROM cleaning_team_members WHERE business_id = $1 AND user_id = $2 LIMIT 1",
        business_id, cleaner_uid,
    )

    lead_id = existing_lead or TM_TEAMLEAD_ID
    cln_id  = existing_cleaner or TM_CLEANER_ID

    if not existing_lead:
        await conn.execute(
            """
            INSERT INTO cleaning_team_members
                (id, business_id, user_id, first_name, last_name, email, role, employment_type,
                 color, status, max_daily_hours, wage_pct)
            VALUES ($1, $2, $3, 'Team', 'Lead', $4, 'lead_cleaner', 'employee',
                    '#1A73E8', 'active', 8.0, 60.00)
            ON CONFLICT (id) DO NOTHING
            """,
            lead_id, business_id, teamlead_uid, TEAMLEAD_EMAIL,
        )

    if not existing_cleaner:
        await conn.execute(
            """
            INSERT INTO cleaning_team_members
                (id, business_id, user_id, first_name, last_name, email, role, employment_type,
                 color, status, max_daily_hours, wage_pct)
            VALUES ($1, $2, $3, 'Demo', 'Cleaner', $4, 'cleaner', 'employee',
                    '#10B981', 'active', 8.0, 60.00)
            ON CONFLICT (id) DO NOTHING
            """,
            cln_id, business_id, cleaner_uid, CLEANER_EMAIL,
        )

    # Ensure membership in Team A (cleaning_teams_members junction — may or may not exist)
    # If the schema uses cleaning_team_members.cleaning_team_id column (per sprint fix 2026-04-17),
    # backfill would have set it. We avoid assumption — do a best-effort UPDATE if column exists.
    try:
        await conn.execute(
            "UPDATE cleaning_team_members SET cleaning_team_id = $1 WHERE id = ANY($2::uuid[]) AND (cleaning_team_id IS NULL OR cleaning_team_id <> $1)",
            TEAM_A_ID, [lead_id, cln_id],
        )
    except asyncpg.UndefinedColumnError:
        pass  # column not in this schema revision — skip silently

    return lead_id, cln_id


async def seed_clients(conn, business_id: uuid.UUID):
    inserted = 0
    for cid, row in zip(CLIENT_IDS, CLIENTS):
        first, last, email, phone, addr, city, state, zip_, ptype, br, ba, sqft = row
        res = await conn.execute(
            """
            INSERT INTO cleaning_clients
                (id, business_id, first_name, last_name, email, phone,
                 address_line1, city, state, zip_code, country,
                 property_type, bedrooms, bathrooms, square_feet,
                 source, status, notes)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,'US',$11,$12,$13,$14,'import','active','[sprint100_seed]')
            ON CONFLICT (id) DO NOTHING
            """,
            cid, business_id, first, last, email, phone, addr, city, state, zip_,
            ptype, br, ba, sqft,
        )
        if res.endswith("1"):
            inserted += 1
    print(f"  [OK] clients: {inserted} inserted / {len(CLIENTS) - inserted} skipped (already present)")


async def seed_services(conn, business_id: uuid.UUID):
    inserted = 0
    for sid, row in zip(SERVICE_IDS, SERVICES):
        name, slug, desc, category, base_price, tier, br, ba, duration = row
        res = await conn.execute(
            """
            INSERT INTO cleaning_services
                (id, business_id, name, slug, description, category,
                 base_price, price_unit, estimated_duration_minutes, min_team_size, sort_order, is_active,
                 tier, bedrooms, bathrooms)
            VALUES ($1,$2,$3,$4,$5,$6,$7,'flat',$8,1,$9,TRUE,$10,$11,$12)
            ON CONFLICT (id) DO NOTHING
            """,
            sid, business_id, name, slug, desc, category, base_price, duration,
            SERVICE_IDS.index(sid), tier, br, ba,
        )
        if res.endswith("1"):
            inserted += 1
    print(f"  [OK] services: {inserted} inserted / {len(SERVICES) - inserted} skipped")


async def seed_extras(conn, business_id: uuid.UUID):
    inserted = 0
    for eid, (name, price, sort_order) in zip(EXTRA_IDS, EXTRAS):
        res = await conn.execute(
            """
            INSERT INTO cleaning_extras (id, business_id, name, price, is_active, sort_order)
            VALUES ($1, $2, $3, $4, TRUE, $5)
            ON CONFLICT (id) DO NOTHING
            """,
            eid, business_id, name, price, sort_order,
        )
        if res.endswith("1"):
            inserted += 1
    print(f"  [OK] extras: {inserted} inserted / {len(EXTRAS) - inserted} skipped")


async def seed_service_extras_whitelist(conn):
    inserted = 0
    for sid in SERVICE_IDS:
        for eid in EXTRA_IDS:
            res = await conn.execute(
                "INSERT INTO cleaning_service_extras (service_id, extra_id) VALUES ($1, $2) ON CONFLICT DO NOTHING",
                sid, eid,
            )
            if res.endswith("1"):
                inserted += 1
    print(f"  [OK] service_extras whitelist: {inserted} inserted / {len(SERVICE_IDS)*len(EXTRA_IDS) - inserted} skipped")


def _build_price_snapshot(service_amount, extras_total, freq_discount_pct, tax_pct):
    subtotal = float(service_amount) + float(extras_total)
    discount = round(subtotal * (freq_discount_pct / 100.0), 2)
    taxable  = subtotal - discount
    tax      = round(taxable * (tax_pct / 100.0), 2)
    total    = round(taxable + tax, 2)
    return {
        "subtotal": round(subtotal, 2),
        "service_amount": round(float(service_amount), 2),
        "extras_total": round(float(extras_total), 2),
        "frequency_discount_pct": freq_discount_pct,
        "discount": discount,
        "adjustment": 0,
        "tax_pct": tax_pct,
        "tax": tax,
        "total": total,
        "breakdown_version": SEED_MARKER,
    }


async def seed_bookings(conn, business_id: uuid.UUID, location_id: uuid.UUID,
                        lead_id: uuid.UUID, cleaner_id: uuid.UUID):
    """
    30 bookings: 10 past completed, 10 future scheduled, 10 open today ±3.
    20 assigned (lead + cleaner); 10 unassigned (to exercise unassigned flows).
    """
    today = date.today()
    specs = []

    # 10 completed (past 30-90 days ago)
    for i in range(10):
        specs.append({
            "offset_days": -(30 + i * 5),
            "status": "completed",
            "start": time(9, 0),
            "assigned": True,
        })
    # 10 scheduled (future 7-30 days)
    for i in range(10):
        specs.append({
            "offset_days": 7 + i * 2,
            "status": "scheduled",
            "start": time(10 + (i % 4), 0),
            "assigned": True,
        })
    # 10 open around today (today-3 .. today+3).
    # 7 assigned+confirmed (exercises /today flow); 3 unassigned+draft (exercises unassigned flow).
    # No in_progress here — that status requires lead + actual_start (covered by "completed" specs above).
    for i in range(10):
        offset = (i % 7) - 3  # evenly distributed -3..+3
        assigned = i < 7
        specs.append({
            "offset_days": offset,
            "status": "confirmed" if assigned else "draft",
            "start": time(11 + (i % 5), 30),
            "assigned": assigned,
        })

    inserted = 0
    for idx, (bid, spec) in enumerate(zip(BOOKING_IDS, specs)):
        client_idx  = idx % len(CLIENTS)
        service_idx = idx % len(SERVICES)
        service     = SERVICES[service_idx]
        client      = CLIENTS[client_idx]
        base_price  = service[4]
        extras_total = 25.00 if idx % 3 == 0 else 0.00  # some bookings have 1 extra
        freq_disc   = 10.0 if idx % 4 == 0 else 0.0
        tax_pct     = 4.5
        snap = _build_price_snapshot(base_price, extras_total, freq_disc, tax_pct)

        sched_date = today + timedelta(days=spec["offset_days"])
        assigned_team = json.dumps([str(lead_id), str(cleaner_id)]) if spec["assigned"] else "[]"
        lead_for_row  = lead_id if spec["assigned"] else None
        actual_start  = None
        actual_end    = None
        if spec["status"] == "completed":
            actual_start = f"{sched_date.isoformat()} {spec['start'].isoformat()}+00"
            # approximate end = start + duration
            end_hour = min(spec["start"].hour + 2, 23)
            actual_end = f"{sched_date.isoformat()} {end_hour:02d}:00:00+00"

        res = await conn.execute(
            """
            INSERT INTO cleaning_bookings
                (id, business_id, client_id, service_id,
                 scheduled_date, scheduled_start, estimated_duration_minutes,
                 address_line1, city, state, zip_code,
                 assigned_team, lead_cleaner_id,
                 quoted_price, final_price, tax_amount, adjustment_amount,
                 price_snapshot, location_id,
                 status, source, special_instructions,
                 actual_start, actual_end)
            VALUES
                ($1,$2,$3,$4,
                 $5,$6,$7,
                 $8,$9,$10,$11,
                 $12::jsonb,$13,
                 $14,$15,$16,0,
                 $17::jsonb,$18,
                 $19,'manual','[sprint100_seed]',
                 $20::timestamptz,$21::timestamptz)
            ON CONFLICT (id) DO NOTHING
            """,
            bid, business_id, CLIENT_IDS[client_idx], SERVICE_IDS[service_idx],
            sched_date, spec["start"], service[8],
            client[4], client[5], client[6], client[7],
            assigned_team, lead_for_row,
            snap["total"], snap["total"], snap["tax"],
            json.dumps(snap), location_id,
            spec["status"],
            actual_start, actual_end,
        )
        if res.endswith("1"):
            inserted += 1
    print(f"  [OK] bookings: {inserted} inserted / {len(BOOKING_IDS) - inserted} skipped")


# ── Counts ──────────────────────────────────────────────────────

async def show_counts(conn, business_id: uuid.UUID):
    clients_n  = await conn.fetchval("SELECT COUNT(*) FROM cleaning_clients WHERE business_id=$1 AND id=ANY($2)", business_id, CLIENT_IDS)
    services_n = await conn.fetchval("SELECT COUNT(*) FROM cleaning_services WHERE business_id=$1 AND id=ANY($2)", business_id, SERVICE_IDS)
    extras_n   = await conn.fetchval("SELECT COUNT(*) FROM cleaning_extras WHERE business_id=$1 AND id=ANY($2)", business_id, EXTRA_IDS)
    bookings_n = await conn.fetchval("SELECT COUNT(*) FROM cleaning_bookings WHERE business_id=$1 AND id=ANY($2)", business_id, BOOKING_IDS)
    assigned_n = await conn.fetchval(
        "SELECT COUNT(*) FROM cleaning_bookings WHERE business_id=$1 AND id=ANY($2) AND lead_cleaner_id IS NOT NULL",
        business_id, BOOKING_IDS,
    )
    print(f"  Counts — clients:{clients_n} services:{services_n} extras:{extras_n} bookings:{bookings_n} (assigned:{assigned_n})")


# ── Revert ──────────────────────────────────────────────────────

async def revert(conn, business_id: uuid.UUID):
    print("\n[REVERT] Deleting seeded rows (ordered by FK)...")
    # Bookings cascade to cleaning_booking_extras automatically
    n = await conn.execute("DELETE FROM cleaning_bookings WHERE business_id=$1 AND id=ANY($2)", business_id, BOOKING_IDS)
    print(f"  bookings deleted: {n}")
    n = await conn.execute("DELETE FROM cleaning_service_extras WHERE service_id=ANY($1) AND extra_id=ANY($2)", SERVICE_IDS, EXTRA_IDS)
    print(f"  service_extras deleted: {n}")
    n = await conn.execute("DELETE FROM cleaning_extras WHERE business_id=$1 AND id=ANY($2)", business_id, EXTRA_IDS)
    print(f"  extras deleted: {n}")
    n = await conn.execute("DELETE FROM cleaning_services WHERE business_id=$1 AND id=ANY($2)", business_id, SERVICE_IDS)
    print(f"  services deleted: {n}")
    n = await conn.execute("DELETE FROM cleaning_clients WHERE business_id=$1 AND id=ANY($2)", business_id, CLIENT_IDS)
    print(f"  clients deleted: {n}")
    # Team members only delete if they match the deterministic IDs (we don't touch pre-existing ones)
    n = await conn.execute("DELETE FROM cleaning_team_members WHERE business_id=$1 AND id=ANY($2::uuid[])", business_id, [TM_TEAMLEAD_ID, TM_CLEANER_ID])
    print(f"  team_members (seed-owned only) deleted: {n}")
    n = await conn.execute("DELETE FROM cleaning_areas WHERE business_id=$1 AND id=$2", business_id, LOCATION_ID)
    print(f"  location (seed-owned only) deleted: {n}")


# ── Main ────────────────────────────────────────────────────────

async def main():
    parser = argparse.ArgumentParser(description="Sprint 100% synthetic seed for Xcleaners")
    parser.add_argument("--revert", action="store_true", help="Undo the seed instead of applying it")
    args = parser.parse_args()

    if not DATABASE_URL:
        print("[ERROR] DATABASE_URL or XCLEANERS_DATABASE_URL not set.")
        sys.exit(1)

    print("=" * 68)
    print(f"Xcleaners — Sprint 100% Seed ({'REVERT' if args.revert else 'APPLY'})")
    print("=" * 68)

    conn = await asyncpg.connect(DATABASE_URL, ssl="require")
    tx = conn.transaction()
    await tx.start()
    try:
        business_id = await resolve_business_id(conn)
        print(f"\n[0] business_id = {business_id}")

        if args.revert:
            await revert(conn, business_id)
            await tx.commit()
            print("\n[DONE] Revert committed.")
            return

        print("\n[1] Ensuring default location...")
        location_id = await ensure_default_location(conn, business_id)
        print(f"  location_id = {location_id}")

        print("\n[2] Ensuring team_members (teamlead + cleaner)...")
        lead_id, cleaner_id = await ensure_team_members(conn, business_id)
        print(f"  lead_id={lead_id}  cleaner_id={cleaner_id}")

        print("\n[3] Clients (15)...")
        await seed_clients(conn, business_id)

        print("\n[4] Services (8)...")
        await seed_services(conn, business_id)

        print("\n[5] Extras (4)...")
        await seed_extras(conn, business_id)

        print("\n[6] Service-extras whitelist (8 × 4 = 32)...")
        await seed_service_extras_whitelist(conn)

        print("\n[7] Bookings (30: 10 completed + 10 scheduled + 10 open)...")
        await seed_bookings(conn, business_id, location_id, lead_id, cleaner_id)

        print("\n[8] Final counts:")
        await show_counts(conn, business_id)

        await tx.commit()
        print("\n[DONE] Seed committed.")
    except Exception:
        await tx.rollback()
        print("\n[ERROR] Transaction rolled back.")
        raise
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
