"""
Xcleaners v3 — Auth Routes.

Endpoints for role resolution (/me), invitation management, and
role listing. All use the existing ClaWtoBusiness auth system --
NO separate auth flow.

Endpoints:
  GET  /api/v1/clean/{slug}/me           — current user's cleaning role info
  POST /api/v1/clean/{slug}/invite       — owner invites a user by email
  POST /api/v1/clean/{slug}/accept-invite — accept invitation with token
  GET  /api/v1/clean/my-roles            — all cleaning roles for current user
"""

import json
import logging
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException

import jwt as pyjwt

from app.auth import get_current_user
from app.config import SECRET_KEY
from app.database import get_db, Database
from app.modules.cleaning.models.auth import (
    PLAN_LIMITS,
    AcceptInviteRequest,
    AcceptInviteResponse,
    CleaningRoleInfo,
    InviteRequest,
    InviteResponse,
    MyRolesResponse,
)
from app.modules.cleaning.middleware.plan_guard import get_business_plan
from app.modules.cleaning.middleware.role_guard import require_role
from app.modules.cleaning.routes.auth_middleware import (
    get_cleaning_role,
    invalidate_role_cache,
)

logger = logging.getLogger("xcleaners.auth_routes")

router = APIRouter(
    prefix="/api/v1/clean",
    tags=["Xcleaners Auth"],
)

# Invitation token expiry
INVITE_TOKEN_EXPIRY_DAYS = 7


# ============================================
# GET /api/v1/clean/{slug}/me
# ============================================

@router.get("/{slug}/me", response_model=CleaningRoleInfo)
async def get_cleaning_me(
    user: dict = Depends(get_cleaning_role),
    db: Database = Depends(get_db),
):
    """
    Get current user's cleaning role, team, and plan info for this business.
    Returns cleaning_role: null if user has no role (not 403).
    """
    # Get user profile info
    profile = await db.pool.fetchrow(
        "SELECT nome, email FROM users WHERE id = $1",
        user["user_id"],
    )

    # Get team name if assigned
    team_name = None
    if user.get("cleaning_team_id"):
        team_name = await db.pool.fetchval(
            "SELECT name FROM cleaning_teams WHERE id = $1",
            user["cleaning_team_id"],
        )

    # Get plan info
    plan = await get_business_plan(user["business_id"], db)

    return CleaningRoleInfo(
        user_id=user["user_id"],
        email=profile["email"] if profile else user["email"],
        name=profile["nome"] if profile else None,
        cleaning_role=user.get("cleaning_role"),
        team_id=user.get("cleaning_team_id"),
        team_name=team_name,
        plan=plan,
        plan_limits=PLAN_LIMITS.get(plan, {}),
    )


# ============================================
# POST /api/v1/clean/{slug}/invite
# ============================================

@router.post("/{slug}/invite", response_model=InviteResponse)
async def invite_user(
    slug: str,
    body: InviteRequest,
    user: dict = Depends(require_role("owner")),
    db: Database = Depends(get_db),
):
    """
    Owner invites a user (cleaner, team_lead, or homeowner) by email.
    Creates a cleaning_user_roles entry with status pending (is_active=false)
    and generates an invitation JWT token.
    """
    business_id = user["business_id"]

    # Validate team_id is provided for team roles
    if body.role in ("team_lead", "cleaner") and not body.team_id:
        raise HTTPException(
            status_code=400,
            detail="team_id is required for team_lead and cleaner roles.",
        )

    # Validate team exists if provided
    if body.team_id:
        team_exists = await db.pool.fetchval(
            "SELECT EXISTS(SELECT 1 FROM cleaning_teams WHERE id = $1 AND business_id = $2)",
            body.team_id,
            business_id,
        )
        if not team_exists:
            raise HTTPException(
                status_code=404,
                detail=f"Team '{body.team_id}' not found in this business.",
            )

    # Check if user already has this role
    existing = await db.pool.fetchrow(
        """
        SELECT id, is_active FROM cleaning_user_roles
        WHERE business_id = $1
          AND role = $2
          AND id IN (
              SELECT cur.id FROM cleaning_user_roles cur
              JOIN users u ON u.id = cur.user_id
              WHERE u.email = $3 AND cur.business_id = $1 AND cur.role = $2
          )
        """,
        business_id,
        body.role,
        body.email,
    )

    if existing and existing["is_active"]:
        raise HTTPException(
            status_code=409,
            detail=f"User {body.email} already has an active '{body.role}' role in this business.",
        )

    # Check if there's a user with this email
    invited_user = await db.pool.fetchrow(
        "SELECT id FROM users WHERE email = $1",
        body.email,
    )

    # Create the role entry (is_active=false until accepted)
    now = datetime.utcnow()
    if invited_user:
        # User exists -- create role entry with user_id
        role_id = await db.pool.fetchval(
            """
            INSERT INTO cleaning_user_roles
                (user_id, business_id, role, team_id, invited_by, invited_at, is_active)
            VALUES ($1, $2, $3, $4, $5, $6, false)
            RETURNING id
            """,
            str(invited_user["id"]),
            business_id,
            body.role,
            body.team_id,
            user["user_id"],
            now,
        )
    else:
        # User doesn't exist yet -- create a placeholder role entry
        # with a NULL user_id that will be linked on acceptance.
        # NOTE: user_id is nullable in DB (migration 017) to support
        # pending invites before the user registers/accepts.
        role_id = await db.pool.fetchval(
            """
            INSERT INTO cleaning_user_roles
                (user_id, business_id, role, team_id, invited_by, invited_at, is_active)
            VALUES (NULL, $1, $2, $3, $4, $5, false)
            RETURNING id
            """,
            business_id,
            body.role,
            body.team_id,
            user["user_id"],
            now,
        )

    role_id = str(role_id)

    # Generate invitation JWT token
    expires_at = now + timedelta(days=INVITE_TOKEN_EXPIRY_DAYS)
    invite_payload = {
        "sub": role_id,
        "type": "cleaning_invite",
        "email": body.email,
        "role": body.role,
        "business_id": business_id,
        "business_slug": slug,
        "team_id": body.team_id,
        "iat": now,
        "exp": expires_at,
    }
    invite_token = pyjwt.encode(invite_payload, SECRET_KEY, algorithm="HS256")

    # Build invite link (PWA will handle this route)
    from app.config import APP_URL
    invite_link = f"{APP_URL}/cleaning/invite?token={invite_token}"

    logger.info(
        "[INVITE] Owner %s invited %s as %s to business %s",
        user["user_id"],
        body.email,
        body.role,
        slug,
    )

    return InviteResponse(
        invite_id=role_id,
        email=body.email,
        role=body.role,
        invite_link=invite_link,
        expires_at=expires_at.isoformat(),
    )


# ============================================
# POST /api/v1/clean/{slug}/accept-invite
# ============================================

@router.post("/{slug}/accept-invite", response_model=AcceptInviteResponse)
async def accept_invite(
    slug: str,
    body: AcceptInviteRequest,
    current_user: dict = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    """
    Accept an invitation to join a cleaning business.
    Validates the invite token, links the user_id to the
    cleaning_user_roles record, and activates the role.
    """
    # Decode and validate the invitation token
    try:
        payload = pyjwt.decode(body.invite_token, SECRET_KEY, algorithms=["HS256"])
    except pyjwt.ExpiredSignatureError:
        raise HTTPException(status_code=400, detail="Invitation has expired.")
    except pyjwt.InvalidTokenError:
        raise HTTPException(status_code=400, detail="Invalid invitation token.")

    if payload.get("type") != "cleaning_invite":
        raise HTTPException(status_code=400, detail="Invalid token type.")

    if payload.get("business_slug") != slug:
        raise HTTPException(
            status_code=400,
            detail="Invitation is for a different business.",
        )

    role_id = payload["sub"]
    invited_email = payload["email"]

    # Verify the current user's email matches the invitation
    if current_user["email"] != invited_email:
        raise HTTPException(
            status_code=403,
            detail=(
                f"This invitation was sent to {invited_email}. "
                f"You are logged in as {current_user['email']}."
            ),
        )

    # Check the role record exists and is pending
    role_row = await db.pool.fetchrow(
        "SELECT id, is_active, role, team_id, business_id FROM cleaning_user_roles WHERE id = $1",
        role_id,
    )

    if not role_row:
        raise HTTPException(status_code=404, detail="Invitation not found.")

    if role_row["is_active"]:
        raise HTTPException(status_code=409, detail="Invitation already accepted.")

    business_id = str(role_row["business_id"])
    now = datetime.utcnow()

    # Activate the role and link user_id
    await db.pool.execute(
        """
        UPDATE cleaning_user_roles
        SET user_id = $1, is_active = true, accepted_at = $2
        WHERE id = $3
        """,
        current_user["user_id"],
        now,
        role_id,
    )

    # Invalidate role cache for this user
    await invalidate_role_cache(business_id, current_user["user_id"])

    # Get business info for response
    biz = await db.pool.fetchrow(
        "SELECT slug, name FROM businesses WHERE id = $1",
        business_id,
    )

    # Get team name if assigned
    team_name = None
    team_id = str(role_row["team_id"]) if role_row["team_id"] else None
    if team_id:
        team_name = await db.pool.fetchval(
            "SELECT name FROM cleaning_teams WHERE id = $1",
            team_id,
        )

    logger.info(
        "[INVITE] User %s accepted role '%s' in business %s",
        current_user["user_id"],
        role_row["role"],
        slug,
    )

    return AcceptInviteResponse(
        role=role_row["role"],
        team_id=team_id,
        team_name=team_name,
        business_slug=biz["slug"] if biz else slug,
        business_name=biz["name"] if biz else slug,
    )


# ============================================
# GET /api/v1/clean/my-roles
# ============================================

@router.get("/my-roles", response_model=MyRolesResponse)
async def get_my_roles(
    current_user: dict = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    """
    Returns all cleaning roles for the current user across all businesses.
    Used for the role-switching UI in the PWA.
    """
    rows = await db.pool.fetch(
        """
        SELECT
            cur.id,
            cur.role,
            cur.team_id,
            cur.business_id,
            cur.is_active,
            cur.created_at,
            b.slug AS business_slug,
            b.name AS business_name,
            b.logo_url AS business_logo,
            t.name AS team_name
        FROM cleaning_user_roles cur
        JOIN businesses b ON b.id = cur.business_id
        LEFT JOIN cleaning_teams t ON t.id = cur.team_id
        WHERE cur.user_id = $1
          AND cur.is_active = true
          AND b.status != 'cancelled'
        ORDER BY b.name, cur.role
        """,
        current_user["user_id"],
    )

    roles = []

    # Virtual super_admin role — if user has platform role 'admin', expose it
    # as a selectable role so the PWA can route them to /admin. Listed FIRST
    # so it becomes the default active role on initial login.
    if current_user.get("role") == "admin":
        roles.append({
            "id": "platform-admin",
            "role": "super_admin",
            "team_id": None,
            "team_name": None,
            "business_id": None,
            "business_slug": "_platform",
            "business_name": "Platform Admin",
            "business_logo": None,
            "created_at": None,
        })

    for row in rows:
        roles.append({
            "id": str(row["id"]),
            "role": row["role"],
            "team_id": str(row["team_id"]) if row["team_id"] else None,
            "team_name": row["team_name"],
            "business_id": str(row["business_id"]),
            "business_slug": row["business_slug"],
            "business_name": row["business_name"],
            "business_logo": row["business_logo"],
            "created_at": row["created_at"].isoformat() if row["created_at"] else None,
        })

    return MyRolesResponse(roles=roles)
