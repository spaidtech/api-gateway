import time
import uuid
import httpx
import pytest
import pytest_asyncio

from app.core.database import engine
from app.main import app


@pytest_asyncio.fixture
async def async_client():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    await engine.dispose()


@pytest_asyncio.fixture
async def setup_subscription_fixtures(async_client):
    ts = int(time.time() * 1000)
    users = {}
    tokens = {}

    for role_name in ["provider_owner", "consumer_owner", "outsider"]:
        email = f"sub_{role_name}_{ts}@test.com"
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
        me = await async_client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
        users[role_name] = me.json()["id"]

    # Provider Org & Consumer Org
    res_prov = await async_client.post(
        "/organizations",
        headers={"Authorization": f"Bearer {tokens['provider_owner']}"},
        json={"name": f"Provider Org {ts}", "slug": f"provider-org-{ts}"},
    )
    provider_org_id = res_prov.json()["id"]

    res_cons = await async_client.post(
        "/organizations",
        headers={"Authorization": f"Bearer {tokens['consumer_owner']}"},
        json={"name": f"Consumer Org {ts}", "slug": f"consumer-org-{ts}"},
    )
    consumer_org_id = res_cons.json()["id"]

    # Provider creates API and Plan
    api_res = await async_client.post(
        f"/organizations/{provider_org_id}/apis",
        headers={"Authorization": f"Bearer {tokens['provider_owner']}"},
        json={"name": "Weather API", "slug": f"weather-api-{ts}", "base_path": "/weather"},
    )
    api_id = api_res.json()["id"]

    plan_res = await async_client.post(
        f"/organizations/{provider_org_id}/apis/{api_id}/plans",
        headers={"Authorization": f"Bearer {tokens['provider_owner']}"},
        json={
            "name": "Pro Tier",
            "price": "29.99",
            "currency": "USD",
            "billing_interval": "monthly",
            "rate_limit": 60,
            "monthly_quota": 10000,
        },
    )
    plan_id = plan_res.json()["id"]

    return {
        "tokens": tokens,
        "provider_org_id": provider_org_id,
        "consumer_org_id": consumer_org_id,
        "api_id": api_id,
        "plan_id": plan_id,
    }


@pytest.mark.asyncio
async def test_subscription_lifecycle(async_client, setup_subscription_fixtures):
    data = setup_subscription_fixtures
    tokens = data["tokens"]
    consumer_org = data["consumer_org_id"]
    plan_id = data["plan_id"]
    consumer_headers = {"Authorization": f"Bearer {tokens['consumer_owner']}"}

    # 1. Create Subscription (Paid Plan -> starts pending)
    create_res = await async_client.post(
        f"/organizations/{consumer_org}/subscriptions",
        headers=consumer_headers,
        json={"plan_id": plan_id},
    )
    assert create_res.status_code == 201
    sub = create_res.json()
    sub_id = sub["id"]
    assert sub["status"] == "pending"
    assert sub["consumer_organization_id"] == consumer_org
    assert sub["plan_id"] == plan_id

    # 2. List Subscriptions
    list_res = await async_client.get(
        f"/organizations/{consumer_org}/subscriptions",
        headers=consumer_headers,
    )
    assert list_res.status_code == 200
    sub_list = list_res.json()
    assert any(s["id"] == sub_id for s in sub_list)

    # 3. Get Subscription by ID
    get_res = await async_client.get(
        f"/organizations/{consumer_org}/subscriptions/{sub_id}",
        headers=consumer_headers,
    )
    assert get_res.status_code == 200
    assert get_res.json()["id"] == sub_id

    # 4. Cancel Subscription
    cancel_res = await async_client.post(
        f"/organizations/{consumer_org}/subscriptions/{sub_id}/cancel",
        headers=consumer_headers,
    )
    assert cancel_res.status_code == 200
    assert cancel_res.json()["status"] == "cancelled"

    # 5. Free plan subscription (price == 0 -> starts active)
    free_plan_res = await async_client.post(
        f"/organizations/{data['provider_org_id']}/apis/{data['api_id']}/plans",
        headers={"Authorization": f"Bearer {tokens['provider_owner']}"},
        json={
            "name": "Free Tier",
            "price": "0.00",
            "currency": "USD",
            "billing_interval": "monthly",
            "rate_limit": 10,
            "monthly_quota": 500,
        },
    )
    free_plan_id = free_plan_res.json()["id"]

    free_sub_res = await async_client.post(
        f"/organizations/{consumer_org}/subscriptions",
        headers=consumer_headers,
        json={"plan_id": free_plan_id},
    )
    assert free_sub_res.status_code == 201
    assert free_sub_res.json()["status"] == "active"

    # 6. Non-existent / invalid plan subscription attempt
    bad_plan_res = await async_client.post(
        f"/organizations/{consumer_org}/subscriptions",
        headers=consumer_headers,
        json={"plan_id": str(uuid.uuid4())},
    )
    assert bad_plan_res.status_code == 400
