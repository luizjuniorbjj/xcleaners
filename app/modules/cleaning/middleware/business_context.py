"""
Xcleaners v3 — Business Context Middleware.

Sets the PostgreSQL session variable `app.current_business_id` on each
request so that Row-Level Security (RLS) policies can filter data
automatically at the database level.

Resolution order:
  1. JWT token claim `business_id`
  2. URL path parameter `slug` → lookup businesses table
  3. None (skip — public or unauthenticated endpoint)

Skipped paths: /health, /auth/*, /cleaning/app, /cleaning/static/*
"""

import logging
import re
from typing import Optional, Set

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger("xcleaners.business_context")

# Paths that do not require business context
_SKIP_PREFIXES = (
    "/health",
    "/auth/",
    "/cleaning/app",
    "/cleaning/static",
    "/docs",
    "/redoc",
    "/openapi.json",
)

# Pattern to extract slug from /api/v1/clean/{slug}/... or /cleaning/{slug}/...
_SLUG_PATTERN = re.compile(
    r"^/(?:api/v1/clean|cleaning)/([a-z0-9][a-z0-9_-]{1,62})/",
)


def _get_redis():
    """Get Redis client. Returns None if unavailable."""
    try:
        from app.redis_client import get_redis
        return get_redis()
    except ImportError:
        return None


async def _resolve_business_id_from_slug(slug: str) -> Optional[str]:
    """
    Resolve a business slug to its UUID, with Redis caching.
    Returns None if business not found.
    """
    cache_key = f"clean:slug:{slug}:bid"
    redis = _get_redis()

    # 1. Check Redis cache
    if redis:
        try:
            cached = await redis.get(cache_key)
            if cached:
                return cached if cached != "__none__" else None
        except Exception:
            pass

    # 2. Database lookup
    try:
        from app.database import get_db_pool
        pool = await get_db_pool()
        if pool is None:
            return None

        row = await pool.fetchval(
            "SELECT id FROM businesses WHERE slug = $1 AND status != 'cancelled'",
            slug,
        )
        business_id = str(row) if row else None

        # 3. Cache result (even negative, to avoid repeated lookups)
        if redis:
            try:
                await redis.setex(cache_key, 3600, business_id or "__none__")
            except Exception:
                pass

        return business_id
    except Exception as exc:
        logger.warning("[BIZ_CTX] Failed to resolve slug '%s': %s", slug, exc)
        return None


def _extract_token_business_id(request: Request) -> Optional[str]:
    """
    Extract business_id from JWT Authorization header without full
    token verification (that happens in route-level dependencies).
    Returns None if not present or not decodable.
    """
    auth_header = request.headers.get("authorization", "")
    if not auth_header.startswith("Bearer "):
        return None

    token = auth_header[7:]
    try:
        from app.security import verify_token
        payload = verify_token(token)
        return payload.get("business_id") if payload else None
    except Exception:
        return None


class BusinessContextMiddleware(BaseHTTPMiddleware):
    """
    Set app.current_business_id on each DB connection from JWT claims
    or URL path slug. This enables PostgreSQL RLS policies.

    Flow:
      1. Check if path should be skipped
      2. Try to get business_id from JWT token
      3. Fallback: extract slug from URL path and resolve via DB
      4. If found, execute SET on a fresh connection
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path

        # Skip paths that don't need business context
        if any(path.startswith(prefix) for prefix in _SKIP_PREFIXES):
            return await call_next(request)

        # Resolve business_id
        business_id = _extract_token_business_id(request)

        if not business_id:
            # Try URL path slug
            match = _SLUG_PATTERN.match(path)
            if match:
                slug = match.group(1)
                business_id = await _resolve_business_id_from_slug(slug)

        if business_id:
            # Store in request state for downstream access
            request.state.business_id = business_id

            # C-2 FIX (2026-04-09): Acquire a connection, set RLS, and keep it
            # in request.state for the entire request lifecycle.
            # Previous code acquired a connection, set RLS, then immediately
            # returned it to the pool — the route handler got a DIFFERENT
            # connection where RLS was never set.
            try:
                from app.database import get_db_pool
                pool = await get_db_pool()
                if pool:
                    conn = await pool.acquire()
                    await conn.execute(
                        "SELECT set_config('app.current_business_id', $1, true)",
                        str(business_id),
                    )
                    # Store connection in request state — route handlers can
                    # access it via request.state.rls_conn
                    request.state.rls_conn = conn
                    request.state._rls_pool = pool
            except Exception as exc:
                logger.warning(
                    "[BIZ_CTX] Failed to set RLS context for %s: %s",
                    business_id, exc,
                )
        else:
            request.state.business_id = None

        try:
            response = await call_next(request)
        finally:
            # Release the RLS connection back to the pool after request completes
            rls_conn = getattr(request.state, "rls_conn", None)
            rls_pool = getattr(request.state, "_rls_pool", None)
            if rls_conn and rls_pool:
                try:
                    # Reset the session variable before returning to pool
                    await rls_conn.execute(
                        "SELECT set_config('app.current_business_id', '', true)"
                    )
                except Exception:
                    pass
                await rls_pool.release(rls_conn)

        return response
