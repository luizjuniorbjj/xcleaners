"""
Xcleaners — ICS (iCalendar RFC 5545) Generator.

Generates .ics calendar event content for a booking, for use as email
attachment. Customer opens email -> opens .ics -> native calendar app
(Google Calendar / Apple Calendar / Outlook) offers "Add event".

Sprint: AI Turbo 2026-04-20 (Bloco 1.7 — Opcao A Google Calendar integration).

Usage:
    from app.utils.ics_generator import build_ics_attachment_for_booking

    attachment = await build_ics_attachment_for_booking(db, booking_id)
    if attachment:
        attachments = [attachment]  # pass to send_email(attachments=...)
"""

from __future__ import annotations

import base64
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from app.database import Database

logger = logging.getLogger("xcleaners.ics_generator")


# Confirmed booking → CONFIRMED in iCal. Draft/pending → TENTATIVE.
# Cancelled → CANCELLED. Others → TENTATIVE as safe default.
_ICS_STATUS_MAP = {
    "draft": "TENTATIVE",
    "scheduled": "CONFIRMED",
    "confirmed": "CONFIRMED",
    "in_progress": "CONFIRMED",
    "completed": "CONFIRMED",
    "cancelled": "CANCELLED",
    "no_show": "CANCELLED",
    "rescheduled": "TENTATIVE",
}


def _ics_escape(text: str) -> str:
    """
    Escape per RFC 5545 section 3.3.11:
      \\ -> \\\\
      ; -> \\;
      , -> \\,
      newlines -> \\n
    """
    if not text:
        return ""
    return (
        text.replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\r\n", "\\n")
        .replace("\n", "\\n")
        .replace("\r", "\\n")
    )


def _fold_line(line: str, limit: int = 73) -> str:
    """
    Fold long lines per RFC 5545 section 3.1 (no longer than 75 octets
    including CRLF; we keep 73 chars to be safe with multi-byte UTF-8).
    Continuation lines are prefixed with a single space.
    """
    if len(line.encode("utf-8")) <= limit:
        return line
    parts = []
    while line:
        chunk = line[:limit]
        line = line[limit:]
        parts.append(chunk)
    return "\r\n ".join(parts)


def _format_date_tz(d, t) -> str:
    """
    Format DTSTART/DTEND value for a date + time combination.
    date objects from asyncpg are datetime.date; times are datetime.time.
    Produces YYYYMMDDTHHMMSS (local time, paired with TZID param).
    """
    if t is None:
        # All-day event fallback — unusual for bookings but safe default.
        return d.strftime("%Y%m%d")
    return f"{d.strftime('%Y%m%d')}T{t.strftime('%H%M%S')}"


def _format_utc_now() -> str:
    """DTSTAMP format: YYYYMMDDTHHMMSSZ in UTC."""
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


async def build_ics_for_booking(db: Database, booking_id: str) -> Optional[str]:
    """
    Build iCalendar VCALENDAR content for the given booking.

    Returns a string with CRLF line endings per RFC 5545, or None if the
    booking is not found or missing critical fields.

    Queries minimal schema — only fields that exist in cleaning_bookings,
    cleaning_clients, cleaning_services, businesses.
    """
    row = await db.pool.fetchrow(
        """
        SELECT
            b.id AS booking_id,
            b.scheduled_date,
            b.scheduled_start,
            b.scheduled_end,
            b.estimated_duration_minutes,
            b.status,
            b.address_line1,
            b.city,
            b.state,
            b.zip_code,
            b.special_instructions,
            s.name AS service_name,
            c.first_name,
            c.last_name,
            c.email AS client_email,
            biz.name AS business_name,
            biz.timezone AS business_timezone
        FROM cleaning_bookings b
        JOIN cleaning_clients c ON c.id = b.client_id
        LEFT JOIN cleaning_services s ON s.id = b.service_id
        LEFT JOIN businesses biz ON biz.id = b.business_id
        WHERE b.id = $1
        """,
        booking_id,
    )

    if not row:
        logger.warning("[ICS] booking not found: %s", booking_id)
        return None
    if not row["scheduled_date"] or not row["scheduled_start"]:
        logger.warning("[ICS] booking missing date/time: %s", booking_id)
        return None

    tz_name = row["business_timezone"] or "America/New_York"
    business_name = row["business_name"] or "Xcleaners"
    service_name = row["service_name"] or "Cleaning Service"
    client_name = f"{row['first_name'] or ''} {row['last_name'] or ''}".strip() or "Client"
    status = _ICS_STATUS_MAP.get(row["status"], "TENTATIVE")

    # Compute end time: prefer scheduled_end; fallback to start + duration
    scheduled_end = row["scheduled_end"]
    if scheduled_end is None:
        duration = row["estimated_duration_minutes"] or 120
        anchor = datetime.combine(row["scheduled_date"], row["scheduled_start"])
        scheduled_end = (anchor + timedelta(minutes=duration)).time()

    # Location: flatten address parts
    location_parts = [
        row["address_line1"],
        row["city"],
        row["state"],
        row["zip_code"],
    ]
    location = ", ".join(p for p in location_parts if p) or ""

    # Description
    description_parts = [
        f"Cleaning service booked via Xcleaners.",
        f"Business: {business_name}",
    ]
    if row["special_instructions"]:
        description_parts.append(f"Notes: {row['special_instructions']}")
    description = "\\n".join(_ics_escape(p) for p in description_parts)

    # Build lines per RFC 5545
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Xcleaners//Scheduling//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "BEGIN:VEVENT",
        f"UID:booking-{row['booking_id']}@xcleaners.app",
        f"DTSTAMP:{_format_utc_now()}",
        f"DTSTART;TZID={tz_name}:{_format_date_tz(row['scheduled_date'], row['scheduled_start'])}",
        f"DTEND;TZID={tz_name}:{_format_date_tz(row['scheduled_date'], scheduled_end)}",
        f"SUMMARY:{_ics_escape(service_name)} — {_ics_escape(business_name)}",
        f"DESCRIPTION:{description}",
        f"STATUS:{status}",
        "TRANSP:OPAQUE",
    ]
    if location:
        lines.append(f"LOCATION:{_ics_escape(location)}")
    if row["client_email"]:
        lines.append(
            f"ATTENDEE;CN={_ics_escape(client_name)};RSVP=FALSE:MAILTO:{row['client_email']}"
        )
    lines.extend([
        "END:VEVENT",
        "END:VCALENDAR",
    ])

    # Fold long lines + CRLF terminate per spec
    folded = [_fold_line(ln) for ln in lines]
    return "\r\n".join(folded) + "\r\n"


async def build_ics_attachment_for_booking(
    db: Database, booking_id: str
) -> Optional[dict]:
    """
    Returns Resend-compatible attachment dict: {filename, content, content_type}.
    `content` is base64-encoded per Resend API. None if booking not buildable.
    """
    ics_content = await build_ics_for_booking(db, booking_id)
    if not ics_content:
        return None

    encoded = base64.b64encode(ics_content.encode("utf-8")).decode("ascii")
    return {
        "filename": f"booking-{booking_id}.ics",
        "content": encoded,
        "content_type": "text/calendar; charset=utf-8; method=PUBLISH",
    }
