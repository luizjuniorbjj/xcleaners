"""
Xcleaners — Standalone FastAPI Entry Point

Isolated Xcleaners service that ONLY loads cleaning-related routes.
Runs independently from the main ClaWtoBusiness monolith on port 8003.
"""

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

# Security middleware
from app.modules.cleaning.middleware.security import (
    SecurityHeadersMiddleware,
    RateLimitMiddleware,
    RequestValidationMiddleware,
)
from app.modules.cleaning.middleware.business_context import BusinessContextMiddleware

# Configure logging
logging.basicConfig(
    level=getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO),
    format="%(levelname)s:%(name)s:%(message)s",
)
logger = logging.getLogger("xcleaners.main")

# Database & Redis
from app.database import init_db, close_db
from app.redis_client import init_redis, close_redis

# Xcleaners route imports (same as app/main.py cleaning section)
from app.modules.cleaning.routes.app_routes import router as cleaning_app_router
from app.modules.cleaning.routes.onboarding import router as cleaning_onboarding_router
from app.modules.cleaning.routes.clients import router as cleaning_clients_router
from app.modules.cleaning.routes.services import router as cleaning_services_router
from app.modules.cleaning.routes.teams import router as cleaning_teams_router
from app.modules.cleaning.routes.members import router as cleaning_members_router
from app.modules.cleaning.routes.schedule import router as cleaning_schedule_router
from app.modules.cleaning.routes.cleaner_routes import router as cleaning_cleaner_router
from app.modules.cleaning.routes.homeowner_routes import router as cleaning_homeowner_router
from app.modules.cleaning.routes.invoice_routes import router as cleaning_invoice_router
from app.modules.cleaning.routes.notification_routes import router as cleaning_notification_router
from app.modules.cleaning.routes.dashboard_routes import router as cleaning_dashboard_router
from app.modules.cleaning.routes.settings_routes import router as cleaning_settings_router
from app.modules.cleaning.routes.ai_routes import router as cleaning_ai_router
from app.modules.cleaning.routes.auth_routes import router as cleaning_auth_router
from app.modules.cleaning.routes.plan import router as cleaning_plan_router
from app.modules.cleaning.routes.push_routes import router as cleaning_push_router

# Auth router (needed for login/token endpoints)
from app.auth import router as auth_router


# ============================================
# CONFIGURATION
# ============================================

XCLEANERS_PORT = int(os.getenv("XCLEANERS_PORT", "8003"))
DEBUG = os.getenv("DEBUG", "false").lower() in ("true", "1", "yes")


# ============================================
# LIFECYCLE
# ============================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage startup and shutdown for Xcleaners service."""
    logger.info("\n  Xcleaners API v1.0.0")
    logger.info("=" * 40)

    # Database — graceful fallback for UI testing without DB
    try:
        await init_db()
        logger.info("[DB] Database connected")
    except Exception as e:
        logger.warning(f"[DB] Not available — API routes will fail but UI is accessible: {e}")

    # Redis — graceful fallback
    try:
        redis_conn = await init_redis()
        if redis_conn:
            logger.info("[REDIS] Connected")
        else:
            logger.warning("[REDIS] Not available — using in-memory fallback")
    except Exception as e:
        logger.warning(f"[REDIS] Not available: {e}")

    logger.info("[OK] Xcleaners API ready")
    logger.info("=" * 40)
    logger.info(f"  http://localhost:{XCLEANERS_PORT}")
    logger.info(f"  http://localhost:{XCLEANERS_PORT}/docs")

    yield

    await close_redis()
    await close_db()
    logger.info("[SHUTDOWN] Xcleaners stopped")


# ============================================
# APP
# ============================================

app = FastAPI(
    title="Xcleaners API",
    description="Standalone API for Xcleaners — cleaning business management PWA",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs" if DEBUG else None,
    redoc_url="/redoc" if DEBUG else None,
)


# ============================================
# CORS
# ============================================

def get_cors_origins():
    """Return CORS origins from env or defaults."""
    env_origins = os.getenv("XCLEANERS_CORS_ORIGINS", "")
    if env_origins:
        return [o.strip() for o in env_origins.split(",") if o.strip()]
    return [
        "http://localhost:3000",
        "http://localhost:8003",
    ]


# Middleware execution order (outermost → innermost):
#   SecurityHeaders → RateLimit → RequestValidation → CORS → BusinessContext → Route
#
# In Starlette, the LAST add_middleware call is the OUTERMOST layer.

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID"],
)
app.add_middleware(BusinessContextMiddleware)
app.add_middleware(RequestValidationMiddleware)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(SecurityHeadersMiddleware)


# ============================================
# ROUTES — Health & Root
# ============================================

@app.get("/health", tags=["Status"])
async def health():
    return {"status": "ok", "service": "xcleaners"}


@app.get("/", tags=["Root"], include_in_schema=False)
async def root_redirect():
    return RedirectResponse(url="/login", status_code=302)


# ============================================
# ROUTES — Xcleaners API (same prefixes as monolith)
# ============================================

app.include_router(auth_router)
app.include_router(cleaning_onboarding_router)
app.include_router(cleaning_clients_router)
app.include_router(cleaning_services_router)
app.include_router(cleaning_teams_router)
app.include_router(cleaning_members_router)
app.include_router(cleaning_schedule_router)
app.include_router(cleaning_cleaner_router)
app.include_router(cleaning_homeowner_router)
app.include_router(cleaning_invoice_router)
app.include_router(cleaning_notification_router)
app.include_router(cleaning_dashboard_router)
app.include_router(cleaning_settings_router)
app.include_router(cleaning_ai_router)
app.include_router(cleaning_auth_router)
app.include_router(cleaning_plan_router)
app.include_router(cleaning_push_router)
app.include_router(cleaning_app_router)


# ============================================
# FRONTEND — Static Files + PWA Shell
# ============================================

_frontend_dir = Path(__file__).resolve().parent / "frontend"
_cleaning_dir = _frontend_dir / "cleaning"

if _cleaning_dir.exists():
    _cleaning_static = _cleaning_dir / "static"
    if _cleaning_static.exists():
        app.mount("/cleaning/static", StaticFiles(directory=str(_cleaning_static)), name="cleaning-static")

    # Legacy route (backwards compatibility)
    @app.get("/cleaning/app", tags=["Frontend"], include_in_schema=False)
    @app.get("/cleaning/app/{path:path}", tags=["Frontend"], include_in_schema=False)
    async def serve_cleaning_app_legacy(path: str = ""):
        return FileResponse(str(_cleaning_dir / "app.html"))

    # PWA assets — explicit routes so they don't hit the SPA catch-all
    @app.get("/cleaning/manifest.json", tags=["Frontend"], include_in_schema=False)
    async def serve_manifest():
        return FileResponse(str(_cleaning_dir / "manifest.json"), media_type="application/json")

    @app.get("/cleaning/sw.js", tags=["Frontend"], include_in_schema=False)
    async def serve_sw():
        return FileResponse(str(_cleaning_dir / "sw.js"), media_type="application/javascript")

    # SEO files — must be served at root, before SPA catch-all
    @app.get("/robots.txt", tags=["SEO"], include_in_schema=False)
    async def serve_robots():
        return FileResponse(str(_frontend_dir / "robots.txt"), media_type="text/plain")

    @app.get("/sitemap.xml", tags=["SEO"], include_in_schema=False)
    async def serve_sitemap():
        return FileResponse(str(_frontend_dir / "sitemap.xml"), media_type="application/xml")

    # Temporary DB admin endpoints
    @app.get("/admin/db-check", tags=["Admin"], include_in_schema=False)
    async def db_check_inline(key: str = ""):
        secret = os.getenv("SECRET_KEY", "")
        if not key or key != secret:
            return {"error": "unauthorized"}
        from app.database import get_db_pool
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            cols = await conn.fetch("SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'users' ORDER BY ordinal_position")
            users = await conn.fetch("SELECT id, email FROM users LIMIT 3")
            return {"columns": [r["column_name"] for r in cols], "user_count": len(users)}

    @app.get("/admin/db-fix-users", tags=["Admin"], include_in_schema=False)
    async def db_fix_users(key: str = ""):
        secret = os.getenv("SECRET_KEY", "")
        if not key or key != secret:
            return {"error": "unauthorized"}
        from app.database import get_db_pool
        pool = await get_db_pool()
        results = []
        async with pool.acquire() as conn:
            for col, typ, default in [
                ("oauth_provider", "VARCHAR(20)", "NULL"),
                ("oauth_id", "VARCHAR(255)", "NULL"),
                ("ref_code", "VARCHAR(50)", "NULL"),
                ("role", "VARCHAR(20)", "'lead'"),
                ("stripe_customer_id", "VARCHAR(100)", "NULL"),
                ("profile_photo_url", "TEXT", "NULL"),
                ("language", "VARCHAR(5)", "'en'"),
                ("message_count", "INTEGER", "0"),
                ("last_login", "TIMESTAMPTZ", "NULL"),
            ]:
                try:
                    await conn.execute(f"ALTER TABLE users ADD COLUMN IF NOT EXISTS {col} {typ} DEFAULT {default}")
                    results.append(f"OK: {col}")
                except Exception as e:
                    results.append(f"ERR: {col}: {str(e)[:80]}")
            cols = await conn.fetch("SELECT column_name FROM information_schema.columns WHERE table_name = 'users' ORDER BY ordinal_position")
            return {"results": results, "columns": [r["column_name"] for r in cols]}

    # Pitch deck (investor presentation)
    @app.get("/pitch", tags=["Frontend"], include_in_schema=False)
    async def serve_pitch():
        return FileResponse(str(_frontend_dir / "pitch.html"), media_type="text/html")

    # SPA catch-all: serve app.html for all non-API, non-static paths
    # This MUST be the last route registered
    @app.get("/{path:path}", tags=["Frontend"], include_in_schema=False)
    async def serve_spa_catchall(request: Request, path: str = ""):
        # Skip API, static, and SEO paths
        if path in ("robots.txt", "sitemap.xml") or path.startswith("api/") or path.startswith("cleaning/static") or path.startswith("docs") or path.startswith("openapi"):
            from fastapi.responses import JSONResponse
            return JSONResponse({"error": "not found"}, status_code=404)
        return FileResponse(str(_cleaning_dir / "app.html"))


# ============================================
# RUN
# ============================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "xcleaners_main:app",
        host="0.0.0.0",
        port=XCLEANERS_PORT,
        reload=DEBUG,
    )


@app.get("/admin/db-check", tags=["Admin"], include_in_schema=False)
async def db_check(key: str = ""):
    secret = os.getenv("SECRET_KEY", "")
    if not key or key != secret:
        return {"error": "unauthorized"}
    from app.database import get_db_pool
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        cols = await conn.fetch("SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'users' ORDER BY ordinal_position")
        users = await conn.fetch("SELECT id, email, nome FROM users LIMIT 3")
        return {
            "columns": [{"name": r["column_name"], "type": r["data_type"]} for r in cols],
            "users": [dict(r) for r in users]
        }
