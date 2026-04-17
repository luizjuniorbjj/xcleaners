"""
Sprint 100% Cleanup - Fase 1 (Backup JSON) + Fase 2 (DELETE em transacao)

Pre-requisitos:
- sprint100_preflight.py rodado com GO/NO-GO: GO
- Luiz autorizou formato estruturado (risco medio)

Uso: railway run --service Postgres python scripts/sprint100_cleanup.py
  --apply  -> executa backup + DELETE + COMMIT
  (sem flag) -> dry-run, backup + DELETE + ROLLBACK (valida sem persistir)
"""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import decimal
import json
import os
import sys
import uuid
from pathlib import Path

import asyncpg


XCLEANERS_DEMO_ID = "ef4dcb08-4461-4e55-a593-76ae42295924"
REVALIDATE_BUSINESS_ID = "10271d87-85e1-40b8-8e87-8921cc3500b8"
REVALIDATE_USER_ID = "d9897899-ab37-4a4c-8952-07fb204a7a21"
REVALIDATE_TEAM_ID = "4b315d01-ab5f-48c4-b362-133caed81226"
REVALIDATE_CLIENT_ID = "8cc74525-7182-4615-b9d7-851f62f1431b"
REVALIDATE_USER_EMAIL = "revalidate-owner@s100revalidate.example"

BACKUP_DIR = Path("C:/xcleaners/backups")


def _json_default(o):
    if isinstance(o, (dt.datetime, dt.date, dt.time)):
        return o.isoformat()
    if isinstance(o, dt.timedelta):
        return o.total_seconds()
    if isinstance(o, uuid.UUID):
        return str(o)
    if isinstance(o, decimal.Decimal):
        return str(o)
    if isinstance(o, (bytes, bytearray, memoryview)):
        return bytes(o).decode("utf-8", errors="replace")
    if isinstance(o, set):
        return list(o)
    raise TypeError(f"Non-serializable type: {type(o)}")


async def dump_table(conn, label, query, params):
    rows = await conn.fetch(query, *params)
    return label, [dict(r) for r in rows]


async def main(apply: bool) -> int:
    db_url = os.environ.get("DATABASE_PUBLIC_URL") or os.environ.get("DATABASE_URL")
    if not db_url:
        print("ERROR: DATABASE_PUBLIC_URL/DATABASE_URL not set", file=sys.stderr)
        return 1

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_path = BACKUP_DIR / f"sprint100-cleanup-backup-{timestamp}.json"

    conn = await asyncpg.connect(db_url)
    try:
        mode = "APPLY (COMMIT)" if apply else "DRY-RUN (ROLLBACK at end)"
        print("=" * 70)
        print(f"SPRINT 100% CLEANUP - FASE 1+2 - MODE: {mode}")
        print("=" * 70)

        # ==================== FASE 1 - BACKUP ====================
        print("\n[FASE 1] BACKUP das linhas alvo (SELECT * antes do DELETE)\n")
        backup = {}

        targets = [
            (
                "services_manual",
                "SELECT * FROM cleaning_services WHERE business_id = $1 AND name LIKE '[S100-MANUAL]%'",
                (XCLEANERS_DEMO_ID,),
            ),
            (
                "extras_manual",
                "SELECT * FROM cleaning_extras WHERE business_id = $1 AND name LIKE '[S100%'",
                (XCLEANERS_DEMO_ID,),
            ),
            (
                "teams_revalidate",
                "SELECT * FROM cleaning_teams WHERE id = $1",
                (REVALIDATE_TEAM_ID,),
            ),
            (
                "clients_revalidate",
                "SELECT * FROM cleaning_clients WHERE id = $1",
                (REVALIDATE_CLIENT_ID,),
            ),
            (
                "roles_revalidate",
                "SELECT * FROM cleaning_user_roles WHERE business_id = $1",
                (REVALIDATE_BUSINESS_ID,),
            ),
            (
                "business_revalidate",
                "SELECT * FROM businesses WHERE id = $1",
                (REVALIDATE_BUSINESS_ID,),
            ),
            (
                "user_revalidate",
                "SELECT * FROM users WHERE id = $1",
                (REVALIDATE_USER_ID,),
            ),
        ]

        for label, q, p in targets:
            _, rows = await dump_table(conn, label, q, p)
            backup[label] = rows
            print(f"  [{label}] backed up {len(rows)} row(s)")

        backup["_meta"] = {
            "timestamp": dt.datetime.now().isoformat(),
            "mode": mode,
            "db_host": db_url.split("@")[-1].split("/")[0] if "@" in db_url else "?",
        }

        backup_path.write_text(
            json.dumps(backup, default=_json_default, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        print(f"\n  Backup salvo: {backup_path}")
        print(f"  Tamanho: {backup_path.stat().st_size} bytes")

        # Validacao backup: precisa ter >= 7 linhas total (exceto _meta)
        total_backed = sum(len(v) for k, v in backup.items() if k != "_meta")
        print(f"  Total rows backed up: {total_backed} (esperado 7)")
        if total_backed != 7:
            print("  ERRO: backup nao bateu com esperado. Abortando antes do DELETE.")
            return 2

        # ==================== FASE 2 - DELETE em TRANSACAO ====================
        print("\n[FASE 2] DELETE em transacao (ordem FK-safe)\n")

        async with conn.transaction():
            rc = {}

            # 2.1 Teams
            rc["teams"] = await conn.execute(
                """
                DELETE FROM cleaning_teams
                 WHERE id = $1
                   AND business_id = $2
                   AND name = $3
                """,
                REVALIDATE_TEAM_ID,
                XCLEANERS_DEMO_ID,
                "[S100-REVALIDATE] Team 2",
            )
            print(f"  2.1 teams DELETE: {rc['teams']}")

            # 2.2 Clients
            rc["clients"] = await conn.execute(
                "DELETE FROM cleaning_clients WHERE id = $1 AND business_id = $2",
                REVALIDATE_CLIENT_ID,
                XCLEANERS_DEMO_ID,
            )
            print(f"  2.2 clients DELETE: {rc['clients']}")

            # 2.3 Services
            rc["services"] = await conn.execute(
                "DELETE FROM cleaning_services WHERE business_id = $1 AND name LIKE '[S100-MANUAL]%'",
                XCLEANERS_DEMO_ID,
            )
            print(f"  2.3 services DELETE: {rc['services']}")

            # 2.4 Extras
            rc["extras"] = await conn.execute(
                "DELETE FROM cleaning_extras WHERE business_id = $1 AND name LIKE '[S100%'",
                XCLEANERS_DEMO_ID,
            )
            print(f"  2.4 extras DELETE: {rc['extras']}")

            # 2.5 Roles do owner REVALIDATE no business REVALIDATE
            rc["roles"] = await conn.execute(
                "DELETE FROM cleaning_user_roles WHERE business_id = $1",
                REVALIDATE_BUSINESS_ID,
            )
            print(f"  2.5 roles DELETE: {rc['roles']}")

            # 2.6 Business REVALIDATE
            rc["business"] = await conn.execute(
                "DELETE FROM businesses WHERE id = $1 AND slug = $2",
                REVALIDATE_BUSINESS_ID,
                "s100-revalidate-test-co",
            )
            print(f"  2.6 business DELETE: {rc['business']}")

            # 2.7 User REVALIDATE (somente se nao tem outros roles ativos)
            remaining_roles = await conn.fetchval(
                "SELECT COUNT(*) FROM cleaning_user_roles WHERE user_id = $1",
                REVALIDATE_USER_ID,
            )
            if remaining_roles > 0:
                print(f"  2.7 user DELETE SKIPPED: user ainda tem {remaining_roles} role(s) em outros businesses")
                rc["user"] = "SKIPPED"
            else:
                rc["user"] = await conn.execute(
                    "DELETE FROM users WHERE id = $1 AND email = $2",
                    REVALIDATE_USER_ID,
                    REVALIDATE_USER_EMAIL,
                )
                print(f"  2.7 user DELETE: {rc['user']}")

            # 2.8 Verify intra-transacao
            print("\n  [2.8] VERIFY intra-transacao (esperado 0 em todas)")
            verify = {}
            verify["services"] = await conn.fetchval(
                "SELECT COUNT(*) FROM cleaning_services WHERE business_id = $1 AND name LIKE '[S100-MANUAL]%'",
                XCLEANERS_DEMO_ID,
            )
            verify["extras"] = await conn.fetchval(
                "SELECT COUNT(*) FROM cleaning_extras WHERE business_id = $1 AND name LIKE '[S100%'",
                XCLEANERS_DEMO_ID,
            )
            verify["teams"] = await conn.fetchval(
                "SELECT COUNT(*) FROM cleaning_teams WHERE id = $1",
                REVALIDATE_TEAM_ID,
            )
            verify["clients"] = await conn.fetchval(
                "SELECT COUNT(*) FROM cleaning_clients WHERE id = $1",
                REVALIDATE_CLIENT_ID,
            )
            verify["business"] = await conn.fetchval(
                "SELECT COUNT(*) FROM businesses WHERE id = $1",
                REVALIDATE_BUSINESS_ID,
            )
            verify["user"] = await conn.fetchval(
                "SELECT COUNT(*) FROM users WHERE id = $1",
                REVALIDATE_USER_ID,
            )
            verify["roles"] = await conn.fetchval(
                "SELECT COUNT(*) FROM cleaning_user_roles WHERE business_id = $1",
                REVALIDATE_BUSINESS_ID,
            )
            for k, v in verify.items():
                status = "OK" if v == 0 else f"ALERT ({v})"
                print(f"    {k}: {v} [{status}]")

            any_remaining = any(v > 0 for v in verify.values())
            if any_remaining:
                print("\n  ERRO: verify falhou - ROLLBACK automatico da transacao")
                raise RuntimeError("Verify pos-DELETE falhou")

            # Safety check: xcleaners-demo intocado
            print("\n  [2.9] SAFETY - xcleaners-demo data real intocada")
            demo_real_clients = await conn.fetchval(
                """
                SELECT COUNT(*) FROM cleaning_clients
                 WHERE business_id = $1
                   AND first_name NOT LIKE '[S100%' AND last_name NOT LIKE '[S100%'
                """,
                XCLEANERS_DEMO_ID,
            )
            demo_real_teams = await conn.fetchval(
                "SELECT COUNT(*) FROM cleaning_teams WHERE business_id = $1 AND name NOT LIKE '[S100-%'",
                XCLEANERS_DEMO_ID,
            )
            demo_real_services = await conn.fetchval(
                "SELECT COUNT(*) FROM cleaning_services WHERE business_id = $1 AND name NOT LIKE '[S100-MANUAL]%'",
                XCLEANERS_DEMO_ID,
            )
            demo_real_extras = await conn.fetchval(
                "SELECT COUNT(*) FROM cleaning_extras WHERE business_id = $1 AND name NOT LIKE '[S100%'",
                XCLEANERS_DEMO_ID,
            )
            print(f"    xcleaners-demo clients (real): {demo_real_clients}")
            print(f"    xcleaners-demo teams (real): {demo_real_teams}")
            print(f"    xcleaners-demo services (real): {demo_real_services}")
            print(f"    xcleaners-demo extras (real): {demo_real_extras}")

            if not apply:
                print("\n  [DRY-RUN] forcando ROLLBACK para nao persistir")
                raise asyncpg.exceptions.PostgresError("DRY-RUN rollback")

            print("\n  Transacao OK -> COMMIT")

        print("\n" + "=" * 70)
        print(f"CLEANUP COMPLETO - modo {mode}")
        print("=" * 70)
        print(f"  Backup: {backup_path}")
        print(f"  Linhas deletadas: {sum(1 for v in rc.values() if isinstance(v, str) and v.startswith('DELETE'))}")
        print(f"  DELETE results: {rc}")
        return 0

    except Exception as e:
        print(f"\n  ERRO: {type(e).__name__}: {e}")
        if not apply and "DRY-RUN rollback" in str(e):
            print("  DRY-RUN concluido com ROLLBACK - estado prod INALTERADO.")
            return 0
        return 99
    finally:
        await conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="COMMIT para valer (sem flag = ROLLBACK dry-run)")
    args = parser.parse_args()
    sys.exit(asyncio.run(main(args.apply)))
