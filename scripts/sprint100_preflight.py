"""
Sprint 100% Cleanup - Fase 0 PRE-FLIGHT (READ-ONLY)

Confirma UUIDs e contagens exatas antes de qualquer DELETE.
Zero mutacao. Safe para rodar multiplas vezes.

Uso: railway run --service cleanclaw-api python scripts/sprint100_preflight.py
"""

from __future__ import annotations

import asyncio
import os
import sys

import asyncpg


XCLEANERS_DEMO_SLUG = "xcleaners-demo"
REVALIDATE_BUSINESS_ID = "10271d87-85e1-40b8-8e87-8921cc3500b8"
REVALIDATE_USER_ID = "d9897899-ab37-4a4c-8952-07fb204a7a21"
REVALIDATE_TEAM_ID = "4b315d01-ab5f-48c4-b362-133caed81226"
REVALIDATE_CLIENT_ID = "8cc74525-7182-4615-b9d7-851f62f1431b"
REVALIDATE_USER_EMAIL = "revalidate-owner@s100revalidate.example"


async def main() -> int:
    db_url = os.environ.get("DATABASE_PUBLIC_URL") or os.environ.get("DATABASE_URL")
    if not db_url:
        print("ERROR: DATABASE_PUBLIC_URL/DATABASE_URL not set (use: railway run --service Postgres)", file=sys.stderr)
        return 1
    using_public = "DATABASE_PUBLIC_URL" in os.environ and os.environ.get("DATABASE_PUBLIC_URL") == db_url
    print(f"Connecting via {'DATABASE_PUBLIC_URL' if using_public else 'DATABASE_URL'}")

    conn = await asyncpg.connect(db_url)
    try:
        print("=" * 70)
        print("SPRINT 100% CLEANUP - FASE 0 PRE-FLIGHT (READ-ONLY)")
        print("=" * 70)

        # 0.1 xcleaners-demo UUID
        print("\n[0.1] xcleaners-demo business")
        demo = await conn.fetchrow(
            "SELECT id, slug, name FROM businesses WHERE slug = $1",
            XCLEANERS_DEMO_SLUG,
        )
        if not demo:
            print("  FATAL: xcleaners-demo not found!")
            return 2
        print(f"  id={demo['id']}  slug={demo['slug']}  name={demo['name']}")
        expected_demo_id = "ef4dcb08-4461-4e55-a593-76ae42295924"
        if str(demo["id"]) != expected_demo_id:
            print(f"  WARNING: id differs from assumed {expected_demo_id}")
            print("  -> Oracle SQL usa UUID hardcoded. Reajustar antes do DELETE.")
        demo_id = str(demo["id"])

        # 0.2 REVALIDATE business
        print("\n[0.2] REVALIDATE business (novo)")
        rev_biz = await conn.fetchrow(
            "SELECT id, slug, name, created_at FROM businesses WHERE id = $1",
            REVALIDATE_BUSINESS_ID,
        )
        if rev_biz:
            print(f"  id={rev_biz['id']}  slug={rev_biz['slug']}  name={rev_biz['name']}  created={rev_biz['created_at']}")
        else:
            print("  NAO ENCONTRADO (ja deletado?)")

        # 0.3 REVALIDATE user
        print("\n[0.3] REVALIDATE user (novo owner)")
        rev_user = await conn.fetchrow(
            "SELECT id, email, created_at FROM users WHERE id = $1",
            REVALIDATE_USER_ID,
        )
        if rev_user:
            print(f"  id={rev_user['id']}  email={rev_user['email']}  created={rev_user['created_at']}")
        else:
            print("  NAO ENCONTRADO (ja deletado?)")

        # 0.4 Contagens por tabela
        print("\n[0.4] Contagens por tabela (escopo exato do cleanup)")
        counts = {}
        counts["services"] = await conn.fetchval(
            "SELECT COUNT(*) FROM cleaning_services WHERE business_id = $1 AND name LIKE '[S100-MANUAL]%'",
            demo_id,
        )
        counts["extras"] = await conn.fetchval(
            "SELECT COUNT(*) FROM cleaning_extras WHERE business_id = $1 AND name LIKE '[S100%'",
            demo_id,
        )
        counts["teams"] = await conn.fetchval(
            "SELECT COUNT(*) FROM cleaning_teams WHERE business_id = $1 AND name LIKE '[S100-REVALIDATE]%'",
            demo_id,
        )
        counts["clients"] = await conn.fetchval(
            "SELECT COUNT(*) FROM cleaning_clients WHERE business_id = $1 AND (first_name LIKE '[S100%' OR last_name LIKE '[S100%')",
            demo_id,
        )
        counts["roles"] = await conn.fetchval(
            "SELECT COUNT(*) FROM cleaning_user_roles WHERE business_id = $1",
            REVALIDATE_BUSINESS_ID,
        )
        for k, v in counts.items():
            print(f"  {k}: {v}")

        # 0.5 FK: bookings (ZERO esperado)
        print("\n[0.5] FK bookings referenciando entidades alvo (ZERO esperado)")
        bookings_cnt = await conn.fetchval(
            """
            SELECT COUNT(*) FROM cleaning_bookings
             WHERE team_id = $1
                OR client_id = $2
                OR business_id = $3
            """,
            REVALIDATE_TEAM_ID,
            REVALIDATE_CLIENT_ID,
            REVALIDATE_BUSINESS_ID,
        )
        print(f"  bookings_affected: {bookings_cnt}")

        # 0.6 FK: team_members (ZERO esperado) - schema-agnostic
        print("\n[0.6] FK team_members para team REVALIDATE (ZERO esperado)")
        tm_cols = await conn.fetch(
            """
            SELECT column_name FROM information_schema.columns
             WHERE table_name = 'cleaning_team_members'
            """
        )
        tm_col_names = [c["column_name"] for c in tm_cols]
        if not tm_col_names:
            print("  tabela cleaning_team_members nao existe -> skip")
            tm_cnt = 0
        else:
            print(f"  schema cols: {tm_col_names}")
            fk_col = None
            for candidate in ("team_id", "cleaning_team_id", "teams_id"):
                if candidate in tm_col_names:
                    fk_col = candidate
                    break
            if not fk_col:
                print("  nenhuma coluna FK identificada -> skip check")
                tm_cnt = 0
            else:
                tm_cnt = await conn.fetchval(
                    f"SELECT COUNT(*) FROM cleaning_team_members WHERE {fk_col} = $1",
                    REVALIDATE_TEAM_ID,
                )
                print(f"  team_members_affected (via {fk_col}): {tm_cnt}")

        # 0.7 FK transitivo: booking_extras -> extras [S100-*]
        print("\n[0.7] FK transitivo booking_extras -> extras [S100-*] (ZERO esperado)")
        try:
            be_cnt = await conn.fetchval(
                """
                SELECT COUNT(*) FROM cleaning_booking_extras be
                  JOIN cleaning_extras e ON be.extra_id = e.id
                 WHERE e.business_id = $1 AND e.name LIKE '[S100%'
                """,
                demo_id,
            )
            print(f"  booking_extras_affected: {be_cnt}")
        except asyncpg.UndefinedTableError:
            print("  tabela cleaning_booking_extras nao existe -> OK (sem FK transitivo)")

        # 0.8 Roles do user em OUTROS businesses
        print("\n[0.8] Roles do user REVALIDATE em outros businesses (ZERO esperado)")
        other_roles = await conn.fetch(
            """
            SELECT r.business_id, b.slug, r.role
              FROM cleaning_user_roles r
              LEFT JOIN businesses b ON r.business_id = b.id
             WHERE r.user_id = $1
               AND r.business_id != $2
            """,
            REVALIDATE_USER_ID,
            REVALIDATE_BUSINESS_ID,
        )
        if other_roles:
            print(f"  WARNING: user tem {len(other_roles)} role(s) em outros businesses!")
            for r in other_roles:
                print(f"    business_id={r['business_id']}  slug={r['slug']}  role={r['role']}")
        else:
            print("  0 (user esta isolado ao business REVALIDATE)")

        # Summary GO/NO-GO
        print("\n" + "=" * 70)
        print("PRE-FLIGHT SUMMARY")
        print("=" * 70)
        total_target = sum(counts.values())
        print(f"  Total entities a deletar: {total_target}")
        print(f"  Business REVALIDATE: {'PRESENTE' if rev_biz else 'AUSENTE'}")
        print(f"  User REVALIDATE: {'PRESENTE' if rev_user else 'AUSENTE'}")
        print(f"  Bookings afetadas: {bookings_cnt} (esperado 0)")
        print(f"  Team_members afetados: {tm_cnt} (esperado 0)")
        print(f"  Outros roles do user: {len(other_roles)} (esperado 0)")

        expected = {"services": 1, "extras": 1, "teams": 1, "clients": 1, "roles": 1}
        mismatch = [k for k, v in expected.items() if counts.get(k, 0) != v]
        if mismatch:
            print(f"\n  GO/NO-GO: NO-GO - contagens divergentes em: {mismatch}")
            print("  REVISAR antes de executar Fase 1+2.")
            return 3
        if bookings_cnt > 0 or tm_cnt > 0 or len(other_roles) > 0:
            print("\n  GO/NO-GO: NO-GO - FK checks com linhas inesperadas")
            return 4
        if not rev_biz or not rev_user:
            print("\n  GO/NO-GO: parcial - business ou user ja ausente, ajustar Fase 2")
            return 5
        print("\n  GO/NO-GO: GO - todas as contagens batem, pode prosseguir com backup+DELETE")
        return 0

    finally:
        await conn.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
