"""
Xcleaners - Rate Limiter
Sliding window rate limiter com Redis primario + memory fallback.

Portado de clawtobusiness em 2026-04-20 (AI Turbo Sprint).
Uso: rate_limiter.is_allowed(user_id, max_requests=30, window_seconds=60)
"""

import time
import secrets
import logging
from typing import Optional

_rate_logger = logging.getLogger("xcleaners.ratelimit")


class RateLimiter:
    """
    Sliding window rate limiter.
    Primary: Redis sorted sets (shared across processes).
    Fallback: In-memory dict (per-process, used when Redis is unavailable).
    """

    def __init__(self):
        self._requests: dict[str, list[float]] = {}

    def _get_redis(self):
        """Lazy import to avoid circular dependency at module load time."""
        try:
            from app.redis_client import get_redis
            return get_redis()
        except ImportError:
            return None

    async def _redis_is_allowed(self, r, key: str, max_requests: int, window_seconds: int) -> bool:
        now = time.time()
        window_start = now - window_seconds
        redis_key = f"ratelimit:{key}"

        pipe = r.pipeline()
        pipe.zremrangebyscore(redis_key, "-inf", window_start)
        pipe.zcard(redis_key)
        pipe.zadd(redis_key, {f"{now}:{secrets.token_hex(4)}": now})
        pipe.expire(redis_key, window_seconds + 1)
        results = await pipe.execute()

        current_count = results[1]
        if current_count >= max_requests:
            return False
        return True

    async def _redis_get_remaining(self, r, key: str, max_requests: int, window_seconds: int) -> int:
        now = time.time()
        window_start = now - window_seconds
        redis_key = f"ratelimit:{key}"

        pipe = r.pipeline()
        pipe.zremrangebyscore(redis_key, "-inf", window_start)
        pipe.zcard(redis_key)
        results = await pipe.execute()

        current_count = results[1]
        return max(0, max_requests - current_count)

    def _memory_is_allowed(self, user_id: str, max_requests: int, window_seconds: int) -> bool:
        now = time.time()
        window_start = now - window_seconds

        if user_id not in self._requests:
            self._requests[user_id] = []

        self._requests[user_id] = [
            req_time for req_time in self._requests[user_id]
            if req_time > window_start
        ]

        if len(self._requests[user_id]) >= max_requests:
            return False

        self._requests[user_id].append(now)
        return True

    def _memory_get_remaining(self, user_id: str, max_requests: int, window_seconds: int) -> int:
        now = time.time()
        window_start = now - window_seconds

        if user_id not in self._requests:
            return max_requests

        recent = [
            req_time for req_time in self._requests[user_id]
            if req_time > window_start
        ]
        return max(0, max_requests - len(recent))

    async def is_allowed(self, user_id: str, max_requests: int = 60, window_seconds: int = 60) -> bool:
        """Check if request is allowed. Tries Redis first, falls back to memory."""
        r = self._get_redis()
        if r:
            try:
                return await self._redis_is_allowed(r, user_id, max_requests, window_seconds)
            except Exception as e:
                _rate_logger.warning("[RATE_LIMIT] Redis error, using fallback: %s", e)
        return self._memory_is_allowed(user_id, max_requests, window_seconds)

    async def get_remaining(self, user_id: str, max_requests: int = 60, window_seconds: int = 60) -> int:
        """Get remaining requests. Tries Redis first, falls back to memory."""
        r = self._get_redis()
        if r:
            try:
                return await self._redis_get_remaining(r, user_id, max_requests, window_seconds)
            except Exception as e:
                _rate_logger.warning("[RATE_LIMIT] Redis error, using fallback: %s", e)
        return self._memory_get_remaining(user_id, max_requests, window_seconds)


# Module-level singleton
rate_limiter = RateLimiter()
