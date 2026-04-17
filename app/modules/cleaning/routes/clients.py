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

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

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

    # Generate invitation token (stored as metadata)
    invite_token = str(uuid.uuid4())

    logger.info(
        "[INVITE] Client %s (%s) invited to business %s with token %s",
        client_id, client["email"], user["business_id"], invite_token,
    )

    return {
        "status": "invited",
        "client_id": client_id,
        "email": client["email"],
        "invite_token": invite_token,
        "invite_url": f"/cleaning/app#/register/invite/{invite_token}",
        "message": f"Invitation ready for {client['first_name']} {client['last_name'] or ''}",
    }
