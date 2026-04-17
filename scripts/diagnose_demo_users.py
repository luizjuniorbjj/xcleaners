"""
Xcleaners — Demo Users DB Diagnostic (Sprint Fix 2026-04-17).

READ-ONLY script that dumps the real state of the 5 demo users and related
seed data (cleaning_user_roles, cleaning_teams, users schema) so we can
confirm Smith's hypothesis: the 403s on /my-jobs/today etc. come from a
NULL team_id in cleaning_user_roles, not an RBAC code bug.

Usage:
    railway run --service cleanclaw-api python scripts/diagnose_demo_users.py

Reads DATABASE_URL from env (injected by railway run).
No UPDATE/DELETE — strictly SELECT.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import uuid
from datetime import date, datetime
from decimal import Decimal

import asyncpg


DEMO_EMAILS = [
    "admin@xcleaners.app",
    "owner.demo@xcleaners.app",
    "teamlead.demo@xcleaners.app",
    "cleaner.demo@xcleaners.app",
    "homeowner.demo@xcleaners.app",
]


def _coerce(value):
    """Make asyncpg rows JSON-serialisable."""
    if isinstance(value, (uuid.UUID,)):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    return value


def _rows_to_list(rows):
    return [{k: _coerce(v) for k, v in dict(r).items()} for r in rows]


async def _run(conn, label: str, sql: str, *args):
    """Run a SELECT and return {rows, error?}."""
    try:
        rows = await conn.fetch(sql, *args)
        return {"rows": _rows_to_list(rows), "count": len(rows)}
    except Exception as exc:
        return {"error": f"{type(exc).__name__}: {exc}", "sql": sql.strip()[:240]}


async def main() -> int:
    # Prefer public URL (works from laptop). Fallback to internal URL (works from Railway pod).
    db_url = os.environ.get("DATABASE_PUBLIC_URL") or os.environ.get("DATABASE_URL")
    if not db_url:
        print(
            "ERROR: Neither DATABASE_PUBLIC_URL nor DATABASE_URL set. "
            "Run via `railway run --service Postgres python scripts/diagnose_demo_users.py`.",
            file=sys.stderr,
        )
        return 1

    conn = await asyncpg.connect(db_url)
    try:
        result: dict = {}

        # Q1 — Users demo existem? (usa as duas variantes de coluna de nome)
        result["Q1_users_demo"] = await _run(
            conn,
            "Q1",
            """
            SELECT id, email, role, created_at,
                   to_jsonb(u) - 'senha_hash' - 'password' - 'password_hash' AS full_row
            FROM users u
            WHERE email = ANY($1::text[])
            ORDER BY email
            """,
            DEMO_EMAILS,
        )

        # Q2 — cleaning_user_roles dos demo users (o coração do diagnóstico)
        result["Q2_cleaning_user_roles"] = await _run(
            conn,
            "Q2",
            """
            SELECT u.email,
                   cur.id AS role_id,
                   cur.business_id,
                   cur.role AS cleaning_role,
                   cur.team_id,
                   cur.is_active,
                   cur.created_at,
                   ct.name AS team_name,
                   b.slug AS business_slug
            FROM cleaning_user_roles cur
            JOIN users u         ON u.id = cur.user_id
            LEFT JOIN cleaning_teams ct ON ct.id = cur.team_id
            LEFT JOIN businesses b     ON b.id = cur.business_id
            WHERE u.email = ANY($1::text[])
            ORDER BY u.email, cur.role
            """,
            DEMO_EMAILS,
        )

        # Q3 — Teams disponíveis no business xcleaners-demo
        result["Q3_teams_xcleaners_demo"] = await _run(
            conn,
            "Q3",
            """
            SELECT ct.id AS team_id, ct.name, ct.business_id, b.slug, ct.is_active,
                   ct.created_at
            FROM cleaning_teams ct
            JOIN businesses b ON b.id = ct.business_id
            WHERE b.slug = 'xcleaners-demo'
            ORDER BY ct.created_at, ct.name
            """,
        )

        # Q4 — Business xcleaners-demo info
        result["Q4_business_xcleaners_demo"] = await _run(
            conn,
            "Q4",
            """
            SELECT id, slug, name, status, created_at
            FROM businesses
            WHERE slug = 'xcleaners-demo'
            """,
        )

        # Q5 — Colunas candidatas a "nome" na tabela users (investigar /me 500)
        result["Q5_users_name_columns"] = await _run(
            conn,
            "Q5",
            """
            SELECT column_name, data_type, is_nullable
            FROM information_schema.columns
            WHERE table_name = 'users'
              AND column_name IN ('nome', 'name', 'full_name', 'display_name', 'first_name', 'last_name')
            ORDER BY column_name
            """,
        )

        # Q6 — Schema completo de cleaning_user_roles (confirmar colunas)
        result["Q6_cleaning_user_roles_schema"] = await _run(
            conn,
            "Q6",
            """
            SELECT column_name, data_type, is_nullable, column_default
            FROM information_schema.columns
            WHERE table_name = 'cleaning_user_roles'
            ORDER BY ordinal_position
            """,
        )

        # Q7 — Contagem total de users no xcleaners-demo business (sanity)
        result["Q7_all_roles_in_xcleaners_demo"] = await _run(
            conn,
            "Q7",
            """
            SELECT cur.role, COUNT(*) AS n,
                   COUNT(cur.team_id) AS with_team,
                   COUNT(*) - COUNT(cur.team_id) AS without_team
            FROM cleaning_user_roles cur
            JOIN businesses b ON b.id = cur.business_id
            WHERE b.slug = 'xcleaners-demo'
            GROUP BY cur.role
            ORDER BY cur.role
            """,
        )

        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0
    finally:
        await conn.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
