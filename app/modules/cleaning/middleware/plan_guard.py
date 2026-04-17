"""
Xcleaners v3 — Plan Guard Middleware.

Provides plan-based feature gating for cleaning API endpoints.
Reads the business plan from the businesses table, caches in Redis,
and blocks access to features that require a higher plan tier.

Plan hierarchy: basic < intermediate < maximum

Usage as FastAPI dependency:
    @router.post("/{slug}/schedule/optimize")
    async def optimize(user: dict = Depends(require_plan("intermediate", "maximum"))):
        ...

Usage for limit checks in services:
    from app.modules.cleaning.middleware.plan_guard import check_limit, PLAN_LIMITS
    await check_limit(business_id, "teams", current_count, db)
"""

import json
import logging
from typing import Callable, Optional

import asyncpg
from fastapi import Depends, HTTPException, Request

from app.auth import get_current_user
from app.database import get_db, Database
from app.modules.cleaning.models.auth import PLAN_HIERARCHY, PLAN_LIMITS

logger = logging.getLogger("xcleaners.plan_guard")

# Redis cache TTL for plan lookups
PLAN_CACHE_TTL = 3600  # 1 hour


def _get_redis():
    """Get Redis client, returns None if unavailable."""
    try:
        from app.redis_client import get_redis
        return get_redis()
    except ImportError:
        return None


async def get_business_plan(business_id: str, db: Database) -> str:
    """
    Get the business plan, with Redis caching.

    Reads from business_subscriptions first (active subscription),
    falls back to businesses.plan column.

    Returns: plan name string ("basic", "intermediate", "maximum")
    """
    cache_key = f"clean:{business_id}:plan"
    redis = _get_redis()

    # 1. Check Redis cache
    if redis:
        try:
            cached = await redis.get(cache_key)
            if cached:
                return cached
        except Exception as e:
            logger.warning("[PLAN_CACHE] Redis read error: %s", e)

    # 2. Check business_subscriptions for active subscription
    try:
        plan = await db.pool.fetchval(
            """
            SELECT plan FROM business_subscriptions
            WHERE business_id = $1
              AND status = 'active'
            ORDER BY created_at DESC
            LIMIT 1
            """,
            business_id,
        )
    except asyncpg.exceptions.UndefinedTableError:
        # Table not present in xcleaners standalone DB — fall through to businesses.plan
        plan = None

    # 3. Fall back to businesses.plan column
    if not plan:
        try:
            plan = await db.pool.fetchval(
                "SELECT plan FROM businesses WHERE id = $1",
                business_id,
            )
        except asyncpg.exceptions.UndefinedColumnError:
            # Dev DB or legacy schema may not have `plan` column — treat as unset
            plan = None

    plan = plan or "basic"

    # 4. Cache in Redis
    if redis:
        try:
            await redis.setex(cache_key, PLAN_CACHE_TTL, plan)
        except Exception as e:
            logger.warning("[PLAN_CACHE] Redis write error: %s", e)

    return plan


async def get_business_plan_by_slug(slug: str, db: Database) -> tuple[str, str]:
    """
    Resolve business slug to (business_id, plan).
    Raises 404 if business not found.
    """
    row = await db.pool.fetchrow(
        "SELECT id, plan FROM businesses WHERE slug = $1 AND status != 'cancelled'",
        slug,
    )
    if not row:
        raise HTTPException(status_code=404, detail=f"Business '{slug}' not found")

    business_id = str(row["id"])
    plan = await get_business_plan(business_id, db)
    return business_id, plan


async def invalidate_plan_cache(business_id: str):
    """Invalidate Redis cache when plan changes."""
    redis = _get_redis()
    if redis:
        try:
            await redis.delete(f"clean:{business_id}:plan")
        except Exception as e:
            logger.warning("[PLAN_CACHE] Redis delete error: %s", e)


def require_plan(*allowed_plans: str) -> Callable:
    """
    FastAPI dependency factory that enforces plan requirements.

    Resolves the business slug from URL path params, checks the plan,
    and returns 403 if the plan is not in allowed_plans.

    Args:
        *allowed_plans: One or more plan names (OR logic).
                        Valid plans: basic, intermediate, maximum

    Returns a dependency function that yields a dict with plan info.

    Example:
        require_plan("intermediate", "maximum")  # blocks basic
        require_plan("maximum")  # only maximum plan
    """
    async def _guard(
        request: Request,
        current_user: dict = Depends(get_current_user),
        db: Database = Depends(get_db),
    ) -> dict:
        slug = request.path_params.get("slug")
        if not slug:
            raise HTTPException(
                status_code=400,
                detail="Business slug required in URL path.",
            )

        business_id, plan = await get_business_plan_by_slug(slug, db)

        if plan not in allowed_plans:
            raise HTTPException(
                status_code=403,
                detail=(
                    f"This feature requires {' or '.join(allowed_plans)} plan. "
                    f"Current plan: {plan}."
                ),
            )

        return {
            **current_user,
            "business_id": business_id,
            "business_slug": slug,
            "plan": plan,
            "plan_limits": PLAN_LIMITS.get(plan, {}),
        }

    return _guard


def require_minimum_plan(minimum: str) -> Callable:
    """
    FastAPI dependency factory that enforces a MINIMUM plan level.

    Unlike require_plan() which uses OR logic, this checks the plan
    hierarchy: basic < intermediate < maximum.

    Example:
        require_minimum_plan("intermediate")  # allows intermediate and maximum
    """
    if minimum not in PLAN_HIERARCHY:
        raise ValueError(f"Invalid plan: {minimum}. Must be one of {PLAN_HIERARCHY}")

    min_index = PLAN_HIERARCHY.index(minimum)
    allowed = PLAN_HIERARCHY[min_index:]

    return require_plan(*allowed)


async def check_limit(
    business_id: str,
    resource: str,
    current_count: int,
    db: Database,
):
    """
    Check if a business has reached its plan limit for a resource.

    Args:
        business_id: UUID of the business
        resource: Resource key from PLAN_LIMITS (e.g. "teams", "clients", "sms_monthly")
        current_count: Current usage count
        db: Database instance

    Raises:
        HTTPException 403 if limit reached
    """
    plan = await get_business_plan(business_id, db)
    limits = PLAN_LIMITS.get(plan, PLAN_LIMITS["basic"])
    limit = limits.get(resource)

    if limit is None:
        logger.warning("[PLAN_GUARD] Unknown resource: %s", resource)
        return

    if limit != -1 and current_count >= limit:
        raise HTTPException(
            status_code=403,
            detail=(
                f"{resource} limit reached ({current_count}/{limit}). "
                f"Upgrade your plan to add more."
            ),
        )


async def check_sms_quota(business_id: str, db: Database) -> dict:
    """
    Check SMS quota using the sms_service.
    Convenience wrapper for plan_guard integration.

    Returns: {used, limit, remaining, allowed}
    """
    try:
        from app.modules.cleaning.services.sms_service import check_sms_quota as _check
        return await _check(db, business_id)
    except ImportError:
        # SMS service not available — allow by default
        return {"used": 0, "limit": -1, "remaining": -1, "allowed": True}
