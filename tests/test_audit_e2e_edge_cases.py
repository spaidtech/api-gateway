import hashlib
import json
import time
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import patch, MagicMock

import httpx
import pytest
import pytest_asyncio
from jose import jwt
from redis.asyncio import Redis
from sqlalchemy import select

from app.core.config import settings
from app.core.database import AsyncSessionLocal, engine
from app.core.redis import get_redis
from app.main import app
from app.models.api_key import APIKey
from app.models.api_key_domain import APIKeyDomain
from app.models.payment import Payment, PaymentProvider, PaymentStatus
from app.models.subscription import Subscription
from app.models.upstream import Upstream
from app.models.usage_record import UsageRecord
from app.services.health_check import HealthCheckService
from app.repositories.health_check import HealthCheckRepository


@pytest_asyncio.fixture
async def async_client():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    await engine.dispose()


@pytest_asyncio.fixture
async def setup_audit_environment(async_client):
    ts = int(time.time() * 1000)
    users = {}
    tokens = {}

    for role_name in ["owner_a", "admin_a", "member_a", "owner_b", "outsider"]:
        email = f"audit_{role_name}_{ts}@test.com"
        await async_client.post(
            "/auth/register",
            json={
                "email": email,
                "password": "Password123!",
                "first_name": role_name,
                "last_name": "Test",
            },
        )
        login_res = await async_client.post(
            "/auth/login",
            json={"email": email, "password": "Password123!"},
        )
        token = login_res.json()["access_token"]
        tokens[role_name] = token
        me = await async_client.get(
            "/auth/me", headers={"Authorization": f"Bearer {token}"}
        )
        users[role_name] = me.json()["id"]

    headers_owner_a = {"Authorization": f"Bearer {tokens['owner_a']}"}
    headers_admin_a = {"Authorization": f"Bearer {tokens['admin_a']}"}
    headers_member_a = {"Authorization": f"Bearer {tokens['member_a']}"}
    headers_owner_b = {"Authorization": f"Bearer {tokens['owner_b']}"}
    headers_outsider = {"Authorization": f"Bearer {tokens['outsider']}"}

    # 1. Create Organization A & Organization B
    res_org_a = await async_client.post(
        "/organizations",
        headers=headers_owner_a,
        json={"name": f"Org A {ts}", "slug": f"org-a-{ts}"},
    )
    org_a_id = res_org_a.json()["id"]

    res_org_b = await async_client.post(
        "/organizations",
        headers=headers_owner_b,
        json={"name": f"Org B {ts}", "slug": f"org-b-{ts}"},
    )
    org_b_id = res_org_b.json()["id"]

    # Add admin_a and member_a to Org A
    roles_res = await async_client.get(
        f"/organizations/{org_a_id}/members",
        headers=headers_owner_a,
    )
    owner_member = roles_res.json()[0]
    admin_role_id = None
    member_role_id = None

    # Fetch role IDs directly from DB
    from app.repositories.role import RoleRepository
    async with AsyncSessionLocal() as session:
        role_repo = RoleRepository(session)
        admin_role = await role_repo.get_by_name("admin")
        member_role = await role_repo.get_by_name("member")
        admin_role_id = str(admin_role.id)
        member_role_id = str(member_role.id)

    # Add admin_a to Org A
    await async_client.post(
        f"/organizations/{org_a_id}/members",
        headers=headers_owner_a,
        json={"user_id": users["admin_a"], "role_id": admin_role_id},
    )

    # Add member_a to Org A
    await async_client.post(
        f"/organizations/{org_a_id}/members",
        headers=headers_owner_a,
        json={"user_id": users["member_a"], "role_id": member_role_id},
    )

    # 2. Org A creates Upstream, API, Route, and Plan
    up_res = await async_client.post(
        f"/organizations/{org_a_id}/upstreams",
        headers=headers_owner_a,
        json={"name": "Primary Upstream", "base_url": "https://httpbin.org"},
    )
    upstream_a_id = up_res.json()["id"]

    api_res = await async_client.post(
        f"/organizations/{org_a_id}/apis",
        headers=headers_owner_a,
        json={"name": "Audit API", "slug": f"audit-api-{ts}", "base_path": "/audit"},
    )
    api_a_id = api_res.json()["id"]
    api_a_slug = api_res.json()["slug"]

    # Publish API
    await async_client.patch(
        f"/organizations/{org_a_id}/apis/{api_a_id}",
        headers=headers_owner_a,
        json={"status": "published"},
    )

    # Route
    route_res = await async_client.post(
        f"/organizations/{org_a_id}/apis/{api_a_id}/routes",
        headers=headers_owner_a,
        json={
            "upstream_id": upstream_a_id,
            "path": "/get-data",
            "method": "GET",
            "target_path": "/get",
        },
    )
    route_a_id = route_res.json()["id"]

    # Paid Plan & Free Plan
    plan_paid_res = await async_client.post(
        f"/organizations/{org_a_id}/apis/{api_a_id}/plans",
        headers=headers_owner_a,
        json={
            "name": "Pro Tier",
            "price": "99.00",
            "currency": "USD",
            "billing_interval": "monthly",
            "rate_limit": 10,
            "monthly_quota": 500,
        },
    )
    plan_paid_id = plan_paid_res.json()["id"]

    plan_free_res = await async_client.post(
        f"/organizations/{org_a_id}/apis/{api_a_id}/plans",
        headers=headers_owner_a,
        json={
            "name": "Free Tier",
            "price": "0.00",
            "currency": "USD",
            "billing_interval": "monthly",
            "rate_limit": 5,
            "monthly_quota": 100,
        },
    )
    plan_free_id = plan_free_res.json()["id"]

    return {
        "ts": ts,
        "users": users,
        "tokens": tokens,
        "headers_owner_a": headers_owner_a,
        "headers_admin_a": headers_admin_a,
        "headers_member_a": headers_member_a,
        "headers_owner_b": headers_owner_b,
        "headers_outsider": headers_outsider,
        "org_a_id": org_a_id,
        "org_a_slug": f"org-a-{ts}",
        "org_b_id": org_b_id,
        "upstream_a_id": upstream_a_id,
        "api_a_id": api_a_id,
        "api_a_slug": api_a_slug,
        "route_a_id": route_a_id,
        "plan_paid_id": plan_paid_id,
        "plan_free_id": plan_free_id,
    }


# =========================================================================
# 1. AUTHENTICATION & JWT SECURITY EDGE CASES
# =========================================================================

@pytest.mark.asyncio
async def test_auth_edge_cases(async_client, setup_audit_environment):
    data = setup_audit_environment
    ts = data["ts"]

    # 1. Register with existing email -> 409
    dup_res = await async_client.post(
        "/auth/register",
        json={"email": f"audit_owner_a_{ts}@test.com", "password": "Password123!"},
    )
    assert dup_res.status_code == 409

    # 2. Login with wrong password -> 401
    bad_login = await async_client.post(
        "/auth/login",
        json={"email": f"audit_owner_a_{ts}@test.com", "password": "WrongPassword!"},
    )
    assert bad_login.status_code == 401

    # 3. Login with unknown email -> 401
    bad_email = await async_client.post(
        "/auth/login",
        json={"email": f"unknown_{ts}@test.com", "password": "Password123!"},
    )
    assert bad_email.status_code == 401

    # 4. Token validation: Corrupted token -> 401
    corrupt_res = await async_client.get(
        "/auth/me",
        headers={"Authorization": "Bearer not.a.valid.jwt"},
    )
    assert corrupt_res.status_code == 401

    # 5. Token validation: Wrong signature secret -> 401
    fake_token = jwt.encode(
        {"sub": data["users"]["owner_a"], "exp": int(time.time()) + 3600, "type": "access"},
        "wrong-secret-key-12345678901234567890",
        algorithm="HS256",
    )
    fake_res = await async_client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {fake_token}"},
    )
    assert fake_res.status_code == 401

    # 6. Token validation: Expired token -> 401
    expired_token = jwt.encode(
        {"sub": data["users"]["owner_a"], "exp": int(time.time()) - 3600, "type": "access"},
        settings.JWT_SECRET_KEY,
        algorithm="HS256",
    )
    expired_res = await async_client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {expired_token}"},
    )
    assert expired_res.status_code == 401

    # 7. Refresh token used as access token -> 401
    refresh_token = jwt.encode(
        {"sub": data["users"]["owner_a"], "exp": int(time.time()) + 3600, "type": "refresh"},
        settings.JWT_SECRET_KEY,
        algorithm="HS256",
    )
    wrong_type_res = await async_client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {refresh_token}"},
    )
    assert wrong_type_res.status_code == 401


# =========================================================================
# 2. RBAC & TENANT ISOLATION (CROSS-ORG INJECTION)
# =========================================================================

@pytest.mark.asyncio
async def test_rbac_and_cross_tenant_isolation(async_client, setup_audit_environment):
    data = setup_audit_environment
    org_a = data["org_a_id"]
    org_b = data["org_b_id"]
    api_a = data["api_a_id"]
    up_a = data["upstream_a_id"]

    # 1. Member cannot create upstreams in Org A -> 403
    res_mem_up = await async_client.post(
        f"/organizations/{org_a}/upstreams",
        headers=data["headers_member_a"],
        json={"name": "Member Upstream", "base_url": "https://api.test"},
    )
    assert res_mem_up.status_code == 403

    # 2. Outsider cannot list Org A resources -> 403
    res_out_list = await async_client.get(
        f"/organizations/{org_a}/upstreams",
        headers=data["headers_outsider"],
    )
    assert res_out_list.status_code == 403

    # 3. Cross-Tenant: Org B owner cannot read Org A's upstream via Org B path -> 404
    res_cross_up = await async_client.get(
        f"/organizations/{org_b}/upstreams/{up_a}",
        headers=data["headers_owner_b"],
    )
    assert res_cross_up.status_code == 404

    # 4. Cross-Tenant: Org B owner cannot create route in Org B referencing Org A's upstream -> 404
    api_b_res = await async_client.post(
        f"/organizations/{org_b}/apis",
        headers=data["headers_owner_b"],
        json={"name": "API B", "slug": f"api-b-{data['ts']}", "base_path": "/b"},
    )
    api_b_id = api_b_res.json()["id"]

    res_cross_route = await async_client.post(
        f"/organizations/{org_b}/apis/{api_b_id}/routes",
        headers=data["headers_owner_b"],
        json={"upstream_id": up_a, "path": "/hijack", "method": "GET", "target_path": "/"},
    )
    assert res_cross_route.status_code == 404

    # 5. Non-member cannot modify Org A membership -> 403
    res_hack_member = await async_client.post(
        f"/organizations/{org_a}/members",
        headers=data["headers_owner_b"],
        json={"user_id": data["users"]["owner_b"], "role_id": str(uuid.uuid4())},
    )
    assert res_hack_member.status_code == 403


# =========================================================================
# 3. API KEY DOMAIN RESTRICTIONS & SPOOFING PREVENTION
# =========================================================================

@pytest.mark.asyncio
async def test_domain_restriction_spoofing_prevention(
    async_client, setup_audit_environment
):
    data = setup_audit_environment
    org_a = data["org_a_id"]
    plan_free = data["plan_free_id"]

    # 1. Subscribe to Free Plan
    sub_res = await async_client.post(
        f"/organizations/{org_a}/subscriptions",
        headers=data["headers_owner_a"],
        json={"plan_id": plan_free},
    )
    assert sub_res.status_code == 201
    sub_id = sub_res.json()["id"]

    # 2. Create API key
    key_res = await async_client.post(
        f"/organizations/{org_a}/api-keys",
        headers=data["headers_owner_a"],
        json={"name": "Domain Test Key", "subscription_id": sub_id},
    )
    assert key_res.status_code == 201
    key_id = key_res.json()["id"]
    raw_key = key_res.json()["api_key"]

    # 3. Add Exact Domain Restriction: "company.com"
    dom_res1 = await async_client.post(
        f"/organizations/{org_a}/api-keys/{key_id}/domains",
        headers=data["headers_owner_a"],
        json={"domain": "company.com"},
    )
    assert dom_res1.status_code == 201

    # Add Wildcard Domain: "*.trusted.org"
    dom_res2 = await async_client.post(
        f"/organizations/{org_a}/api-keys/{key_id}/domains",
        headers=data["headers_owner_a"],
        json={"domain": "*.trusted.org"},
    )
    assert dom_res2.status_code == 201

    # Exact match: "company.com" -> Allowed
    res_exact = await async_client.get(
        "/gateway/verify",
        headers={"X-API-Key": raw_key, "Origin": "https://company.com"},
    )
    assert res_exact.status_code == 200

    # Wildcard match: "api.trusted.org" -> Allowed
    res_wildcard = await async_client.get(
        "/gateway/verify",
        headers={"X-API-Key": raw_key, "Origin": "https://api.trusted.org"},
    )
    assert res_wildcard.status_code == 200

    # Wildcard base: "trusted.org" -> Allowed
    res_wildcard_base = await async_client.get(
        "/gateway/verify",
        headers={"X-API-Key": raw_key, "Origin": "https://trusted.org"},
    )
    assert res_wildcard_base.status_code == 200

    # Spoofing Attempt 1: Subdomain prefix "company.com.evil.com" -> Rejected 403
    res_spoof_1 = await async_client.get(
        "/gateway/verify",
        headers={"X-API-Key": raw_key, "Origin": "https://company.com.evil.com"},
    )
    assert res_spoof_1.status_code == 403

    # Spoofing Attempt 2: Prefix attack "evil-company.com" -> Rejected 403
    res_spoof_2 = await async_client.get(
        "/gateway/verify",
        headers={"X-API-Key": raw_key, "Origin": "https://evil-company.com"},
    )
    assert res_spoof_2.status_code == 403

    # Spoofing Attempt 3: Suffix attack "evil-trusted.org" -> Rejected 403
    res_spoof_3 = await async_client.get(
        "/gateway/verify",
        headers={"X-API-Key": raw_key, "Origin": "https://evil-trusted.org"},
    )
    assert res_spoof_3.status_code == 403

    # Missing Origin header when domain restriction is active -> Rejected 403
    res_no_origin = await async_client.get(
        "/gateway/verify",
        headers={"X-API-Key": raw_key},
    )
    assert res_no_origin.status_code == 403


# =========================================================================
# 4. HEALTH CHECK ERROR HANDLING & UNHEALTHY RESILIENCY
# =========================================================================

@pytest.mark.asyncio
async def test_health_check_resiliency_and_invalid_urls(
    async_client, setup_audit_environment
):
    data = setup_audit_environment
    org_a = data["org_a_id"]
    api_a = data["api_a_id"]

    # 1. Create upstream with invalid/unreachable URL
    unreachable_up = await async_client.post(
        f"/organizations/{org_a}/upstreams",
        headers=data["headers_owner_a"],
        json={"name": "Bad Upstream", "base_url": "http://192.0.2.1:9999"},  # TEST-NET non-routable IP
    )
    assert unreachable_up.status_code == 201
    bad_up_id = unreachable_up.json()["id"]

    # 2. Trigger health check on bad upstream -> Should succeed without crashing (recording status='unhealthy')
    hc_res = await async_client.post(
        f"/organizations/{org_a}/upstreams/{bad_up_id}/health-check?api_id={api_a}",
        headers=data["headers_owner_a"],
    )
    assert hc_res.status_code == 200
    assert hc_res.json()["status"] == "unhealthy"

    # 3. Retrieve latest health status
    latest_res = await async_client.get(
        f"/organizations/{org_a}/upstreams/{bad_up_id}/health",
        headers=data["headers_owner_a"],
    )
    assert latest_res.status_code == 200
    assert latest_res.json()["status"] == "unhealthy"


# =========================================================================
# 5. SUBSCRIPTION CANCELLATION & EXPIRED KEY ACCESS REVOCATION
# =========================================================================

@pytest.mark.asyncio
async def test_cancellation_and_expiry_access_cutoff(
    async_client, setup_audit_environment
):
    data = setup_audit_environment
    org_b = data["org_b_id"]
    plan_free = data["plan_free_id"]

    # 1. Org B subscribes to Free Plan
    sub_res = await async_client.post(
        f"/organizations/{org_b}/subscriptions",
        headers=data["headers_owner_b"],
        json={"plan_id": plan_free},
    )
    sub_id = sub_res.json()["id"]

    # 2. Org B creates API key
    key_res = await async_client.post(
        f"/organizations/{org_b}/api-keys",
        headers=data["headers_owner_b"],
        json={"name": "Key to Cancel", "subscription_id": sub_id},
    )
    raw_key = key_res.json()["api_key"]
    key_id = key_res.json()["id"]

    # 3. Key works initially
    verify_res1 = await async_client.get(
        "/gateway/verify",
        headers={"X-API-Key": raw_key},
    )
    assert verify_res1.status_code == 200

    # 4. Cancel Subscription
    cancel_res = await async_client.post(
        f"/organizations/{org_b}/subscriptions/{sub_id}/cancel",
        headers=data["headers_owner_b"],
    )
    assert cancel_res.status_code == 200

    # 5. Key is immediately denied access -> 403 Forbidden
    verify_res2 = await async_client.get(
        "/gateway/verify",
        headers={"X-API-Key": raw_key},
    )
    assert verify_res2.status_code == 403

    # 6. Key regeneration on cancelled subscription -> 400 Bad Request
    regen_res = await async_client.post(
        f"/organizations/{org_b}/api-keys/{key_id}/regenerate",
        headers=data["headers_owner_b"],
    )
    assert regen_res.status_code == 400
    assert "not active" in regen_res.json()["detail"]
