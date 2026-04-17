"""
One-shot migration applier for 025_booking_payment_tracking.sql.

Usage:
  railway run --service Postgres python scripts/apply_migration_025.py
  (local dev) DATABASE_URL=postgresql://... DATABASE_PUBLIC_URL= python scripts/apply_migration_025.py

Reads DATABASE_PUBLIC_URL (preferred) or DATABASE_URL from env.
Applies the migration via asyncpg, captures NOTICE messages, verifies
both columns exist + partial indexes + CHECK constraint.
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import asyncpg


MIGRATION_FILE = Path(__file__).parent.parent / "database/migrations/025_booking_payment_tracking.sql"


async def main() -> int:
    db_url = os.environ.get("DATABASE_PUBLIC_URL") or os.environ.get("DATABASE_URL")
    if not db_url:
        print("ERROR: DATABASE_PUBLIC_URL/DATABASE_URL not set", file=sys.stderr)
        return 1

    using_public = "DATABASE_PUBLIC_URL" in os.environ and os.environ.get("DATABASE_PUBLIC_URL") == db_url
    print(f"Connecting via {'DATABASE_PUBLIC_URL' if using_public else 'DATABASE_URL'}")

    if not MIGRATION_FILE.exists():
        print(f"ERROR: migration file not found: {MIGRATION_FILE}", file=sys.stderr)
        return 2

    sql = MIGRATION_FILE.read_text(encoding="utf-8")
    print(f"Migration file: {MIGRATION_FILE}")
    print(f"SQL size: {len(sql)} chars")

    conn = await asyncpg.connect(db_url)

    notices: list[str] = []
    def _on_notice(con, msg):
        notices.append(str(msg))
    conn.add_log_listener(_on_notice)

    try:
        print("\n[1/3] Checking pre-migration state")
        pre_cols = await conn.fetch(
            """
            SELECT column_name FROM information_schema.columns
             WHERE table_name = 'cleaning_bookings'
               AND column_name IN ('stripe_payment_intent_id', 'payment_status')
            """
        )
        existing = sorted(c["column_name"] for c in pre_cols)
        print(f"  existing target cols: {existing or 'none'}")

        print("\n[2/3] Applying migration 025")
        await conn.execute(sql)
        print("  Migration applied successfully.")

        if notices:
            print("\n  NOTICE messages:")
            for n in notices:
                print(f"    {n}")

        print("\n[3/3] Post-migration verification")

        # Both columns exist
        cols = await conn.fetch(
            """
            SELECT column_name, data_type, is_nullable
              FROM information_schema.columns
             WHERE table_name = 'cleaning_bookings'
               AND column_name IN ('stripe_payment_intent_id', 'payment_status')
             ORDER BY column_name
            """
        )
        cols_by_name = {c["column_name"]: c for c in cols}
        for required in ("stripe_payment_intent_id", "payment_status"):
            if required not in cols_by_name:
                print(f"  FAIL: column {required} not found")
                return 3
            c = cols_by_name[required]
            print(f"  column: {c['column_name']} ({c['data_type']}, nullable={c['is_nullable']})")

        # Both partial indexes exist
        idx_rows = await conn.fetch(
            """
            SELECT indexname, indexdef
              FROM pg_indexes
             WHERE tablename = 'cleaning_bookings'
               AND indexname IN (
                 'idx_cleaning_bookings_stripe_payment_intent_id',
                 'idx_cleaning_bookings_payment_status'
               )
             ORDER BY indexname
            """
        )
        if len(idx_rows) != 2:
            print(f"  FAIL: expected 2 indexes, found {len(idx_rows)}")
            return 4
        for r in idx_rows:
            print(f"  index: {r['indexname']}")

        # CHECK constraint present
        constraint = await conn.fetchrow(
            """
            SELECT conname, pg_get_constraintdef(oid) AS def
              FROM pg_constraint
             WHERE conname = 'cleaning_bookings_payment_status_check'
            """
        )
        if not constraint:
            print("  FAIL: CHECK constraint missing")
            return 5
        print(f"  constraint: {constraint['conname']}")
        print(f"    def: {constraint['def']}")

        # Total bookings (all should be NULL for new cols)
        total = await conn.fetchval("SELECT COUNT(*) FROM cleaning_bookings")
        with_pi = await conn.fetchval(
            "SELECT COUNT(*) FROM cleaning_bookings WHERE stripe_payment_intent_id IS NOT NULL"
        )
        with_ps = await conn.fetchval(
            "SELECT COUNT(*) FROM cleaning_bookings WHERE payment_status IS NOT NULL"
        )
        print(f"  bookings total: {total} / with payment_intent: {with_pi} / with payment_status: {with_ps}")
        print(f"  (expected 0/0 since columns are new)")

        print("\nMigration 025 applied successfully.")
        return 0

    finally:
        await conn.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
