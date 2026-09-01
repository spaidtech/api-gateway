import asyncio
import hashlib
import time
import uuid
from datetime import datetime, timedelta, timezone

import httpx
import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy import select


from app.core.database import AsyncSessionLocal, engine
from app.core.redis import get_redis
from app.main import app
from app.models.api import API, APIStatus
from app.models.api_key import APIKey
from app.models.api_plan import APIPlan
from app.models.api_route import APIRoute
from app.models.health_check import HealthCheck
from app.models.membership import OrganizationMember
from app.models.organization import Organization
from app.models.subscription import Subscription
from app.models.upstream import Upstream
from app.models.usage_record import UsageRecord
from app.models.user import User
from app.services.gateway_proxy import GatewayProxyService
from app.services.quota import QuotaService
from app.services.rate_limit import RateLimitService


@pytest_asyncio.fixture
async def async_client():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    await engine.dispose()


@pytest_asyncio.fixture
async def e2e_environment(async_client):
    ts = int(time.time() * 1000)
    users = {}
    tokens = {}

    # Register 3 users: provider_owner, consumer_owner, attacker
    for role_name in ["provider_owner", "consumer_owner", "attacker"]:
        email = f"e2e_{role_name}_{ts}@test.com"
        await async_client.post(
            "/auth/register",
            json={
                "email": email,
                "password": "Password123!",
                "first_name": role_name,
                "last_name": "E2E",
            },
        )
        login_res = await async_client.post(
            "/auth/login",
            json={"email": email, "password": "Password123!"},
        )
        token = login_res.json()["access_token"]
        tokens[role_name] = token
        me = await async_client.get(
            "/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        users[role_name] = me.json()["id"]

    provider_headers = {"Authorization": f"Bearer {tokens['provider_owner']}"}
    consumer_headers = {"Authorization": f"Bearer {tokens['consumer_owner']}"}
    attacker_headers = {"Authorization": f"Bearer {tokens['attacker']}"}

    # 1. Provider Org
    res_prov = await async_client.post(
        "/organizations",
        headers=provider_headers,
        json={"name": f"Provider Org {ts}", "slug": f"provider-{ts}"},
    )
    provider_org_id = res_prov.json()["id"]
    provider_slug = res_prov.json()["slug"]

    # 2. Consumer Org
    res_cons = await async_client.post(
        "/organizations",
        headers=consumer_headers,
        json={"name": f"Consumer Org {ts}", "slug": f"consumer-{ts}"},
    )
    consumer_org_id = res_cons.json()["id"]
    consumer_slug = res_cons.json()["slug"]

    # 3. Provider registers an Upstream
    upstream_res = await async_client.post(
        f"/organizations/{provider_org_id}/upstreams",
        headers=provider_headers,
        json={
            "name": "E2E Payment Service",
            "base_url": "https://httpbin.org",
            "is_active": True,
        },
    )
    upstream_id = upstream_res.json()["id"]

    # 4. Provider creates an API
    api_res = await async_client.post(
        f"/organizations/{provider_org_id}/apis",
        headers=provider_headers,
        json={
            "name": "Payments API",
            "slug": f"payments-{ts}",
            "version": "v1",
            "base_path": "/payments",
            "visibility": "public",
        },
    )
    assert api_res.status_code == 201, f"Failed to create API: {api_res.text}"
    api_id = api_res.json()["id"]
    api_slug = api_res.json()["slug"]

    # Publish the API
    await async_client.patch(
        f"/organizations/{provider_org_id}/apis/{api_id}",
        headers=provider_headers,
        json={"status": "published"},
    )


    # 5. Provider creates API Route
    route_res = await async_client.post(
        f"/organizations/{provider_org_id}/apis/{api_id}/routes",
        headers=provider_headers,
        json={
            "upstream_id": upstream_id,
            "path": "/charge",
            "method": "POST",
            "target_path": "/post",
        },
    )
    route_id = route_res.json()["id"]

    # 6. Provider creates API Plan (Rate Limit: 5 req/min, Monthly Quota: 100)
    plan_res = await async_client.post(
        f"/organizations/{provider_org_id}/apis/{api_id}/plans",
        headers=provider_headers,
        json={
            "name": "Growth Tier",
            "price": "49.99",
            "currency": "USD",
            "billing_interval": "monthly",
            "rate_limit": 5,
            "monthly_quota": 100,
        },
    )
    plan_id = plan_res.json()["id"]

    # 7. Consumer Subscribes to Provider's Plan
    sub_res = await async_client.post(
        f"/organizations/{consumer_org_id}/subscriptions",
        headers=consumer_headers,
        json={"plan_id": plan_id},
    )
    subscription_id = sub_res.json()["id"]

    # Activate subscription in db for e2e gateway test
    async with AsyncSessionLocal() as session:
        sub_obj = (await session.execute(select(Subscription).where(Subscription.id == uuid.UUID(subscription_id)))).scalar_one()
        sub_obj.status = "active"
        sub_obj.starts_at = datetime.now(timezone.utc)
        sub_obj.ends_at = datetime.now(timezone.utc) + timedelta(days=30)
        await session.commit()

    # 8. Consumer Generates an API Key tied to their subscription
    key_res = await async_client.post(
        f"/organizations/{consumer_org_id}/api-keys",
        headers=consumer_headers,
        json={"name": "Consumer Production Key", "subscription_id": subscription_id},
    )
    consumer_api_key_id = key_res.json()["id"]
    consumer_raw_key = key_res.json()["api_key"]

    return {
        "ts": ts,
        "users": users,
        "tokens": tokens,
        "provider_headers": provider_headers,
        "consumer_headers": consumer_headers,
        "attacker_headers": attacker_headers,
        "provider_org_id": provider_org_id,
        "provider_slug": provider_slug,
        "consumer_org_id": consumer_org_id,
        "consumer_slug": consumer_slug,
        "upstream_id": upstream_id,
        "api_id": api_id,
        "api_slug": api_slug,
        "route_id": route_id,
        "plan_id": plan_id,
        "subscription_id": subscription_id,
        "consumer_api_key_id": consumer_api_key_id,
        "consumer_raw_key": consumer_raw_key,
    }


@pytest.mark.asyncio
async def test_full_subscription_and_gateway_proxy_flow(async_client, e2e_environment, monkeypatch):
    data = e2e_environment
    provider_slug = data["provider_slug"]
    api_slug = data["api_slug"]
    raw_key = data["consumer_raw_key"]

    # Mock the upstream response to test end-to-end proxy behavior deterministically
    async def mock_forward_request(self, *, method, url, headers, query_params=None, body=b""):
        assert method == "POST"
        assert "/post" in url
        return httpx.Response(
            status_code=200,
            headers={"Content-Type": "application/json", "X-Upstream-Service": "PaymentService"},
            json={"status": "success", "charge_id": "ch_12345", "amount": 100},
        )

    monkeypatch.setattr(GatewayProxyService, "forward_request", mock_forward_request)

    # Make gateway proxy request as consumer using subscription API key
    response = await async_client.post(
        f"/gateway/{provider_slug}/{api_slug}/charge?ref=test1",
        headers={
            "X-API-Key": raw_key,
            "Content-Type": "application/json",
            "X-Custom-Client": "ClientApp1",
        },
        json={"amount": 100, "currency": "USD"},
    )

    assert response.status_code == 200
    res_data = response.json()
    assert res_data["status"] == "success"
    assert res_data["charge_id"] == "ch_12345"
    assert "X-RateLimit-Limit" in response.headers
    assert response.headers["X-RateLimit-Limit"] == "5"
    assert "X-RateLimit-Remaining" in response.headers
    assert response.headers.get("X-Upstream-Service") == "PaymentService"


@pytest.mark.asyncio
async def test_rate_limiting_enforcement(async_client, e2e_environment, monkeypatch):
    data = e2e_environment
    provider_slug = data["provider_slug"]
    api_slug = data["api_slug"]
    raw_key = data["consumer_raw_key"]

    async def mock_forward(self, **kwargs):
        return httpx.Response(status_code=200, json={"ok": True})

    monkeypatch.setattr(GatewayProxyService, "forward_request", mock_forward)

    # 5 requests should succeed (limit is 5)
    for i in range(5):
        res = await async_client.post(
            f"/gateway/{provider_slug}/{api_slug}/charge",
            headers={"X-API-Key": raw_key},
        )
        assert res.status_code == 200, f"Request {i+1} failed"

    # 6th request must be rate limited
    res_exceeded = await async_client.post(
        f"/gateway/{provider_slug}/{api_slug}/charge",
        headers={"X-API-Key": raw_key},
    )
    assert res_exceeded.status_code == 429
    assert "Rate limit exceeded" in res_exceeded.json()["detail"]
    assert res_exceeded.headers.get("X-RateLimit-Remaining") == "0"


@pytest.mark.asyncio
async def test_domain_restriction_matching_and_wildcard(async_client, e2e_environment, monkeypatch):
    data = e2e_environment
    consumer_headers = data["consumer_headers"]
    consumer_org_id = data["consumer_org_id"]
    key_id = data["consumer_api_key_id"]
    raw_key = data["consumer_raw_key"]
    provider_slug = data["provider_slug"]
    api_slug = data["api_slug"]

    async def mock_forward(self, **kwargs):
        return httpx.Response(status_code=200, json={"ok": True})

    monkeypatch.setattr(GatewayProxyService, "forward_request", mock_forward)

    # 1. Add domain restriction: *.example.com
    add_dom_res = await async_client.post(
        f"/organizations/{consumer_org_id}/api-keys/{key_id}/domains",
        headers=consumer_headers,
        json={"domain": "*.example.com"},
    )
    assert add_dom_res.status_code == 201

    # 2. Add exact domain restriction: app.payments.io
    await async_client.post(
        f"/organizations/{consumer_org_id}/api-keys/{key_id}/domains",
        headers=consumer_headers,
        json={"domain": "app.payments.io"},
    )

    # 3. Request without origin header -> Forbidden
    res_no_origin = await async_client.post(
        f"/gateway/{provider_slug}/{api_slug}/charge",
        headers={"X-API-Key": raw_key},
    )
    assert res_no_origin.status_code == 403

    # 4. Request with disallowed origin -> Forbidden
    res_bad_origin = await async_client.post(
        f"/gateway/{provider_slug}/{api_slug}/charge",
        headers={"X-API-Key": raw_key, "Origin": "https://malicious.site.com"},
    )
    assert res_bad_origin.status_code == 403

    # 5. Request with wildcard matched origin -> Success
    res_wildcard = await async_client.post(
        f"/gateway/{provider_slug}/{api_slug}/charge",
        headers={"X-API-Key": raw_key, "Origin": "https://sub.example.com"},
    )
    assert res_wildcard.status_code == 200

    # 6. Request with exact matched origin -> Success
    res_exact = await async_client.post(
        f"/gateway/{provider_slug}/{api_slug}/charge",
        headers={"X-API-Key": raw_key, "Origin": "https://app.payments.io"},
    )
    assert res_exact.status_code == 200


@pytest.mark.asyncio
async def test_upstream_health_monitoring_and_history(async_client, e2e_environment, monkeypatch):
    data = e2e_environment
    provider_headers = data["provider_headers"]
    provider_org_id = data["provider_org_id"]
    upstream_id = data["upstream_id"]
    api_id = data["api_id"]

    # 1. Trigger health check on healthy upstream
    res_check = await async_client.post(
        f"/organizations/{provider_org_id}/upstreams/{upstream_id}/health-check?api_id={api_id}",
        headers=provider_headers,
    )
    assert res_check.status_code == 200
    hc_data = res_check.json()
    assert hc_data["upstream_id"] == upstream_id
    assert hc_data["status"] in ["healthy", "unhealthy"]

    # 2. Get latest health
    res_latest = await async_client.get(
        f"/organizations/{provider_org_id}/upstreams/{upstream_id}/health",
        headers=provider_headers,
    )
    assert res_latest.status_code == 200
    assert res_latest.json()["id"] == hc_data["id"]

    # 3. Get health history
    res_history = await async_client.get(
        f"/organizations/{provider_org_id}/upstreams/{upstream_id}/health-history?limit=10",
        headers=provider_headers,
    )
    assert res_history.status_code == 200
    assert len(res_history.json()) >= 1


@pytest.mark.asyncio
async def test_cross_tenant_security_and_isolation(async_client, e2e_environment):
    data = e2e_environment
    provider_org_id = data["provider_org_id"]
    consumer_org_id = data["consumer_org_id"]
    attacker_headers = data["attacker_headers"]
    consumer_headers = data["consumer_headers"]
    upstream_id = data["upstream_id"]
    api_id = data["api_id"]
    plan_id = data["plan_id"]
    subscription_id = data["subscription_id"]

    # 1. Attacker tries to access provider's upstream -> 403 Forbidden
    res_upstream = await async_client.get(
        f"/organizations/{provider_org_id}/upstreams/{upstream_id}",
        headers=attacker_headers,
    )
    assert res_upstream.status_code == 403

    # 2. Attacker tries to access provider's API -> 403 Forbidden
    res_api = await async_client.get(
        f"/organizations/{provider_org_id}/apis/{api_id}",
        headers=attacker_headers,
    )
    assert res_api.status_code == 403

    # 3. Attacker tries to modify members of consumer org -> 403 Forbidden
    res_mem = await async_client.get(
        f"/organizations/{consumer_org_id}/members",
        headers=attacker_headers,
    )
    assert res_mem.status_code == 403

    # 4. Attacker tries to view provider's analytics -> 403 Forbidden
    res_analytics = await async_client.get(
        f"/organizations/{provider_org_id}/analytics",
        headers=attacker_headers,
    )
    assert res_analytics.status_code == 403

    # 5. Attacker tries to create API key with consumer's subscription_id -> 400 Bad Request
    res_spoof_sub = await async_client.post(
        f"/organizations/{provider_org_id}/api-keys",
        headers=data["provider_headers"],
        json={"name": "Spoofed Key", "subscription_id": subscription_id},  # sub belongs to consumer_org
    )
    assert res_spoof_sub.status_code == 400


@pytest.mark.asyncio
async def test_upstream_failures_and_timeouts(async_client, e2e_environment):
    proxy_service = GatewayProxyService()

    # 1. Connection failure -> 502 Bad Gateway
    with pytest.raises(HTTPException) as exc_502:
        await proxy_service.forward_request(
            method="GET",
            url="http://127.0.0.1:59999/unreachable",
            headers={},
        )
    assert exc_502.value.status_code == 502
    assert "Unable to connect" in exc_502.value.detail

    # 2. Timeout failure -> 504 Gateway Timeout
    with pytest.raises(HTTPException) as exc_504:
        timeout_service = GatewayProxyService(timeout=0.000001)
        await timeout_service.forward_request(
            method="GET",
            url="https://httpbin.org/delay/5",
            headers={},
        )
    assert exc_504.value.status_code == 504
    assert "timed out" in exc_504.value.detail



@pytest.mark.asyncio
async def test_analytics_endpoints_and_filtering(async_client, e2e_environment):
    data = e2e_environment
    provider_headers = data["provider_headers"]
    provider_org_id = data["provider_org_id"]
    api_id = data["api_id"]
    route_id = data["route_id"]

    # Populate usage record directly in db to verify analytics calculation
    async with AsyncSessionLocal() as session:
        record = UsageRecord(
            organization_id=uuid.UUID(provider_org_id),
            api_id=uuid.UUID(api_id),
            route_id=uuid.UUID(route_id),
            api_key_id=uuid.UUID(data["consumer_api_key_id"]),
            status_code=200,
            latency_ms=45,
            domain="app.test.com",
            timestamp=datetime.now(timezone.utc),
        )
        session.add(record)
        await session.commit()

    # 1. Organization analytics
    res_org = await async_client.get(
        f"/organizations/{provider_org_id}/analytics",
        headers=provider_headers,
    )
    assert res_org.status_code == 200
    assert res_org.json()["total_requests"] >= 1
    assert "200" in res_org.json()["status_distribution"]

    # 2. API-level analytics
    res_api = await async_client.get(
        f"/organizations/{provider_org_id}/analytics/apis/{api_id}",
        headers=provider_headers,
    )
    assert res_api.status_code == 200
    assert res_api.json()["total_requests"] >= 1

    # 3. Route-level analytics
    res_route = await async_client.get(
        f"/organizations/{provider_org_id}/analytics/apis/{api_id}/routes/{route_id}",
        headers=provider_headers,
    )
    assert res_route.status_code == 200
    assert res_route.json()["total_requests"] >= 1

    # 4. Cross-tenant API analytics attempt -> 404
    consumer_headers = data["consumer_headers"]
    consumer_org_id = data["consumer_org_id"]
    res_cross = await async_client.get(
        f"/organizations/{consumer_org_id}/analytics/apis/{api_id}",
        headers=consumer_headers,
    )
    assert res_cross.status_code == 404
