"""
Xcleaners v3 — Notification Service (Sprint 4).

Omnichannel notification orchestrator.
Routes notifications through the optimal channel:
  WhatsApp (free) -> Push (free) -> SMS (paid fallback)

Critical notifications (24h reminder) go directly via SMS.

Templates: booking_confirmation, reminder_24h, invoice_sent,
           schedule_changed, checkin_alert, payment_reminder

Tables: cleaning_notifications (migration 011).
"""

import json
import logging
from typing import Optional

from app.database import Database

logger = logging.getLogger("xcleaners.notification_service")

# Channel priority (default): WhatsApp first (free), then push, SMS as fallback
DEFAULT_CHANNEL_PRIORITY = ["whatsapp", "push", "sms"]

# Templates that always get SMS (critical)
CRITICAL_TEMPLATES = {"reminder_24h", "checkin_alert"}


# ============================================
# MAIN SEND FUNCTION
# ============================================

async def send_notification(
    db: Database,
    business_id: str,
    target_type: str,
    target_id: str,
    template_key: str,
    data: dict,
    channel_priority: Optional[list] = None,
) -> dict:
    """
    Send a notification through the best available channel.

    Channel priority: WhatsApp (free) -> Push (free) -> SMS (paid fallback).
    Critical notifications (24h reminder): SMS directly.

    Args:
        db: Database instance
        business_id: Business UUID
        target_type: 'client', 'cleaner', or 'owner'
        target_id: UUID of the target (client_id, member_id, or user_id)
        template_key: Notification template name
        data: Template variables
        channel_priority: Override default channel priority

    Returns: {sent, channel, details}
    """
    priority = channel_priority or DEFAULT_CHANNEL_PRIORITY

    # Critical templates go directly via SMS
    if template_key in CRITICAL_TEMPLATES:
        priority = ["sms", "whatsapp"]

    # Resolve contact info for the target
    contact = await _resolve_contact(db, business_id, target_type, target_id)
    if not contact:
        logger.warning(
            "[NOTIFY] Could not resolve contact for %s/%s in business %s",
            target_type, target_id, business_id,
        )
        return {"sent": False, "error": "Contact not found"}

    # Try each channel in priority order
    for channel in priority:
        result = await _try_channel(
            db, business_id, channel, contact,
            target_type, target_id, template_key, data,
        )
        if result.get("sent"):
            return result

    # All channels failed
    logger.warning(
        "[NOTIFY] All channels failed for %s/%s template=%s",
        target_type, target_id, template_key,
    )
    return {"sent": False, "error": "All notification channels failed"}


# ============================================
# CHANNEL DISPATCH
# ============================================

async def _try_channel(
    db: Database,
    business_id: str,
    channel: str,
    contact: dict,
    target_type: str,
    target_id: str,
    template_key: str,
    data: dict,
) -> dict:
    """Try sending via a specific channel."""
    if channel == "whatsapp":
        return await send_whatsapp(
            db, business_id, contact.get("phone"), template_key, data,
            target_type, target_id,
        )
    elif channel == "sms":
        return await send_sms_notification(
            db, business_id, contact.get("phone"), template_key, data,
            target_type, target_id,
        )
    elif channel == "push":
        return await send_push(
            db, business_id, contact.get("user_id"),
            _template_title(template_key),
            _render_template(template_key, data),
            target_type, target_id,
        )
    elif channel == "email":
        return await send_email_notification(
            db, business_id, contact.get("email"),
            _template_title(template_key),
            _render_template(template_key, data),
            target_type, target_id,
        )

    return {"sent": False, "error": f"Unknown channel: {channel}"}


# ============================================
# WHATSAPP — via existing Evolution API adapter
# ============================================

async def send_whatsapp(
    db: Database,
    business_id: str,
    phone: Optional[str],
    template_key: str,
    data: dict,
    target_type: str = "client",
    target_id: Optional[str] = None,
) -> dict:
    """Send notification via WhatsApp using the existing Evolution API adapter."""
    if not phone:
        return {"sent": False, "error": "No phone number"}

    try:
        import os as _os
        channel_row = await db.pool.fetchrow(
            """SELECT instance_name, phone_number, webhook_secret
               FROM business_channels
               WHERE business_id = $1 AND channel_type = 'whatsapp'
                 AND status IN ('connected', 'connecting', 'active')
               LIMIT 1""",
            business_id,
        )
        if not channel_row:
            return {"sent": False, "error": "WhatsApp channel not configured"}

        from app.modules.channels.whatsapp import WhatsAppAdapter

        config = {
            "api_url": _os.getenv("EVOLUTION_API_URL", ""),
            "api_key": _os.getenv("EVOLUTION_API_KEY", ""),
            "instance_name": channel_row["instance_name"],
            "phone_number": channel_row["phone_number"],
            "webhook_secret": channel_row["webhook_secret"],
        }

        adapter = WhatsAppAdapter(business_id, config)
        message = _render_template(template_key, data)
        success = await adapter.send_message(phone, message)

        # Record notification
        status = "sent" if success else "failed"
        await _record_notification(
            db, business_id, "whatsapp", "evolution_api",
            target_type, target_id, phone, None,
            template_key, data, status, 0.0,
        )

        return {"sent": success, "channel": "whatsapp", "status": status}

    except Exception as e:
        logger.warning("[NOTIFY] WhatsApp send failed: %s", e)
        return {"sent": False, "error": str(e)}


# ============================================
# SMS — via Twilio (sms_service)
# ============================================

async def send_sms_notification(
    db: Database,
    business_id: str,
    phone: Optional[str],
    template_key: str,
    data: dict,
    target_type: str = "client",
    target_id: Optional[str] = None,
) -> dict:
    """Send notification via SMS using the Twilio sms_service."""
    if not phone:
        return {"sent": False, "error": "No phone number"}

    try:
        from app.modules.cleaning.services.sms_service import send_template_sms

        result = await send_template_sms(
            db, business_id, phone, template_key, data,
            target_type=target_type, target_id=target_id,
        )
        return {
            "sent": result.get("success", False),
            "channel": "sms",
            "status": result.get("status", "failed"),
            "cost": result.get("cost", 0),
            "details": result,
        }
    except ImportError:
        logger.warning("[NOTIFY] SMS service not available")
        return {"sent": False, "error": "SMS service not available"}
    except Exception as e:
        logger.warning("[NOTIFY] SMS send failed: %s", e)
        return {"sent": False, "error": str(e)}


# ============================================
# PUSH — via VAPID Web Push
# ============================================

async def send_push(
    db: Database,
    business_id: str,
    user_id: Optional[str],
    title: str,
    body: str,
    target_type: str = "client",
    target_id: Optional[str] = None,
) -> dict:
    """Send a push notification via VAPID Web Push."""
    if not user_id:
        return {"sent": False, "error": "No user_id for push"}

    try:
        import os
        vapid_private = os.getenv("VAPID_PRIVATE_KEY", "")
        vapid_email = os.getenv("VAPID_CONTACT_EMAIL", "")

        if not vapid_private:
            return {"sent": False, "error": "VAPID not configured"}

        # Get push subscriptions for user
        subs = await db.pool.fetch(
            """SELECT subscription_json FROM cleaning_push_subscriptions
               WHERE user_id = $1 AND business_id = $2 AND is_active = true""",
            user_id, business_id,
        )
        if not subs:
            return {"sent": False, "error": "No push subscription"}

        from pywebpush import webpush, WebPushException

        payload = json.dumps({
            "title": title,
            "body": body,
            "icon": "/cleaning/static/img/icon-192.png",
            "badge": "/cleaning/static/img/badge-72.png",
            "data": {"url": f"/cleaning/app.html"},
        })

        sent_count = 0
        for sub_row in subs:
            sub_info = sub_row["subscription_json"]
            if isinstance(sub_info, str):
                sub_info = json.loads(sub_info)
            try:
                webpush(
                    subscription_info=sub_info,
                    data=payload,
                    vapid_private_key=vapid_private,
                    vapid_claims={"sub": f"mailto:{vapid_email}"},
                )
                sent_count += 1
            except WebPushException as e:
                logger.warning("[PUSH] Failed for subscription: %s", e)
                # Mark subscription as inactive if 410 Gone
                if "410" in str(e):
                    await db.pool.execute(
                        """UPDATE cleaning_push_subscriptions
                           SET is_active = false WHERE subscription_json = $1::JSONB""",
                        json.dumps(sub_info),
                    )

        success = sent_count > 0

        await _record_notification(
            db, business_id, "push", "vapid",
            target_type, target_id, None, None,
            "push_notification", {"title": title, "body": body},
            "sent" if success else "failed", 0.0,
        )

        return {"sent": success, "channel": "push", "delivered_to": sent_count}

    except ImportError:
        logger.warning("[NOTIFY] pywebpush not installed")
        return {"sent": False, "error": "Push service not available"}
    except Exception as e:
        logger.warning("[NOTIFY] Push send failed: %s", e)
        return {"sent": False, "error": str(e)}


# ============================================
# EMAIL — via existing email service
# ============================================

async def send_email_notification(
    db: Database,
    business_id: str,
    email: Optional[str],
    subject: str,
    body: str,
    target_type: str = "client",
    target_id: Optional[str] = None,
) -> dict:
    """Send email notification via existing email infrastructure."""
    if not email:
        return {"sent": False, "error": "No email address"}

    try:
        import os
        import smtplib
        from email.mime.text import MIMEText

        smtp_host = os.getenv("SMTP_HOST", "")
        smtp_port = int(os.getenv("SMTP_PORT", "587"))
        smtp_user = os.getenv("SMTP_USER", "")
        smtp_pass = os.getenv("SMTP_PASSWORD", "")
        from_email = os.getenv("SMTP_FROM_EMAIL", smtp_user)

        if not smtp_host or not smtp_user:
            return {"sent": False, "error": "Email not configured"}

        msg = MIMEText(body, "plain")
        msg["Subject"] = subject
        msg["From"] = from_email
        msg["To"] = email

        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.send_message(msg)

        await _record_notification(
            db, business_id, "email", "smtp",
            target_type, target_id, None, email,
            "email_notification", {"subject": subject},
            "sent", 0.0,
        )

        return {"sent": True, "channel": "email"}

    except Exception as e:
        logger.warning("[NOTIFY] Email send failed: %s", e)
        return {"sent": False, "error": str(e)}


# ============================================
# CONTACT RESOLUTION
# ============================================

async def _resolve_contact(
    db: Database,
    business_id: str,
    target_type: str,
    target_id: str,
) -> Optional[dict]:
    """Resolve contact info (phone, email, user_id) for a target."""
    if target_type == "client":
        row = await db.pool.fetchrow(
            """SELECT id, phone, email, user_id
               FROM cleaning_clients
               WHERE id = $1 AND business_id = $2""",
            target_id, business_id,
        )
        if row:
            return {
                "phone": row["phone"],
                "email": row["email"],
                "user_id": str(row["user_id"]) if row.get("user_id") else None,
            }

    elif target_type == "cleaner":
        row = await db.pool.fetchrow(
            """SELECT m.id, m.phone, m.email, m.user_id
               FROM cleaning_team_members m
               WHERE m.id = $1 AND m.business_id = $2""",
            target_id, business_id,
        )
        if row:
            return {
                "phone": row["phone"],
                "email": row["email"],
                "user_id": str(row["user_id"]) if row.get("user_id") else None,
            }

    elif target_type == "owner":
        row = await db.pool.fetchrow(
            """SELECT u.id, u.email
               FROM users u
               JOIN businesses b ON b.owner_id = u.id
               WHERE b.id = $1""",
            business_id,
        )
        if row:
            return {
                "phone": None,
                "email": row["email"],
                "user_id": str(row["id"]),
            }

    return None


# ============================================
# NOTIFICATION HISTORY
# ============================================

async def get_notifications(
    db: Database,
    business_id: str,
    channel: Optional[str] = None,
    status: Optional[str] = None,
    page: int = 1,
    page_size: int = 50,
) -> dict:
    """List sent notifications with filters."""
    conditions = ["business_id = $1"]
    params: list = [business_id]
    idx = 2

    if channel:
        conditions.append(f"channel = ${idx}")
        params.append(channel)
        idx += 1

    if status:
        conditions.append(f"status = ${idx}")
        params.append(status)
        idx += 1

    where = " AND ".join(conditions)

    total = await db.pool.fetchval(
        f"SELECT COUNT(*) FROM cleaning_notifications WHERE {where}",
        *params,
    )

    offset = (page - 1) * page_size
    rows = await db.pool.fetch(
        f"""SELECT * FROM cleaning_notifications
            WHERE {where}
            ORDER BY created_at DESC
            LIMIT {page_size} OFFSET {offset}""",
        *params,
    )

    notifications = []
    for r in rows:
        d = dict(r)
        for key in ["id", "business_id", "target_id"]:
            if d.get(key):
                d[key] = str(d[key])
        for key in ["created_at", "sent_at"]:
            if d.get(key):
                d[key] = str(d[key])
        if d.get("cost"):
            d["cost"] = float(d["cost"])
        if d.get("payload_json") and isinstance(d["payload_json"], str):
            try:
                d["payload_json"] = json.loads(d["payload_json"])
            except (json.JSONDecodeError, TypeError):
                pass
        notifications.append(d)

    return {"notifications": notifications, "total": total, "page": page}


# ============================================
# DELIVERY STATS
# ============================================

async def get_notification_stats(
    db: Database,
    business_id: str,
) -> dict:
    """Delivery stats by channel."""
    rows = await db.pool.fetch(
        """SELECT channel,
                  COUNT(*) AS total,
                  COUNT(*) FILTER (WHERE status = 'sent') AS sent,
                  COUNT(*) FILTER (WHERE status = 'delivered') AS delivered,
                  COUNT(*) FILTER (WHERE status = 'failed') AS failed,
                  COALESCE(SUM(cost), 0) AS total_cost
           FROM cleaning_notifications
           WHERE business_id = $1
             AND created_at >= DATE_TRUNC('month', CURRENT_DATE)
           GROUP BY channel""",
        business_id,
    )

    stats = {}
    for r in rows:
        stats[r["channel"]] = {
            "total": r["total"],
            "sent": r["sent"],
            "delivered": r["delivered"],
            "failed": r["failed"],
            "total_cost": float(r["total_cost"]),
        }

    # SMS quota
    from app.modules.cleaning.services.sms_service import check_sms_quota
    sms_quota = await check_sms_quota(db, business_id)
    stats["sms_quota"] = sms_quota

    return stats


# ============================================
# TEMPLATES
# ============================================

NOTIFICATION_TEMPLATES = {
    "booking_confirmation": {
        "title": "Booking Confirmed",
        "body": "Your cleaning is confirmed for {date} at {time} at {address}.",
    },
    "reminder_24h": {
        "title": "Cleaning Tomorrow",
        "body": "Reminder: Your cleaning is tomorrow ({date}) at {time}. Our team will arrive at {address}.",
    },
    "invoice_sent": {
        "title": "Invoice Ready",
        "body": "Invoice {invoice_number} for ${total} is ready. Due: {due_date}. Pay online: {payment_url}",
    },
    "payment_reminder": {
        "title": "Payment Reminder",
        "body": "Invoice {invoice_number} is {days_overdue} days overdue. Balance: ${balance_due}.",
    },
    "schedule_changed": {
        "title": "Schedule Update",
        "body": "Your cleaning has been rescheduled to {new_date} at {new_time}.",
    },
    "checkin_alert": {
        "title": "Team Arrived",
        "body": "Your cleaning team has arrived and started working at {address}.",
    },
}


def _template_title(template_key: str) -> str:
    """Get the title for a template."""
    tmpl = NOTIFICATION_TEMPLATES.get(template_key, {})
    return tmpl.get("title", "Xcleaners Notification")


def _render_template(template_key: str, data: dict) -> str:
    """Render a notification template with data."""
    tmpl = NOTIFICATION_TEMPLATES.get(template_key, {})
    body = tmpl.get("body", "")
    if not body:
        return str(data)
    try:
        return body.format(**{k: v or "" for k, v in data.items()})
    except KeyError:
        return body


# ============================================
# RECORD NOTIFICATION
# ============================================

async def _record_notification(
    db: Database,
    business_id: str,
    channel: str,
    provider: str,
    target_type: str,
    target_id: Optional[str],
    phone: Optional[str],
    email: Optional[str],
    template_key: str,
    data: dict,
    status: str,
    cost: float,
):
    """Record a notification in the cleaning_notifications table."""
    try:
        await db.pool.execute(
            """INSERT INTO cleaning_notifications
               (business_id, channel, provider, target_type, target_id,
                phone_number, email_address, template_key, payload_json,
                status, cost, sent_at)
               VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9::JSONB, $10, $11,
                       CASE WHEN $10 = 'sent' THEN NOW() ELSE NULL END)""",
            business_id, channel, provider, target_type, target_id,
            phone, email, template_key, json.dumps(data),
            status, cost,
        )
    except Exception as e:
        logger.error("[NOTIFY] Failed to record notification: %s", e)
