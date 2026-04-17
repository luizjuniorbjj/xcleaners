"""
One-shot migration applier for 024_client_stripe_customer.sql.

Usage:
  railway run --service Postgres python scripts/apply_migration_024.py

Reads DATABASE_PUBLIC_URL (preferred) or DATABASE_URL from env.
Applies the migration via asyncpg, captures NOTICE messages, verifies column exists.
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import asyncpg


MIGRATION_FILE = Path(__file__).parent.parent / "database/migrations/024_client_stripe_customer.sql"


async def main() -> int:
    db_url = os.environ.get("DATABASE_PUBLIC_URL") or os.environ.get("DATABASE_URL")
    if not db_url:
        print("ERROR: DATABASE_PUBLIC_URL/DATABASE_URL not set (use: railway run --service Postgres)", file=sys.stderr)
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
        pre = await conn.fetchval(
            """
            SELECT COUNT(*)
              FROM information_schema.columns
             WHERE table_name = 'cleaning_clients'
               AND column_name = 'stripe_customer_id'
            """
        )
        print(f"  stripe_customer_id existed before: {pre == 1}")

        print("\n[2/3] Applying migration 024")
        await conn.execute(sql)
        print("  Migration applied successfully.")

        if notices:
            print("\n  NOTICE messages:")
            for n in notices:
                print(f"    {n}")

        print("\n[3/3] Post-migration verification")

        # Column exists
        col = await conn.fetchrow(
            """
            SELECT column_name, data_type, is_nullable, column_default
              FROM information_schema.columns
             WHERE table_name = 'cleaning_clients'
               AND column_name = 'stripe_customer_id'
            """
        )
        if not col:
            print("  FAIL: stripe_customer_id column not found after migration")
            return 3
        print(f"  column: {col['column_name']} ({col['data_type']}, nullable={col['is_nullable']}, default={col['column_default']})")

        # Index exists
        idx = await conn.fetchrow(
            """
            SELECT indexname, indexdef
              FROM pg_indexes
             WHERE tablename = 'cleaning_clients'
               AND indexname = 'idx_cleaning_clients_stripe_customer_id'
            """
        )
        if not idx:
            print("  FAIL: partial index not created")
            return 4
        print(f"  index: {idx['indexname']}")
        print(f"    def: {idx['indexdef']}")

        # Comment exists
        comment = await conn.fetchval(
            """
            SELECT pg_catalog.col_description(c.oid, a.attnum)
              FROM pg_class c
              JOIN pg_attribute a ON a.attrelid = c.oid
             WHERE c.relname = 'cleaning_clients'
               AND a.attname = 'stripe_customer_id'
            """
        )
        print(f"  comment: {comment}")

        # Row count of NULL stripe_customer_id (expected = total clients)
        null_count = await conn.fetchval(
            "SELECT COUNT(*) FROM cleaning_clients WHERE stripe_customer_id IS NULL"
        )
        total = await conn.fetchval("SELECT COUNT(*) FROM cleaning_clients")
        print(f"  clients total: {total} / with NULL stripe_customer_id: {null_count} (expected equal)")

        print("\nMigration 024 applied successfully.")
        return 0

    finally:
        await conn.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
