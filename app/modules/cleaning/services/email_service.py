"""
Xcleaners v3 — Email Service (Sprint 4).

Transactional emails for cleaning businesses via configurable SMTP.
Templates: booking_confirmation, booking_reminder, booking_cancelled,
           invoice_sent, invoice_reminder, team_invite, welcome.

All templates use inline CSS for responsive HTML email.
"""

import asyncio
import html
import logging
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

from app.database import Database

logger = logging.getLogger("xcleaners.email_service")

# ============================================
# SMTP CONFIG (from env)
# ============================================

SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
FROM_EMAIL = os.getenv("XCLEANERS_FROM_EMAIL", "noreply@xcleaners.com")
FROM_NAME = os.getenv("XCLEANERS_FROM_NAME", "Xcleaners")

# Xcleaners brand color
BRAND_BLUE = "#1a73e8"
BRAND_DARK = "#1557b0"


# ============================================
# BASE EMAIL SEND
# ============================================

def _send_smtp(to: str, subject: str, html_body: str, text_body: str) -> None:
    """
    Synchronous SMTP send — runs in a thread executor to avoid blocking the event loop.
    Raises on any SMTP error so the async caller can handle it.
    """
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"{FROM_NAME} <{FROM_EMAIL}>"
    msg["To"] = to

    msg.attach(MIMEText(text_body, "plain"))
    msg.attach(MIMEText(html_body, "html"))

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        server.starttls()
        server.login(SMTP_USER, SMTP_PASSWORD)
        server.send_message(msg)


async def send_email(
    to: str,
    subject: str,
    html_body: str,
    text_body: Optional[str] = None,
) -> dict:
    """
    Send an email via SMTP (non-blocking).

    Args:
        to: Recipient email address
        subject: Email subject
        html_body: HTML content
        text_body: Plain text fallback (auto-generated if None)

    Returns: {sent: bool, error?: str}
    """
    if not SMTP_HOST or not SMTP_USER:
        logger.warning("[EMAIL] SMTP not configured (SMTP_HOST or SMTP_USER missing)")
        return {"sent": False, "error": "Email not configured"}

    if not to:
        return {"sent": False, "error": "No recipient email"}

    # Build plain text fallback before dispatching to thread
    if not text_body:
        text_body = _strip_html(html_body)

    try:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, _send_smtp, to, subject, html_body, text_body)

        logger.info("[EMAIL] Sent to %s: %s", to, subject)
        return {"sent": True}

    except smtplib.SMTPAuthenticationError as e:
        logger.error("[EMAIL] SMTP auth failed: %s", e)
        return {"sent": False, "error": "SMTP authentication failed"}
    except smtplib.SMTPException as e:
        logger.error("[EMAIL] SMTP error sending to %s: %s", to, e)
        return {"sent": False, "error": f"SMTP error: {str(e)}"}
    except Exception as e:
        logger.error("[EMAIL] Unexpected error sending to %s: %s", to, e)
        return {"sent": False, "error": str(e)}


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
    )


async def send_invoice_email(db: Database, invoice_id: str) -> dict:
    """Send invoice email with payment link to the client."""
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

    # Build payment link if Stripe reference exists
    payment_link = ""
    if inv.get("stripe_invoice_id"):
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
    )


async def send_invoice_reminder(
    db: Database,
    invoice_id: str,
    days_overdue: int = 0,
) -> dict:
    """Send overdue invoice reminder to the client."""
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

    payment_link = ""
    if inv.get("stripe_invoice_id"):
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
    )


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
        subject=f"You're Invited to Join {html.escape(business_name)} on Xcleaners",
        html_body=html,
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
