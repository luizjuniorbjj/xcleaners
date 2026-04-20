"""
Xcleaners v3 — Invoice Routes (Sprint 4).

Endpoints:
  GET  /api/v1/clean/{slug}/invoices                    — list (filterable, paginated)
  POST /api/v1/clean/{slug}/invoices                    — create from booking
  POST /api/v1/clean/{slug}/invoices/batch              — batch generate
  GET  /api/v1/clean/{slug}/invoices/{id}               — invoice detail
  POST /api/v1/clean/{slug}/invoices/{id}/send          — send to client
  POST /api/v1/clean/{slug}/invoices/{id}/mark-paid     — manual payment
  POST /api/v1/clean/{slug}/invoices/{id}/payment-link  — create Stripe link
  POST /api/v1/clean/{slug}/invoices/{id}/auto-charge   — charge saved card
  POST /api/v1/clean/{slug}/invoices/remind-overdue     — bulk reminders
  GET  /api/v1/clean/{slug}/payments/dashboard          — payment overview
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.database import get_db, Database
from app.modules.cleaning.middleware.role_guard import require_role
from app.modules.cleaning.services.invoice_service import (
    generate_invoice,
    generate_batch_invoices,
    get_invoices,
    get_invoice,
    send_invoice,
    mark_paid,
    create_payment_link,
    auto_charge,
    get_overdue_invoices,
    send_payment_reminders,
    get_payment_dashboard,
)

logger = logging.getLogger("xcleaners.invoice_routes")

router = APIRouter(
    prefix="/api/v1/clean/{slug}",
    tags=["Xcleaners Invoices"],
)


# ============================================
# REQUEST MODELS
# ============================================

class CreateInvoiceRequest(BaseModel):
    booking_id: str


class BatchInvoiceRequest(BaseModel):
    date_from: str = Field(..., description="YYYY-MM-DD start date")
    date_to: str = Field(..., description="YYYY-MM-DD end date")


class MarkPaidRequest(BaseModel):
    method: str = Field(..., pattern=r"^(cash|check|zelle|venmo|other)$")
    amount: float = Field(..., gt=0)
    reference: Optional[str] = None


# ============================================
# LIST INVOICES
# ============================================

@router.get("/invoices")
async def list_invoices(
    slug: str,
    status: Optional[str] = Query(None, description="Filter by status"),
    client_id: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None, description="YYYY-MM-DD"),
    date_to: Optional[str] = Query(None, description="YYYY-MM-DD"),
    search: Optional[str] = Query(None, description="Search client name or invoice #"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    user: dict = Depends(require_role("owner")),
    db: Database = Depends(get_db),
):
    """List invoices with filters and pagination."""
    return await get_invoices(
        db, user["business_id"],
        status=status, client_id=client_id,
        date_from=date_from, date_to=date_to,
        search=search, page=page, page_size=page_size,
    )


# ============================================
# CREATE INVOICE FROM BOOKING
# ============================================

@router.post("/invoices")
async def create_invoice(
    slug: str,
    body: CreateInvoiceRequest,
    user: dict = Depends(require_role("owner")),
    db: Database = Depends(get_db),
):
    """Create an invoice from a completed booking."""
    result = await generate_invoice(db, user["business_id"], body.booking_id)
    if result.get("error"):
        raise HTTPException(
            status_code=result.get("status_code", 400),
            detail=result["error"],
        )
    return result


# ============================================
# BATCH GENERATE
# ============================================

@router.post("/invoices/batch")
async def batch_generate(
    slug: str,
    body: BatchInvoiceRequest,
    user: dict = Depends(require_role("owner")),
    db: Database = Depends(get_db),
):
    """Batch generate invoices for all completed bookings in date range."""
    return await generate_batch_invoices(
        db, user["business_id"], body.date_from, body.date_to,
    )


# ============================================
# INVOICE DETAIL
# ============================================

@router.get("/invoices/{invoice_id}")
async def invoice_detail(
    slug: str,
    invoice_id: str,
    user: dict = Depends(require_role("owner")),
    db: Database = Depends(get_db),
):
    """Get invoice with line items."""
    inv = await get_invoice(db, user["business_id"], invoice_id)
    if not inv:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return inv


# ============================================
# SEND INVOICE
# ============================================

@router.post("/invoices/{invoice_id}/send")
async def send_invoice_route(
    slug: str,
    invoice_id: str,
    user: dict = Depends(require_role("owner")),
    db: Database = Depends(get_db),
):
    """
    Send invoice to client via email/SMS with Stripe payment link.
    Marks invoice status as 'sent' if currently draft.
    """
    result = await send_invoice(db, user["business_id"], invoice_id)
    if result.get("error"):
        raise HTTPException(
            status_code=result.get("status_code", 400),
            detail=result["error"],
        )

    # Create payment link for the notification
    link_result = await create_payment_link(db, user["business_id"], invoice_id)
    payment_url = link_result.get("payment_url")

    # Trigger notification if notification service is available
    try:
        from app.modules.cleaning.services.notification_service import send_notification
        await send_notification(
            db=db,
            business_id=user["business_id"],
            target_type="client",
            target_id=str(result.get("client_id")),
            template_key="invoice_sent",
            data={
                "invoice_number": result.get("invoice_number"),
                "total": result.get("total"),
                "due_date": result.get("due_date"),
                "payment_url": payment_url,
                "client_name": result.get("client_name", ""),
            },
        )
    except (ImportError, Exception) as e:
        logger.warning("[INVOICE] Notification send failed: %s", e)

    # Best-effort direct email via Resend — ensures delivery even if
    # notification_service is not configured. Failure does not block.
    email_sent = False
    if payment_url:
        try:
            from app.modules.cleaning.services.email_service import send_invoice_email
            email_result = await send_invoice_email(db, invoice_id, payment_url=payment_url)
            email_sent = bool(email_result.get("sent"))
            if email_sent:
                logger.info(
                    "[INVOICE] Email delivered for invoice %s via Resend (id=%s)",
                    invoice_id, email_result.get("id"),
                )
            else:
                logger.warning(
                    "[INVOICE] Email delivery failed for invoice %s: %s",
                    invoice_id, email_result.get("error"),
                )
        except Exception as e:  # pragma: no cover
            logger.exception("[INVOICE] Unexpected error sending invoice email %s", invoice_id)

    return {
        "message": "Invoice sent",
        "invoice_id": invoice_id,
        "payment_url": payment_url,
        "email_sent": email_sent,
        "status": result.get("status"),
    }


# ============================================
# MARK PAID
# ============================================

@router.post("/invoices/{invoice_id}/mark-paid")
async def mark_paid_route(
    slug: str,
    invoice_id: str,
    body: MarkPaidRequest,
    user: dict = Depends(require_role("owner")),
    db: Database = Depends(get_db),
):
    """Record a manual payment (cash, check, Zelle, Venmo, other)."""
    result = await mark_paid(
        db, user["business_id"], invoice_id,
        body.method, body.amount, body.reference,
    )
    if result.get("error"):
        raise HTTPException(
            status_code=result.get("status_code", 400),
            detail=result["error"],
        )
    return result


# ============================================
# PAYMENT LINK
# ============================================

@router.post("/invoices/{invoice_id}/payment-link")
async def create_payment_link_route(
    slug: str,
    invoice_id: str,
    user: dict = Depends(require_role("owner")),
    db: Database = Depends(get_db),
):
    """Create a Stripe payment link for the invoice."""
    result = await create_payment_link(db, user["business_id"], invoice_id)
    if result.get("error"):
        raise HTTPException(
            status_code=result.get("status_code", 400),
            detail=result["error"],
        )
    return result


# ============================================
# AUTO-CHARGE
# ============================================

@router.post("/invoices/{invoice_id}/auto-charge")
async def auto_charge_route(
    slug: str,
    invoice_id: str,
    user: dict = Depends(require_role("owner")),
    db: Database = Depends(get_db),
):
    """Charge saved card for recurring clients with card on file."""
    result = await auto_charge(db, user["business_id"], invoice_id)
    if result.get("error"):
        raise HTTPException(
            status_code=result.get("status_code", 400),
            detail=result["error"],
        )
    return result


# ============================================
# REMIND OVERDUE (bulk)
# ============================================

@router.post("/invoices/remind-overdue")
async def remind_overdue_route(
    slug: str,
    user: dict = Depends(require_role("owner")),
    db: Database = Depends(get_db),
):
    """Send payment reminders for all overdue invoices."""
    result = await send_payment_reminders(db, user["business_id"])

    # Send notifications for each overdue invoice
    try:
        from app.modules.cleaning.services.notification_service import send_notification
        for inv in result.get("invoices", []):
            await send_notification(
                db=db,
                business_id=user["business_id"],
                target_type="client",
                target_id=inv.get("invoice_id"),
                template_key="payment_reminder",
                data={
                    "invoice_number": inv.get("invoice_number"),
                    "balance_due": inv.get("balance_due"),
                    "days_overdue": inv.get("days_overdue"),
                    "client_name": inv.get("client_name", ""),
                },
            )
    except (ImportError, Exception) as e:
        logger.warning("[INVOICE] Reminder notifications failed: %s", e)

    return result


# ============================================
# PAYMENT DASHBOARD
# ============================================

@router.get("/payments/dashboard")
async def payment_dashboard_route(
    slug: str,
    user: dict = Depends(require_role("owner")),
    db: Database = Depends(get_db),
):
    """Payment overview: revenue, outstanding, overdue, by method."""
    return await get_payment_dashboard(db, user["business_id"])
