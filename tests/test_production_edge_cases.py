import hashlib
import json
import time
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

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
from app.models.api import API, APIStatus
from app.models.api_key import APIKey
from app.models.api_key_domain import APIKeyDomain
from app.models.api_plan import APIPlan
from app.models.api_route import APIRoute
from app.models.payment import Payment, PaymentProvider, PaymentStatus
from app.models.role import Role
from app.models.subscription import Subscription
from app.models.upstream import Upstream
from app.models.user import User
from app.repositories.role import RoleRepository
from app.services.gateway_proxy import GatewayProxyService


@pytest_asyncio.fixture
async def async_client():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    await engine.dispose()


@pytest_asyncio.fixture
async def prod_test_env(async_client):
    ts = int(time.time() * 1000)
    users = {}
    tokens = {}

    # Dynamically fetch role IDs from DB
    async with AsyncSessionLocal() as session:
        role_repo = RoleRepository(session)
        admin_role = await role_repo.get_by_name("admin")
        member_role = await role_repo.get_by_name("member")
        owner_role = await role_repo.get_by_name("owner")
        roles = {
            "admin": str(admin_role.id),
            "member": str(member_role.id),
            "owner": str(owner_role.id),
        }

    # Register users: owner_a, admin_a, member_a, owner_b, outsider
    for role_name in ["owner_a", "admin_a", "member_a", "owner_b", "outsider"]:
        email = f"prod_edge_{role_name}_{ts}@test.com"
        reg_res = await async_client.post(
            "/auth/register",
            json={
                "email": email,
                "password": "Password123!",
                "first_name": role_name,
                "last_name": "Test",
            },
        )
        assert reg_res.status_code == 201

        login_res = await async_client.post(
            "/auth/login",
            json={"email": email, "password": "Password123!"},
        )
        assert login_res.status_code == 200
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

    # Create Org A
    res_a = await async_client.post(
        "/organizations",
        headers=headers_owner_a,
        json={"name": f"Prod Org A {ts}", "slug": f"prod-org-a-{ts}"},
    )
    assert res_a.status_code == 201
    org_a = res_a.json()["id"]

    # Create Org B
    res_b = await async_client.post(
        "/organizations",
        headers=headers_owner_b,
        json={"name": f"Prod Org B {ts}", "slug": f"prod-org-b-{ts}"},
    )
    assert res_b.status_code == 201
    org_b = res_b.json()["id"]

    # Add admin_a and member_a to Org A
    await async_client.post(
        f"/organizations/{org_a}/members",
        headers=headers_owner_a,
        json={"user_id": users["admin_a"], "role_id": roles["admin"]},
    )
    await async_client.post(
        f"/organizations/{org_a}/members",
        headers=headers_owner_a,
        json={"user_id": users["member_a"], "role_id": roles["member"]},
    )

    # Org A creates Upstream, API, Route, and Plan
    up_res = await async_client.post(
        f"/organizations/{org_a}/upstreams",
        headers=headers_owner_a,
        json={"name": "Prod Upstream A", "base_url": "https://httpbin.org"},
    )
    assert up_res.status_code == 201
    upstream_a = up_res.json()["id"]

    api_res = await async_client.post(
        f"/organizations/{org_a}/apis",
        headers=headers_owner_a,
        json={"name": "Prod API A", "slug": f"prod-api-a-{ts}", "base_path": "/api-a"},
    )
    assert api_res.status_code == 201
    api_a = api_res.json()["id"]

    route_res = await async_client.post(
        f"/organizations/{org_a}/apis/{api_a}/routes",
        headers=headers_owner_a,
        json={
            "upstream_id": upstream_a,
            "path": "/users",
            "method": "GET",
            "target_path": "/get",
        },
    )
    assert route_res.status_code == 201
    route_a = route_res.json()["id"]

    plan_res = await async_client.post(
        f"/organizations/{org_a}/apis/{api_a}/plans",
        headers=headers_owner_a,
        json={
            "name": "Standard Plan",
            "price": "49.00",
            "currency": "USD",
            "billing_interval": "monthly",
            "rate_limit": 5,
            "monthly_quota": 100,
        },
    )
    assert plan_res.status_code == 201
    plan_a = plan_res.json()["id"]

    return {
        "ts": ts,
        "users": users,
        "tokens": tokens,
        "roles": roles,
        "org_a": org_a,
        "org_b": org_b,
        "upstream_a": upstream_a,
        "api_a": api_a,
        "route_a": route_a,
        "plan_a": plan_a,
        "headers_owner_a": headers_owner_a,
        "headers_admin_a": headers_admin_a,
        "headers_member_a": headers_member_a,
        "headers_owner_b": headers_owner_b,
        "headers_outsider": headers_outsider,
    }


# =========================================================================
# 1. AUTHENTICATION & JWT SECURITY EDGE CASES
# =========================================================================

@pytest.mark.asyncio
async def test_auth_security_jwt_edge_cases(async_client, prod_test_env):
    data = prod_test_env

    # 1. Missing Authorization Header -> 401
    res_no_auth = await async_client.get("/auth/me")
    assert res_no_auth.status_code == 401

    # 2. Malformed JWT -> 401
    res_malformed = await async_client.get(
        "/auth/me", headers={"Authorization": "Bearer not.a.valid.jwt"}
    )
    assert res_malformed.status_code == 401

    # 3. Tampered JWT signature -> 401
    tampered_token = jwt.encode(
        {"sub": data["users"]["owner_a"], "exp": datetime.now(timezone.utc) + timedelta(hours=1)},
        "completely-wrong-secret-key-00000000",
        algorithm="HS256",
    )
    res_tampered = await async_client.get(
        "/auth/me", headers={"Authorization": f"Bearer {tampered_token}"}
    )
    assert res_tampered.status_code == 401

    # 4. Expired JWT -> 401
    expired_token = jwt.encode(
        {"sub": data["users"]["owner_a"], "exp": datetime.now(timezone.utc) - timedelta(hours=1)},
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )
    res_expired = await async_client.get(
        "/auth/me", headers={"Authorization": f"Bearer {expired_token}"}
    )
    assert res_expired.status_code == 401

    # 5. Non-UUID subject in JWT -> 401
    invalid_sub_token = jwt.encode(
        {"sub": "not-a-valid-uuid", "exp": datetime.now(timezone.utc) + timedelta(hours=1)},
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )
    res_bad_sub = await async_client.get(
        "/auth/me", headers={"Authorization": f"Bearer {invalid_sub_token}"}
    )
    assert res_bad_sub.status_code == 401

    # 6. Using access token in refresh endpoint -> 401
    res_wrong_type = await async_client.post(
        "/auth/refresh", json={"refresh_token": data["tokens"]["owner_a"]}
    )
    assert res_wrong_type.status_code == 401


# =========================================================================
# 2. RBAC & TENANT ISOLATION EDGE CASES
# =========================================================================

@pytest.mark.asyncio
async def test_rbac_and_tenant_isolation_edge_cases(async_client, prod_test_env):
    data = prod_test_env
    org_a = data["org_a"]
    org_b = data["org_b"]
    api_a = data["api_a"]

    # 1. Member cannot create API plans -> 403
    res_mem_plan = await async_client.post(
        f"/organizations/{org_a}/apis/{api_a}/plans",
        headers=data["headers_member_a"],
        json={
            "name": "Member Plan",
            "price": "10.00",
            "currency": "USD",
            "billing_interval": "monthly",
            "rate_limit": 10,
            "monthly_quota": 100,
        },
    )
    assert res_mem_plan.status_code == 403

    # 2. Admin cannot manage organization ownership or membership -> 403
    res_admin_membership = await async_client.post(
        f"/organizations/{org_a}/members",
        headers=data["headers_admin_a"],
        json={"user_id": data["users"]["outsider"], "role_id": data["roles"]["member"]},
    )
    assert res_admin_membership.status_code == 403

    # 3. Cross-Tenant: Org B cannot access Org A's analytics -> 404 / 403
    res_cross_analytics = await async_client.get(
        f"/organizations/{org_b}/analytics/apis/{api_a}",
        headers=data["headers_owner_b"],
    )
    assert res_cross_analytics.status_code == 404

    # 4. Outsider cannot list Org A's subscriptions -> 403
    res_out_sub = await async_client.get(
        f"/organizations/{org_a}/subscriptions",
        headers=data["headers_outsider"],
    )
    assert res_out_sub.status_code == 403


# =========================================================================
# 3. PAYMENT WEBHOOK IDEMPOTENCY & PROVIDER SAFETY
# =========================================================================

@pytest.mark.asyncio
async def test_webhook_idempotency_and_provider_validation(async_client, prod_test_env):
    data = prod_test_env
    org_b = data["org_b"]
    plan_a = data["plan_a"]

    # 1. Org B creates subscription for Plan A (starts pending)
    sub_res = await async_client.post(
        f"/organizations/{org_b}/subscriptions",
        headers=data["headers_owner_b"],
        json={"plan_id": plan_a},
    )
    assert sub_res.status_code == 201
    sub_id = sub_res.json()["id"]
    assert sub_res.json()["status"] == "pending"

    # 2. Checkout with invalid provider -> 422
    bad_checkout = await async_client.post(
        f"/organizations/{org_b}/subscriptions/{sub_id}/checkout",
        headers=data["headers_owner_b"],
        json={"provider": "bitcoin_fake"},
    )
    assert bad_checkout.status_code == 422

    # 3. Mock Stripe checkout and successful webhook activation
    with patch("stripe.checkout.Session.create") as mock_stripe_create, \
         patch("stripe.Webhook.construct_event") as mock_stripe_event:

        mock_session = SimpleNamespace(
            id=f"cs_test_{data['ts']}",
            url="https://checkout.stripe.com/pay/test",
        )
        mock_stripe_create.return_value = mock_session

        checkout_res = await async_client.post(
            f"/organizations/{org_b}/subscriptions/{sub_id}/checkout",
            headers=data["headers_owner_b"],
            json={"provider": "stripe"},
        )
        assert checkout_res.status_code == 201
        payment_id = checkout_res.json()["payment"]["id"]

        # Simulate Stripe webhook payload
        webhook_event = {
            "id": f"evt_test_{data['ts']}",
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "id": f"cs_test_{data['ts']}",
                    "metadata": {"payment_id": payment_id},
                }
            },
        }
        mock_stripe_event.return_value = webhook_event

        # First webhook delivery -> activates subscription
        wh_res_1 = await async_client.post(
            "/payments/webhooks/stripe",
            headers={"Stripe-Signature": "t=123,v1=valid_sig"},
            content=json.dumps(webhook_event),
        )
        assert wh_res_1.status_code == 200

        # Verify subscription is now active
        sub_check = await async_client.get(
            f"/organizations/{org_b}/subscriptions/{sub_id}",
            headers=data["headers_owner_b"],
        )
        assert sub_check.json()["status"] == "active"

        # Duplicate webhook delivery (Idempotency test) -> must succeed without errors or duplicates
        wh_res_2 = await async_client.post(
            "/payments/webhooks/stripe",
            headers={"Stripe-Signature": "t=123,v1=valid_sig"},
            content=json.dumps(webhook_event),
        )
        assert wh_res_2.status_code == 200

        # Verify subscription remains active
        sub_check_2 = await async_client.get(
            f"/organizations/{org_b}/subscriptions/{sub_id}",
            headers=data["headers_owner_b"],
        )
        assert sub_check_2.json()["status"] == "active"


# =========================================================================
# 4. GATEWAY PROXY HEADERS & RESILIENCY
# =========================================================================

@pytest.mark.asyncio
async def test_gateway_proxy_sensitive_header_stripping():
    service = GatewayProxyService()

    mock_client = AsyncMock()
    mock_response = httpx.Response(
        status_code=200,
        content=b'{"ok": true}',
        headers={"content-type": "application/json", "x-upstream-header": "test"},
    )
    mock_client.request.return_value = mock_response

    service._client = mock_client

    incoming_headers = {
        "x-api-key": "secret_key_123",
        "host": "api.gateway.internal",
        "connection": "keep-alive",
        "content-length": "123",
        "authorization": "Bearer user-token",
        "x-custom-tenant-header": "custom-val",
    }

    response = await service.forward_request(
        method="GET",
        url="https://upstream.example.com/api",
        headers=incoming_headers,
    )

    assert response.status_code == 200

    # Verify forwarded headers do NOT include excluded/hop-by-hop/sensitive headers
    call_args = mock_client.request.call_args[1]
    forwarded = call_args["headers"]
    assert "x-api-key" not in forwarded
    assert "host" not in forwarded
    assert "connection" not in forwarded
    assert "content-length" not in forwarded
    assert forwarded.get("authorization") == "Bearer user-token"
    assert forwarded.get("x-custom-tenant-header") == "custom-val"
