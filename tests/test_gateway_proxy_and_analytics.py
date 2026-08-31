import time
import uuid
import httpx
import pytest
import pytest_asyncio

from app.core.database import engine
from app.core.redis import get_redis
from app.main import app
from app.services.rate_limit import RateLimitService
from app.services.quota import QuotaService


@pytest_asyncio.fixture
async def async_client():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    await engine.dispose()


@pytest.mark.asyncio
async def test_rate_limit_service():
    redis = await get_redis()
    try:
        service = RateLimitService(redis)
        test_key_id = uuid.uuid4()

        # Under limit
        res1 = await service.check(api_key_id=test_key_id, limit=2)
        assert res1.allowed is True
        assert res1.remaining == 1

        res2 = await service.check(api_key_id=test_key_id, limit=2)
        assert res2.allowed is True
        assert res2.remaining == 0

        # Over limit
        res3 = await service.check(api_key_id=test_key_id, limit=2)
        assert res3.allowed is False
        assert res3.remaining == 0
    finally:
        await redis.aclose()


@pytest.mark.asyncio
async def test_quota_service():
    redis = await get_redis()
    try:
        service = QuotaService(redis)
        test_sub_id = uuid.uuid4()

        # Consume quota
        res1 = await service.consume(subscription_id=test_sub_id, monthly_quota=2)
        assert res1.allowed is True
        assert res1.used == 1

        res2 = await service.consume(subscription_id=test_sub_id, monthly_quota=2)
        assert res2.allowed is True
        assert res2.used == 2

        res3 = await service.consume(subscription_id=test_sub_id, monthly_quota=2)
        assert res3.allowed is False
    finally:
        await redis.aclose()


@pytest.mark.asyncio
async def test_analytics_endpoints(async_client):
    ts = int(time.time() * 1000)
    email = f"analytics_owner_{ts}@test.com"

    await async_client.post(
        "/auth/register",
        json={"email": email, "password": "Password123!", "first_name": "Analytics", "last_name": "Owner"},
    )
    login_res = await async_client.post("/auth/login", json={"email": email, "password": "Password123!"})
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    org_res = await async_client.post(
        "/organizations",
        headers=headers,
        json={"name": f"Analytics Org {ts}", "slug": f"analytics-org-{ts}"},
    )
    org_id = org_res.json()["id"]

    api_res = await async_client.post(
        f"/organizations/{org_id}/apis",
        headers=headers,
        json={"name": "Analytics API", "slug": f"analytics-api-{ts}", "base_path": "/analytics"},
    )
    api_id = api_res.json()["id"]

    # Organization analytics
    org_analytics_res = await async_client.get(
        f"/organizations/{org_id}/analytics",
        headers=headers,
    )
    assert org_analytics_res.status_code == 200
    data = org_analytics_res.json()
    assert "total_requests" in data
    assert "average_response_time_ms" in data
    assert "status_distribution" in data

    # API analytics
    api_analytics_res = await async_client.get(
        f"/organizations/{org_id}/analytics/apis/{api_id}",
        headers=headers,
    )
    assert api_analytics_res.status_code == 200
    api_data = api_analytics_res.json()
    assert "total_requests" in api_data
