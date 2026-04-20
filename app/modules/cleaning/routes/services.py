"""
Xcleaners v3 — Service Catalog Routes.

CRUD endpoints for cleaning services and checklists.
All endpoints require owner role unless noted.

Endpoints:
  GET    /api/v1/clean/{slug}/services               — list services
  POST   /api/v1/clean/{slug}/services               — create service
  GET    /api/v1/clean/{slug}/services/{id}           — get service detail
  PATCH  /api/v1/clean/{slug}/services/{id}           — update service
  DELETE /api/v1/clean/{slug}/services/{id}           — soft-delete (deactivate)
  GET    /api/v1/clean/{slug}/services/{id}/checklists — get checklist
  POST   /api/v1/clean/{slug}/services/{id}/checklists — create/replace checklist
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query

from app.database import get_db, Database
from app.modules.cleaning.middleware.role_guard import require_role
from app.modules.cleaning.models.services import (
    CleaningServiceCreate,
    CleaningServiceListResponse,
    CleaningServiceResponse,
    CleaningServiceUpdate,
)
from app.modules.cleaning.services.catalog_service import (
    create_service,
    delete_service,
    get_checklists,
    get_service,
    list_services,
    save_checklist,
    update_service,
)

logger = logging.getLogger("xcleaners.service_routes")

router = APIRouter(
    prefix="/api/v1/clean/{slug}/services",
    tags=["Xcleaners Services"],
)


# ============================================
# GET /api/v1/clean/{slug}/services
# ============================================

@router.get("", response_model=CleaningServiceListResponse)
async def list_services_route(
    slug: str,
    include_inactive: bool = Query(False, description="Include deactivated services"),
    user: dict = Depends(require_role("owner", "homeowner", "team_lead", "cleaner")),
    db: Database = Depends(get_db),
):
    """
    List cleaning services for this business. Homeowners and crew see the
    active catalog (read-only); owners can optionally include inactive rows.
    """
    # Homeowners and crew never see deactivated services
    if user.get("cleaning_role") != "owner":
        include_inactive = False
    result = await list_services(db, user["business_id"], include_inactive)
    return result


# ============================================
# POST /api/v1/clean/{slug}/services
# ============================================

@router.post("", response_model=CleaningServiceResponse, status_code=201)
async def create_service_route(
    slug: str,
    body: CleaningServiceCreate,
    user: dict = Depends(require_role("owner")),
    db: Database = Depends(get_db),
):
    """Create a new cleaning service."""
    result = await create_service(db, user["business_id"], body.model_dump())
    return result


# ============================================
# GET /api/v1/clean/{slug}/services/{service_id}
# ============================================

@router.get("/{service_id}", response_model=CleaningServiceResponse)
async def get_service_route(
    slug: str,
    service_id: str,
    user: dict = Depends(require_role("owner")),
    db: Database = Depends(get_db),
):
    """Get a single cleaning service by ID."""
    result = await get_service(db, user["business_id"], service_id)
    if not result:
        raise HTTPException(status_code=404, detail="Service not found.")
    return result


# ============================================
# PATCH /api/v1/clean/{slug}/services/{service_id}
# ============================================

@router.patch("/{service_id}", response_model=CleaningServiceResponse)
async def update_service_route(
    slug: str,
    service_id: str,
    body: CleaningServiceUpdate,
    user: dict = Depends(require_role("owner")),
    db: Database = Depends(get_db),
):
    """Update a cleaning service."""
    data = body.model_dump(exclude_unset=True)
    result = await update_service(db, user["business_id"], service_id, data)
    if not result:
        raise HTTPException(status_code=404, detail="Service not found.")
    return result


# ============================================
# DELETE /api/v1/clean/{slug}/services/{service_id}
# ============================================

@router.delete("/{service_id}")
async def delete_service_route(
    slug: str,
    service_id: str,
    user: dict = Depends(require_role("owner")),
    db: Database = Depends(get_db),
):
    """Soft-delete a cleaning service (deactivate). Returns 409 if future bookings exist."""
    # Verify it exists first
    existing = await get_service(db, user["business_id"], service_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Service not found.")

    result = await delete_service(db, user["business_id"], service_id)

    if result.get("conflict"):
        raise HTTPException(status_code=409, detail=result["message"])

    return {"success": True, "message": "Service deactivated."}


# ============================================
# GET /api/v1/clean/{slug}/services/{service_id}/checklists
# ============================================

@router.get("/{service_id}/checklists")
async def get_checklists_route(
    slug: str,
    service_id: str,
    user: dict = Depends(require_role("owner", "team_lead", "cleaner")),
    db: Database = Depends(get_db),
):
    """Get checklist items for a service. Accessible by owner and team roles."""
    # Verify service exists
    existing = await get_service(db, user["business_id"], service_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Service not found.")

    result = await get_checklists(db, user["business_id"], service_id)
    return result


# ============================================
# POST /api/v1/clean/{slug}/services/{service_id}/checklists
# ============================================

@router.post("/{service_id}/checklists")
async def save_checklists_route(
    slug: str,
    service_id: str,
    body: dict,
    user: dict = Depends(require_role("owner")),
    db: Database = Depends(get_db),
):
    """Create or replace checklist for a service. Body: {items: [{name, description, is_required, sort_order}]}"""
    # Verify service exists
    existing = await get_service(db, user["business_id"], service_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Service not found.")

    items = body.get("items", [])
    if not items:
        raise HTTPException(status_code=400, detail="At least one checklist item is required.")

    # Validate items
    for i, item in enumerate(items):
        if not item.get("name"):
            raise HTTPException(
                status_code=400,
                detail=f"Checklist item {i + 1} is missing 'name'.",
            )

    result = await save_checklist(db, user["business_id"], service_id, items)
    return result
