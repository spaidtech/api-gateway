import hashlib
import time
import uuid
from decimal import Decimal

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.main import app
from app.models.api_key import APIKey
from app.models.api_key_domain import APIKeyDomain
from app.models.api_plan import APIPlan
from app.models.api_route import APIRoute

from app.core.database import AsyncSessionLocal, engine
from app.repositories.role import RoleRepository


@pytest_asyncio.fixture
async def async_client():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    await engine.dispose()


@pytest_asyncio.fixture
async def setup_tenants(async_client):
    ts = int(time.time() * 1000)
    users = {}
    tokens = {}

    # Dynamically fetch role IDs from the current database
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

    # Register users
    for role_name in ["owner_a", "admin_a", "member_a", "multi", "owner_b", "outsider"]:
        email = f"{role_name}_{ts}@test.com"
        await async_client.post(
            "/auth/register",
            json={"email": email, "password": "Password123!", "first_name": role_name, "last_name": "Test"},
        )
        login_res = await async_client.post("/auth/login", json={"email": email, "password": "Password123!"})
        token = login_res.json()["access_token"]
        tokens[role_name] = token
        me = await async_client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
        users[role_name] = me.json()["id"]

    # Create Org A and Org B
    res_a = await async_client.post(
        "/organizations",
        headers={"Authorization": f"Bearer {tokens['owner_a']}"},
        json={"name": f"Org A {ts}", "slug": f"org-a-{ts}"},
    )
    org_a = res_a.json()["id"]

    res_b = await async_client.post(
        "/organizations",
        headers={"Authorization": f"Bearer {tokens['owner_b']}"},
        json={"name": f"Org B {ts}", "slug": f"org-b-{ts}"},
    )
    org_b = res_b.json()["id"]

    # Assign roles in Org A
    await async_client.post(
        f"/organizations/{org_a}/members",
        headers={"Authorization": f"Bearer {tokens['owner_a']}"},
        json={"user_id": users["admin_a"], "role_id": roles["admin"]},
    )
    await async_client.post(
        f"/organizations/{org_a}/members",
        headers={"Authorization": f"Bearer {tokens['owner_a']}"},
        json={"user_id": users["member_a"], "role_id": roles["member"]},
    )
    await async_client.post(
        f"/organizations/{org_a}/members",
        headers={"Authorization": f"Bearer {tokens['owner_a']}"},
        json={"user_id": users["multi"], "role_id": roles["admin"]},
    )

    # Assign roles in Org B (multi is only member)
    await async_client.post(
        f"/organizations/{org_b}/members",
        headers={"Authorization": f"Bearer {tokens['owner_b']}"},
        json={"user_id": users["multi"], "role_id": roles["member"]},
    )

    return {
        "tokens": tokens,
        "users": users,
        "org_a": org_a,
        "org_b": org_b,
    }


def auth(tokens, role):
    return {"Authorization": f"Bearer {tokens[role]}"}


@pytest.mark.asyncio
async def test_upstream_lifecycle_and_rbac(async_client, setup_tenants):
    tokens = setup_tenants["tokens"]
    org_a = setup_tenants["org_a"]
    org_b = setup_tenants["org_b"]

    # 1. Owner can create
    res = await async_client.post(
        f"/organizations/{org_a}/upstreams",
        headers=auth(tokens, "owner_a"),
        json={"name": "Upstream 1", "base_url": "https://api1.internal"},
    )
    assert res.status_code == 201
    up_id = res.json()["id"]

    # 2. Member cannot create
    res_mem = await async_client.post(
        f"/organizations/{org_a}/upstreams",
        headers=auth(tokens, "member_a"),
        json={"name": "Upstream 2", "base_url": "https://api2.internal"},
    )
    assert res_mem.status_code == 403

    # 3. Member can read
    res_get = await async_client.get(
        f"/organizations/{org_a}/upstreams/{up_id}",
        headers=auth(tokens, "member_a"),
    )
    assert res_get.status_code == 200

    # 4. Cross-tenant isolation: Org B cannot access Org A upstream
    res_cross = await async_client.get(
        f"/organizations/{org_b}/upstreams/{up_id}",
        headers=auth(tokens, "owner_b"),
    )
    assert res_cross.status_code == 404

    # 5. Delete by Admin
    del_res = await async_client.delete(
        f"/organizations/{org_a}/upstreams/{up_id}",
        headers=auth(tokens, "admin_a"),
    )
    assert del_res.status_code == 204


@pytest.mark.asyncio
async def test_api_duplicate_slug_and_tenant_isolation(async_client, setup_tenants):
    tokens = setup_tenants["tokens"]
    org_a = setup_tenants["org_a"]
    org_b = setup_tenants["org_b"]

    # Create API in Org A
    res_a = await async_client.post(
        f"/organizations/{org_a}/apis",
        headers=auth(tokens, "owner_a"),
        json={"name": "Auth API", "slug": "auth-api", "base_path": "/auth-service"},
    )
    assert res_a.status_code == 201
    api_a_id = res_a.json()["id"]

    # Duplicate slug in Org A must be 409
    res_dup = await async_client.post(
        f"/organizations/{org_a}/apis",
        headers=auth(tokens, "owner_a"),
        json={"name": "Auth API 2", "slug": "auth-api", "base_path": "/auth-service-2"},
    )
    assert res_dup.status_code == 409

    # Same slug in Org B must succeed (tenant isolation)
    res_b = await async_client.post(
        f"/organizations/{org_b}/apis",
        headers=auth(tokens, "owner_b"),
        json={"name": "Auth API Org B", "slug": "auth-api", "base_path": "/auth-service"},
    )
    assert res_b.status_code == 201

    # Cross-tenant get
    res_cross = await async_client.get(
        f"/organizations/{org_b}/apis/{api_a_id}",
        headers=auth(tokens, "owner_b"),
    )
    assert res_cross.status_code == 404


@pytest.mark.asyncio
async def test_api_route_upstream_cross_tenant_injection(async_client, setup_tenants):
    tokens = setup_tenants["tokens"]
    org_a = setup_tenants["org_a"]
    org_b = setup_tenants["org_b"]

    # Create API and Upstream in Org A
    res_api = await async_client.post(
        f"/organizations/{org_a}/apis",
        headers=auth(tokens, "owner_a"),
        json={"name": "Gateway API", "slug": "gateway-api", "base_path": "/gateway"},
    )
    api_id = res_api.json()["id"]

    res_up_a = await async_client.post(
        f"/organizations/{org_a}/upstreams",
        headers=auth(tokens, "owner_a"),
        json={"name": "Gateway Upstream", "base_url": "https://gateway.internal"},
    )
    up_a_id = res_up_a.json()["id"]

    # Create Upstream in Org B
    res_up_b = await async_client.post(
        f"/organizations/{org_b}/upstreams",
        headers=auth(tokens, "owner_b"),
        json={"name": "Org B Upstream", "base_url": "https://b.internal"},
    )
    up_b_id = res_up_b.json()["id"]

    # 1. Attempt cross-tenant upstream injection
    res_inject = await async_client.post(
        f"/organizations/{org_a}/apis/{api_id}/routes",
        headers=auth(tokens, "owner_a"),
        json={"upstream_id": up_b_id, "path": "/inject", "method": "GET"},
    )
    assert res_inject.status_code == 404

    # 2. Normal creation with method normalization
    res_route = await async_client.post(
        f"/organizations/{org_a}/apis/{api_id}/routes",
        headers=auth(tokens, "owner_a"),
        json={"upstream_id": up_a_id, "path": "/v1/users", "method": "get"},
    )
    assert res_route.status_code == 201
    assert res_route.json()["method"] == "GET"

    # 3. Duplicate (path, method) rejection
    res_dup = await async_client.post(
        f"/organizations/{org_a}/apis/{api_id}/routes",
        headers=auth(tokens, "owner_a"),
        json={"upstream_id": up_a_id, "path": " /v1/users ", "method": "GET"},
    )
    assert res_dup.status_code == 409


@pytest.mark.asyncio
async def test_api_plan_validation_and_rbac(async_client, setup_tenants):
    tokens = setup_tenants["tokens"]
    org_a = setup_tenants["org_a"]

    res_api = await async_client.post(
        f"/organizations/{org_a}/apis",
        headers=auth(tokens, "owner_a"),
        json={"name": "Billing API", "slug": "billing-api", "base_path": "/billing"},
    )
    api_id = res_api.json()["id"]

    # Valid plan creation
    res_plan = await async_client.post(
        f"/organizations/{org_a}/apis/{api_id}/plans",
        headers=auth(tokens, "owner_a"),
        json={
            "name": "Standard Plan",
            "price": "29.99",
            "currency": "USD",
            "billing_interval": "monthly",
            "rate_limit": 50,
            "monthly_quota": 10000,
        },
    )
    assert res_plan.status_code == 201

    # Invalid negative price
    res_neg = await async_client.post(
        f"/organizations/{org_a}/apis/{api_id}/plans",
        headers=auth(tokens, "owner_a"),
        json={
            "name": "Invalid Plan",
            "price": "-5.00",
            "currency": "USD",
            "billing_interval": "monthly",
            "rate_limit": 50,
            "monthly_quota": 10000,
        },
    )
    assert res_neg.status_code == 422


@pytest.mark.asyncio
async def test_api_key_security_regeneration_revocation(async_client, setup_tenants):
    tokens = setup_tenants["tokens"]
    org_a = setup_tenants["org_a"]

    # Create API Key
    res_create = await async_client.post(
        f"/organizations/{org_a}/api-keys",
        headers=auth(tokens, "owner_a"),
        json={"name": "Production Key"},
    )
    assert res_create.status_code == 201
    raw_key = res_create.json()["api_key"]
    key_id = res_create.json()["id"]

    # Verify SHA-256 hash in DB
    async with AsyncSessionLocal() as session:
        k_db = await session.execute(select(APIKey).where(APIKey.id == uuid.UUID(key_id)))
        key_record = k_db.scalar_one_or_none()
        assert key_record is not None
        assert key_record.key_hash == hashlib.sha256(raw_key.encode("utf-8")).hexdigest()

    # Verify raw key omitted on GET
    res_get = await async_client.get(
        f"/organizations/{org_a}/api-keys/{key_id}",
        headers=auth(tokens, "owner_a"),
    )
    assert res_get.status_code == 200
    assert "api_key" not in res_get.json()

    # Regenerate key
    res_regen = await async_client.post(
        f"/organizations/{org_a}/api-keys/{key_id}/regenerate",
        headers=auth(tokens, "admin_a"),
    )
    assert res_regen.status_code == 200
    new_raw_key = res_regen.json()["api_key"]
    assert new_raw_key != raw_key

    # Revoke key
    res_revoke = await async_client.post(
        f"/organizations/{org_a}/api-keys/{key_id}/revoke",
        headers=auth(tokens, "owner_a"),
    )
    assert res_revoke.status_code == 200
    assert res_revoke.json()["status"] == "revoked"


@pytest.mark.asyncio
async def test_api_key_domain_management_and_validation(async_client, setup_tenants):
    tokens = setup_tenants["tokens"]
    org_a = setup_tenants["org_a"]

    res_key = await async_client.post(
        f"/organizations/{org_a}/api-keys",
        headers=auth(tokens, "owner_a"),
        json={"name": "Domain Bound Key"},
    )
    key_id = res_key.json()["id"]

    # Add domain with normalization
    res_dom = await async_client.post(
        f"/organizations/{org_a}/api-keys/{key_id}/domains",
        headers=auth(tokens, "owner_a"),
        json={"domain": "  API.CLIENT.COM. "},
    )
    assert res_dom.status_code == 201
    assert res_dom.json()["domain"] == "api.client.com"
    dom_id = res_dom.json()["id"]

    # Duplicate domain
    res_dup = await async_client.post(
        f"/organizations/{org_a}/api-keys/{key_id}/domains",
        headers=auth(tokens, "owner_a"),
        json={"domain": "api.client.com"},
    )
    assert res_dup.status_code == 409

    # Invalid domain format
    res_inv = await async_client.post(
        f"/organizations/{org_a}/api-keys/{key_id}/domains",
        headers=auth(tokens, "owner_a"),
        json={"domain": "invalid_domain_format"},
    )
    assert res_inv.status_code == 422

    # Delete domain
    res_del = await async_client.delete(
        f"/organizations/{org_a}/api-keys/{key_id}/domains/{dom_id}",
        headers=auth(tokens, "owner_a"),
    )
    assert res_del.status_code == 204


@pytest.mark.asyncio
async def test_contextual_multi_org_rbac(async_client, setup_tenants):
    tokens = setup_tenants["tokens"]
    org_a = setup_tenants["org_a"]
    org_b = setup_tenants["org_b"]

    # User 'multi' is Admin in Org A -> Allowed to create API
    res_a = await async_client.post(
        f"/organizations/{org_a}/apis",
        headers=auth(tokens, "multi"),
        json={"name": "Multi Admin API", "slug": "multi-admin-api", "base_path": "/multi-admin"},
    )
    assert res_a.status_code == 201

    # User 'multi' is Member in Org B -> Denied to create API
    res_b = await async_client.post(
        f"/organizations/{org_b}/apis",
        headers=auth(tokens, "multi"),
        json={"name": "Multi Member API", "slug": "multi-member-api", "base_path": "/multi-member"},
    )
    assert res_b.status_code == 403
