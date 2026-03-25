"""
Xcleaners v3 — Security Middleware Suite.

Three middleware layers for defense-in-depth:
  1. SecurityHeadersMiddleware — OWASP security headers on every response
  2. RateLimitMiddleware       — Redis-based sliding-window rate limiting
  3. RequestValidationMiddleware — body-size, path-traversal, UA blocking

All middlewares degrade gracefully when Redis is unavailable.
"""

import html
import logging
import os
import re
import time
from typing import Callable, List, Optional, Set

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

logger = logging.getLogger("xcleaners.security")

# Trusted reverse-proxy IPs (comma-separated in env var).
# Only requests arriving from these IPs will have X-Forwarded-For trusted.
# Empty by default — trust only the direct TCP connection.
TRUSTED_PROXIES: List[str] = [
    ip.strip() for ip in os.getenv("TRUSTED_PROXIES", "").split(",") if ip.strip()
]


# ============================================
# HELPERS
# ============================================

def _get_redis():
    """Get Redis client. Returns None if unavailable."""
    try:
        from app.redis_client import get_redis
        return get_redis()
    except ImportError:
        return None


def _client_ip(request: Request) -> str:
    """Extract client IP, only trusting X-Forwarded-For from known proxies."""
    direct_ip = request.client.host if request.client else None
    if direct_ip and TRUSTED_PROXIES and direct_ip in TRUSTED_PROXIES:
        forwarded = request.headers.get("x-forwarded-for", "")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return direct_ip if direct_ip else "unknown"


# ============================================
# 1. SECURITY HEADERS MIDDLEWARE
# ============================================

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Add OWASP-recommended security headers to every HTTP response.

    Applied as the outermost middleware so headers are present even
    when inner middleware short-circuits (e.g. rate-limit 429).
    """

    HEADERS = {
        "Strict-Transport-Security": "max-age=31536000; includeSubDomains; preload",
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "X-XSS-Protection": "1; mode=block",
        "Referrer-Policy": "strict-origin-when-cross-origin",
        "Content-Security-Policy": (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://accounts.google.com https://static.cloudflareinsights.com; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com; "
            "img-src 'self' data: https:; "
            "connect-src 'self' https://accounts.google.com https://fonts.googleapis.com https://cdn.jsdelivr.net"
        ),
        "Permissions-Policy": "camera=(), microphone=(), geolocation=(self)",
    }

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        response = await call_next(request)
        # Skip CSP in debug mode to avoid blocking CDN/fonts during development
        is_debug = os.getenv("DEBUG", "false").lower() in ("true", "1", "yes")
        for header, value in self.HEADERS.items():
            if is_debug and header == "Content-Security-Policy":
                continue  # Skip CSP in debug mode
            response.headers[header] = value
        return response


# ============================================
# 2. RATE LIMIT MIDDLEWARE
# ============================================

# Endpoint-specific rate-limit rules
# (path_prefix, max_requests, window_seconds)
_AUTH_PATHS = frozenset({"/auth/login", "/auth/register"})
_PASSWORD_RESET_PATHS = frozenset({"/auth/reset-password", "/auth/forgot-password"})

# Default limits
_GENERAL_LIMIT = 100       # requests
_GENERAL_WINDOW = 60       # seconds
_AUTH_LIMIT = 5            # requests
_AUTH_WINDOW = 60          # seconds
_RESET_LIMIT = 3           # requests
_RESET_WINDOW = 3600       # seconds (1 hour)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Redis-based sliding-window rate limiting per IP (and stricter for auth).

    Strategy: Redis INCR + EXPIRE for a simple fixed-window counter.
    Falls back gracefully (allows request) if Redis is unavailable.
    """

    # Paths exempt from rate limiting
    EXEMPT_PATHS: Set[str] = {"/health", "/docs", "/redoc", "/openapi.json"}

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        path = request.url.path

        # Skip exempt paths
        if path in self.EXEMPT_PATHS or path.startswith("/cleaning/static"):
            return await call_next(request)

        redis = _get_redis()
        if redis is None:
            # Redis unavailable — allow request, log warning once
            return await call_next(request)

        ip = _client_ip(request)

        # Determine limit and window based on path
        if path in _AUTH_PATHS:
            limit, window = _AUTH_LIMIT, _AUTH_WINDOW
            key = f"rl:auth:{ip}:{path}"
        elif path in _PASSWORD_RESET_PATHS:
            limit, window = _RESET_LIMIT, _RESET_WINDOW
            key = f"rl:reset:{ip}:{path}"
        else:
            limit, window = _GENERAL_LIMIT, _GENERAL_WINDOW
            key = f"rl:general:{ip}"

        try:
            pipe = redis.pipeline()
            pipe.incr(key)
            pipe.expire(key, window, nx=True)  # set TTL only if not already set
            results = await pipe.execute()
            current_count = results[0]

            if current_count > limit:
                retry_after = await redis.ttl(key)
                retry_after = max(retry_after, 1)
                logger.warning(
                    "[RATE_LIMIT] %s hit limit on %s (%d/%d)",
                    ip, path, current_count, limit,
                )
                return JSONResponse(
                    status_code=429,
                    content={"detail": "Too many requests. Please try again later."},
                    headers={"Retry-After": str(retry_after)},
                )
        except Exception as exc:
            # Redis error — degrade gracefully, allow request
            logger.warning("[RATE_LIMIT] Redis error, allowing request: %s", exc)

        return await call_next(request)


# ============================================
# 3. REQUEST VALIDATION MIDDLEWARE
# ============================================

# Known scanner / malicious User-Agent fragments
_BLOCKED_UA_PATTERNS = re.compile(
    r"(sqlmap|nikto|nessus|dirbuster|havij|netsparker|acunetix|"
    r"w3af|skipfish|openvas|masscan|zgrab|nuclei)",
    re.IGNORECASE,
)

# Path traversal pattern
_PATH_TRAVERSAL = re.compile(r"\.\./|\.\.\\|%2e%2e[/\\%]", re.IGNORECASE)

# Max request body size: 10 MB
_MAX_BODY_SIZE = 10 * 1024 * 1024

# Simple script-tag pattern for query param sanitization
_SCRIPT_TAG = re.compile(r"<\s*script[^>]*>", re.IGNORECASE)


class RequestValidationMiddleware(BaseHTTPMiddleware):
    """
    Validate and sanitize incoming requests.

    Checks:
      - Request body size (max 10 MB)
      - Block empty or known-malicious User-Agents
      - Detect and block path traversal attempts
      - Strip <script> tags from query parameters
    """

    # Paths exempt from body-size check (file uploads may be larger)
    UPLOAD_PATHS: Set[str] = set()

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        ip = _client_ip(request)
        path = request.url.path

        # --- Path traversal check ---
        if _PATH_TRAVERSAL.search(path):
            logger.warning("[SECURITY] Path traversal attempt from %s: %s", ip, path)
            return JSONResponse(
                status_code=400,
                content={"detail": "Invalid request path."},
            )

        # --- User-Agent check ---
        user_agent = request.headers.get("user-agent", "")
        if not user_agent:
            logger.warning("[SECURITY] Empty User-Agent from %s on %s", ip, path)
            return JSONResponse(
                status_code=403,
                content={"detail": "Request blocked."},
            )

        if _BLOCKED_UA_PATTERNS.search(user_agent):
            logger.warning(
                "[SECURITY] Blocked scanner UA from %s: %s", ip, user_agent[:80]
            )
            return JSONResponse(
                status_code=403,
                content={"detail": "Request blocked."},
            )

        # --- Body size check ---
        content_length = request.headers.get("content-length")
        if content_length and path not in self.UPLOAD_PATHS:
            try:
                if int(content_length) > _MAX_BODY_SIZE:
                    logger.warning(
                        "[SECURITY] Oversized request from %s: %s bytes",
                        ip, content_length,
                    )
                    return JSONResponse(
                        status_code=413,
                        content={"detail": "Request body too large."},
                    )
            except ValueError:
                pass  # non-numeric content-length handled by server

        # --- Query param sanitization ---
        # We sanitize at the logging/detection level; actual stripping
        # happens in route-level validation. Here we detect and log.
        query_string = str(request.url.query) if request.url.query else ""
        if _SCRIPT_TAG.search(query_string):
            logger.warning(
                "[SECURITY] Script tag in query params from %s: %s",
                ip, query_string[:200],
            )
            return JSONResponse(
                status_code=400,
                content={"detail": "Invalid query parameters."},
            )

        return await call_next(request)
