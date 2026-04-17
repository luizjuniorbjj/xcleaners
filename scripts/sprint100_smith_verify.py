"""
Smith adversarial verify - ESTADO POS-CLEANUP em prod.

Valida que Tank nao vazou DELETE alem do escopo declarado.
READ-ONLY. Zero mutacao.

Uso: railway run --service Postgres python scripts/sprint100_smith_verify.py
"""

from __future__ import annotations

import asyncio
import os
import sys

import asyncpg


XCLEANERS_DEMO_ID = "ef4dcb08-4461-4e55-a593-76ae42295924"
REVALIDATE_BUSINESS_ID = "10271d87-85e1-40b8-8e87-8921cc3500b8"
REVALIDATE_USER_ID = "d9897899-ab37-4a4c-8952-07fb204a7a21"
REVALIDATE_TEAM_ID = "4b315d01-ab5f-48c4-b362-133caed81226"
REVALIDATE_CLIENT_ID = "8cc74525-7182-4615-b9d7-851f62f1431b"


async def main() -> int:
    db_url = os.environ.get("DATABASE_PUBLIC_URL") or os.environ.get("DATABASE_URL")
    if not db_url:
        print("ERROR: DATABASE_PUBLIC_URL not set", file=sys.stderr)
        return 1

    conn = await asyncpg.connect(db_url)
    try:
        print("=" * 70)
        print("SMITH ADVERSARIAL VERIFY - POS-CLEANUP")
        print("=" * 70)

        # V1: Alvos estao mesmo ausentes?
        print("\n[V1] Entidades alvo estao AUSENTES (esperado 0 em todas)")
        v1 = {}
        v1["biz_revalidate"] = await conn.fetchval("SELECT COUNT(*) FROM businesses WHERE id = $1", REVALIDATE_BUSINESS_ID)
        v1["user_revalidate"] = await conn.fetchval("SELECT COUNT(*) FROM users WHERE id = $1", REVALIDATE_USER_ID)
        v1["team_revalidate"] = await conn.fetchval("SELECT COUNT(*) FROM cleaning_teams WHERE id = $1", REVALIDATE_TEAM_ID)
        v1["client_revalidate"] = await conn.fetchval("SELECT COUNT(*) FROM cleaning_clients WHERE id = $1", REVALIDATE_CLIENT_ID)
        v1["roles_revalidate"] = await conn.fetchval("SELECT COUNT(*) FROM cleaning_user_roles WHERE business_id = $1", REVALIDATE_BUSINESS_ID)
        v1["services_s100"] = await conn.fetchval(
            "SELECT COUNT(*) FROM cleaning_services WHERE name LIKE '[S100%'"
        )
        v1["extras_s100"] = await conn.fetchval(
            "SELECT COUNT(*) FROM cleaning_extras WHERE name LIKE '[S100%'"
        )
        v1["teams_s100"] = await conn.fetchval(
            "SELECT COUNT(*) FROM cleaning_teams WHERE name LIKE '[S100%'"
        )
        v1["clients_s100"] = await conn.fetchval(
            "SELECT COUNT(*) FROM cleaning_clients WHERE first_name LIKE '[S100%' OR last_name LIKE '[S100%'"
        )
        v1["biz_s100"] = await conn.fetchval(
            "SELECT COUNT(*) FROM businesses WHERE slug LIKE 's100-%' OR name LIKE '[S100%'"
        )
        v1["user_s100"] = await conn.fetchval(
            "SELECT COUNT(*) FROM users WHERE email LIKE '%@s100revalidate.example' OR email LIKE '%s100%'"
        )
        for k, v in v1.items():
            flag = "OK" if v == 0 else f"FAIL ({v})"
            print(f"  {k}: {v} [{flag}]")

        # V2: xcleaners-demo data REAL intacta
        print("\n[V2] xcleaners-demo DATA REAL intacta (esperado > 0 onde aplicavel)")
        v2 = {}
        v2["real_clients"] = await conn.fetchval(
            "SELECT COUNT(*) FROM cleaning_clients WHERE business_id = $1 AND first_name NOT LIKE '[S100%' AND last_name NOT LIKE '[S100%'",
            XCLEANERS_DEMO_ID,
        )
        v2["real_teams"] = await conn.fetchval(
            "SELECT COUNT(*) FROM cleaning_teams WHERE business_id = $1 AND name NOT LIKE '[S100%'",
            XCLEANERS_DEMO_ID,
        )
        v2["real_services"] = await conn.fetchval(
            "SELECT COUNT(*) FROM cleaning_services WHERE business_id = $1 AND name NOT LIKE '[S100%'",
            XCLEANERS_DEMO_ID,
        )
        v2["real_extras"] = await conn.fetchval(
            "SELECT COUNT(*) FROM cleaning_extras WHERE business_id = $1 AND name NOT LIKE '[S100%'",
            XCLEANERS_DEMO_ID,
        )
        v2["real_roles"] = await conn.fetchval(
            "SELECT COUNT(*) FROM cleaning_user_roles WHERE business_id = $1",
            XCLEANERS_DEMO_ID,
        )
        v2["real_bookings"] = await conn.fetchval(
            "SELECT COUNT(*) FROM cleaning_bookings WHERE business_id = $1",
            XCLEANERS_DEMO_ID,
        )
        for k, v in v2.items():
            print(f"  {k}: {v}")

        # V3: Outros businesses (todos) intactos
        print("\n[V3] TOTAL de businesses + users em prod (baseline)")
        total_biz = await conn.fetchval("SELECT COUNT(*) FROM businesses")
        total_users = await conn.fetchval("SELECT COUNT(*) FROM users")
        total_clients = await conn.fetchval("SELECT COUNT(*) FROM cleaning_clients")
        total_bookings = await conn.fetchval("SELECT COUNT(*) FROM cleaning_bookings")
        total_teams = await conn.fetchval("SELECT COUNT(*) FROM cleaning_teams")
        print(f"  businesses: {total_biz}")
        print(f"  users: {total_users}")
        print(f"  clients: {total_clients}")
        print(f"  bookings: {total_bookings}")
        print(f"  teams: {total_teams}")

        # V4: Bookings / schedules / payroll orfaos?
        print("\n[V4] FK orfaos - entidades apontando para IDs deletados")
        v4 = {}
        v4["bookings_orphan_business"] = await conn.fetchval(
            "SELECT COUNT(*) FROM cleaning_bookings WHERE business_id = $1",
            REVALIDATE_BUSINESS_ID,
        )
        v4["bookings_orphan_team"] = await conn.fetchval(
            "SELECT COUNT(*) FROM cleaning_bookings WHERE team_id = $1",
            REVALIDATE_TEAM_ID,
        )
        v4["bookings_orphan_client"] = await conn.fetchval(
            "SELECT COUNT(*) FROM cleaning_bookings WHERE client_id = $1",
            REVALIDATE_CLIENT_ID,
        )
        v4["roles_orphan_user"] = await conn.fetchval(
            "SELECT COUNT(*) FROM cleaning_user_roles WHERE user_id = $1",
            REVALIDATE_USER_ID,
        )
        v4["roles_orphan_biz"] = await conn.fetchval(
            "SELECT COUNT(*) FROM cleaning_user_roles WHERE business_id = $1",
            REVALIDATE_BUSINESS_ID,
        )
        for k, v in v4.items():
            flag = "OK" if v == 0 else f"DANGLING ({v})"
            print(f"  {k}: {v} [{flag}]")

        # V5: admin e demo users preservados
        print("\n[V5] Users demo + admin preservados (esperado >= 4)")
        critical_emails = [
            "admin@xcleaners.app",
            "owner.demo@xcleaners.app",
            "teamlead.demo@xcleaners.app",
            "cleaner.demo@xcleaners.app",
            "homeowner.demo@xcleaners.app",
        ]
        missing = []
        for email in critical_emails:
            exists = await conn.fetchval("SELECT COUNT(*) FROM users WHERE email = $1", email)
            flag = "OK" if exists == 1 else f"MISSING ({exists})"
            print(f"  {email}: [{flag}]")
            if exists != 1:
                missing.append(email)

        # Verdict
        print("\n" + "=" * 70)
        print("SMITH VERDICT DATA")
        print("=" * 70)
        any_target_remaining = any(v > 0 for v in v1.values())
        any_orphan = any(v > 0 for v in v4.values())
        demo_intact = v2["real_roles"] > 0  # demo tem pelo menos o Team A role
        admin_intact = len(missing) == 0

        print(f"  Targets ausentes: {'SIM' if not any_target_remaining else 'NAO'}")
        print(f"  Zero FK dangling: {'SIM' if not any_orphan else 'NAO'}")
        print(f"  xcleaners-demo intacto: {'SIM' if demo_intact else 'NAO'}")
        print(f"  Admin + demo users preservados: {'SIM' if admin_intact else 'NAO'} ({5-len(missing)}/5)")

        if any_target_remaining or any_orphan or not demo_intact or not admin_intact:
            print("\n  VERDICT DATA: INFECTED")
            return 2
        print("\n  VERDICT DATA: CLEAN")
        return 0

    finally:
        await conn.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
