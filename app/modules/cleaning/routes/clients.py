"""
Xcleaners v3 — Client & Schedule Routes (S2.3).

Endpoints:
  GET    /api/v1/clean/{slug}/clients             — list clients (paginated, searchable, filterable)
  POST   /api/v1/clean/{slug}/clients             — create client
  GET    /api/v1/clean/{slug}/clients/{id}         — client detail with property + schedules + booking history
  PATCH  /api/v1/clean/{slug}/clients/{id}         — update client
  DELETE /api/v1/clean/{slug}/clients/{id}         — soft delete
  GET    /api/v1/clean/{slug}/clients/{id}/schedules              — list recurring schedules
  POST   /api/v1/clean/{slug}/clients/{id}/schedules              — create recurring schedule
  PATCH  /api/v1/clean/{slug}/clients/{id}/schedules/{sched_id}   — update schedule
  DELETE /api/v1/clean/{slug}/clients/{id}/schedules/{sched_id}   — cancel schedule
  POST   /api/v1/clean/{slug}/clients/{id}/schedules/{sched_id}/pause  — pause schedule
  POST   /api/v1/clean/{slug}/clients/{id}/schedules/{sched_id}/resume — resume schedule
  POST   /api/v1/clean/{slug}/clients/{id}/invite  — invite client to create account (homeowner role)

All protected by require_role("owner").
"""

import csv
import io
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from fastapi.responses import Response
from pydantic import ValidationError

from app.database import get_db, Database
from app.modules.cleaning.middleware.role_guard import require_role
from app.modules.cleaning.models.clients import (
    CleaningClientCreate,
    CleaningClientUpdate,
    CleaningClientResponse,
    CleaningClientListResponse,
)
from app.modules.cleaning.models.schedules import (
    ClientScheduleCreate,
    ClientScheduleUpdate,
    ClientScheduleResponse,
    ClientScheduleListResponse,
)
from app.modules.cleaning.services.client_service import (
    create_client,
    get_client,
    update_client,
    delete_client,
    list_clients,
)
from app.modules.cleaning.services.schedule_service import (
    create_schedule,
    update_schedule,
    cancel_schedule,
    list_client_schedules,
    pause_schedule,
    resume_schedule,
)
from app.modules.cleaning.services.stripe_connect_service import (
    create_setup_intent_for_client,
    list_saved_payment_methods,
    detach_payment_method,
)

import os as _os

STRIPE_SECRET_KEY_PRESENT = bool(_os.getenv("STRIPE_SECRET_KEY", ""))
STRIPE_PUBLISHABLE_KEY = _os.getenv("STRIPE_PUBLISHABLE_KEY", "")

logger = logging.getLogger("xcleaners.client_routes")

router = APIRouter(
    prefix="/api/v1/clean/{slug}/clients",
    tags=["Xcleaners Clients"],
)


# ============================================
# GET /api/v1/clean/{slug}/clients
# ============================================

@router.get("", response_model=CleaningClientListResponse)
async def api_list_clients(
    slug: str,
    search: Optional[str] = Query(None, description="Search by name, email, phone, address"),
    status: Optional[str] = Query(None, description="Filter by status: active, paused, former"),
    frequency: Optional[str] = Query(None, description="Filter by schedule frequency"),
    team_id: Optional[str] = Query(None, description="Filter by preferred team ID"),
    tag: Optional[str] = Query(None, description="Filter by tag"),
    has_balance: Optional[bool] = Query(None, description="Filter clients with outstanding balance"),
    sort_by: str = Query("last_name", description="Sort column"),
    sort_order: str = Query("asc", description="Sort direction: asc or desc"),
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(25, ge=1, le=100, description="Items per page"),
    user: dict = Depends(require_role("owner")),
    db: Database = Depends(get_db),
):
    """List clients with search, filter, sort, and pagination."""
    result = await list_clients(
        db=db,
        business_id=user["business_id"],
        search=search,
        status=status,
        frequency=frequency,
        team_id=team_id,
        tag=tag,
        has_balance=has_balance,
        sort_by=sort_by,
        sort_order=sort_order,
        page=page,
        per_page=per_page,
    )
    return result


# ============================================
# POST /api/v1/clean/{slug}/clients
# ============================================

@router.post("", response_model=CleaningClientResponse, status_code=201)
async def api_create_client(
    slug: str,
    body: CleaningClientCreate,
    user: dict = Depends(require_role("owner")),
    db: Database = Depends(get_db),
):
    """Create a new cleaning client."""
    data = body.model_dump(exclude_none=True)
    result = await create_client(db, user["business_id"], data)

    # Check for duplicate detection
    if result.get("duplicate"):
        raise HTTPException(
            status_code=409,
            detail={
                "message": f"Duplicate client detected: {result['match_field']} already exists",
                "existing_client_id": result["existing_client_id"],
                "match_field": result["match_field"],
            },
        )

    # Check for structured errors from the service (constraint violations etc)
    if result.get("error"):
        raise HTTPException(status_code=result["status"], detail=result["message"])

    return result


# ============================================
# GET /api/v1/clean/{slug}/clients/{client_id}
# ============================================

@router.get("/{client_id}", response_model=CleaningClientResponse)
async def api_get_client(
    slug: str,
    client_id: str,
    user: dict = Depends(require_role("owner")),
    db: Database = Depends(get_db),
):
    """Get client detail with property info, schedules count, and financial summary."""
    result = await get_client(db, user["business_id"], client_id)
    if not result:
        raise HTTPException(status_code=404, detail="Client not found")
    return result


# ============================================
# PATCH /api/v1/clean/{slug}/clients/{client_id}
# ============================================

@router.patch("/{client_id}", response_model=CleaningClientResponse)
async def api_update_client(
    slug: str,
    client_id: str,
    body: CleaningClientUpdate,
    user: dict = Depends(require_role("owner")),
    db: Database = Depends(get_db),
):
    """Update client fields. Setting status to 'paused' suspends all schedules."""
    data = body.model_dump(exclude_none=True)
    if not data:
        raise HTTPException(status_code=400, detail="No fields to update")

    result = await update_client(db, user["business_id"], client_id, data)
    if not result:
        raise HTTPException(status_code=404, detail="Client not found")
    return result


# ============================================
# DELETE /api/v1/clean/{slug}/clients/{client_id}
# ============================================

@router.delete("/{client_id}", status_code=204)
async def api_delete_client(
    slug: str,
    client_id: str,
    user: dict = Depends(require_role("owner")),
    db: Database = Depends(get_db),
):
    """Soft delete a client (sets status to blocked, cancels schedules)."""
    deleted = await delete_client(db, user["business_id"], client_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Client not found or already deleted")
    return None


# ============================================
# GET /api/v1/clean/{slug}/clients/{client_id}/schedules
# ============================================

@router.get("/{client_id}/schedules", response_model=ClientScheduleListResponse)
async def api_list_schedules(
    slug: str,
    client_id: str,
    include_cancelled: bool = Query(False, description="Include cancelled schedules"),
    user: dict = Depends(require_role("owner")),
    db: Database = Depends(get_db),
):
    """List recurring schedules for a client."""
    result = await list_client_schedules(
        db, user["business_id"], client_id, include_cancelled
    )
    return result


# ============================================
# POST /api/v1/clean/{slug}/clients/{client_id}/schedules
# ============================================

@router.post(
    "/{client_id}/schedules",
    response_model=ClientScheduleResponse,
    status_code=201,
)
async def api_create_schedule(
    slug: str,
    client_id: str,
    body: ClientScheduleCreate,
    user: dict = Depends(require_role("owner")),
    db: Database = Depends(get_db),
):
    """Create a recurring schedule for a client."""
    data = body.model_dump(exclude_none=True)
    # Override client_id from URL path
    data["client_id"] = client_id

    result = await create_schedule(db, user["business_id"], client_id, data)

    if result.get("error"):
        raise HTTPException(
            status_code=result.get("status_code", 400),
            detail=result["error"],
        )

    return result


# ============================================
# PATCH /api/v1/clean/{slug}/clients/{client_id}/schedules/{sched_id}
# ============================================

@router.patch(
    "/{client_id}/schedules/{sched_id}",
    response_model=ClientScheduleResponse,
)
async def api_update_schedule(
    slug: str,
    client_id: str,
    sched_id: str,
    body: ClientScheduleUpdate,
    user: dict = Depends(require_role("owner")),
    db: Database = Depends(get_db),
):
    """Update a recurring schedule."""
    data = body.model_dump(exclude_none=True)
    if not data:
        raise HTTPException(status_code=400, detail="No fields to update")

    result = await update_schedule(db, user["business_id"], sched_id, data)
    if not result:
        raise HTTPException(status_code=404, detail="Schedule not found")
    return result


# ============================================
# DELETE /api/v1/clean/{slug}/clients/{client_id}/schedules/{sched_id}
# ============================================

@router.delete("/{client_id}/schedules/{sched_id}", status_code=204)
async def api_cancel_schedule(
    slug: str,
    client_id: str,
    sched_id: str,
    user: dict = Depends(require_role("owner")),
    db: Database = Depends(get_db),
):
    """Cancel a recurring schedule (soft delete)."""
    cancelled = await cancel_schedule(db, user["business_id"], sched_id)
    if not cancelled:
        raise HTTPException(status_code=404, detail="Schedule not found or already cancelled")
    return None


# ============================================
# POST /api/v1/clean/{slug}/clients/{client_id}/schedules/{sched_id}/pause
# ============================================

@router.post(
    "/{client_id}/schedules/{sched_id}/pause",
    response_model=ClientScheduleResponse,
)
async def api_pause_schedule(
    slug: str,
    client_id: str,
    sched_id: str,
    user: dict = Depends(require_role("owner")),
    db: Database = Depends(get_db),
):
    """Pause an active schedule."""
    result = await pause_schedule(db, user["business_id"], sched_id)
    if not result:
        raise HTTPException(status_code=404, detail="Schedule not found or not active")
    return result


# ============================================
# POST /api/v1/clean/{slug}/clients/{client_id}/schedules/{sched_id}/resume
# ============================================

@router.post(
    "/{client_id}/schedules/{sched_id}/resume",
    response_model=ClientScheduleResponse,
)
async def api_resume_schedule(
    slug: str,
    client_id: str,
    sched_id: str,
    user: dict = Depends(require_role("owner")),
    db: Database = Depends(get_db),
):
    """Resume a paused schedule (recomputes next_occurrence)."""
    result = await resume_schedule(db, user["business_id"], sched_id)
    if not result:
        raise HTTPException(status_code=404, detail="Schedule not found or not paused")
    return result


# ============================================
# POST /api/v1/clean/{slug}/clients/{client_id}/invite
# ============================================

@router.post("/{client_id}/invite")
async def api_invite_client(
    slug: str,
    client_id: str,
    user: dict = Depends(require_role("owner")),
    db: Database = Depends(get_db),
):
    """
    Invite a client to create an account with homeowner role.
    Creates an invitation token and (in future) sends email.
    """
    import uuid

    client = await db.pool.fetchrow(
        "SELECT id, email, first_name, last_name FROM cleaning_clients WHERE id = $1 AND business_id = $2",
        client_id, user["business_id"],
    )
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    if not client["email"]:
        raise HTTPException(status_code=400, detail="Client has no email address. Add an email first.")

    # Check if already has a user account linked
    if await db.pool.fetchval(
        "SELECT user_id FROM cleaning_clients WHERE id = $1 AND user_id IS NOT NULL",
        client_id,
    ):
        raise HTTPException(status_code=409, detail="Client already has an account linked")

    # Check if already has a pending invitation
    existing_invite = await db.pool.fetchrow(
        """SELECT id FROM cleaning_user_roles
           WHERE business_id = $1 AND role = 'homeowner'
           AND (SELECT id FROM users WHERE email = $2) = user_id""",
        user["business_id"], client["email"],
    )
    if existing_invite:
        raise HTTPException(status_code=409, detail="An invitation for this email already exists")

    # Generate invitation token and persist it so accept-client-invite can validate.
    # Expires in 7 days; callers can re-invite to refresh.
    from datetime import datetime, timedelta, timezone
    invite_token = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(days=7)

    await db.pool.execute(
        """UPDATE cleaning_clients
           SET invite_token = $1::uuid,
               invite_sent_at = $2,
               invite_expires_at = $3,
               updated_at = NOW()
           WHERE id = $4 AND business_id = $5""",
        invite_token, now, expires_at, client_id, user["business_id"],
    )

    logger.info(
        "[INVITE] Client %s (%s) invited to business %s with token %s (expires %s)",
        client_id, client["email"], user["business_id"], invite_token, expires_at.isoformat(),
    )

    # Best-effort email send — failure does not block the invite flow
    try:
        from app.modules.cleaning.services.email_service import send_homeowner_invite
        email_result = await send_homeowner_invite(db, client_id, invite_token)
        if email_result.get("sent"):
            logger.info(
                "[INVITE] Email delivered to %s via Resend (id=%s)",
                client["email"], email_result.get("id"),
            )
        else:
            logger.warning(
                "[INVITE] Email delivery failed for %s: %s",
                client["email"], email_result.get("error"),
            )
    except Exception as e:  # pragma: no cover — email failures never block invitation
        logger.exception("[INVITE] Unexpected error sending email to %s", client["email"])
        email_result = {"sent": False, "error": str(e)}

    return {
        "status": "invited",
        "client_id": client_id,
        "email": client["email"],
        "invite_token": invite_token,
        "invite_url": f"/cleaning/app#/register/invite/{invite_token}",
        "email_sent": email_result.get("sent", False),
        "message": f"Invitation sent to {client['first_name']} {client['last_name'] or ''}".strip(),
    }


# ============================================================================
# PAYMENT METHODS (Stripe Connect setup-intent flow) [3S-1]
# ============================================================================
# Owner-assisted card collection: Ana collects card on behalf of a client via
# Stripe Elements (phone or in-person). Card is saved on the BUSINESS's
# connected Stripe account (not platform) — so charges go directly to owner.
#
# Endpoints:
#   POST   /clients/{id}/setup-intent          → client_secret for Stripe Elements
#   GET    /clients/{id}/payment-methods       → list saved cards
#   DELETE /clients/{id}/payment-methods/{pm}  → remove a saved card


async def _require_connected_stripe(db: Database, business_id) -> str:
    """Fetch stripe_account_id for business or raise HTTPException."""
    row = await db.pool.fetchrow(
        "SELECT stripe_account_id, stripe_charges_enabled FROM businesses WHERE id = $1",
        business_id,
    )
    if not row or not row["stripe_account_id"]:
        raise HTTPException(
            status_code=409,
            detail="Business has not connected Stripe yet. Complete onboarding first.",
        )
    if not STRIPE_SECRET_KEY_PRESENT:
        raise HTTPException(
            status_code=503,
            detail="Payments are not configured on this server.",
        )
    return row["stripe_account_id"]


async def _fetch_client_or_404(db: Database, business_id, client_id: str) -> dict:
    row = await db.pool.fetchrow(
        """
        SELECT id, business_id, first_name, last_name, email,
               stripe_customer_id
          FROM cleaning_clients
         WHERE id = $1 AND business_id = $2
        """,
        client_id, business_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail="Client not found")
    return dict(row)


@router.post("/{client_id}/setup-intent", status_code=201)
async def api_create_client_setup_intent(
    slug: str,
    client_id: str,
    user: dict = Depends(require_role("owner")),
    db: Database = Depends(get_db),
):
    """
    Create a Stripe SetupIntent to collect a card on file for the client.

    Returns client_secret for Stripe Elements. On first call, creates a Stripe
    Customer and persists its ID in cleaning_clients.stripe_customer_id.
    Subsequent calls reuse the existing customer (saves another PM to same customer).
    """
    stripe_account_id = await _require_connected_stripe(db, user["business_id"])
    client = await _fetch_client_or_404(db, user["business_id"], client_id)

    client_name = " ".join(
        p for p in (client.get("first_name"), client.get("last_name")) if p
    ).strip() or "Client"
    client_email = client.get("email") or ""

    try:
        result = await create_setup_intent_for_client(
            connected_account_id=stripe_account_id,
            client_email=client_email,
            client_name=client_name,
            client_metadata={
                "xcleaners_client_id": str(client["id"]),
                "xcleaners_business_id": str(client["business_id"]),
            },
            existing_customer_id=client.get("stripe_customer_id"),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception:
        logger.exception("setup_intent: Stripe error for client %s", client_id)
        raise HTTPException(status_code=502, detail="Upstream payment provider error")

    # Persist customer_id on first successful call
    if not client.get("stripe_customer_id"):
        await db.pool.execute(
            "UPDATE cleaning_clients SET stripe_customer_id = $1 WHERE id = $2",
            result["customer_id"], client_id,
        )

    return {
        "client_secret": result["client_secret"],
        "customer_id": result["customer_id"],
        "setup_intent_id": result["setup_intent_id"],
        "publishable_key": STRIPE_PUBLISHABLE_KEY,
        "stripe_account_id": stripe_account_id,
    }


@router.get("/{client_id}/payment-methods")
async def api_list_client_payment_methods(
    slug: str,
    client_id: str,
    user: dict = Depends(require_role("owner")),
    db: Database = Depends(get_db),
):
    """List saved payment methods (cards) for a client."""
    stripe_account_id = await _require_connected_stripe(db, user["business_id"])
    client = await _fetch_client_or_404(db, user["business_id"], client_id)

    if not client.get("stripe_customer_id"):
        return {"payment_methods": []}

    try:
        methods = await list_saved_payment_methods(
            stripe_account_id, client["stripe_customer_id"],
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception:
        logger.exception("list_pms: Stripe error for client %s", client_id)
        raise HTTPException(status_code=502, detail="Upstream payment provider error")

    return {"payment_methods": methods}


# ============================================================================
# CSV IMPORT (bulk client onboarding) [3S-3]
# ============================================================================
# Ana uploads CSV (e.g., Launch27 export or Google Sheets) → system imports in
# batch. Reuses client_service.create_client per row to keep validation + dup
# detection consistent with single-POST flow.

_IMPORT_REQUIRED_HEADERS = [
    "first_name", "last_name", "email", "phone",
    "address_line1", "city", "state", "zip_code", "country",
]
_IMPORT_OPTIONAL_HEADERS = [
    "notes", "preferred_day", "property_type", "bedrooms", "bathrooms",
    "phone_secondary", "preferred_contact", "billing_address", "internal_notes",
]
_IMPORT_ALL_HEADERS = _IMPORT_REQUIRED_HEADERS + _IMPORT_OPTIONAL_HEADERS
_IMPORT_MAX_ROWS = 500


def _normalize_headers(headers) -> list[str]:
    """Lowercase + strip each column header for case-insensitive matching."""
    return [(h or "").strip().lower() for h in headers]


def _coerce_row_types(row: dict) -> dict:
    """Cast numeric fields where present; empty strings → None."""
    cleaned = {}
    for k, v in row.items():
        if v is None:
            cleaned[k] = None
            continue
        v = v.strip() if isinstance(v, str) else v
        if v == "":
            cleaned[k] = None
            continue
        if k in ("bedrooms",):
            try:
                cleaned[k] = int(v)
            except (ValueError, TypeError):
                cleaned[k] = v  # let Pydantic reject
        elif k in ("bathrooms",):
            try:
                cleaned[k] = float(v)
            except (ValueError, TypeError):
                cleaned[k] = v
        else:
            cleaned[k] = v
    return cleaned


@router.post("/import")
async def api_import_clients_csv(
    slug: str,
    file: UploadFile = File(..., description="CSV file with client data"),
    user: dict = Depends(require_role("owner")),
    db: Database = Depends(get_db),
):
    """
    Bulk import clients from a CSV file.

    Required columns: first_name, last_name, email, phone, address_line1,
                      city, state, zip_code, country
    Optional columns: notes, preferred_day, property_type, bedrooms, bathrooms,
                      phone_secondary, preferred_contact, billing_address, internal_notes

    Returns: {imported, skipped: [...], errors: [...], total_rows}
      - skipped: duplicate emails or phones (not a hard fail)
      - errors:  validation failures or DB errors per row
    """
    filename = (file.filename or "").lower()
    if filename and not filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="File must be a .csv")

    # Read + decode
    try:
        raw = await file.read()
        text = raw.decode("utf-8-sig")  # BOM-tolerant
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="File must be UTF-8 encoded")

    reader = csv.reader(io.StringIO(text))
    try:
        header_row = next(reader)
    except StopIteration:
        raise HTTPException(status_code=400, detail="CSV is empty (no header row)")

    normalized_headers = _normalize_headers(header_row)
    missing = [h for h in _IMPORT_REQUIRED_HEADERS if h not in normalized_headers]
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"Missing required columns: {', '.join(missing)}",
        )

    # Map index → known column name (ignore unknown columns silently)
    col_map: dict[int, str] = {
        idx: h for idx, h in enumerate(normalized_headers) if h in _IMPORT_ALL_HEADERS
    }

    imported = 0
    skipped: list[dict] = []
    errors: list[dict] = []
    total_rows = 0

    for row_num, raw_row in enumerate(reader, start=2):  # row 1 is header
        total_rows += 1
        if total_rows > _IMPORT_MAX_ROWS:
            errors.append({
                "row": row_num,
                "reason": f"Exceeded max {_IMPORT_MAX_ROWS} rows per upload; stopping here.",
            })
            break

        row_dict: dict[str, Optional[str]] = {}
        for idx, col_name in col_map.items():
            row_dict[col_name] = raw_row[idx] if idx < len(raw_row) else None

        row_dict = _coerce_row_types(row_dict)

        # Skip fully-empty rows (trailing blanks in spreadsheets)
        if not any(v for v in row_dict.values()):
            total_rows -= 1  # don't count blank trailing rows
            continue

        # Default source for imported clients
        row_dict.setdefault("source", "import")

        # Validate with Pydantic (same rules as POST /clients)
        try:
            model = CleaningClientCreate(**row_dict)
        except ValidationError as ve:
            msgs = "; ".join(
                f"{'.'.join(str(p) for p in err['loc'])}: {err['msg']}"
                for err in ve.errors()
            )
            errors.append({"row": row_num, "reason": f"Validation failed — {msgs}"})
            continue

        data = model.model_dump(exclude_none=True)

        try:
            result = await create_client(db, user["business_id"], data)
        except Exception as exc:
            logger.exception("import_clients: unexpected error on row %d", row_num)
            errors.append({"row": row_num, "reason": f"Internal error: {exc}"})
            continue

        if result.get("duplicate"):
            skipped.append({
                "row": row_num,
                "email": row_dict.get("email"),
                "phone": row_dict.get("phone"),
                "reason": f"duplicate_{result.get('match_field', 'match')}",
                "existing_client_id": result.get("existing_client_id"),
            })
            continue
        if result.get("error"):
            errors.append({
                "row": row_num,
                "reason": result.get("message", "unknown error"),
            })
            continue

        imported += 1

    return {
        "imported": imported,
        "skipped": skipped,
        "errors": errors,
        "total_rows": total_rows,
    }


@router.get("/import/template")
async def api_download_import_template(
    slug: str,
    user: dict = Depends(require_role("owner")),
):
    """Return a CSV template with all supported columns + 1 example row."""
    example_row = {
        "first_name": "Jane",
        "last_name": "Doe",
        "email": "jane@example.com",
        "phone": "+1-555-0100",
        "address_line1": "123 Main St",
        "city": "New Orleans",
        "state": "LA",
        "zip_code": "70112",
        "country": "US",
        "notes": "Prefers morning cleanings",
        "preferred_day": "tuesday",
        "property_type": "house",
        "bedrooms": "3",
        "bathrooms": "2",
        "phone_secondary": "",
        "preferred_contact": "email",
        "billing_address": "",
        "internal_notes": "",
    }
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=_IMPORT_ALL_HEADERS)
    writer.writeheader()
    writer.writerow({k: example_row.get(k, "") for k in _IMPORT_ALL_HEADERS})
    return Response(
        content=buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="clients-template.csv"'},
    )


@router.delete("/{client_id}/payment-methods/{pm_id}", status_code=204)
async def api_detach_client_payment_method(
    slug: str,
    client_id: str,
    pm_id: str,
    user: dict = Depends(require_role("owner")),
    db: Database = Depends(get_db),
):
    """Detach a payment method from the client (removes card from file)."""
    stripe_account_id = await _require_connected_stripe(db, user["business_id"])
    # Ensures client belongs to this business (404 if cross-tenant)
    await _fetch_client_or_404(db, user["business_id"], client_id)

    try:
        await detach_payment_method(stripe_account_id, pm_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception:
        logger.exception("detach_pm: Stripe error for client %s / pm %s", client_id, pm_id)
        raise HTTPException(status_code=502, detail="Upstream payment provider error")

    return None
