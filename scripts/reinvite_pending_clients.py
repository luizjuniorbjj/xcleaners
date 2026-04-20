"""
Reissue invitations for any cleaning_clients in a given business that have no
user_id linked yet. Persists a fresh UUID token (7-day expiry) and dispatches
the homeowner invite email via Resend.

Run from Railway so RESEND_API_KEY and DATABASE_URL are available:
  railway run --service cleanclaw-api python scripts/reinvite_pending_clients.py <business_slug>
"""

from __future__ import annotations

import asyncio
import sys
import uuid
from datetime import datetime, timedelta, timezone


async def main(slug: str) -> int:
    # Late imports so we use the same DB + email plumbing as the API process
    from app.database import get_db_instance
    from app.modules.cleaning.services.email_service import send_homeowner_invite

    db = await get_db_instance()
    if not db:
        print("ERROR: could not initialize DB", file=sys.stderr)
        return 3

    try:
        biz = await db.pool.fetchrow(
            "SELECT id, name, slug FROM businesses WHERE slug = $1 LIMIT 1",
            slug,
        )
        if not biz:
            print(f"ERROR: business '{slug}' not found", file=sys.stderr)
            return 2

        print(f"Business: {biz['name']} ({biz['slug']}) id={biz['id']}")

        rows = await db.pool.fetch(
            """SELECT id, first_name, last_name, email
               FROM cleaning_clients
               WHERE business_id = $1
                 AND user_id IS NULL
                 AND email IS NOT NULL
               ORDER BY first_name""",
            biz["id"],
        )

        if not rows:
            print("No pending clients (all already linked).")
            return 0

        print(f"Reissuing invites for {len(rows)} client(s)...\n")

        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(days=7)

        for r in rows:
            tok = str(uuid.uuid4())
            await db.pool.execute(
                """UPDATE cleaning_clients
                   SET invite_token = $1::uuid,
                       invite_sent_at = $2,
                       invite_expires_at = $3,
                       updated_at = NOW()
                   WHERE id = $4""",
                tok, now, expires_at, r["id"],
            )

            name = f"{r['first_name']} {r['last_name'] or ''}".strip()
            result = await send_homeowner_invite(db, str(r["id"]), tok)
            status = "OK" if result.get("sent") else "FAIL"
            err = result.get("error") or ""
            print(f"  [{status}] {name} <{r['email']}> token={tok} {err}")

        return 0

    finally:
        # Pool is managed globally; no explicit close needed
        pass


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python scripts/reinvite_pending_clients.py <business_slug>", file=sys.stderr)
        sys.exit(1)
    sys.exit(asyncio.run(main(sys.argv[1])))
