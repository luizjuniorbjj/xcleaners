"""
One-shot migration applier for 022_recurring_pricing_inputs.sql.
Use via: railway run --service cleanclaw-api python scripts/apply_migration_022.py

Reads DATABASE_URL from env (injected by railway run).
Executes migration SQL via asyncpg, captures all NOTICE messages.
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import asyncpg


MIGRATION_FILE = Path(__file__).parent.parent / "database/migrations/022_recurring_pricing_inputs.sql"


async def main() -> int:
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        print("ERROR: DATABASE_URL not set", file=sys.stderr)
        return 1

    sql = MIGRATION_FILE.read_text(encoding="utf-8")
    print(f"Migration file: {MIGRATION_FILE}")
    print(f"SQL size: {len(sql)} chars")
    print(f"Connecting to DB...")

    conn = await asyncpg.connect(db_url)

    notices: list[str] = []
    def _on_notice(con, msg):
        notices.append(str(msg))

    conn.add_log_listener(_on_notice)

    try:
        print("Applying migration...")
        await conn.execute(sql)
        print("\n✅ Migration 022 applied successfully.")

        if notices:
            print("\n=== NOTICES captured ===")
            for n in notices:
                print(f"  {n}")

        # Validate post-migration state
        print("\n=== VALIDATION ===")
        freq_count = await conn.fetchval(
            "SELECT COUNT(*) FROM cleaning_client_schedules WHERE frequency_id IS NOT NULL"
        )
        total = await conn.fetchval("SELECT COUNT(*) FROM cleaning_client_schedules")
        print(f"  cleaning_client_schedules with frequency_id: {freq_count} / {total}")

        loc_count = await conn.fetchval(
            "SELECT COUNT(*) FROM cleaning_client_schedules WHERE location_id IS NOT NULL"
        )
        print(f"  cleaning_client_schedules with location_id: {loc_count} / {total}")

        new_tables = await conn.fetch(
            """
            SELECT tablename FROM pg_tables
            WHERE tablename IN ('cleaning_client_schedule_extras', 'cleaning_schedule_skips')
            ORDER BY tablename
            """
        )
        print(f"  New tables created: {[r['tablename'] for r in new_tables]}")

        return 0
    finally:
        await conn.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
