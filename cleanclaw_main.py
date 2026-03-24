"""
CleanClaw — Standalone FastAPI Entry Point

Isolated CleanClaw service that ONLY loads cleaning-related routes.
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
logger = logging.getLogger("cleanclaw.main")

# Database & Redis
from app.database import init_db, close_db
from app.redis_client import init_redis, close_redis

# CleanClaw route imports (same as app/main.py cleaning section)
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

CLEANCLAW_PORT = int(os.getenv("CLEANCLAW_PORT", "8003"))
DEBUG = os.getenv("DEBUG", "false").lower() in ("true", "1", "yes")


# ============================================
# LIFECYCLE
# ============================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage startup and shutdown for CleanClaw service."""
    logger.info("\n  xCleaners API v1.0.0")
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

    logger.info("[OK] xCleaners API ready")
    logger.info("=" * 40)
    logger.info(f"  http://localhost:{CLEANCLAW_PORT}")
    logger.info(f"  http://localhost:{CLEANCLAW_PORT}/docs")

    yield

    await close_redis()
    await close_db()
    logger.info("[SHUTDOWN] xCleaners stopped")


# ============================================
# APP
# ============================================

app = FastAPI(
    title="xCleaners API",
    description="Standalone API for xCleaners — cleaning business management PWA",
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
    env_origins = os.getenv("CLEANCLAW_CORS_ORIGINS", "")
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
    return RedirectResponse(url="/cleaning/app", status_code=302)


# ============================================
# ROUTES — CleanClaw API (same prefixes as monolith)
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

    @app.get("/cleaning/app", tags=["Frontend"], include_in_schema=False)
    @app.get("/cleaning/app/{path:path}", tags=["Frontend"], include_in_schema=False)
    async def serve_cleaning_app(path: str = ""):
        return FileResponse(str(_cleaning_dir / "app.html"))


# ============================================
# RUN
# ============================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "cleanclaw_main:app",
        host="0.0.0.0",
        port=CLEANCLAW_PORT,
        reload=DEBUG,
    )


# ============================================
# TEMPORARY — Migration endpoint (remove after use)
# ============================================

@app.get("/admin/migrate", tags=["Admin"], include_in_schema=False)
async def run_migrations(key: str = ""):
    """One-time migration endpoint. Requires SECRET_KEY as query param."""
    import glob
    secret = os.getenv("SECRET_KEY", "")
    if not key or key != secret:
        return {"error": "unauthorized"}
    
    from app.database import get_db_pool
    pool = await get_db_pool()
    if not pool:
        return {"error": "no database connection"}
    
    results = []
    migration_dir = Path(__file__).resolve().parent / "database" / "migrations"
    files = sorted(glob.glob(str(migration_dir / "01[129]*.sql")))
    
    # Check existing tables
    async with pool.acquire() as conn:
        existing = await conn.fetch("SELECT tablename FROM pg_tables WHERE tablename LIKE 'cleaning_%' ORDER BY 1")
        results.append(f"existing_tables: {len(existing)}")
    
    # Run each migration in its own connection to avoid transaction issues
    for mig_file in files:
        name = os.path.basename(mig_file)
        try:
            with open(mig_file, 'r') as f:
                sql = f.read()
            async with pool.acquire() as conn:
                await conn.execute(sql)
            results.append(f"OK: {name}")
        except Exception as e:
            err = str(e).split(chr(10))[0]
            results.append(f"WARN: {name}: {err}")
    
    # Final count
    async with pool.acquire() as conn:
        final = await conn.fetch("SELECT tablename FROM pg_tables WHERE tablename LIKE 'cleaning_%' ORDER BY 1")
        results.append(f"final_tables: {len(final)}")
        tables = [r['tablename'] for r in final]
    
    return {"results": results, "tables": tables}


@app.get("/admin/seed", tags=["Admin"], include_in_schema=False)
async def run_seed(key: str = ""):
    """One-time seed endpoint. Requires SECRET_KEY as query param."""
    secret = os.getenv("SECRET_KEY", "")
    if not key or key != secret:
        return {"error": "unauthorized"}
    
    from app.database import get_db_pool
    pool = await get_db_pool()
    if not pool:
        return {"error": "no database connection"}
    
    import uuid
    OWNER_ID = uuid.uuid5(uuid.NAMESPACE_DNS, "cleanneworleans.owner")
    BUSINESS_ID = uuid.uuid5(uuid.NAMESPACE_DNS, "cleanneworleans.business")
    
    results = []
    async with pool.acquire() as conn:
        # Check if already seeded
        exists = await conn.fetchval("SELECT id FROM businesses WHERE slug = 'clean-new-orleans'")
        if exists:
            # Get stats
            clients = await conn.fetchval("SELECT count(*) FROM cleaning_clients WHERE business_id = $1", exists)
            teams = await conn.fetchval("SELECT count(*) FROM cleaning_teams WHERE business_id = $1", exists)
            services = await conn.fetchval("SELECT count(*) FROM cleaning_services WHERE business_id = $1", exists)
            return {"status": "already_seeded", "business_id": str(exists), "clients": clients, "teams": teams, "services": services}
        
        try:
            # Create owner user
            owner_exists = await conn.fetchval("SELECT id FROM users WHERE email = 'admin@cleanneworleans.com'")
            if not owner_exists:
                from app.security import hash_password
                hashed = hash_password("admin123")
                await conn.execute(
                    "INSERT INTO users (id, email, password_hash, name, is_active) VALUES ($1, $2, $3, $4, true)",
                    OWNER_ID, "admin@cleanneworleans.com", hashed, "Clean NOLA Admin"
                )
                results.append("OK: created owner user")
            else:
                OWNER_ID_ACTUAL = owner_exists
                results.append(f"SKIP: owner user exists ({owner_exists})")
            
            owner_id = owner_exists or OWNER_ID
            
            # Create business
            await conn.execute("""
                INSERT INTO businesses (id, name, slug, owner_id, business_type, timezone, is_active, settings)
                VALUES ($1, $2, 'clean-new-orleans', $3, 'cleaning', 'America/Chicago', true, $4::jsonb)
            """, BUSINESS_ID, "Clean New Orleans", owner_id, '{"currency":"USD","language":"en","tax_rate":0.0,"business_hours":{"start":"07:00","end":"18:00"}}')
            results.append("OK: created business")
            
            # Owner role
            await conn.execute("""
                INSERT INTO cleaning_user_roles (id, user_id, business_id, role)
                VALUES ($1, $2, $3, 'owner')
                ON CONFLICT DO NOTHING
            """, uuid.uuid4(), owner_id, BUSINESS_ID)
            results.append("OK: owner role assigned")
            
            # Copy service templates -> services
            templates = await conn.fetch("SELECT * FROM cleaning_service_templates")
            for t in templates:
                await conn.execute("""
                    INSERT INTO cleaning_services (id, business_id, name, slug, description, duration_minutes,
                        base_price, category, is_active)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, true)
                    ON CONFLICT DO NOTHING
                """, uuid.uuid4(), BUSINESS_ID, t['name'], t['slug'], t.get('description',''),
                    t['duration_minutes'], t['base_price'], t.get('category', 'residential'))
            results.append(f"OK: {len(templates)} services copied from templates")
            
            # Create teams
            teams_data = [
                ("Team Alpha", "#4CAF50"), ("Team Beta", "#2196F3"), ("Team Gamma", "#FF9800")
            ]
            for tname, color in teams_data:
                await conn.execute("""
                    INSERT INTO cleaning_teams (id, business_id, name, color, is_active)
                    VALUES ($1, $2, $3, $4, true) ON CONFLICT DO NOTHING
                """, uuid.uuid4(), BUSINESS_ID, tname, color)
            results.append("OK: 3 teams created")
            
            # Service areas
            areas = [
                ("French Quarter / CBD", ["70112","70116","70130"]),
                ("Uptown / Garden District", ["70115","70118","70130"]),
                ("Mid-City / Gentilly", ["70119","70122","70125"]),
                ("Lakeview / Metairie", ["70124","70001","70002"]),
                ("Bywater / Marigny", ["70117","70116"]),
                ("Algiers / West Bank", ["70114","70131"]),
                ("New Orleans East", ["70126","70127","70128"]),
                ("Kenner / River Ridge", ["70062","70065","70123"]),
            ]
            for aname, zips in areas:
                await conn.execute("""
                    INSERT INTO cleaning_areas (id, business_id, name, zip_codes, city, is_active)
                    VALUES ($1, $2, $3, $4, 'New Orleans', true) ON CONFLICT DO NOTHING
                """, uuid.uuid4(), BUSINESS_ID, aname, zips)
            results.append(f"OK: {len(areas)} service areas created")
            
            results.append("SEED COMPLETE")
            
        except Exception as e:
            results.append(f"ERROR: {str(e)[:200]}")
    
    return {"results": results, "business_id": str(BUSINESS_ID)}
