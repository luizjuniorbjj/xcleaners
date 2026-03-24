"""
ClaWin1Click - Authentication System
OAuth (Google + GitHub) with optional email/password
Single-platform (NOT multi-tenant) — no agency_slug
"""

import logging
from datetime import datetime, timedelta
from typing import Optional
from urllib.parse import urlencode
import secrets
import httpx

logger = logging.getLogger("clawin.auth")

from fastapi import APIRouter, HTTPException, Depends, Header, Query, BackgroundTasks
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, EmailStr

from app.security import (
    hash_password,
    verify_password,
    create_access_token,
    create_refresh_token,
    verify_token,
    generate_secure_token
)
from app.database import get_db, Database
from app.config import (
    GOOGLE_CLIENT_ID,
    GOOGLE_CLIENT_SECRET,
    GOOGLE_REDIRECT_URI,
    GITHUB_CLIENT_ID,
    GITHUB_CLIENT_SECRET,
    GITHUB_REDIRECT_URI,
    RESEND_API_KEY,
    EMAIL_FROM,
    APP_URL,
    APP_NAME,
    DEBUG,
    ADMIN_EMAILS
)

router = APIRouter(prefix="/auth", tags=["Authentication"])

# OAuth state storage — Redis (primary) with in-memory fallback
_oauth_states_memory: dict = {}
OAUTH_STATE_TTL_SECONDS = 600  # 10 minutes


async def _store_oauth_state(state: str, data: dict) -> None:
    """Store OAuth state in Redis (preferred) or in-memory (fallback)."""
    try:
        from app.redis_client import get_redis
        import json as _json
        r = get_redis()
        if r:
            await r.setex(
                f"oauth_state:{state}",
                OAUTH_STATE_TTL_SECONDS,
                _json.dumps(data, default=str),
            )
            return
    except Exception:
        pass
    # Cleanup expired states to prevent memory leak
    now = datetime.now().timestamp()
    expired = [
        k for k, v in _oauth_states_memory.items()
        if now - v.get("_stored_at", 0) > OAUTH_STATE_TTL_SECONDS
    ]
    for k in expired:
        del _oauth_states_memory[k]
    data["_stored_at"] = now
    _oauth_states_memory[state] = data


async def _pop_oauth_state(state: str) -> Optional[dict]:
    """Retrieve and delete OAuth state. Returns None if not found or expired."""
    try:
        from app.redis_client import get_redis
        import json as _json
        r = get_redis()
        if r:
            pipe = r.pipeline()
            pipe.get(f"oauth_state:{state}")
            pipe.delete(f"oauth_state:{state}")
            results = await pipe.execute()
            raw = results[0]
            if raw:
                return _json.loads(raw)
            return None
    except Exception:
        pass
    data = _oauth_states_memory.pop(state, None)
    if data:
        stored_at = data.pop("_stored_at", 0)
        if datetime.now().timestamp() - stored_at > OAUTH_STATE_TTL_SECONDS:
            return None
    return data


# ============================================
# MODELS
# ============================================

class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    nome: Optional[str] = None
    ref_code: Optional[str] = None  # Affiliate referral slug
    accepted_terms: bool = False
    language: Optional[str] = "pt"


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = 3600


class RefreshRequest(BaseModel):
    refresh_token: str


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetConfirm(BaseModel):
    token: str
    new_password: str


class UserResponse(BaseModel):
    id: str
    email: str
    role: str
    nome: Optional[str] = None
    profile_photo_url: Optional[str] = None
    language: Optional[str] = "pt"
    created_at: datetime


# ============================================
# EMAIL HELPER
# ============================================

async def _send_reset_email(email: str, token: str, nome: str = "", language: str = "pt"):
    """Send password reset email via EmailService"""
    from app.email_service import email_service
    await email_service.send_password_reset_email(
        to=email,
        nome=nome or email.split("@")[0],
        reset_token=token,
        language=language
    )


# ============================================
# DEPENDENCY: AUTHENTICATED USER
# ============================================

async def get_current_user(
    authorization: str = Header(None, description="Bearer token")
) -> dict:
    """
    FastAPI dependency that extracts and validates user from JWT token.
    Returns: {user_id, email, role}
    """
    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization header required")
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid token format")

    token = authorization.replace("Bearer ", "")
    payload = verify_token(token)

    if not payload:
        raise HTTPException(status_code=401, detail="Token expired or invalid")

    if payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="Invalid token type")

    return {
        "user_id": payload["sub"],
        "email": payload["email"],
        "role": payload.get("role", "lead")
    }


async def require_admin(current_user: dict = Depends(get_current_user)) -> dict:
    """Dependency that requires admin role"""
    if current_user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user


async def require_subscriber(current_user: dict = Depends(get_current_user)) -> dict:
    """Dependency that requires subscriber or admin role"""
    if current_user["role"] not in ("subscriber", "admin"):
        raise HTTPException(status_code=403, detail="Active subscription required")
    return current_user


# ============================================
# ROUTES
# ============================================

@router.post("/register", response_model=TokenResponse)
async def register(request: RegisterRequest, background_tasks: BackgroundTasks, db: Database = Depends(get_db)):
    """Register new user"""
    if not request.accepted_terms:
        raise HTTPException(
            status_code=400,
            detail="You must accept the Terms of Service and Privacy Policy"
        )

    # Check if email already exists
    existing = await db.get_user_by_email(request.email)
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    if len(request.password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")

    # Create user
    password_hash = hash_password(request.password)
    user = await db.create_user(
        email=request.email,
        senha_hash=password_hash,
        nome=request.nome,
        ref_code=request.ref_code
    )

    # Create initial profile
    language = request.language if request.language in ["en", "pt", "es"] else "pt"
    await db.create_user_profile(
        user_id=str(user["id"]),
        nome=request.nome,
        language=language
    )

    # Generate tokens
    access_token = create_access_token(
        user["id"], user["email"], role=user.get("role", "lead")
    )
    refresh_token = create_refresh_token(user["id"])

    # Send welcome email (background)
    from app.email_service import email_service
    background_tasks.add_task(
        email_service.send_welcome_email,
        to=request.email,
        nome=request.nome or request.email.split("@")[0],
        language=language
    )

    # Audit log
    await db.log_audit(
        user_id=str(user["id"]),
        action="register",
        details={"email": request.email, "ref_code": request.ref_code}
    )

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token
    )


@router.post("/login", response_model=TokenResponse)
async def login(request: LoginRequest, db: Database = Depends(get_db)):
    """Login existing user"""
    user = await db.get_user_by_email(request.email)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if not user.get("senha_hash") or not verify_password(request.password, user["senha_hash"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if not user.get("is_active", True):
        raise HTTPException(status_code=403, detail="Account deactivated")

    # Update last login
    await db.update_last_login(str(user["id"]))

    # Auto-promote to admin if email is in ADMIN_EMAILS
    role = user.get("role", "lead")
    if user["email"] in ADMIN_EMAILS and role != "admin":
        await db.update_user_role(str(user["id"]), "admin")
        role = "admin"

    # Generate tokens
    access_token = create_access_token(
        user["id"], user["email"], role=role
    )
    refresh_token = create_refresh_token(user["id"])

    await db.log_audit(
        user_id=str(user["id"]),
        action="login",
        details={}
    )

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token_route(request: RefreshRequest, db: Database = Depends(get_db)):
    """Renew tokens using refresh token"""
    payload = verify_token(request.refresh_token)

    if not payload:
        raise HTTPException(status_code=401, detail="Refresh token invalid or expired")

    if payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid token type")

    user = await db.get_user_by_id(payload["sub"])
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    if not user.get("is_active", True):
        raise HTTPException(status_code=403, detail="Account deactivated")

    access_token = create_access_token(
        user["id"], user["email"], role=user.get("role", "lead")
    )
    new_refresh_token = create_refresh_token(user["id"])

    return TokenResponse(
        access_token=access_token,
        refresh_token=new_refresh_token
    )


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: dict = Depends(get_current_user), db: Database = Depends(get_db)):
    """Return authenticated user data"""
    user = await db.get_user_by_id(current_user["user_id"])
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    profile = await db.get_user_profile(current_user["user_id"])

    return UserResponse(
        id=str(user["id"]),
        email=user["email"],
        role=user.get("role", "lead"),
        nome=profile.get("nome") if profile else user.get("nome"),
        profile_photo_url=user.get("profile_photo_url"),
        language=profile.get("language", "pt") if profile else "pt",
        created_at=user["created_at"]
    )


@router.post("/password-reset")
async def request_password_reset(request: PasswordResetRequest, db: Database = Depends(get_db)):
    """Request password reset"""
    user = await db.get_user_by_email(request.email)

    if user:
        token = generate_secure_token()
        expires_at = datetime.utcnow() + timedelta(hours=1)
        await db.save_reset_token(str(user["id"]), token, expires_at)
        profile = await db.get_user_profile(str(user["id"]))
        nome = profile.get("nome", "") if profile else ""
        language = profile.get("language", "pt") if profile else "pt"
        await _send_reset_email(request.email, token, nome=nome, language=language)

    # Always return success to avoid email enumeration
    return {"message": "If the email exists, you will receive password reset instructions"}


@router.post("/password-reset/confirm")
async def confirm_password_reset(request: PasswordResetConfirm, db: Database = Depends(get_db)):
    """Confirm password reset with token"""
    token_data = await db.verify_reset_token(request.token)
    if not token_data:
        raise HTTPException(status_code=400, detail="Invalid or expired token")

    if len(request.new_password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")

    password_hash = hash_password(request.new_password)
    await db.update_user_password(str(token_data["user_id"]), password_hash)
    await db.use_reset_token(request.token)

    await db.log_audit(
        user_id=str(token_data["user_id"]),
        action="password_reset",
        details={"method": "email_token"}
    )

    return {"message": "Password updated successfully"}


@router.post("/logout")
async def logout(current_user: dict = Depends(get_current_user), db: Database = Depends(get_db)):
    """Logout (audit log only — JWT is stateless)"""
    await db.log_audit(
        user_id=current_user["user_id"],
        action="logout",
        details={}
    )
    return {"message": "Logged out successfully"}


# ============================================
# DEV LOGIN (DEBUG ONLY — disabled in production)
# ============================================

class DevLoginRequest(BaseModel):
    email: EmailStr


@router.post("/dev-login", response_model=TokenResponse)
async def dev_login(request: DevLoginRequest, db: Database = Depends(get_db)):
    """
    Dev-only login: bypasses password/OAuth for local testing.
    Only available when DEBUG=True. NEVER enable in production.
    """
    if not DEBUG:
        raise HTTPException(status_code=404, detail="Not found")

    email = request.email
    user = await db.get_user_by_email(email)

    if not user:
        # Create user on the fly for dev
        role = "admin" if email in ADMIN_EMAILS else "lead"
        user = await db.create_user(
            email=email,
            senha_hash=hash_password("dev-only-password"),
            nome=email.split("@")[0],
        )
        await db.create_user_profile(
            user_id=str(user["id"]),
            nome=email.split("@")[0]
        )
        # Set role if admin
        if role == "admin":
            await db.update_user_role(str(user["id"]), "admin")
            user["role"] = "admin"
        logger.info(f"[DEV-LOGIN] Created {role} user: {email}")

    access_token = create_access_token(
        user["id"], user["email"], role=user.get("role", "lead")
    )
    refresh_token = create_refresh_token(user["id"])

    await db.log_audit(
        user_id=str(user["id"]),
        action="dev_login",
        details={"warning": "DEBUG mode only"}
    )

    logger.info(f"[DEV-LOGIN] Logged in as {email} (role={user.get('role', 'lead')})")

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token
    )


# ============================================
# OAUTH - GOOGLE
# ============================================

@router.get("/google")
async def google_login(ref: Optional[str] = Query(None, description="Affiliate referral slug")):
    """Start Google OAuth flow"""
    if not GOOGLE_CLIENT_ID:
        raise HTTPException(status_code=501, detail="Google login not configured")

    state = secrets.token_urlsafe(32)
    await _store_oauth_state(state, {
        "provider": "google",
        "ref_code": ref,
    })

    params = {
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "access_type": "offline",
        "prompt": "consent"
    }

    auth_url = f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}"
    return RedirectResponse(url=auth_url)


@router.get("/google/callback")
async def google_callback(
    code: str = Query(None),
    state: str = Query(None),
    error: str = Query(None),
    db: Database = Depends(get_db)
):
    """Google OAuth callback"""
    if error:
        return RedirectResponse(url=f"{APP_URL}/dashboard?error={error}")

    if not code or not state:
        return RedirectResponse(url=f"{APP_URL}/dashboard?error=missing_params")

    state_data = await _pop_oauth_state(state)
    if not state_data:
        return RedirectResponse(url=f"{APP_URL}/dashboard?error=invalid_state")

    ref_code = state_data.get("ref_code")

    try:
        async with httpx.AsyncClient() as client:
            token_response = await client.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "client_id": GOOGLE_CLIENT_ID,
                    "client_secret": GOOGLE_CLIENT_SECRET,
                    "code": code,
                    "grant_type": "authorization_code",
                    "redirect_uri": GOOGLE_REDIRECT_URI
                }
            )

            if token_response.status_code != 200:
                return RedirectResponse(url=f"{APP_URL}/dashboard?error=token_exchange_failed")

            tokens = token_response.json()
            access_token = tokens.get("access_token")

            user_response = await client.get(
                "https://www.googleapis.com/oauth2/v2/userinfo",
                headers={"Authorization": f"Bearer {access_token}"}
            )

            if user_response.status_code != 200:
                return RedirectResponse(url=f"{APP_URL}/dashboard?error=user_info_failed")

            user_info = user_response.json()

        email = user_info.get("email")
        nome = user_info.get("name")
        google_id = user_info.get("id")
        picture = user_info.get("picture")

        if not email:
            return RedirectResponse(url=f"{APP_URL}/dashboard?error=no_email")

        user = await db.get_user_by_email(email)

        if user:
            # Existing user — login
            await db.update_last_login(str(user["id"]))
            if picture and not user.get("profile_photo_url"):
                await db.update_user_profile_photo(str(user["id"]), picture)
        else:
            # New user — register via OAuth
            user = await db.create_user(
                email=email,
                senha_hash=None,
                nome=nome,
                oauth_provider="google",
                oauth_id=google_id,
                ref_code=ref_code
            )
            await db.create_user_profile(
                user_id=str(user["id"]),
                nome=nome
            )
            if picture:
                await db.update_user_profile_photo(str(user["id"]), picture)

            # Send welcome email for new OAuth user
            try:
                from app.email_service import email_service
                await email_service.send_welcome_email(
                    to=email, nome=nome or email.split("@")[0]
                )
            except Exception as we:
                logger.warning(f"[AUTH] Welcome email failed: {we}")

        jwt_access = create_access_token(
            user["id"], email, role=user.get("role", "lead")
        )
        jwt_refresh = create_refresh_token(user["id"])

        await db.log_audit(
            user_id=str(user["id"]),
            action="oauth_login",
            details={"provider": "google"}
        )

        redirect_url = f"{APP_URL}/dashboard?access_token={jwt_access}&refresh_token={jwt_refresh}"
        return RedirectResponse(url=redirect_url)

    except Exception as e:
        logger.error(f"[AUTH] Google OAuth error: {e}")
        return RedirectResponse(url=f"{APP_URL}/dashboard?error=oauth_failed")


# ============================================
# OAUTH - GITHUB
# ============================================

@router.get("/github")
async def github_login(ref: Optional[str] = Query(None, description="Affiliate referral slug")):
    """Start GitHub OAuth flow"""
    if not GITHUB_CLIENT_ID:
        raise HTTPException(status_code=501, detail="GitHub login not configured")

    state = secrets.token_urlsafe(32)
    await _store_oauth_state(state, {
        "provider": "github",
        "ref_code": ref,
    })

    params = {
        "client_id": GITHUB_CLIENT_ID,
        "redirect_uri": GITHUB_REDIRECT_URI,
        "scope": "read:user user:email",
        "state": state
    }

    auth_url = f"https://github.com/login/oauth/authorize?{urlencode(params)}"
    return RedirectResponse(url=auth_url)


@router.get("/github/callback")
async def github_callback(
    code: str = Query(None),
    state: str = Query(None),
    error: str = Query(None),
    db: Database = Depends(get_db)
):
    """GitHub OAuth callback"""
    if error:
        return RedirectResponse(url=f"{APP_URL}/dashboard?error={error}")

    if not code or not state:
        return RedirectResponse(url=f"{APP_URL}/dashboard?error=missing_params")

    state_data = await _pop_oauth_state(state)
    if not state_data:
        return RedirectResponse(url=f"{APP_URL}/dashboard?error=invalid_state")

    ref_code = state_data.get("ref_code")

    try:
        async with httpx.AsyncClient() as client:
            # Exchange code for access token
            token_response = await client.post(
                "https://github.com/login/oauth/access_token",
                headers={"Accept": "application/json"},
                data={
                    "client_id": GITHUB_CLIENT_ID,
                    "client_secret": GITHUB_CLIENT_SECRET,
                    "code": code,
                    "redirect_uri": GITHUB_REDIRECT_URI
                }
            )

            if token_response.status_code != 200:
                return RedirectResponse(url=f"{APP_URL}/dashboard?error=token_exchange_failed")

            tokens = token_response.json()
            access_token = tokens.get("access_token")

            if not access_token:
                return RedirectResponse(url=f"{APP_URL}/dashboard?error=no_access_token")

            # Fetch user info
            user_response = await client.get(
                "https://api.github.com/user",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/vnd.github+json"
                }
            )

            if user_response.status_code != 200:
                return RedirectResponse(url=f"{APP_URL}/dashboard?error=user_info_failed")

            user_info = user_response.json()

            # Fetch primary email (may not be public)
            email = user_info.get("email")
            if not email:
                emails_response = await client.get(
                    "https://api.github.com/user/emails",
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "Accept": "application/vnd.github+json"
                    }
                )
                if emails_response.status_code == 200:
                    emails = emails_response.json()
                    primary = next((e for e in emails if e.get("primary")), None)
                    if primary:
                        email = primary["email"]

        if not email:
            return RedirectResponse(url=f"{APP_URL}/dashboard?error=no_email")

        nome = user_info.get("name") or user_info.get("login")
        github_id = str(user_info.get("id"))
        picture = user_info.get("avatar_url")

        user = await db.get_user_by_email(email)

        if user:
            await db.update_last_login(str(user["id"]))
            if picture and not user.get("profile_photo_url"):
                await db.update_user_profile_photo(str(user["id"]), picture)
        else:
            user = await db.create_user(
                email=email,
                senha_hash=None,
                nome=nome,
                oauth_provider="github",
                oauth_id=github_id,
                ref_code=ref_code
            )
            await db.create_user_profile(
                user_id=str(user["id"]),
                nome=nome
            )
            if picture:
                await db.update_user_profile_photo(str(user["id"]), picture)

            # Send welcome email for new OAuth user
            try:
                from app.email_service import email_service
                await email_service.send_welcome_email(
                    to=email, nome=nome or email.split("@")[0]
                )
            except Exception as we:
                logger.warning(f"[AUTH] Welcome email failed: {we}")

        jwt_access = create_access_token(
            user["id"], email, role=user.get("role", "lead")
        )
        jwt_refresh = create_refresh_token(user["id"])

        await db.log_audit(
            user_id=str(user["id"]),
            action="oauth_login",
            details={"provider": "github"}
        )

        redirect_url = f"{APP_URL}/dashboard?access_token={jwt_access}&refresh_token={jwt_refresh}"
        return RedirectResponse(url=redirect_url)

    except Exception as e:
        logger.error(f"[AUTH] GitHub OAuth error: {e}")
        return RedirectResponse(url=f"{APP_URL}/dashboard?error=oauth_failed")


# ============================================
# OAUTH - PROVIDERS STATUS
# ============================================

@router.get("/oauth/providers")
async def get_oauth_providers():
    """Return which OAuth providers are configured"""
    return {
        "google": bool(GOOGLE_CLIENT_ID),
        "github": bool(GITHUB_CLIENT_ID)
    }
