"""
Xcleaners — Backfill demo users team_id (Sprint Fix 2026-04-17).

Reversible UPDATE that assigns Team A to teamlead.demo and cleaner.demo.
Safe:
  - Runs inside a transaction
  - Aborts if affected rows != 2
  - Reversible via SET team_id = NULL WHERE same predicate

Usage:
    railway run --service Postgres python scripts/backfill_demo_team.py

No Redis invalidate needed: REDIS_URL in prod points to localhost (cache
is effectively disabled, so the next API call reads straight from DB).
"""

from __future__ import annotations

import asyncio
import os
import sys

import asyncpg


BUSINESS_ID = "ef4dcb08-4461-4e55-a593-76ae42295924"  # xcleaners-demo
TEAM_A_ID = "5cc614f9-be6b-4eb5-aecd-c8c3c3230537"
EXPECTED_ROWS = 2  # cleaner.demo + teamlead.demo


async def main() -> int:
    db_url = os.environ.get("DATABASE_PUBLIC_URL") or os.environ.get("DATABASE_URL")
    if not db_url:
        print("ERROR: need DATABASE_PUBLIC_URL or DATABASE_URL", file=sys.stderr)
        return 1

    conn = await asyncpg.connect(db_url)
    try:
        async with conn.transaction():
            # Preview state BEFORE
            before = await conn.fetch(
                """
                SELECT u.email, cur.role, cur.team_id
                FROM cleaning_user_roles cur
                JOIN users u ON u.id = cur.user_id
                WHERE cur.business_id = $1
                  AND cur.role IN ('cleaner', 'team_lead')
                ORDER BY cur.role
                """,
                BUSINESS_ID,
            )
            print("=== BEFORE ===")
            for row in before:
                print(f"  {row['email']} [{row['role']}] team_id={row['team_id']}")

            # Execute UPDATE
            result = await conn.execute(
                """
                UPDATE cleaning_user_roles
                SET team_id = $1
                WHERE business_id = $2
                  AND role IN ('cleaner', 'team_lead')
                  AND team_id IS NULL
                """,
                TEAM_A_ID,
                BUSINESS_ID,
            )
            # asyncpg returns 'UPDATE <rowcount>'
            affected = int(result.split()[-1])
            print(f"\nUPDATE affected {affected} rows (expected {EXPECTED_ROWS})")

            if affected != EXPECTED_ROWS:
                raise RuntimeError(
                    f"ABORT: expected {EXPECTED_ROWS} rows, got {affected}. "
                    "Transaction will rollback. Nothing was persisted."
                )

            # Preview AFTER (still inside tx)
            after = await conn.fetch(
                """
                SELECT u.email, cur.role, cur.team_id, ct.name AS team_name
                FROM cleaning_user_roles cur
                JOIN users u ON u.id = cur.user_id
                LEFT JOIN cleaning_teams ct ON ct.id = cur.team_id
                WHERE cur.business_id = $1
                  AND cur.role IN ('cleaner', 'team_lead')
                ORDER BY cur.role
                """,
                BUSINESS_ID,
            )
            print("\n=== AFTER ===")
            for row in after:
                print(
                    f"  {row['email']} [{row['role']}] "
                    f"team_id={row['team_id']} team_name={row['team_name']}"
                )

        print("\n✅ COMMIT OK — 2 rows updated. Rollback SQL:")
        print(
            f"  UPDATE cleaning_user_roles SET team_id = NULL "
            f"WHERE business_id = '{BUSINESS_ID}' "
            f"AND role IN ('cleaner', 'team_lead') "
            f"AND team_id = '{TEAM_A_ID}';"
        )
        return 0
    finally:
        await conn.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
