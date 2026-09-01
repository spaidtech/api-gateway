import hashlib
import time
import uuid
from datetime import datetime, timedelta, timezone

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import select

from app.core.database import AsyncSessionLocal, engine
from app.main import app
from app.models.api_key import APIKey
from app.models.subscription import Subscription


@pytest_asyncio.fixture
async def async_client():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    await engine.dispose()


@pytest_asyncio.fixture
async def setup_phase5(async_client):
    ts = int(time.time() * 1000)
    users = {}
    tokens = {}

    for role_name in ["owner_a", "owner_b"]:
        email = f"p5_{role_name}_{ts}@test.com"
        await async_client.post(
            "/auth/register",
            json={"email": email, "password": "Password123!", "first_name": role_name, "last_name": "Test"},
        )
        login_res = await async_client.post("/auth/login", json={"email": email, "password": "Password123!"})
        token = login_res.json()["access_token"]
        tokens[role_name] = token
        me = await async_client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
        users[role_name] = me.json()["id"]

    res_a = await async_client.post(
        "/organizations",
        headers={"Authorization": f"Bearer {tokens['owner_a']}"},
        json={"name": f"P5 Org A {ts}", "slug": f"p5-org-a-{ts}"},
    )
    org_a = res_a.json()["id"]

    res_b = await async_client.post(
        "/organizations",
        headers={"Authorization": f"Bearer {tokens['owner_b']}"},
        json={"name": f"P5 Org B {ts}", "slug": f"p5-org-b-{ts}"},
    )
    org_b = res_b.json()["id"]

    api_res = await async_client.post(
        f"/organizations/{org_a}/apis",
        headers={"Authorization": f"Bearer {tokens['owner_a']}"},
        json={"name": "P5 API", "slug": f"p5-api-{ts}", "base_path": "/p5"},
    )
    api_id = api_res.json()["id"]

    plan_res = await async_client.post(
        f"/organizations/{org_a}/apis/{api_id}/plans",
        headers={"Authorization": f"Bearer {tokens['owner_a']}"},
        json={
            "name": "P5 Plan",
            "price": "10.00",
            "currency": "USD",
            "billing_interval": "monthly",
            "rate_limit": 100,
            "monthly_quota": 5000,
        },
    )
    plan_id = plan_res.json()["id"]

    # Inactive plan
    inactive_plan_res = await async_client.post(
        f"/organizations/{org_a}/apis/{api_id}/plans",
        headers={"Authorization": f"Bearer {tokens['owner_a']}"},
        json={
            "name": "P5 Inactive Plan",
            "price": "0.00",
            "currency": "USD",
            "billing_interval": "monthly",
            "rate_limit": 10,
            "monthly_quota": 100,
        },
    )
    inactive_plan_id = inactive_plan_res.json()["id"]
    await async_client.patch(
        f"/organizations/{org_a}/apis/{api_id}/plans/{inactive_plan_id}",
        headers={"Authorization": f"Bearer {tokens['owner_a']}"},
        json={"is_active": False},
    )

    async with AsyncSessionLocal() as session:
        sub_active = Subscription(
            consumer_organization_id=uuid.UUID(org_a),
            plan_id=uuid.UUID(plan_id),
            status="active",
            starts_at=datetime.now(timezone.utc) - timedelta(days=1),
            ends_at=datetime.now(timezone.utc) + timedelta(days=30),
        )
        sub_cancelled = Subscription(
            consumer_organization_id=uuid.UUID(org_a),
            plan_id=uuid.UUID(plan_id),
            status="cancelled",
            starts_at=datetime.now(timezone.utc) - timedelta(days=1),
            ends_at=datetime.now(timezone.utc) + timedelta(days=30),
        )
        sub_inactive_plan = Subscription(
            consumer_organization_id=uuid.UUID(org_a),
            plan_id=uuid.UUID(inactive_plan_id),
            status="active",
            starts_at=datetime.now(timezone.utc) - timedelta(days=1),
            ends_at=datetime.now(timezone.utc) + timedelta(days=30),
        )
        session.add_all([sub_active, sub_cancelled, sub_inactive_plan])
        await session.commit()
        await session.refresh(sub_active)
        await session.refresh(sub_cancelled)
        await session.refresh(sub_inactive_plan)

        sub_active_id = str(sub_active.id)
        sub_cancelled_id = str(sub_cancelled.id)
        sub_inactive_plan_id = str(sub_inactive_plan.id)

    return {
        "tokens": tokens,
        "org_a": org_a,
        "org_b": org_b,
        "api_id": api_id,
        "plan_id": plan_id,
        "sub_active_id": sub_active_id,
        "sub_cancelled_id": sub_cancelled_id,
        "sub_inactive_plan_id": sub_inactive_plan_id,
    }


def auth(tokens, role):
    return {"Authorization": f"Bearer {tokens[role]}"}


@pytest.mark.asyncio
async def test_api_key_authentication_and_revocation(async_client, setup_phase5):
    tokens = setup_phase5["tokens"]
    org_a = setup_phase5["org_a"]
    sub_id = setup_phase5["sub_active_id"]

    # 1. Create API key
    res = await async_client.post(
        f"/organizations/{org_a}/api-keys",
        headers=auth(tokens, "owner_a"),
        json={"name": "Auth Test", "subscription_id": sub_id},
    )
    assert res.status_code == 201
    raw_key = res.json()["api_key"]
    key_id = res.json()["id"]

    # 2. Valid request
    res_valid = await async_client.get("/gateway/verify", headers={"X-API-Key": raw_key})
    assert res_valid.status_code == 200
    assert res_valid.json()["status"] == "authenticated"

    # 3. Missing API key header
    res_missing = await async_client.get("/gateway/verify")
    assert res_missing.status_code == 401

    # 4. Invalid API key header
    res_invalid = await async_client.get("/gateway/verify", headers={"X-API-Key": "ak_live_invalidkey"})
    assert res_invalid.status_code == 401

    # 5. Revoked key
    await async_client.post(f"/organizations/{org_a}/api-keys/{key_id}/revoke", headers=auth(tokens, "owner_a"))
    res_rev = await async_client.get("/gateway/verify", headers={"X-API-Key": raw_key})
    assert res_rev.status_code == 401


@pytest.mark.asyncio
async def test_api_key_regeneration_flow(async_client, setup_phase5):
    tokens = setup_phase5["tokens"]
    org_a = setup_phase5["org_a"]

    res = await async_client.post(
        f"/organizations/{org_a}/api-keys",
        headers=auth(tokens, "owner_a"),
        json={"name": "Regen Test"},
    )
    old_key = res.json()["api_key"]
    key_id = res.json()["id"]

    # Old key works
    res_1 = await async_client.get("/gateway/verify", headers={"X-API-Key": old_key})
    assert res_1.status_code == 200

    # Regenerate
    res_regen = await async_client.post(
        f"/organizations/{org_a}/api-keys/{key_id}/regenerate",
        headers=auth(tokens, "owner_a"),
    )
    assert res_regen.status_code == 200
    new_key = res_regen.json()["api_key"]

    # Old key fails
    res_old = await async_client.get("/gateway/verify", headers={"X-API-Key": old_key})
    assert res_old.status_code == 401

    # New key succeeds
    res_new = await async_client.get("/gateway/verify", headers={"X-API-Key": new_key})
    assert res_new.status_code == 200


@pytest.mark.asyncio
async def test_subscription_and_plan_validation(async_client, setup_phase5):
    tokens = setup_phase5["tokens"]
    org_a = setup_phase5["org_a"]
    sub_active_id = setup_phase5["sub_active_id"]
    sub_cancelled_id = setup_phase5["sub_cancelled_id"]
    sub_inactive_plan_id = setup_phase5["sub_inactive_plan_id"]

    # 1. Active subscription + active plan
    res_active = await async_client.post(
        f"/organizations/{org_a}/api-keys",
        headers=auth(tokens, "owner_a"),
        json={"name": "Active Sub", "subscription_id": sub_active_id},
    )
    res_v1 = await async_client.get("/gateway/verify", headers={"X-API-Key": res_active.json()["api_key"]})
    assert res_v1.status_code == 200

    # 2. Creating API key with cancelled subscription is blocked
    res_canc_blocked = await async_client.post(
        f"/organizations/{org_a}/api-keys",
        headers=auth(tokens, "owner_a"),
        json={"name": "Cancelled Sub Key", "subscription_id": sub_cancelled_id},
    )
    assert res_canc_blocked.status_code == 400

    # 3. Creating API key with inactive plan is blocked
    res_inact_blocked = await async_client.post(
        f"/organizations/{org_a}/api-keys",
        headers=auth(tokens, "owner_a"),
        json={"name": "Inactive Plan Key", "subscription_id": sub_inactive_plan_id},
    )
    assert res_inact_blocked.status_code == 400

    # 4. Existing key immediately loses gateway access when subscription is cancelled
    await async_client.post(
        f"/organizations/{org_a}/subscriptions/{sub_active_id}/cancel",
        headers=auth(tokens, "owner_a"),
    )
    res_canc_gateway = await async_client.get("/gateway/verify", headers={"X-API-Key": res_active.json()["api_key"]})
    assert res_canc_gateway.status_code == 403


@pytest.mark.asyncio
async def test_domain_restriction_policy(async_client, setup_phase5):
    tokens = setup_phase5["tokens"]
    org_a = setup_phase5["org_a"]

    res_key = await async_client.post(
        f"/organizations/{org_a}/api-keys",
        headers=auth(tokens, "owner_a"),
        json={"name": "Domain Test"},
    )
    raw_key = res_key.json()["api_key"]
    key_id = res_key.json()["id"]

    # Add domain
    await async_client.post(
        f"/organizations/{org_a}/api-keys/{key_id}/domains",
        headers=auth(tokens, "owner_a"),
        json={"domain": "api.myapp.com"},
    )
    await async_client.post(
        f"/organizations/{org_a}/api-keys/{key_id}/domains",
        headers=auth(tokens, "owner_a"),
        json={"domain": "*.client.org"},
    )

    # Allowed exact
    res_exact = await async_client.get("/gateway/verify", headers={"X-API-Key": raw_key, "Origin": "https://api.myapp.com"})
    assert res_exact.status_code == 200

    # Allowed wildcard
    res_wc = await async_client.get("/gateway/verify", headers={"X-API-Key": raw_key, "Origin": "https://sub.client.org:3000"})
    assert res_wc.status_code == 200

    # Disallowed
    res_bad = await async_client.get("/gateway/verify", headers={"X-API-Key": raw_key, "Origin": "https://attacker.com"})
    assert res_bad.status_code == 403

    # Missing origin when restrictions exist
    res_no_orig = await async_client.get("/gateway/verify", headers={"X-API-Key": raw_key})
    assert res_no_orig.status_code == 403
