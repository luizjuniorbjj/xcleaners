"""
Xcleaners v3 — Auth & Role Pydantic models.
Models for role resolution, invitation, and /me endpoint responses.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field


# ============================================
# PLAN LIMITS (shared across module)
# ============================================

PLAN_HIERARCHY = ["basic", "intermediate", "maximum"]

PLAN_LIMITS = {
    # Single-tier policy: all businesses are premium. Numeric limits kept
    # per plan for backward compatibility with check_limit() but all are
    # unlimited (-1). SMS kept bounded on basic to protect from abuse only.
    "basic": {"teams": -1, "clients": -1, "sms_monthly": 500},
    "intermediate": {"teams": -1, "clients": -1, "sms_monthly": 1000},
    "maximum": {"teams": -1, "clients": -1, "sms_monthly": 2000},  # -1 = unlimited
}


# ============================================
# ROLE CONSTANTS
# ============================================

VALID_CLEANING_ROLES = ("owner", "homeowner", "team_lead", "cleaner")


# ============================================
# REQUEST MODELS
# ============================================

class CleaningUserRoleCreate(BaseModel):
    """Model for creating a cleaning_user_roles record directly."""
    user_id: str
    business_id: str
    role: str = Field(
        ...,
        pattern=r"^(owner|homeowner|team_lead|cleaner)$",
        description="Cleaning role within the business."
    )
    team_id: Optional[str] = None
    invited_by: Optional[str] = None


class InviteRequest(BaseModel):
    """Request body for inviting a user to a cleaning business."""
    email: EmailStr
    role: str = Field(
        ...,
        pattern=r"^(homeowner|team_lead|cleaner)$",
        description="Role to assign. Owner cannot be invited."
    )
    team_id: Optional[str] = Field(
        None,
        description="Required for team_lead and cleaner roles."
    )


class AcceptInviteRequest(BaseModel):
    """Request body for accepting an invitation."""
    invite_token: str


class AcceptClientInviteRequest(BaseModel):
    """Public endpoint body: homeowner self-registers from an email link."""
    invite_token: str = Field(..., description="UUID from cleaning_clients.invite_token")
    nome: str = Field(..., min_length=1, max_length=255)
    password: str = Field(..., min_length=8, max_length=200)
    accepted_terms: bool = Field(..., description="Must be true — TOS/Privacy acceptance")


class AcceptClientInviteResponse(BaseModel):
    """Response after accepting a client invite — logs the homeowner in."""
    access_token: str
    refresh_token: str
    business_slug: str
    business_name: str
    client_id: str


# ============================================
# RESPONSE MODELS
# ============================================

class CleaningRoleInfo(BaseModel):
    """Cleaning role info returned by /me endpoint."""
    user_id: str
    email: str
    name: Optional[str] = None
    cleaning_role: Optional[str] = None
    team_id: Optional[str] = None
    team_name: Optional[str] = None
    plan: str = "basic"
    plan_limits: dict = {}


class InviteResponse(BaseModel):
    """Response after creating an invitation."""
    invite_id: str
    email: str
    role: str
    invite_link: str
    expires_at: str


class AcceptInviteResponse(BaseModel):
    """Response after accepting an invitation."""
    role: str
    team_id: Optional[str] = None
    team_name: Optional[str] = None
    business_slug: str
    business_name: str


class MyRolesResponse(BaseModel):
    """Response for /my-roles — all cleaning roles for current user."""
    roles: list[dict]
