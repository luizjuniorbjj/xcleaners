"""
Xcleaners v3 — Email Service (Resend provider).

Transactional emails for cleaning businesses via Resend API.
Templates: booking_confirmation, booking_reminder, booking_cancelled,
           invoice_sent, invoice_reminder, team_invite, homeowner_invite, welcome.

All templates use inline CSS for responsive HTML email.

Env vars:
  RESEND_API_KEY              — Resend API key
  XCLEANERS_FROM_NOREPLY      — invites, welcome (default: noreply@xcleaners.app)
  XCLEANERS_FROM_APPOINTMENT  — booking_* emails
  XCLEANERS_FROM_INVOICE      — invoice_* emails
  XCLEANERS_FROM_CONTACT      — generic / reply-to
"""

import asyncio
import html
import logging
import os
from html import escape as html_escape  # avoid collision with local `html` vars
from typing import Optional

import resend

from app.database import Database

logger = logging.getLogger("xcleaners.email_service")

# ============================================
# RESEND CONFIG (from env)
# ============================================

RESEND_API_KEY = os.getenv("RESEND_API_KEY", "")

FROM_NOREPLY = os.getenv(
    "XCLEANERS_FROM_NOREPLY", "Xcleaners <noreply@xcleaners.app>"
)
FROM_APPOINTMENT = os.getenv(
    "XCLEANERS_FROM_APPOINTMENT", "Xcleaners Appointments <appointment@xcleaners.app>"
)
FROM_INVOICE = os.getenv(
    "XCLEANERS_FROM_INVOICE", "Xcleaners Invoices <invoice@xcleaners.app>"
)
FROM_CONTACT = os.getenv(
    "XCLEANERS_FROM_CONTACT", "Xcleaners <contact@xcleaners.app>"
)

# Category → FROM address mapping (semantic sender per email type)
_FROM_BY_CATEGORY = {
    "invite": FROM_NOREPLY,      # team_invite, homeowner_invite
    "booking": FROM_APPOINTMENT, # booking_confirmation/reminder/cancelled
    "invoice": FROM_INVOICE,     # invoice_sent/reminder/paid
    "welcome": FROM_NOREPLY,
    "contact": FROM_CONTACT,
    "noreply": FROM_NOREPLY,
}

if RESEND_API_KEY:
    resend.api_key = RESEND_API_KEY

# Xcleaners brand color
BRAND_BLUE = "#1a73e8"
BRAND_DARK = "#1557b0"


# ============================================
# BASE EMAIL SEND
# ============================================

def _send_via_resend(
    from_addr: str,
    to: str,
    subject: str,
    html_body: str,
    text_body: str,
    reply_to: Optional[str] = None,
) -> dict:
    """
    Synchronous Resend send — runs in a thread executor to avoid blocking the event loop.
    Raises resend.exceptions.ResendError on API failure so the async caller can handle it.
    """
    params: dict = {
        "from": from_addr,
        "to": [to],
        "subject": subject,
        "html": html_body,
        "text": text_body,
    }
    if reply_to:
        params["reply_to"] = reply_to
    return resend.Emails.send(params)


async def send_email(
    to: str,
    subject: str,
    html_body: str,
    text_body: Optional[str] = None,
    category: str = "noreply",
    reply_to: Optional[str] = None,
) -> dict:
    """
    Send an email via Resend (non-blocking).

    Args:
        to: Recipient email address
        subject: Email subject
        html_body: HTML content
        text_body: Plain text fallback (auto-generated if None)
        category: One of 'invite', 'booking', 'invoice', 'welcome', 'contact', 'noreply'.
                  Selects the semantically correct FROM address.
        reply_to: Optional Reply-To header (defaults to None, replies go to FROM)

    Returns: {sent: bool, id?: str, error?: str}
    """
    if not RESEND_API_KEY:
        logger.warning("[EMAIL] Resend not configured (RESEND_API_KEY missing)")
        return {"sent": False, "error": "Email not configured"}

    if not to:
        return {"sent": False, "error": "No recipient email"}

    from_addr = _FROM_BY_CATEGORY.get(category, FROM_NOREPLY)

    if not text_body:
        text_body = _strip_html(html_body)

    try:
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None, _send_via_resend, from_addr, to, subject, html_body, text_body, reply_to,
        )
        email_id = result.get("id") if isinstance(result, dict) else None
        logger.info("[EMAIL] Sent to %s via Resend (id=%s, from=%s, subject=%r)",
                    to, email_id, from_addr, subject)
        return {"sent": True, "id": email_id}

    except Exception as e:
        # resend SDK raises various exceptions — handle generically to keep
        # business flows running even if email delivery fails.
        logger.error("[EMAIL] Resend error sending to %s: %s (%s)",
                     to, e, type(e).__name__)
        return {"sent": False, "error": f"{type(e).__name__}: {e}"}


# ============================================
# HIGH-LEVEL SEND FUNCTIONS
# ============================================

async def send_booking_confirmation(db: Database, booking_id: str) -> dict:
    """Send booking confirmation email to the client."""
    booking = await db.pool.fetchrow(
        """SELECT b.scheduled_date, b.scheduled_time, b.address,
                  c.first_name, c.last_name, c.email,
                  s.name AS service_name,
                  t.name AS team_name
           FROM cleaning_bookings b
           JOIN cleaning_clients c ON c.id = b.client_id
           LEFT JOIN cleaning_services s ON s.id = b.service_id
           LEFT JOIN cleaning_teams t ON t.id = b.team_id
           WHERE b.id = $1""",
        booking_id,
    )
    if not booking or not booking["email"]:
        return {"sent": False, "error": "Booking or client email not found"}

    client_name = f"{booking['first_name'] or ''} {booking['last_name'] or ''}".strip()
    html = _template_booking_confirmation(
        client_name=client_name,
        service=booking["service_name"] or "Cleaning Service",
        date=str(booking["scheduled_date"]),
        time=str(booking["scheduled_time"] or ""),
        team_name=booking["team_name"] or "Our team",
        address=booking["address"] or "",
    )
    return await send_email(
        to=booking["email"],
        subject="Your Booking is Confirmed!",
        html_body=html,
        category="booking",
    )


async def send_booking_reminder(db: Database, booking_id: str) -> dict:
    """Send 24h booking reminder email to the client."""
    booking = await db.pool.fetchrow(
        """SELECT b.scheduled_date, b.scheduled_time,
                  c.first_name, c.last_name, c.email,
                  s.name AS service_name
           FROM cleaning_bookings b
           JOIN cleaning_clients c ON c.id = b.client_id
           LEFT JOIN cleaning_services s ON s.id = b.service_id
           WHERE b.id = $1""",
        booking_id,
    )
    if not booking or not booking["email"]:
        return {"sent": False, "error": "Booking or client email not found"}

    client_name = f"{booking['first_name'] or ''} {booking['last_name'] or ''}".strip()
    html = _template_booking_reminder(
        client_name=client_name,
        service=booking["service_name"] or "Cleaning Service",
        date=str(booking["scheduled_date"]),
        time=str(booking["scheduled_time"] or ""),
    )
    return await send_email(
        to=booking["email"],
        subject="Reminder: Your Cleaning is Tomorrow!",
        html_body=html,
        category="booking",
    )


async def send_booking_cancelled(
    db: Database,
    booking_id: str,
    reason: str = "",
) -> dict:
    """Send booking cancellation email to the client."""
    booking = await db.pool.fetchrow(
        """SELECT b.scheduled_date,
                  c.first_name, c.last_name, c.email,
                  s.name AS service_name
           FROM cleaning_bookings b
           JOIN cleaning_clients c ON c.id = b.client_id
           LEFT JOIN cleaning_services s ON s.id = b.service_id
           WHERE b.id = $1""",
        booking_id,
    )
    if not booking or not booking["email"]:
        return {"sent": False, "error": "Booking or client email not found"}

    client_name = f"{booking['first_name'] or ''} {booking['last_name'] or ''}".strip()
    html = _template_booking_cancelled(
        client_name=client_name,
        service=booking["service_name"] or "Cleaning Service",
        date=str(booking["scheduled_date"]),
        reason=reason,
    )
    return await send_email(
        to=booking["email"],
        subject="Booking Cancelled",
        html_body=html,
        category="booking",
    )


async def send_invoice_email(
    db: Database,
    invoice_id: str,
    payment_url: Optional[str] = None,
) -> dict:
    """
    Send invoice email with payment link to the client.

    Args:
        payment_url: Payment URL from Stripe PaymentLink.create (buy.stripe.com/...).
                     If provided, used as-is. If omitted, falls back to reconstructing
                     from stripe_invoice_id (legacy path, may produce invalid links for
                     Payment Links stored as plink_*).
    """
    inv = await db.pool.fetchrow(
        """SELECT i.invoice_number, i.total, i.balance_due, i.due_date,
                  i.stripe_invoice_id,
                  c.first_name, c.last_name, c.email
           FROM cleaning_invoices i
           JOIN cleaning_clients c ON c.id = i.client_id
           WHERE i.id = $1""",
        invoice_id,
    )
    if not inv or not inv["email"]:
        return {"sent": False, "error": "Invoice or client email not found"}

    client_name = f"{inv['first_name'] or ''} {inv['last_name'] or ''}".strip()
    amount = float(inv["balance_due"] or inv["total"] or 0)

    payment_link = payment_url or ""
    if not payment_link and inv.get("stripe_invoice_id"):
        # Legacy fallback — only works for `in_*` Stripe Invoice IDs, not `plink_*`
        payment_link = f"https://checkout.stripe.com/pay/{inv['stripe_invoice_id']}"

    html = _template_invoice_sent(
        client_name=client_name,
        amount=f"${amount:,.2f}",
        due_date=str(inv["due_date"]),
        payment_link=payment_link,
    )
    return await send_email(
        to=inv["email"],
        subject=f"Invoice {inv['invoice_number']} — Payment Due",
        html_body=html,
        category="invoice",
    )


async def send_invoice_reminder(
    db: Database,
    invoice_id: str,
    days_overdue: int = 0,
    payment_url: Optional[str] = None,
) -> dict:
    """Send overdue invoice reminder to the client. See send_invoice_email for payment_url semantics."""
    inv = await db.pool.fetchrow(
        """SELECT i.invoice_number, i.total, i.balance_due, i.due_date,
                  i.stripe_invoice_id,
                  c.first_name, c.last_name, c.email
           FROM cleaning_invoices i
           JOIN cleaning_clients c ON c.id = i.client_id
           WHERE i.id = $1""",
        invoice_id,
    )
    if not inv or not inv["email"]:
        return {"sent": False, "error": "Invoice or client email not found"}

    client_name = f"{inv['first_name'] or ''} {inv['last_name'] or ''}".strip()
    amount = float(inv["balance_due"] or inv["total"] or 0)

    payment_link = payment_url or ""
    if not payment_link and inv.get("stripe_invoice_id"):
        payment_link = f"https://checkout.stripe.com/pay/{inv['stripe_invoice_id']}"

    html = _template_invoice_reminder(
        client_name=client_name,
        amount=f"${amount:,.2f}",
        due_date=str(inv["due_date"]),
        days_overdue=days_overdue,
        payment_link=payment_link,
    )
    return await send_email(
        to=inv["email"],
        subject=f"Payment Reminder — Invoice {inv['invoice_number']}",
        html_body=html,
        category="invoice",
    )


async def send_homeowner_invite(
    db: Database,
    client_id: str,
    invite_token: str,
) -> dict:
    """
    Send homeowner portal invitation email to a client.

    Looks up client + business, builds the register/invite URL, and sends via Resend.
    Returns {sent, error?} — caller should log but not fail on email errors.
    """
    row = await db.pool.fetchrow(
        """SELECT c.first_name, c.last_name, c.email,
                  b.name AS business_name
           FROM cleaning_clients c
           JOIN businesses b ON b.id = c.business_id
           WHERE c.id = $1""",
        client_id,
    )
    if not row or not row["email"]:
        return {"sent": False, "error": "Client or email not found"}

    from app.config import APP_URL
    accept_link = f"{APP_URL}/cleaning/app#/register/invite/{invite_token}"

    business_name = row["business_name"] or "Your cleaning business"
    inviter_name = business_name
    client_name = f"{row['first_name'] or ''} {row['last_name'] or ''}".strip()
    greeting = f"Hi {client_name}," if client_name else "Hello,"

    # Re-use team_invite template (visually matches homeowner portal)
    html = _template_team_invite(
        business_name=business_name,
        inviter_name=inviter_name,
        role="homeowner",
        accept_link=accept_link,
    )
    # Prepend personalized greeting
    html = html.replace("<p>You've been invited", f"<p>{greeting}</p><p>You've been invited", 1)

    return await send_email(
        to=row["email"],
        subject=f"You're invited to {html_escape(business_name)}'s client portal",
        html_body=html,
        category="invite",
    )


# ============================================
# OWNER NOTIFICATIONS (business → owners + leads)
# ============================================

async def _get_owner_notification_emails(
    db: Database,
    business_id: str,
) -> list:
    """
    Return list of emails to notify for business-level events.
    Includes:
      - All users with cleaning_user_roles.role='owner' (primary)
      - All cleaning_members with role in (lead_cleaner, supervisor, manager)
    Dedup'd + filtered to non-null emails.
    """
    rows = await db.pool.fetch(
        """
        SELECT DISTINCT email FROM (
            SELECT u.email
              FROM users u
              JOIN cleaning_user_roles cur ON cur.user_id = u.id
             WHERE cur.business_id = $1
               AND cur.role = 'owner'
               AND cur.is_active = TRUE
            UNION
            SELECT cm.email
              FROM cleaning_members cm
             WHERE cm.business_id = $1
               AND cm.role IN ('lead_cleaner', 'supervisor', 'manager')
               AND cm.status = 'active'
               AND cm.email IS NOT NULL
        ) recipients
        WHERE email IS NOT NULL
        """,
        business_id,
    )
    return [r["email"] for r in rows if r["email"]]


async def send_owner_alert(
    db: Database,
    business_id: str,
    subject: str,
    title: str,
    body_html: str,
    cta_link: Optional[str] = None,
    cta_text: Optional[str] = None,
) -> dict:
    """
    Fan-out a business-level alert email to all owners + operational leads.
    Fire-and-forget: failures per-recipient are logged but do not raise.
    Returns {sent_count, failed_count, recipients}.
    """
    recipients = await _get_owner_notification_emails(db, business_id)
    if not recipients:
        logger.info("[OWNER_ALERT] No recipients for business %s — skipped", business_id)
        return {"sent_count": 0, "failed_count": 0, "recipients": []}

    html_body = _template_owner_alert(title, body_html, cta_link, cta_text)
    sent = 0
    failed = 0
    for addr in recipients:
        result = await send_email(
            to=addr,
            subject=subject,
            html_body=html_body,
            category="contact",  # from contact@ so replies reach the business inbox
        )
        if result.get("sent"):
            sent += 1
        else:
            failed += 1
    logger.info(
        "[OWNER_ALERT] business=%s subject=%r sent=%d failed=%d",
        business_id, subject, sent, failed,
    )
    return {"sent_count": sent, "failed_count": failed, "recipients": recipients}


async def send_owner_new_client(db: Database, client_id: str) -> dict:
    """Owner alert: a client activated their portal account."""
    row = await db.pool.fetchrow(
        """SELECT c.first_name, c.last_name, c.email, c.business_id,
                  b.slug AS biz_slug
             FROM cleaning_clients c
             JOIN businesses b ON b.id = c.business_id
            WHERE c.id = $1""",
        client_id,
    )
    if not row:
        return {"sent_count": 0, "failed_count": 0}

    from app.config import APP_URL
    client_name = f"{row['first_name'] or ''} {row['last_name'] or ''}".strip() or "A client"
    biz_id = str(row["business_id"])
    body = (
        f"<p><strong>{html_escape(client_name)}</strong> just activated their "
        f"client portal account with email <em>{html_escape(row['email'] or '')}</em>.</p>"
        f"<p>They can now view their bookings, invoices, and save payment methods online.</p>"
    )
    return await send_owner_alert(
        db=db,
        business_id=biz_id,
        subject=f"✨ New client activated: {client_name}",
        title="New client active",
        body_html=body,
        cta_link=f"{APP_URL}/clients",
        cta_text="View in Xcleaners",
    )


async def send_owner_new_booking(db: Database, booking_id: str) -> dict:
    """Owner alert: a new booking was created."""
    row = await db.pool.fetchrow(
        """SELECT b.scheduled_date, b.scheduled_start, b.final_price, b.business_id,
                  c.first_name, c.last_name,
                  s.name AS service_name,
                  t.name AS team_name
             FROM cleaning_bookings b
             JOIN cleaning_clients c ON c.id = b.client_id
        LEFT JOIN cleaning_services s ON s.id = b.service_id
        LEFT JOIN cleaning_teams t ON t.id = b.team_id
            WHERE b.id = $1""",
        booking_id,
    )
    if not row:
        return {"sent_count": 0, "failed_count": 0}

    from app.config import APP_URL
    client_name = f"{row['first_name'] or ''} {row['last_name'] or ''}".strip() or "Client"
    service_name = row["service_name"] or "Cleaning"
    team_name = row["team_name"] or "Unassigned"
    price = f"${float(row['final_price'] or 0):,.2f}"
    body = (
        f"<p><strong>{html_escape(service_name)}</strong> booked for "
        f"<strong>{html_escape(client_name)}</strong>.</p>"
        f"<ul>"
        f"<li><strong>Date:</strong> {row['scheduled_date']} at {row['scheduled_start']}</li>"
        f"<li><strong>Team:</strong> {html_escape(team_name)}</li>"
        f"<li><strong>Price:</strong> {price}</li>"
        f"</ul>"
    )
    return await send_owner_alert(
        db=db,
        business_id=str(row["business_id"]),
        subject=f"📅 New booking: {client_name} — {row['scheduled_date']}",
        title="New booking",
        body_html=body,
        cta_link=f"{APP_URL}/schedule",
        cta_text="View schedule",
    )


async def send_owner_booking_cancelled(
    db: Database,
    booking_id: str,
    reason: str = "",
    cancelled_by: str = "client",
) -> dict:
    """Owner alert: a booking was cancelled."""
    row = await db.pool.fetchrow(
        """SELECT b.scheduled_date, b.scheduled_start, b.business_id,
                  c.first_name, c.last_name
             FROM cleaning_bookings b
             JOIN cleaning_clients c ON c.id = b.client_id
            WHERE b.id = $1""",
        booking_id,
    )
    if not row:
        return {"sent_count": 0, "failed_count": 0}

    from app.config import APP_URL
    client_name = f"{row['first_name'] or ''} {row['last_name'] or ''}".strip() or "Client"
    reason_html = f"<p><strong>Reason:</strong> {html_escape(reason)}</p>" if reason else ""
    body = (
        f"<p><strong>{html_escape(client_name)}</strong> cancelled their booking "
        f"scheduled for <strong>{row['scheduled_date']} at {row['scheduled_start']}</strong>.</p>"
        f"{reason_html}"
        f"<p><em>Cancelled by: {html_escape(cancelled_by)}</em></p>"
    )
    return await send_owner_alert(
        db=db,
        business_id=str(row["business_id"]),
        subject=f"❌ Booking cancelled: {client_name} — {row['scheduled_date']}",
        title="Booking cancelled",
        body_html=body,
        cta_link=f"{APP_URL}/bookings",
        cta_text="View bookings",
    )


async def send_invoice_paid_confirmation(
    db: Database,
    invoice_id: str,
    amount_paid: float,
) -> dict:
    """
    Duplex notification triggered by webhook when invoice transitions to paid:
      1. Receipt to the client
      2. Alert to owners + leads
    """
    inv = await db.pool.fetchrow(
        """SELECT i.invoice_number, i.total, i.business_id,
                  c.first_name, c.last_name, c.email AS client_email
             FROM cleaning_invoices i
             JOIN cleaning_clients c ON c.id = i.client_id
            WHERE i.id = $1""",
        invoice_id,
    )
    if not inv:
        return {"client": {"sent": False}, "owner": {"sent_count": 0}}

    from app.config import APP_URL
    client_name = f"{inv['first_name'] or ''} {inv['last_name'] or ''}".strip() or "Client"
    biz_id = str(inv["business_id"])
    amount_str = f"${amount_paid:,.2f}"

    # 1. Client receipt
    client_result = {"sent": False}
    if inv["client_email"]:
        receipt_body = (
            f"<p>Hi {html_escape(client_name)},</p>"
            f"<p>Thank you! We've received your payment of <strong>{amount_str}</strong> "
            f"for invoice <strong>{inv['invoice_number']}</strong>.</p>"
            f"<p>A copy of your receipt is available in your client portal.</p>"
        )
        receipt_html = _template_owner_alert(
            title="Payment received — thank you!",
            body_html=receipt_body,
            cta_link=f"{APP_URL}/my-invoices",
            cta_text="View receipt",
        )
        client_result = await send_email(
            to=inv["client_email"],
            subject=f"Payment received — {inv['invoice_number']}",
            html_body=receipt_html,
            category="invoice",
        )

    # 2. Owner alert
    owner_body = (
        f"<p><strong>{html_escape(client_name)}</strong> paid "
        f"<strong>{amount_str}</strong> for invoice "
        f"<strong>{inv['invoice_number']}</strong>.</p>"
        f"<p>Funds will be transferred to your connected Stripe account "
        f"on the next payout cycle (typically T+2).</p>"
    )
    owner_result = await send_owner_alert(
        db=db,
        business_id=biz_id,
        subject=f"💰 Payment received: {amount_str} from {client_name}",
        title="Payment received",
        body_html=owner_body,
        cta_link=f"{APP_URL}/invoices",
        cta_text="View invoices",
    )
    return {"client": client_result, "owner": owner_result}


async def send_team_invite(
    db: Database,
    business_id: str,
    email: str,
    role: str,
    inviter_name: str,
) -> dict:
    """Send team invitation email."""
    biz = await db.pool.fetchrow(
        "SELECT name FROM businesses WHERE id = $1",
        business_id,
    )
    business_name = biz["name"] if biz else "Your cleaning business"

    from app.config import APP_URL
    accept_link = f"{APP_URL}/cleaning/app?invite={business_id}&role={role}"

    html = _template_team_invite(
        business_name=business_name,
        inviter_name=inviter_name,
        role=role,
        accept_link=accept_link,
    )
    return await send_email(
        to=email,
        subject=f"You're Invited to Join {html_escape(business_name)} on Xcleaners",
        html_body=html,
        category="invite",
    )


async def send_welcome(
    db: Database,
    user_id: str,
    business_id: str,
) -> dict:
    """Send welcome email after registration/onboarding."""
    user = await db.pool.fetchrow(
        "SELECT name, email FROM users WHERE id = $1",
        user_id,
    )
    biz = await db.pool.fetchrow(
        "SELECT name FROM businesses WHERE id = $1",
        business_id,
    )
    if not user or not user["email"]:
        return {"sent": False, "error": "User email not found"}

    user_name = user["name"] or "there"
    business_name = biz["name"] if biz else "your business"

    html = _template_welcome(
        user_name=user_name,
        business_name=business_name,
    )
    return await send_email(
        to=user["email"],
        subject="Welcome to Xcleaners!",
        html_body=html,
        category="welcome",
    )


# ============================================
# HTML EMAIL TEMPLATES
# ============================================

def _base_template(title: str, content: str) -> str:
    """Wrap content in a responsive email base template."""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title}</title>
</head>
<body style="margin:0;padding:0;background-color:#f4f6f9;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;">
  <table role="presentation" cellpadding="0" cellspacing="0" width="100%" style="background-color:#f4f6f9;">
    <tr>
      <td align="center" style="padding:24px 16px;">
        <table role="presentation" cellpadding="0" cellspacing="0" width="100%" style="max-width:560px;background-color:#ffffff;border-radius:8px;box-shadow:0 1px 3px rgba(0,0,0,0.1);">
          <!-- Header -->
          <tr>
            <td style="background-color:{BRAND_BLUE};padding:24px 32px;border-radius:8px 8px 0 0;">
              <h1 style="margin:0;color:#ffffff;font-size:22px;font-weight:600;">Xcleaners</h1>
            </td>
          </tr>
          <!-- Body -->
          <tr>
            <td style="padding:32px;">
              {content}
            </td>
          </tr>
          <!-- Footer -->
          <tr>
            <td style="padding:16px 32px;border-top:1px solid #e8eaed;color:#999;font-size:12px;text-align:center;">
              <p style="margin:0;">Sent by Xcleaners &mdash; Smart Cleaning Business Management</p>
              <p style="margin:4px 0 0 0;">You received this email because of your Xcleaners account.</p>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""


def _safe_url(url: str) -> str:
    """Validate that a URL starts with https:// and return it, or empty string."""
    if url and url.startswith("https://"):
        return url
    return ""


def _button(text: str, url: str) -> str:
    """Render a CTA button for email."""
    url = _safe_url(url)
    if not url:
        return ""
    return f"""<table role="presentation" cellpadding="0" cellspacing="0" style="margin:24px 0;">
  <tr>
    <td style="background-color:{BRAND_BLUE};border-radius:6px;padding:12px 28px;">
      <a href="{url}" style="color:#ffffff;text-decoration:none;font-weight:600;font-size:15px;display:inline-block;">{text}</a>
    </td>
  </tr>
</table>"""


def _template_booking_confirmation(
    client_name: str,
    service: str,
    date: str,
    time: str,
    team_name: str,
    address: str,
) -> str:
    cn = html.escape(client_name)
    svc = html.escape(service)
    tn = html.escape(team_name)
    addr = html.escape(address)
    content = f"""
<h2 style="margin:0 0 16px;color:#333;font-size:20px;">Booking Confirmed!</h2>
<p style="color:#555;font-size:15px;line-height:1.6;">Hi {cn},</p>
<p style="color:#555;font-size:15px;line-height:1.6;">Your cleaning has been confirmed. Here are the details:</p>
<table role="presentation" cellpadding="0" cellspacing="0" width="100%" style="margin:16px 0;background-color:#f8f9fa;border-radius:6px;padding:16px;">
  <tr><td style="padding:8px 16px;color:#333;font-size:14px;">
    <strong>Service:</strong> {svc}<br>
    <strong>Date:</strong> {date}<br>
    <strong>Time:</strong> {time}<br>
    <strong>Team:</strong> {tn}<br>
    <strong>Address:</strong> {addr}
  </td></tr>
</table>
<p style="color:#555;font-size:15px;line-height:1.6;">If you need to reschedule or cancel, please contact us as soon as possible.</p>
<p style="color:#555;font-size:14px;line-height:1.6;">Thank you for choosing us!</p>
"""
    return _base_template("Booking Confirmed", content)


def _template_booking_reminder(
    client_name: str,
    service: str,
    date: str,
    time: str,
) -> str:
    cn = html.escape(client_name)
    svc = html.escape(service)
    content = f"""
<h2 style="margin:0 0 16px;color:#333;font-size:20px;">Cleaning Tomorrow!</h2>
<p style="color:#555;font-size:15px;line-height:1.6;">Hi {cn},</p>
<p style="color:#555;font-size:15px;line-height:1.6;">This is a friendly reminder that your <strong>{svc}</strong> is scheduled for tomorrow.</p>
<table role="presentation" cellpadding="0" cellspacing="0" width="100%" style="margin:16px 0;background-color:#f8f9fa;border-radius:6px;padding:16px;">
  <tr><td style="padding:8px 16px;color:#333;font-size:14px;">
    <strong>Date:</strong> {date}<br>
    <strong>Time:</strong> {time}
  </td></tr>
</table>
<p style="color:#555;font-size:15px;line-height:1.6;">Please make sure the space is accessible for our team. See you tomorrow!</p>
"""
    return _base_template("Reminder: Cleaning Tomorrow", content)


def _template_booking_cancelled(
    client_name: str,
    service: str,
    date: str,
    reason: str,
) -> str:
    cn = html.escape(client_name)
    svc = html.escape(service)
    rsn = html.escape(reason)
    reason_text = f"<p style=\"color:#555;font-size:15px;line-height:1.6;\"><strong>Reason:</strong> {rsn}</p>" if reason else ""
    content = f"""
<h2 style="margin:0 0 16px;color:#333;font-size:20px;">Booking Cancelled</h2>
<p style="color:#555;font-size:15px;line-height:1.6;">Hi {cn},</p>
<p style="color:#555;font-size:15px;line-height:1.6;">Your <strong>{svc}</strong> booking scheduled for <strong>{date}</strong> has been cancelled.</p>
{reason_text}
<p style="color:#555;font-size:15px;line-height:1.6;">If you'd like to rebook, please contact us or schedule through the app.</p>
"""
    return _base_template("Booking Cancelled", content)


def _template_invoice_sent(
    client_name: str,
    amount: str,
    due_date: str,
    payment_link: str,
) -> str:
    cn = html.escape(client_name)
    btn = _button("Pay Now", payment_link)
    content = f"""
<h2 style="margin:0 0 16px;color:#333;font-size:20px;">Invoice Ready</h2>
<p style="color:#555;font-size:15px;line-height:1.6;">Hi {cn},</p>
<p style="color:#555;font-size:15px;line-height:1.6;">Your invoice for <strong>{amount}</strong> is ready.</p>
<table role="presentation" cellpadding="0" cellspacing="0" width="100%" style="margin:16px 0;background-color:#f8f9fa;border-radius:6px;padding:16px;">
  <tr><td style="padding:8px 16px;color:#333;font-size:14px;">
    <strong>Amount Due:</strong> {amount}<br>
    <strong>Due Date:</strong> {due_date}
  </td></tr>
</table>
{btn}
<p style="color:#555;font-size:14px;line-height:1.6;">If you have questions about this invoice, please don't hesitate to reach out.</p>
"""
    return _base_template("Invoice Ready", content)


def _template_invoice_reminder(
    client_name: str,
    amount: str,
    due_date: str,
    days_overdue: int,
    payment_link: str,
) -> str:
    cn = html.escape(client_name)
    btn = _button("Pay Now", payment_link)
    overdue_text = f"<strong>{days_overdue} day{'s' if days_overdue != 1 else ''}</strong> past due" if days_overdue > 0 else "due soon"
    content = f"""
<h2 style="margin:0 0 16px;color:#e53935;font-size:20px;">Payment Reminder</h2>
<p style="color:#555;font-size:15px;line-height:1.6;">Hi {cn},</p>
<p style="color:#555;font-size:15px;line-height:1.6;">Your invoice for <strong>{amount}</strong> is {overdue_text}.</p>
<table role="presentation" cellpadding="0" cellspacing="0" width="100%" style="margin:16px 0;background-color:#fff3f3;border-radius:6px;border:1px solid #ffcdd2;padding:16px;">
  <tr><td style="padding:8px 16px;color:#333;font-size:14px;">
    <strong>Amount Due:</strong> {amount}<br>
    <strong>Original Due Date:</strong> {due_date}<br>
    <strong>Days Overdue:</strong> {days_overdue}
  </td></tr>
</table>
{btn}
<p style="color:#555;font-size:14px;line-height:1.6;">Please settle this invoice at your earliest convenience. Thank you!</p>
"""
    return _base_template("Payment Reminder", content)


def _template_owner_alert(
    title: str,
    body_html: str,
    cta_link: Optional[str] = None,
    cta_text: Optional[str] = None,
) -> str:
    """
    Generic business-facing alert template. Title + pre-escaped HTML body + optional CTA.
    Caller is responsible for escaping user-controlled strings in body_html.
    """
    btn = _button(cta_text, cta_link) if (cta_link and cta_text) else ""
    content = f"""
<h2 style="margin:0 0 16px;color:#333;font-size:20px;">{html_escape(title)}</h2>
<div style="color:#555;font-size:15px;line-height:1.6;">{body_html}</div>
{btn}
<p style="color:#999;font-size:12px;line-height:1.6;margin-top:24px;">You're receiving this because you manage this business on Xcleaners. Reply to this email to contact our team.</p>
"""
    return _base_template(title, content)


def _template_team_invite(
    business_name: str,
    inviter_name: str,
    role: str,
    accept_link: str,
) -> str:
    bn = html.escape(business_name)
    inv = html.escape(inviter_name)
    role_display = html.escape(role.replace("_", " ").title())
    btn = _button("Accept Invitation", accept_link)
    content = f"""
<h2 style="margin:0 0 16px;color:#333;font-size:20px;">You're Invited!</h2>
<p style="color:#555;font-size:15px;line-height:1.6;"><strong>{inv}</strong> has invited you to join <strong>{bn}</strong> on Xcleaners as a <strong>{role_display}</strong>.</p>
<p style="color:#555;font-size:15px;line-height:1.6;">Xcleaners helps cleaning businesses manage schedules, clients, invoices, and teams — all in one place.</p>
{btn}
<p style="color:#999;font-size:12px;line-height:1.6;">If you didn't expect this invitation, you can safely ignore this email.</p>
"""
    return _base_template(f"Join {bn} on Xcleaners", content)


def _template_welcome(
    user_name: str,
    business_name: str,
) -> str:
    un = html.escape(user_name)
    bn = html.escape(business_name)
    content = f"""
<h2 style="margin:0 0 16px;color:#333;font-size:20px;">Welcome to Xcleaners!</h2>
<p style="color:#555;font-size:15px;line-height:1.6;">Hi {un},</p>
<p style="color:#555;font-size:15px;line-height:1.6;">Your account for <strong>{bn}</strong> is all set up! Here's what you can do next:</p>
<ul style="color:#555;font-size:15px;line-height:1.8;padding-left:20px;">
  <li>Add your cleaning services and pricing</li>
  <li>Invite your team members</li>
  <li>Start scheduling bookings</li>
  <li>Set up invoicing and payments</li>
</ul>
<p style="color:#555;font-size:15px;line-height:1.6;">We're here to help your cleaning business grow. Let's get started!</p>
"""
    return _base_template("Welcome to Xcleaners", content)


# ============================================
# HELPERS
# ============================================

def _strip_html(html: str) -> str:
    """Minimal HTML to plain text conversion for email fallback."""
    import re
    text = re.sub(r"<br\s*/?>", "\n", html)
    text = re.sub(r"<li[^>]*>", "- ", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"&mdash;", "—", text)
    text = re.sub(r"&amp;", "&", text)
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
