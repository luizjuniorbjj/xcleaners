"""
One-shot migration applier for 027_client_invite_token.sql.

Usage:
  railway run --service Postgres python scripts/apply_migration_027.py
  (local) DATABASE_PUBLIC_URL=postgresql://... python scripts/apply_migration_027.py

Reads DATABASE_PUBLIC_URL (preferred) or DATABASE_URL from env.
Adds invite_token / invite_sent_at / invite_expires_at to cleaning_clients.
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import asyncpg


MIGRATION_FILE = Path(__file__).parent.parent / "database/migrations/027_client_invite_token.sql"


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
        print("\n[1/3] Pre-migration state (existing columns)")
        pre = await conn.fetch(
            """
            SELECT column_name, data_type
              FROM information_schema.columns
             WHERE table_name = 'cleaning_clients'
               AND column_name IN ('invite_token', 'invite_sent_at', 'invite_expires_at')
            """
        )
        print(f"  before: {[dict(r) for r in pre]}")

        print("\n[2/3] Applying migration 027")
        await conn.execute(sql)
        print("  Migration applied successfully.")

        if notices:
            print("\n  NOTICE messages:")
            for n in notices:
                print(f"    {n}")

        print("\n[3/3] Post-migration verification")
        post = await conn.fetch(
            """
            SELECT column_name, data_type, is_nullable
              FROM information_schema.columns
             WHERE table_name = 'cleaning_clients'
               AND column_name IN ('invite_token', 'invite_sent_at', 'invite_expires_at')
             ORDER BY column_name
            """
        )
        rows = [dict(r) for r in post]
        print(f"  after: {rows}")
        if len(rows) != 3:
            print("  FAIL: expected 3 new columns")
            return 3

        idx_ok = await conn.fetchval(
            "SELECT 1 FROM pg_indexes WHERE indexname = 'idx_cleaning_clients_invite_token'"
        )
        print(f"  partial unique index present: {bool(idx_ok)}")
        if not idx_ok:
            print("  FAIL: index missing")
            return 4

        print("\nMigration 027 applied successfully.")
        return 0

    finally:
        await conn.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
