"""
Xcleaners — Payroll Service (60% Commission Split)

Materializes cleaner pay per completed booking into an immutable ledger
(cleaning_cleaner_earnings). Idempotent per (booking_id, cleaner_id).

Design (Sprint D Track B):
  - Snapshot wage_pct at calc time → historical earnings never shift if
    the owner later changes a cleaner's wage_pct.
  - One row per (booking, cleaner). v1 assumes single cleaner per booking
    (lead_cleaner_id). Multi-cleaner split is a future story.
  - Earnings are CREATED when booking status transitions to 'completed'
    AND has a lead_cleaner_id. If either is missing, skip silently.
  - Earnings rows can transition: pending → paid (records payout_ref)
    or pending → void (cleaner-initiated cancel, refund, etc.).

Consumers:
  - payroll_routes.py (list/summary/mark-paid)
  - schedule.py / booking status update hook

Author: @dev (Neo), 2026-04-16 (Sprint D Track B)
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Optional
from uuid import UUID

from app.database import Database

logger = logging.getLogger("xcleaners.payroll")


# ============================================================================
# CONSTANTS
# ============================================================================

_DEFAULT_WAGE_PCT = Decimal("60.00")  # 3Sisters-inspired default (mig 021)
_CENT = Decimal("0.01")


class PayrollError(ValueError):
    """Raised when earnings cannot be computed for a reason the caller should see."""


# ============================================================================
# CORE: calculate earnings on booking completion
# ============================================================================

async def calculate_cleaner_earnings(
    db: Database,
    booking_id: UUID | str,
) -> dict[str, Any] | None:
    """
    Compute and persist cleaner earnings for a completed booking.

    Returns the earnings row as a dict, or None if the booking is ineligible
    (e.g. no lead_cleaner_id assigned, or not completed yet).

    Idempotent: UNIQUE(booking_id, cleaner_id) means calling this twice for
    the same pair returns the existing row rather than duplicating.

    Raises PayrollError if the booking exists but its data is inconsistent
    (e.g. final_price is NULL — booking was never priced).
    """
    booking = await db.pool.fetchrow(
        """
        SELECT id, business_id, lead_cleaner_id, status, final_price
        FROM cleaning_bookings
        WHERE id = $1
        """,
        booking_id,
    )
    if booking is None:
        raise PayrollError(f"booking {booking_id} not found")

    if booking["status"] != "completed":
        logger.debug(
            "payroll: booking %s status=%s, skipping earnings",
            booking_id, booking["status"],
        )
        return None

    cleaner_id = booking["lead_cleaner_id"]
    if cleaner_id is None:
        logger.info(
            "payroll: booking %s has no lead_cleaner_id, skipping earnings",
            booking_id,
        )
        return None

    if booking["final_price"] is None:
        raise PayrollError(
            f"booking {booking_id} has NULL final_price — cannot compute earnings"
        )

    # Fast path: earnings already exist (idempotent behavior)
    existing = await db.pool.fetchrow(
        """
        SELECT id, booking_id, cleaner_id, gross_amount, commission_pct,
               net_amount, status, paid_at, payout_ref, created_at
        FROM cleaning_cleaner_earnings
        WHERE booking_id = $1 AND cleaner_id = $2
        """,
        booking_id, cleaner_id,
    )
    if existing is not None:
        logger.debug(
            "payroll: earnings already exist for booking=%s cleaner=%s",
            booking_id, cleaner_id,
        )
        return dict(existing)

    # Fetch wage_pct; fallback to default if member missing column / NULL
    wage_row = await db.pool.fetchrow(
        "SELECT wage_pct FROM cleaning_team_members WHERE id = $1",
        cleaner_id,
    )
    if wage_row is None:
        raise PayrollError(
            f"cleaner {cleaner_id} not found in cleaning_team_members"
        )
    wage_pct = (
        Decimal(str(wage_row["wage_pct"]))
        if wage_row["wage_pct"] is not None
        else _DEFAULT_WAGE_PCT
    )

    gross = Decimal(str(booking["final_price"]))
    net = (gross * wage_pct / Decimal("100")).quantize(_CENT, rounding=ROUND_HALF_UP)

    row = await db.pool.fetchrow(
        """
        INSERT INTO cleaning_cleaner_earnings
            (business_id, booking_id, cleaner_id,
             gross_amount, commission_pct, net_amount, status)
        VALUES ($1, $2, $3, $4, $5, $6, 'pending')
        ON CONFLICT (booking_id, cleaner_id) DO NOTHING
        RETURNING id, booking_id, cleaner_id, gross_amount, commission_pct,
                  net_amount, status, paid_at, payout_ref, created_at
        """,
        booking["business_id"], booking_id, cleaner_id,
        gross, wage_pct, net,
    )

    if row is None:
        # Race: another caller inserted between our SELECT and INSERT.
        # Return the row that now exists.
        row = await db.pool.fetchrow(
            """
            SELECT id, booking_id, cleaner_id, gross_amount, commission_pct,
                   net_amount, status, paid_at, payout_ref, created_at
            FROM cleaning_cleaner_earnings
            WHERE booking_id = $1 AND cleaner_id = $2
            """,
            booking_id, cleaner_id,
        )

    logger.info(
        "payroll: created earnings booking=%s cleaner=%s gross=%s pct=%s net=%s",
        booking_id, cleaner_id, gross, wage_pct, net,
    )
    return dict(row) if row else None


# ============================================================================
# LISTING & REPORTING
# ============================================================================

async def list_earnings(
    db: Database,
    business_id: UUID | str,
    *,
    cleaner_id: Optional[UUID | str] = None,
    status: Optional[str] = None,
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
    limit: int = 200,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """
    List earnings for a business, with optional filters.

    Filters are anded together. `from_date`/`to_date` are inclusive and
    applied to `created_at::date`.
    """
    where = ["e.business_id = $1"]
    params: list[Any] = [business_id]

    if cleaner_id is not None:
        params.append(cleaner_id)
        where.append(f"e.cleaner_id = ${len(params)}")

    if status is not None:
        if status not in ("pending", "paid", "void"):
            raise PayrollError(f"invalid status '{status}'")
        params.append(status)
        where.append(f"e.status = ${len(params)}")

    if from_date is not None:
        params.append(from_date)
        where.append(f"e.created_at::date >= ${len(params)}")

    if to_date is not None:
        params.append(to_date)
        where.append(f"e.created_at::date <= ${len(params)}")

    params.extend([limit, offset])
    sql = f"""
        SELECT e.id, e.booking_id, e.cleaner_id,
               e.gross_amount, e.commission_pct, e.net_amount,
               e.status, e.paid_at, e.payout_ref,
               e.created_at, e.updated_at,
               b.scheduled_date, b.final_price AS booking_final_price,
               TRIM(COALESCE(tm.first_name, '') || ' ' || COALESCE(tm.last_name, '')) AS cleaner_name
        FROM cleaning_cleaner_earnings e
        JOIN cleaning_bookings b ON b.id = e.booking_id
        LEFT JOIN cleaning_team_members tm ON tm.id = e.cleaner_id
        WHERE {' AND '.join(where)}
        ORDER BY e.created_at DESC
        LIMIT ${len(params) - 1} OFFSET ${len(params)}
    """
    rows = await db.pool.fetch(sql, *params)
    return [dict(r) for r in rows]


async def get_cleaner_summary(
    db: Database,
    business_id: UUID | str,
    *,
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
) -> list[dict[str, Any]]:
    """
    Aggregate earnings by cleaner for the period.

    Returns one row per cleaner with:
      cleaner_id, cleaner_name, bookings_count,
      gross_total, net_total, pending_net, paid_net.
    """
    where = ["e.business_id = $1"]
    params: list[Any] = [business_id]

    if from_date is not None:
        params.append(from_date)
        where.append(f"e.created_at::date >= ${len(params)}")

    if to_date is not None:
        params.append(to_date)
        where.append(f"e.created_at::date <= ${len(params)}")

    sql = f"""
        SELECT e.cleaner_id,
               TRIM(COALESCE(tm.first_name, '') || ' ' || COALESCE(tm.last_name, '')) AS cleaner_name,
               COUNT(*) AS bookings_count,
               COALESCE(SUM(e.gross_amount), 0) AS gross_total,
               COALESCE(SUM(e.net_amount), 0) AS net_total,
               COALESCE(SUM(e.net_amount) FILTER (WHERE e.status = 'pending'), 0) AS pending_net,
               COALESCE(SUM(e.net_amount) FILTER (WHERE e.status = 'paid'), 0) AS paid_net
        FROM cleaning_cleaner_earnings e
        LEFT JOIN cleaning_team_members tm ON tm.id = e.cleaner_id
        WHERE {' AND '.join(where)}
        GROUP BY e.cleaner_id, tm.first_name, tm.last_name
        ORDER BY net_total DESC
    """
    rows = await db.pool.fetch(sql, *params)
    return [dict(r) for r in rows]


# ============================================================================
# STATE TRANSITIONS
# ============================================================================

async def mark_paid(
    db: Database,
    business_id: UUID | str,
    earnings_ids: list[UUID | str],
    payout_ref: str,
) -> dict[str, Any]:
    """
    Mark one or more earnings rows as paid.

    Idempotent: already-paid rows with the SAME payout_ref are treated as
    a no-op. Rows paid with a DIFFERENT payout_ref raise PayrollError
    (prevents accidentally overwriting a previous payout's ref).

    Returns: {updated: N, skipped_already_paid: N, ids_updated: [...]}
    """
    if not earnings_ids:
        raise PayrollError("earnings_ids must not be empty")
    if not payout_ref or not payout_ref.strip():
        raise PayrollError("payout_ref is required")
    payout_ref = payout_ref.strip()

    # Wrap read+check+update in a transaction with row-level locking (Smith finding #5).
    async with db.pool.acquire() as conn:
        async with conn.transaction():
            existing = await conn.fetch(
                """
                SELECT id, status, payout_ref
                FROM cleaning_cleaner_earnings
                WHERE business_id = $1 AND id = ANY($2::uuid[])
                FOR UPDATE
                """,
                business_id, [str(x) for x in earnings_ids],
            )

            if len(existing) != len(earnings_ids):
                found = {str(r["id"]) for r in existing}
                missing = [str(x) for x in earnings_ids if str(x) not in found]
                raise PayrollError(f"earnings not found or wrong business: {missing}")

            # Check for conflicting paid refs
            conflicts = [
                str(r["id"]) for r in existing
                if r["status"] == "paid" and r["payout_ref"] != payout_ref
            ]
            if conflicts:
                raise PayrollError(
                    f"earnings already paid with different payout_ref: {conflicts}"
                )

            to_update = [r["id"] for r in existing if r["status"] == "pending"]
            skipped = len(existing) - len(to_update)

            if to_update:
                await conn.execute(
                    """
                    UPDATE cleaning_cleaner_earnings
                       SET status = 'paid', paid_at = NOW(), payout_ref = $1
                     WHERE id = ANY($2::uuid[]) AND status = 'pending'
                    """,
                    payout_ref, to_update,
                )

    logger.info(
        "payroll: mark_paid business=%s updated=%d skipped=%d ref=%s",
        business_id, len(to_update), skipped, payout_ref,
    )
    return {
        "updated": len(to_update),
        "skipped_already_paid": skipped,
        "ids_updated": [str(x) for x in to_update],
    }


async def void_earning(
    db: Database,
    business_id: UUID | str,
    earning_id: UUID | str,
    reason: Optional[str] = None,
) -> bool:
    """
    Void a single pending earning (e.g. booking was refunded after completion).

    Returns True if voided, False if already paid/void or not found.
    Paid earnings cannot be voided without a separate reversal workflow.
    `reason` is logged but not persisted (payout_ref is only for payment IDs,
    not void reasons — Smith finding #4).
    """
    row = await db.pool.fetchrow(
        """
        UPDATE cleaning_cleaner_earnings
           SET status = 'void'
         WHERE id = $1 AND business_id = $2 AND status = 'pending'
         RETURNING id
        """,
        earning_id, business_id,
    )
    ok = row is not None
    logger.info(
        "payroll: void business=%s earning=%s result=%s reason=%r",
        business_id, earning_id, ok, reason,
    )
    return ok
