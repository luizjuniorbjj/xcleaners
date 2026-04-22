"""
Xcleaners v3 — Invoice Service (Sprint 4).

Full invoice lifecycle: generate from booking, batch generate,
list/filter, send, mark paid, Stripe payment links, auto-charge,
overdue tracking, payment reminders, and payment dashboard.

Tables: cleaning_invoices, cleaning_invoice_items (migration 011).
"""

import logging
from datetime import date, datetime, timedelta
from typing import Optional

import stripe

from app.config import STRIPE_SECRET_KEY, APP_URL
from app.database import Database
from app.modules.cleaning.models.invoices import (
    InvoiceCreate,
    InvoiceItemCreate,
)
from app.modules.cleaning.services._type_helpers import to_date

logger = logging.getLogger("xcleaners.invoice_service")

if STRIPE_SECRET_KEY:
    stripe.api_key = STRIPE_SECRET_KEY


# ============================================
# INVOICE NUMBER GENERATION
# ============================================

async def _next_invoice_number(db: Database, business_id: str) -> str:
    """Generate next invoice number atomically using FOR UPDATE to prevent races."""
    async with db.pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                """SELECT invoice_number FROM cleaning_invoices
                   WHERE business_id = $1
                   ORDER BY created_at DESC
                   LIMIT 1
                   FOR UPDATE""",
                business_id,
            )
            if row and row["invoice_number"]:
                # Parse "INV-2026-0042" -> 42
                parts = row["invoice_number"].rsplit("-", 1)
                try:
                    seq = int(parts[-1]) + 1
                except (ValueError, IndexError):
                    seq = 1
            else:
                seq = 1

            year = date.today().year
            return f"INV-{year}-{seq:04d}"


# ============================================
# GENERATE INVOICE FROM BOOKING
# ============================================

async def generate_invoice(
    db: Database,
    business_id: str,
    booking_id: str,
) -> dict:
    """
    Create an invoice from a completed booking.
    Pulls service + extras as line items.
    """
    # Fetch booking with client and service info
    booking = await db.pool.fetchrow(
        """SELECT b.*, c.first_name, c.last_name, c.email,
                  s.name AS service_name, s.base_price
           FROM cleaning_bookings b
           JOIN cleaning_clients c ON c.id = b.client_id
           LEFT JOIN cleaning_services s ON s.id = b.service_id
           WHERE b.id = $1 AND b.business_id = $2""",
        booking_id, business_id,
    )
    if not booking:
        return {"error": "Booking not found", "status_code": 404}

    # Check if invoice already exists for this booking
    existing = await db.pool.fetchval(
        """SELECT id FROM cleaning_invoices
           WHERE booking_id = $1 AND business_id = $2
           AND status NOT IN ('void', 'refunded')""",
        booking_id, business_id,
    )
    if existing:
        return {"error": "Invoice already exists for this booking", "status_code": 409}

    invoice_number = await _next_invoice_number(db, business_id)

    # Line item from service
    service_name = booking["service_name"] or "Cleaning Service"
    unit_price = float(booking["quoted_price"] or booking["base_price"] or 0)

    subtotal = unit_price
    tax_rate = 0.0
    tax_amount = 0.0
    total = subtotal

    due_date = date.today() + timedelta(days=15)

    # Create invoice
    inv_row = await db.pool.fetchrow(
        """INSERT INTO cleaning_invoices
           (business_id, client_id, booking_id, invoice_number,
            subtotal, tax_rate, tax_amount, discount_amount, total,
            issue_date, due_date, status)
           VALUES ($1, $2, $3, $4, $5, $6, $7, 0, $8,
                   CURRENT_DATE, $9, 'draft')
           RETURNING *""",
        business_id, str(booking["client_id"]), booking_id,
        invoice_number, subtotal, tax_rate, tax_amount, total, due_date,
    )

    invoice_id = str(inv_row["id"])

    # Create line item
    await db.pool.execute(
        """INSERT INTO cleaning_invoice_items
           (invoice_id, business_id, service_id, description,
            quantity, unit_price, total, sort_order)
           VALUES ($1, $2, $3, $4, 1, $5, $5, 0)""",
        invoice_id, business_id,
        str(booking["service_id"]) if booking["service_id"] else None,
        service_name, unit_price,
    )

    return _invoice_to_dict(inv_row)


# ============================================
# BATCH GENERATE INVOICES
# ============================================

async def generate_batch_invoices(
    db: Database,
    business_id: str,
    date_from: str,
    date_to: str,
) -> dict:
    """
    Batch generate invoices for all completed bookings in date range
    that don't already have an invoice.
    """
    # Find completed bookings without invoices
    rows = await db.pool.fetch(
        """SELECT b.id
           FROM cleaning_bookings b
           WHERE b.business_id = $1
             AND b.scheduled_date BETWEEN $2 AND $3
             AND b.status = 'completed'
             AND NOT EXISTS (
                 SELECT 1 FROM cleaning_invoices i
                 WHERE i.booking_id = b.id
                 AND i.status NOT IN ('void', 'refunded')
             )
           ORDER BY b.scheduled_date""",
        business_id, to_date(date_from), to_date(date_to),
    )

    created = []
    errors = []
    for row in rows:
        result = await generate_invoice(db, business_id, str(row["id"]))
        if result.get("error"):
            errors.append({"booking_id": str(row["id"]), "error": result["error"]})
        else:
            created.append(result)

    return {
        "created": len(created),
        "errors": len(errors),
        "invoices": created,
        "error_details": errors if errors else None,
    }


# ============================================
# LIST / FILTER INVOICES
# ============================================

async def get_invoices(
    db: Database,
    business_id: str,
    status: Optional[str] = None,
    client_id: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    search: Optional[str] = None,
    page: int = 1,
    page_size: int = 50,
) -> dict:
    """List invoices with filters and pagination."""
    conditions = ["i.business_id = $1"]
    params: list = [business_id]
    idx = 2

    if status:
        conditions.append(f"i.status = ${idx}")
        params.append(status)
        idx += 1

    if client_id:
        conditions.append(f"i.client_id = ${idx}")
        params.append(client_id)
        idx += 1

    if date_from:
        conditions.append(f"i.issue_date >= ${idx}")
        params.append(to_date(date_from))
        idx += 1

    if date_to:
        conditions.append(f"i.issue_date <= ${idx}")
        params.append(to_date(date_to))
        idx += 1

    if search:
        conditions.append(
            f"(i.invoice_number ILIKE ${idx} OR c.first_name ILIKE ${idx} OR c.last_name ILIKE ${idx})"
        )
        params.append(f"%{search}%")
        idx += 1

    where = " AND ".join(conditions)

    # Total count
    total = await db.pool.fetchval(
        f"""SELECT COUNT(*) FROM cleaning_invoices i
            LEFT JOIN cleaning_clients c ON c.id = i.client_id
            WHERE {where}""",
        *params,
    )

    # Paginated results
    offset = (page - 1) * page_size
    rows = await db.pool.fetch(
        f"""SELECT i.*, c.first_name AS client_first, c.last_name AS client_last,
                   c.email AS client_email, c.phone AS client_phone
            FROM cleaning_invoices i
            LEFT JOIN cleaning_clients c ON c.id = i.client_id
            WHERE {where}
            ORDER BY i.created_at DESC
            LIMIT {page_size} OFFSET {offset}""",
        *params,
    )

    invoices = [_invoice_to_dict(r) for r in rows]
    return {"invoices": invoices, "total": total, "page": page, "page_size": page_size}


# ============================================
# GET SINGLE INVOICE (with items)
# ============================================

async def get_invoice(
    db: Database,
    business_id: str,
    invoice_id: str,
) -> Optional[dict]:
    """Get invoice with line items."""
    row = await db.pool.fetchrow(
        """SELECT i.*, c.first_name AS client_first, c.last_name AS client_last,
                  c.email AS client_email, c.phone AS client_phone
           FROM cleaning_invoices i
           LEFT JOIN cleaning_clients c ON c.id = i.client_id
           WHERE i.id = $1 AND i.business_id = $2""",
        invoice_id, business_id,
    )
    if not row:
        return None

    inv = _invoice_to_dict(row)

    # Fetch line items
    items = await db.pool.fetch(
        """SELECT * FROM cleaning_invoice_items
           WHERE invoice_id = $1 AND business_id = $2
           ORDER BY sort_order""",
        invoice_id, business_id,
    )
    inv["items"] = [_item_to_dict(it) for it in items]
    return inv


# ============================================
# SEND INVOICE
# ============================================

async def send_invoice(
    db: Database,
    business_id: str,
    invoice_id: str,
) -> dict:
    """
    Mark invoice as sent. Actual delivery (email/SMS/WhatsApp)
    is handled by the notification service.
    Returns invoice data for the notification layer to use.
    """
    row = await db.pool.fetchrow(
        """UPDATE cleaning_invoices
           SET status = CASE WHEN status = 'draft' THEN 'sent' ELSE status END,
               updated_at = NOW()
           WHERE id = $1 AND business_id = $2
           RETURNING *""",
        invoice_id, business_id,
    )
    if not row:
        return {"error": "Invoice not found", "status_code": 404}

    inv = _invoice_to_dict(row)

    # Get client contact info
    client = await db.pool.fetchrow(
        "SELECT first_name, last_name, email, phone FROM cleaning_clients WHERE id = $1",
        str(row["client_id"]),
    )
    if client:
        inv["client_email"] = client["email"]
        inv["client_phone"] = client["phone"]
        inv["client_name"] = f"{client['first_name'] or ''} {client['last_name'] or ''}".strip()

    return inv


# ============================================
# MARK PAID (manual payment)
# ============================================

async def mark_paid(
    db: Database,
    business_id: str,
    invoice_id: str,
    method: str,
    amount: float,
    reference: Optional[str] = None,
) -> dict:
    """Record a manual payment (cash, check, Zelle, Venmo, other)."""
    # Get current invoice
    current = await db.pool.fetchrow(
        "SELECT * FROM cleaning_invoices WHERE id = $1 AND business_id = $2",
        invoice_id, business_id,
    )
    if not current:
        return {"error": "Invoice not found", "status_code": 404}

    new_paid = float(current["amount_paid"] or 0) + amount
    total = float(current["total"])
    new_status = "paid" if new_paid >= total else "partial"

    # Cast $4 explicitly — asyncpg raises AmbiguousParameterError when a param
    # is used in both a SET clause and a CASE comparison (can't deduce type).
    row = await db.pool.fetchrow(
        """UPDATE cleaning_invoices
           SET amount_paid = $3, status = $4::varchar,
               payment_method = $5, payment_reference = $6,
               paid_at = CASE WHEN $4::varchar = 'paid' THEN NOW() ELSE paid_at END,
               updated_at = NOW()
           WHERE id = $1 AND business_id = $2
           RETURNING *""",
        invoice_id, business_id, new_paid, new_status, method, reference,
    )

    # Email notifications when fully paid (best-effort)
    if row and new_status == "paid":
        try:
            from app.modules.cleaning.services.email_service import (
                send_payment_received,
                send_owner_payment_received,
            )
            await send_payment_received(db, invoice_id)
            await send_owner_payment_received(db, invoice_id)
        except Exception as e:
            logger.warning("[INVOICE] mark_paid email notify failed: %s", e)

    return _invoice_to_dict(row) if row else {"error": "Update failed", "status_code": 500}


# ============================================
# CREATE STRIPE PAYMENT LINK
# ============================================

async def create_payment_link(
    db: Database,
    business_id: str,
    invoice_id: str,
) -> dict:
    """Create a Stripe payment link for an invoice on the business's Connect account."""
    if not STRIPE_SECRET_KEY:
        return {"error": "Stripe not configured", "status_code": 500}

    inv = await db.pool.fetchrow(
        """SELECT i.*, c.email AS client_email, c.first_name, c.last_name,
                  b.stripe_account_id, b.stripe_charges_enabled
           FROM cleaning_invoices i
           JOIN cleaning_clients c ON c.id = i.client_id
           JOIN businesses b ON b.id = i.business_id
           WHERE i.id = $1 AND i.business_id = $2""",
        invoice_id, business_id,
    )
    if not inv:
        return {"error": "Invoice not found", "status_code": 404}

    stripe_account_id = inv["stripe_account_id"]
    if not stripe_account_id:
        return {
            "error": "Stripe Connect not configured. Complete onboarding at /settings/payments before sending invoices.",
            "status_code": 400,
        }
    if not inv["stripe_charges_enabled"]:
        return {
            "error": "Stripe Connect onboarding incomplete. Finish required fields at /settings/payments to enable charges.",
            "status_code": 400,
        }

    if inv["status"] in ("paid", "void", "refunded"):
        return {"error": f"Cannot create payment link for {inv['status']} invoice", "status_code": 400}

    balance = float(inv["balance_due"])
    if balance <= 0:
        return {"error": "No balance due", "status_code": 400}

    try:
        price = stripe.Price.create(
            unit_amount=int(balance * 100),
            currency="usd",
            product_data={
                "name": f"Invoice {inv['invoice_number']}",
            },
            stripe_account=stripe_account_id,
        )

        payment_link = stripe.PaymentLink.create(
            line_items=[{"price": price.id, "quantity": 1}],
            metadata={
                "invoice_id": invoice_id,
                "business_id": business_id,
                "invoice_number": inv["invoice_number"],
            },
            after_completion={
                "type": "redirect",
                "redirect": {"url": f"{APP_URL}/cleaning/payment-success?invoice={invoice_id}"},
            },
            stripe_account=stripe_account_id,
        )

        # Store Stripe invoice reference
        await db.pool.execute(
            """UPDATE cleaning_invoices
               SET stripe_invoice_id = $3, updated_at = NOW()
               WHERE id = $1 AND business_id = $2""",
            invoice_id, business_id, payment_link.id,
        )

        return {
            "payment_url": payment_link.url,
            "invoice_id": invoice_id,
            "amount": balance,
        }

    except stripe.error.StripeError as e:
        logger.error("[INVOICE] Stripe payment link error: %s", e)
        return {"error": f"Stripe error: {str(e)}", "status_code": 500}


# ============================================
# AUTO-CHARGE (saved card)
# ============================================

async def auto_charge(
    db: Database,
    business_id: str,
    invoice_id: str,
) -> dict:
    """
    Charge a saved card for recurring clients with card on file.
    Requires the client to have a stripe_customer_id stored on the Connect account.
    """
    if not STRIPE_SECRET_KEY:
        return {"error": "Stripe not configured", "status_code": 500}

    inv = await db.pool.fetchrow(
        """SELECT i.*, c.email AS client_email,
                  b.stripe_account_id, b.stripe_charges_enabled
           FROM cleaning_invoices i
           JOIN cleaning_clients c ON c.id = i.client_id
           JOIN businesses b ON b.id = i.business_id
           WHERE i.id = $1 AND i.business_id = $2""",
        invoice_id, business_id,
    )
    if not inv:
        return {"error": "Invoice not found", "status_code": 404}

    stripe_account_id = inv["stripe_account_id"]
    if not stripe_account_id:
        return {
            "error": "Stripe Connect not configured. Complete onboarding at /settings/payments before charging.",
            "status_code": 400,
        }
    if not inv["stripe_charges_enabled"]:
        return {
            "error": "Stripe Connect onboarding incomplete. Finish required fields at /settings/payments to enable charges.",
            "status_code": 400,
        }

    if inv["status"] in ("paid", "void", "refunded"):
        return {"error": f"Cannot charge {inv['status']} invoice", "status_code": 400}

    balance = float(inv["balance_due"])
    if balance <= 0:
        return {"error": "No balance due", "status_code": 400}

    # Look up Stripe customer for this client
    client_stripe = await db.pool.fetchval(
        """SELECT metadata->>'stripe_customer_id'
           FROM cleaning_clients WHERE id = $1 AND business_id = $2""",
        str(inv["client_id"]), business_id,
    )
    if not client_stripe:
        return {"error": "Client has no card on file", "status_code": 400}

    try:
        payment_intent = stripe.PaymentIntent.create(
            amount=int(balance * 100),
            currency="usd",
            customer=client_stripe,
            off_session=True,
            confirm=True,
            metadata={
                "invoice_id": invoice_id,
                "business_id": business_id,
                "invoice_number": inv["invoice_number"],
            },
            stripe_account=stripe_account_id,
        )

        if payment_intent.status == "succeeded":
            await db.pool.execute(
                """UPDATE cleaning_invoices
                   SET amount_paid = total, status = 'paid',
                       payment_method = 'stripe', payment_reference = $3,
                       stripe_invoice_id = $4, paid_at = NOW(), updated_at = NOW()
                   WHERE id = $1 AND business_id = $2""",
                invoice_id, business_id, payment_intent.id, payment_intent.id,
            )
            return {
                "success": True,
                "payment_intent_id": payment_intent.id,
                "amount": balance,
            }
        else:
            return {"error": f"Payment status: {payment_intent.status}", "status_code": 400}

    except stripe.error.CardError as e:
        logger.warning("[INVOICE] Card declined for invoice %s: %s", invoice_id, e)
        return {"error": f"Card declined: {e.user_message}", "status_code": 400}
    except stripe.error.StripeError as e:
        logger.error("[INVOICE] Stripe auto-charge error: %s", e)
        return {"error": f"Stripe error: {str(e)}", "status_code": 500}


# ============================================
# OVERDUE INVOICES
# ============================================

async def get_overdue_invoices(
    db: Database,
    business_id: str,
) -> dict:
    """Get all overdue invoices sorted by days overdue."""
    rows = await db.pool.fetch(
        """SELECT i.*, c.first_name AS client_first, c.last_name AS client_last,
                  c.email AS client_email, c.phone AS client_phone,
                  (CURRENT_DATE - i.due_date) AS days_overdue
           FROM cleaning_invoices i
           JOIN cleaning_clients c ON c.id = i.client_id
           WHERE i.business_id = $1
             AND i.balance_due > 0
             AND i.due_date < CURRENT_DATE
             AND i.status NOT IN ('void', 'refunded', 'paid', 'draft')
           ORDER BY i.due_date ASC""",
        business_id,
    )

    invoices = []
    for r in rows:
        inv = _invoice_to_dict(r)
        inv["days_overdue"] = r["days_overdue"]
        invoices.append(inv)

    total_overdue = sum(float(r["balance_due"]) for r in rows)
    return {
        "invoices": invoices,
        "total": len(invoices),
        "total_overdue_amount": total_overdue,
    }


# ============================================
# SEND PAYMENT REMINDERS (bulk)
# ============================================

async def send_payment_reminders(
    db: Database,
    business_id: str,
) -> dict:
    """
    Collect overdue invoices and return them for the notification
    service to send reminders. Marks each with a reminder timestamp.
    """
    overdue = await get_overdue_invoices(db, business_id)
    reminded = []

    for inv in overdue.get("invoices", []):
        # Update internal_notes with reminder timestamp
        await db.pool.execute(
            """UPDATE cleaning_invoices
               SET internal_notes = COALESCE(internal_notes, '') ||
                   E'\nReminder sent: ' || NOW()::TEXT,
                   updated_at = NOW()
               WHERE id = $1 AND business_id = $2""",
            inv["id"], business_id,
        )
        reminded.append({
            "invoice_id": inv["id"],
            "invoice_number": inv.get("invoice_number"),
            "client_name": inv.get("client_name", ""),
            "balance_due": inv.get("balance_due"),
            "days_overdue": inv.get("days_overdue"),
        })

    return {
        "reminded": len(reminded),
        "invoices": reminded,
    }


# ============================================
# PAYMENT DASHBOARD
# ============================================

async def get_payment_dashboard(
    db: Database,
    business_id: str,
) -> dict:
    """
    Summary: total revenue, outstanding, overdue, by frequency.
    Used by the owner dashboard and invoice manager KPI cards.
    """
    # Current month
    now = date.today()
    month_start = now.replace(day=1)
    month_end = (month_start + timedelta(days=32)).replace(day=1) - timedelta(days=1)

    # Revenue this month (paid invoices)
    month_revenue = await db.pool.fetchval(
        """SELECT COALESCE(SUM(amount_paid), 0)
           FROM cleaning_invoices
           WHERE business_id = $1
             AND paid_at >= $2 AND paid_at <= $3
             AND status IN ('paid', 'partial')""",
        business_id,
        datetime.combine(month_start, datetime.min.time()),
        datetime.combine(month_end, datetime.max.time()),
    )

    # Outstanding (unpaid balance)
    outstanding = await db.pool.fetchval(
        """SELECT COALESCE(SUM(balance_due), 0)
           FROM cleaning_invoices
           WHERE business_id = $1
             AND balance_due > 0
             AND status NOT IN ('void', 'refunded', 'draft')""",
        business_id,
    )

    # Overdue
    overdue = await db.pool.fetchrow(
        """SELECT COUNT(*) AS count, COALESCE(SUM(balance_due), 0) AS amount
           FROM cleaning_invoices
           WHERE business_id = $1
             AND balance_due > 0
             AND due_date < CURRENT_DATE
             AND status NOT IN ('void', 'refunded', 'paid', 'draft')""",
        business_id,
    )

    # Revenue by payment method
    by_method = await db.pool.fetch(
        """SELECT COALESCE(payment_method, 'unknown') AS method,
                  SUM(amount_paid) AS total
           FROM cleaning_invoices
           WHERE business_id = $1 AND amount_paid > 0
           GROUP BY payment_method""",
        business_id,
    )

    # Total invoices by status
    by_status = await db.pool.fetch(
        """SELECT status, COUNT(*) AS count, COALESCE(SUM(total), 0) AS total_amount
           FROM cleaning_invoices
           WHERE business_id = $1
           GROUP BY status""",
        business_id,
    )

    return {
        "month_revenue": float(month_revenue),
        "outstanding": float(outstanding),
        "overdue_count": overdue["count"],
        "overdue_amount": float(overdue["amount"]),
        "by_method": [{"method": r["method"], "total": float(r["total"])} for r in by_method],
        "by_status": [
            {"status": r["status"], "count": r["count"], "total": float(r["total_amount"])}
            for r in by_status
        ],
        "period": {"start": str(month_start), "end": str(month_end)},
    }


# ============================================
# HELPERS
# ============================================

def _invoice_to_dict(row) -> dict:
    """Convert invoice DB row to serializable dict."""
    if not row:
        return {}
    d = dict(row)
    # UUID to str
    for key in ["id", "business_id", "client_id", "booking_id"]:
        if d.get(key) is not None:
            d[key] = str(d[key])
    # Dates to str
    for key in ["issue_date", "due_date", "created_at", "updated_at", "paid_at"]:
        if d.get(key) is not None:
            d[key] = str(d[key])
    # Numeric to float
    for key in ["subtotal", "tax_rate", "tax_amount", "discount_amount",
                 "total", "amount_paid", "balance_due"]:
        if d.get(key) is not None:
            d[key] = float(d[key])
    # Derive client_name if present
    first = d.pop("client_first", None) or ""
    last = d.pop("client_last", None) or ""
    if first or last:
        d["client_name"] = f"{first} {last}".strip()
    return d


def _item_to_dict(row) -> dict:
    """Convert invoice item DB row to serializable dict."""
    if not row:
        return {}
    d = dict(row)
    for key in ["id", "invoice_id", "business_id", "service_id"]:
        if d.get(key) is not None:
            d[key] = str(d[key])
    for key in ["quantity", "unit_price", "total"]:
        if d.get(key) is not None:
            d[key] = float(d[key])
    if d.get("created_at") is not None:
        d["created_at"] = str(d["created_at"])
    return d
