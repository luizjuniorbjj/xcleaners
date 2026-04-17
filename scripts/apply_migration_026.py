"""
One-shot migration applier for 026_payment_status_add_processing.sql.

Usage:
  railway run --service Postgres python scripts/apply_migration_026.py
  (local dev) DATABASE_URL=postgresql://... DATABASE_PUBLIC_URL= python scripts/apply_migration_026.py

Reads DATABASE_PUBLIC_URL (preferred) or DATABASE_URL from env.
Applies the migration via asyncpg, verifies CHECK constraint now includes 'processing'.
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import asyncpg


MIGRATION_FILE = Path(__file__).parent.parent / "database/migrations/026_payment_status_add_processing.sql"


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
        print("\n[1/3] Pre-migration state (existing constraint def)")
        pre = await conn.fetchval(
            """
            SELECT pg_get_constraintdef(oid)
              FROM pg_constraint
             WHERE conname = 'cleaning_bookings_payment_status_check'
            """
        )
        print(f"  before: {pre}")

        print("\n[2/3] Applying migration 026")
        await conn.execute(sql)
        print("  Migration applied successfully.")

        if notices:
            print("\n  NOTICE messages:")
            for n in notices:
                print(f"    {n}")

        print("\n[3/3] Post-migration verification")

        post = await conn.fetchrow(
            """
            SELECT conname, pg_get_constraintdef(oid) AS def, convalidated
              FROM pg_constraint
             WHERE conname = 'cleaning_bookings_payment_status_check'
            """
        )
        if not post:
            print("  FAIL: CHECK constraint missing after migration")
            return 3
        print(f"  constraint: {post['conname']}")
        print(f"    def: {post['def']}")
        print(f"    validated: {post['convalidated']}")

        if "'processing'" not in post["def"]:
            print("  FAIL: 'processing' not present in CHECK")
            return 4

        # State of rows (all should be NULL or valid value)
        total = await conn.fetchval("SELECT COUNT(*) FROM cleaning_bookings")
        null_status = await conn.fetchval(
            "SELECT COUNT(*) FROM cleaning_bookings WHERE payment_status IS NULL"
        )
        print(f"  bookings total: {total} / with NULL payment_status: {null_status}")

        print("\nMigration 026 applied successfully.")
        return 0

    finally:
        await conn.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
