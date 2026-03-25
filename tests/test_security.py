"""Security tests."""
import pytest
from httpx import AsyncClient, ASGITransport


@pytest.mark.asyncio
async def test_unauthenticated_api_returns_401():
    """API endpoints require authentication."""
    from xcleaners_main import app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # /api/v1/clean/my-roles requires a valid JWT via get_current_user
        response = await client.get("/api/v1/clean/my-roles")
        assert response.status_code in (401, 403, 422)


@pytest.mark.asyncio
async def test_invalid_token_rejected():
    """Invalid JWT tokens are rejected."""
    from xcleaners_main import app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/api/v1/clean/my-roles",
            headers={"Authorization": "Bearer invalid.token.here"}
        )
        assert response.status_code in (401, 403)


@pytest.mark.asyncio
async def test_security_headers_present():
    """Security headers are set on responses."""
    from xcleaners_main import app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")
        # Check security headers from SecurityHeadersMiddleware
        assert "x-content-type-options" in response.headers or "X-Content-Type-Options" in response.headers
