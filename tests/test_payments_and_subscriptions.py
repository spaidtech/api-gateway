import hmac
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
from sqlalchemy import select

from app.core.config import settings
from app.core.database import AsyncSessionLocal, engine
from app.main import app
from app.models.api import API
from app.models.api_key import APIKey
from app.models.api_plan import APIPlan
from app.models.payment import Payment, PaymentProvider, PaymentStatus
from app.models.subscription import Subscription


@pytest_asyncio.fixture
async def async_client():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    await engine.dispose()


@pytest_asyncio.fixture
async def setup_payment_fixtures(async_client):
    ts = int(time.time() * 1000)
    users = {}
    tokens = {}

    for role_name in ["prov_owner", "cons_owner", "attacker"]:
        email = f"pay_{role_name}_{ts}@test.com"
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

    prov_headers = {"Authorization": f"Bearer {tokens['prov_owner']}"}
    cons_headers = {"Authorization": f"Bearer {tokens['cons_owner']}"}
    att_headers = {"Authorization": f"Bearer {tokens['attacker']}"}

    # 1. Create Provider Org & Consumer Org & Attacker Org
    res_prov = await async_client.post(
        "/organizations",
        headers=prov_headers,
        json={"name": f"Provider {ts}", "slug": f"prov-{ts}"},
    )
    provider_org_id = res_prov.json()["id"]

    res_cons = await async_client.post(
        "/organizations",
        headers=cons_headers,
        json={"name": f"Consumer {ts}", "slug": f"cons-{ts}"},
    )
    consumer_org_id = res_cons.json()["id"]

    res_att = await async_client.post(
        "/organizations",
        headers=att_headers,
        json={"name": f"Attacker {ts}", "slug": f"att-{ts}"},
    )
    attacker_org_id = res_att.json()["id"]

    # 2. Provider creates API and Plans (Paid & Free)
    api_res = await async_client.post(
        f"/organizations/{provider_org_id}/apis",
        headers=prov_headers,
        json={"name": "Finance API", "slug": f"finance-{ts}", "base_path": "/fin"},
    )
    api_id = api_res.json()["id"]

    paid_plan_res = await async_client.post(
        f"/organizations/{provider_org_id}/apis/{api_id}/plans",
        headers=prov_headers,
        json={
            "name": "Pro Monthly",
            "price": "49.00",
            "currency": "INR",
            "billing_interval": "monthly",
            "rate_limit": 100,
            "monthly_quota": 5000,
        },
    )
    paid_plan_id = paid_plan_res.json()["id"]

    free_plan_res = await async_client.post(
        f"/organizations/{provider_org_id}/apis/{api_id}/plans",
        headers=prov_headers,
        json={
            "name": "Free Monthly",
            "price": "0.00",
            "currency": "USD",
            "billing_interval": "monthly",
            "rate_limit": 10,
            "monthly_quota": 100,
        },
    )
    free_plan_id = free_plan_res.json()["id"]

    return {
        "ts": ts,
        "tokens": tokens,
        "prov_headers": prov_headers,
        "cons_headers": cons_headers,
        "att_headers": att_headers,
        "provider_org_id": provider_org_id,
        "consumer_org_id": consumer_org_id,
        "attacker_org_id": attacker_org_id,
        "api_id": api_id,
        "paid_plan_id": paid_plan_id,
        "free_plan_id": free_plan_id,
    }


# =========================================================================
# 1. SUBSCRIPTION CREATION & API KEY GATING
# =========================================================================

@pytest.mark.asyncio
async def test_paid_subscription_starts_pending_and_blocks_key_creation(
    async_client, setup_payment_fixtures
):
    data = setup_payment_fixtures
    cons_headers = data["cons_headers"]
    consumer_org_id = data["consumer_org_id"]
    paid_plan_id = data["paid_plan_id"]

    # Create subscription for paid plan
    sub_res = await async_client.post(
        f"/organizations/{consumer_org_id}/subscriptions",
        headers=cons_headers,
        json={"plan_id": paid_plan_id},
    )
    assert sub_res.status_code == 201
    sub = sub_res.json()
    assert sub["status"] == "pending"
    sub_id = sub["id"]

    # Attempt to create API key before payment -> must be rejected
    key_res = await async_client.post(
        f"/organizations/{consumer_org_id}/api-keys",
        headers=cons_headers,
        json={"name": "Premature Key", "subscription_id": sub_id},
    )
    assert key_res.status_code == 400
    assert "not active" in key_res.json()["detail"]


@pytest.mark.asyncio
async def test_free_subscription_starts_active_and_allows_key_creation(
    async_client, setup_payment_fixtures
):
    data = setup_payment_fixtures
    cons_headers = data["cons_headers"]
    consumer_org_id = data["consumer_org_id"]
    free_plan_id = data["free_plan_id"]

    # Create subscription for free plan
    sub_res = await async_client.post(
        f"/organizations/{consumer_org_id}/subscriptions",
        headers=cons_headers,
        json={"plan_id": free_plan_id},
    )
    assert sub_res.status_code == 201
    sub = sub_res.json()
    assert sub["status"] == "active"
    assert sub["ends_at"] is not None
    sub_id = sub["id"]

    # Create API key -> succeeds
    key_res = await async_client.post(
        f"/organizations/{consumer_org_id}/api-keys",
        headers=cons_headers,
        json={"name": "Free Key", "subscription_id": sub_id},
    )
    assert key_res.status_code == 201
    assert "api_key" in key_res.json()


# =========================================================================
# 2. CHECKOUT CREATION (RAZORPAY & STRIPE)
# =========================================================================

@pytest.mark.asyncio
async def test_razorpay_checkout_creation(async_client, setup_payment_fixtures):
    data = setup_payment_fixtures
    cons_headers = data["cons_headers"]
    consumer_org_id = data["consumer_org_id"]
    paid_plan_id = data["paid_plan_id"]

    # Create subscription
    sub_res = await async_client.post(
        f"/organizations/{consumer_org_id}/subscriptions",
        headers=cons_headers,
        json={"plan_id": paid_plan_id},
    )
    sub_id = sub_res.json()["id"]

    mock_order = {"id": f"order_rzp_{data['ts']}"}
    with patch("razorpay.Client") as mock_rzp:
        instance = mock_rzp.return_value
        instance.order.create.return_value = mock_order

        checkout_res = await async_client.post(
            f"/organizations/{consumer_org_id}/subscriptions/{sub_id}/checkout",
            headers=cons_headers,
            json={"provider": "razorpay"},
        )
        assert checkout_res.status_code == 201
        res_json = checkout_res.json()
        assert res_json["payment"]["provider"] == "razorpay"
        assert res_json["payment"]["status"] == "pending"
        assert res_json["payment"]["provider_payment_id"] == mock_order["id"]
        assert res_json["checkout_data"]["order_id"] == mock_order["id"]


@pytest.mark.asyncio
async def test_stripe_checkout_creation(async_client, setup_payment_fixtures):
    data = setup_payment_fixtures
    cons_headers = data["cons_headers"]
    consumer_org_id = data["consumer_org_id"]
    paid_plan_id = data["paid_plan_id"]

    # Create subscription
    sub_res = await async_client.post(
        f"/organizations/{consumer_org_id}/subscriptions",
        headers=cons_headers,
        json={"plan_id": paid_plan_id},
    )
    sub_id = sub_res.json()["id"]

    mock_session = MagicMock()
    mock_session.id = f"cs_test_{data['ts']}"
    mock_session.url = f"https://checkout.stripe.com/c/pay/{mock_session.id}"

    with patch("stripe.checkout.Session.create", return_value=mock_session):
        checkout_res = await async_client.post(
            f"/organizations/{consumer_org_id}/subscriptions/{sub_id}/checkout",
            headers=cons_headers,
            json={"provider": "stripe"},
        )
        assert checkout_res.status_code == 201
        res_json = checkout_res.json()
        assert res_json["payment"]["provider"] == "stripe"
        assert res_json["payment"]["status"] == "pending"
        assert res_json["payment"]["provider_payment_id"] == mock_session.id
        assert res_json["checkout_data"]["checkout_url"] == mock_session.url


@pytest.mark.asyncio
async def test_checkout_invalid_provider(async_client, setup_payment_fixtures):
    data = setup_payment_fixtures
    cons_headers = data["cons_headers"]
    consumer_org_id = data["consumer_org_id"]
    paid_plan_id = data["paid_plan_id"]

    sub_res = await async_client.post(
        f"/organizations/{consumer_org_id}/subscriptions",
        headers=cons_headers,
        json={"plan_id": paid_plan_id},
    )
    sub_id = sub_res.json()["id"]

    checkout_res = await async_client.post(
        f"/organizations/{consumer_org_id}/subscriptions/{sub_id}/checkout",
        headers=cons_headers,
        json={"provider": "paypal"},
    )
    assert checkout_res.status_code == 422


# =========================================================================
# 3. RAZORPAY WEBHOOK & SIGNATURE VERIFICATION & IDEMPOTENCY
# =========================================================================

@pytest.mark.asyncio
async def test_razorpay_webhook_successful_payment_activates_subscription(
    async_client, setup_payment_fixtures
):
    data = setup_payment_fixtures
    cons_headers = data["cons_headers"]
    consumer_org_id = data["consumer_org_id"]
    paid_plan_id = data["paid_plan_id"]

    sub_res = await async_client.post(
        f"/organizations/{consumer_org_id}/subscriptions",
        headers=cons_headers,
        json={"plan_id": paid_plan_id},
    )
    sub_id = sub_res.json()["id"]
    assert sub_res.json()["status"] == "pending"

    order_id = f"order_rzp_success_{data['ts']}"
    with patch("razorpay.Client") as mock_rzp:
        instance = mock_rzp.return_value
        instance.order.create.return_value = {"id": order_id}

        checkout_res = await async_client.post(
            f"/organizations/{consumer_org_id}/subscriptions/{sub_id}/checkout",
            headers=cons_headers,
            json={"provider": "razorpay"},
        )
        assert checkout_res.status_code == 201
        payment_id = checkout_res.json()["payment"]["id"]

    webhook_payload = json.dumps({
        "event": "payment.captured",
        "payload": {
            "payment": {
                "entity": {
                    "id": f"pay_rzp_{data['ts']}",
                    "order_id": order_id,
                    "amount": 4900,
                    "status": "captured",
                    "notes": {"payment_id": payment_id},
                }
            }
        }
    }).encode("utf-8")

    # Mock utility.verify_webhook_signature
    with patch("razorpay.Client") as mock_rzp:
        instance = mock_rzp.return_value
        instance.utility.verify_webhook_signature.return_value = True

        webhook_res = await async_client.post(
            "/payments/webhooks/razorpay",
            content=webhook_payload,
            headers={
                "Content-Type": "application/json",
                "X-Razorpay-Signature": "valid_signature_hash",
            },
        )
        assert webhook_res.status_code == 200
        assert webhook_res.json() == {"status": "ok"}

    # Verify subscription is now active!
    sub_check = await async_client.get(
        f"/organizations/{consumer_org_id}/subscriptions/{sub_id}",
        headers=cons_headers,
    )
    assert sub_check.status_code == 200
    assert sub_check.json()["status"] == "active"
    assert sub_check.json()["ends_at"] is not None

    # Verify API key can now be created
    key_res = await async_client.post(
        f"/organizations/{consumer_org_id}/api-keys",
        headers=cons_headers,
        json={"name": "Post-Payment Key", "subscription_id": sub_id},
    )
    assert key_res.status_code == 201

    # Test Idempotency: Send same webhook again
    with patch("razorpay.Client") as mock_rzp:
        instance = mock_rzp.return_value
        instance.utility.verify_webhook_signature.return_value = True

        webhook_res_2 = await async_client.post(
            "/payments/webhooks/razorpay",
            content=webhook_payload,
            headers={
                "Content-Type": "application/json",
                "X-Razorpay-Signature": "valid_signature_hash",
            },
        )
        assert webhook_res_2.status_code == 200


@pytest.mark.asyncio
async def test_razorpay_webhook_invalid_signature_rejected(
    async_client, setup_payment_fixtures
):
    with patch("razorpay.Client") as mock_rzp:
        instance = mock_rzp.return_value
        instance.utility.verify_webhook_signature.side_effect = Exception("Signature verification failed")

        webhook_res = await async_client.post(
            "/payments/webhooks/razorpay",
            content=b'{"event": "payment.captured"}',
            headers={
                "Content-Type": "application/json",
                "X-Razorpay-Signature": "tampered_signature",
            },
        )
        assert webhook_res.status_code == 400
        assert "Invalid Razorpay webhook" in webhook_res.json()["detail"]


# =========================================================================
# 4. STRIPE WEBHOOK & SIGNATURE VERIFICATION & IDEMPOTENCY
# =========================================================================

@pytest.mark.asyncio
async def test_stripe_webhook_successful_payment_activates_subscription(
    async_client, setup_payment_fixtures
):
    data = setup_payment_fixtures
    cons_headers = data["cons_headers"]
    consumer_org_id = data["consumer_org_id"]
    paid_plan_id = data["paid_plan_id"]

    sub_res = await async_client.post(
        f"/organizations/{consumer_org_id}/subscriptions",
        headers=cons_headers,
        json={"plan_id": paid_plan_id},
    )
    sub_id = sub_res.json()["id"]

    session_id = f"cs_stripe_success_{data['ts']}"
    mock_session = MagicMock()
    mock_session.id = session_id
    mock_session.url = f"https://checkout.stripe.com/{session_id}"

    with patch("stripe.checkout.Session.create", return_value=mock_session):
        checkout_res = await async_client.post(
            f"/organizations/{consumer_org_id}/subscriptions/{sub_id}/checkout",
            headers=cons_headers,
            json={"provider": "stripe"},
        )
        assert checkout_res.status_code == 201
        payment_id = checkout_res.json()["payment"]["id"]

    stripe_event = {
        "id": f"evt_{data['ts']}",
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "id": session_id,
                "payment_status": "paid",
                "metadata": {"payment_id": payment_id},
            }
        },
    }

    with patch("stripe.Webhook.construct_event", return_value=stripe_event):
        webhook_res = await async_client.post(
            "/payments/webhooks/stripe",
            content=json.dumps(stripe_event).encode("utf-8"),
            headers={"Stripe-Signature": "t=123,v1=signature"},
        )
        assert webhook_res.status_code == 200
        assert webhook_res.json() == {"status": "ok"}

    # Check subscription is now active
    sub_check = await async_client.get(
        f"/organizations/{consumer_org_id}/subscriptions/{sub_id}",
        headers=cons_headers,
    )
    assert sub_check.status_code == 200
    assert sub_check.json()["status"] == "active"

    # Idempotency check: replay webhook
    with patch("stripe.Webhook.construct_event", return_value=stripe_event):
        webhook_res_2 = await async_client.post(
            "/payments/webhooks/stripe",
            content=json.dumps(stripe_event).encode("utf-8"),
            headers={"Stripe-Signature": "t=123,v1=signature"},
        )
        assert webhook_res_2.status_code == 200


@pytest.mark.asyncio
async def test_stripe_webhook_invalid_signature_rejected(
    async_client, setup_payment_fixtures
):
    with patch("stripe.Webhook.construct_event", side_effect=Exception("Invalid signature")):
        webhook_res = await async_client.post(
            "/payments/webhooks/stripe",
            content=b'{"type": "checkout.session.completed"}',
            headers={"Stripe-Signature": "invalid_sig"},
        )
        assert webhook_res.status_code == 400


# =========================================================================
# 5. FAILED PAYMENT & SUBSCRIPTION STATE
# =========================================================================

@pytest.mark.asyncio
async def test_failed_payment_webhook_leaves_subscription_pending(
    async_client, setup_payment_fixtures
):
    data = setup_payment_fixtures
    cons_headers = data["cons_headers"]
    consumer_org_id = data["consumer_org_id"]
    paid_plan_id = data["paid_plan_id"]

    sub_res = await async_client.post(
        f"/organizations/{consumer_org_id}/subscriptions",
        headers=cons_headers,
        json={"plan_id": paid_plan_id},
    )
    sub_id = sub_res.json()["id"]

    order_id = f"order_fail_{data['ts']}"
    with patch("razorpay.Client") as mock_rzp:
        instance = mock_rzp.return_value
        instance.order.create.return_value = {"id": order_id}

        checkout_res = await async_client.post(
            f"/organizations/{consumer_org_id}/subscriptions/{sub_id}/checkout",
            headers=cons_headers,
            json={"provider": "razorpay"},
        )
        payment_id = checkout_res.json()["payment"]["id"]

    # Send payment.failed webhook
    fail_event = {
        "event": "payment.failed",
        "payload": {
            "payment": {
                "entity": {
                    "id": f"pay_fail_{data['ts']}",
                    "order_id": order_id,
                    "error_description": "Card expired",
                    "notes": {"payment_id": payment_id},
                }
            }
        },
    }
    with patch("razorpay.Client") as mock_rzp:
        instance = mock_rzp.return_value
        instance.utility.verify_webhook_signature.return_value = True

        res = await async_client.post(
            "/payments/webhooks/razorpay",
            content=json.dumps(fail_event).encode("utf-8"),
            headers={"X-Razorpay-Signature": "sig"},
        )
        assert res.status_code == 200

    # Payment marked failed
    pay_res = await async_client.get(
        f"/organizations/{consumer_org_id}/payments/{payment_id}",
        headers=cons_headers,
    )
    assert pay_res.status_code == 200
    assert pay_res.json()["status"] == "failed"
    assert pay_res.json()["error_message"] == "Card expired"

    # Subscription still pending
    sub_check = await async_client.get(
        f"/organizations/{consumer_org_id}/subscriptions/{sub_id}",
        headers=cons_headers,
    )
    assert sub_check.json()["status"] == "pending"


# =========================================================================
# 6. RENEWAL FLOW & RESTORING GATEWAY ACCESS
# =========================================================================

@pytest.mark.asyncio
async def test_subscription_renewal_flow(async_client, setup_payment_fixtures):
    data = setup_payment_fixtures
    cons_headers = data["cons_headers"]
    consumer_org_id = data["consumer_org_id"]
    paid_plan_id = data["paid_plan_id"]

    # 1. Create subscription and activate it
    sub_res = await async_client.post(
        f"/organizations/{consumer_org_id}/subscriptions",
        headers=cons_headers,
        json={"plan_id": paid_plan_id},
    )
    sub_id = sub_res.json()["id"]

    async with AsyncSessionLocal() as session:
        sub_obj = (await session.execute(select(Subscription).where(Subscription.id == uuid.UUID(sub_id)))).scalar_one()
        sub_obj.status = "active"
        # Make subscription expired 1 hour ago
        sub_obj.starts_at = datetime.now(timezone.utc) - timedelta(days=30)
        sub_obj.ends_at = datetime.now(timezone.utc) - timedelta(hours=1)
        await session.commit()

    # 2. Create API key while expired -> fails
    key_fail_res = await async_client.post(
        f"/organizations/{consumer_org_id}/api-keys",
        headers=cons_headers,
        json={"name": "Renewal Key", "subscription_id": sub_id},
    )
    assert key_fail_res.status_code == 400
    assert "expired" in key_fail_res.json()["detail"]

    # 3. Create existing key earlier in db
    raw_existing_key = f"ak_live_test_raw_key_{data['ts']}"
    async with AsyncSessionLocal() as session:
        api_key_obj = APIKey(
            organization_id=uuid.UUID(consumer_org_id),
            subscription_id=uuid.UUID(sub_id),
            name="Existing Key",
            key_prefix="ak_live_test",
            key_hash=hashlib.sha256(raw_existing_key.encode()).hexdigest(),
            status="active",
        )
        session.add(api_key_obj)
        await session.commit()
        await session.refresh(api_key_obj)
        key_id = str(api_key_obj.id)

    # 4. Gateway access with this key while expired -> 403 Forbidden
    verify_res = await async_client.get(
        "/gateway/verify",
        headers={"X-API-Key": raw_existing_key},
    )
    assert verify_res.status_code == 403
    assert "expired" in verify_res.json()["detail"]

    # 5. Key regeneration while expired -> fails
    regen_res = await async_client.post(
        f"/organizations/{consumer_org_id}/api-keys/{key_id}/regenerate",
        headers=cons_headers,
    )
    assert regen_res.status_code == 400
    assert "expired" in regen_res.json()["detail"]

    # 6. Renew Subscription via Checkout & Webhook
    renewal_order_id = f"order_renew_{data['ts']}"
    with patch("razorpay.Client") as mock_rzp:
        instance = mock_rzp.return_value
        instance.order.create.return_value = {"id": renewal_order_id}

        checkout_res = await async_client.post(
            f"/organizations/{consumer_org_id}/subscriptions/{sub_id}/checkout",
            headers=cons_headers,
            json={"provider": "razorpay"},
        )
        assert checkout_res.status_code == 201
        renewal_pay_id = checkout_res.json()["payment"]["id"]

    # Deliver successful renewal webhook
    renewal_event = {
        "event": "payment.captured",
        "payload": {
            "payment": {
                "entity": {
                    "id": f"pay_renew_{data['ts']}",
                    "order_id": renewal_order_id,
                    "amount": 4900,
                    "status": "captured",
                    "notes": {"payment_id": renewal_pay_id},
                }
            }
        },
    }
    with patch("razorpay.Client") as mock_rzp:
        instance = mock_rzp.return_value
        instance.utility.verify_webhook_signature.return_value = True

        webhook_res = await async_client.post(
            "/payments/webhooks/razorpay",
            content=json.dumps(renewal_event).encode("utf-8"),
            headers={"X-Razorpay-Signature": "sig"},
        )
        assert webhook_res.status_code == 200

    # 7. Subscription is now reactivated with new valid ends_at
    sub_renewed = await async_client.get(
        f"/organizations/{consumer_org_id}/subscriptions/{sub_id}",
        headers=cons_headers,
    )
    assert sub_renewed.json()["status"] == "active"
    ends_at_str = sub_renewed.json()["ends_at"].replace("Z", "+00:00")
    ends_at = datetime.fromisoformat(ends_at_str)
    assert ends_at > datetime.now(timezone.utc)

    # 8. Same existing API key automatically works again on the gateway!
    verify_res_after = await async_client.get(
        "/gateway/verify",
        headers={"X-API-Key": raw_existing_key},
    )
    assert verify_res_after.status_code == 200
    assert verify_res_after.json()["status"] == "authenticated"

    # 9. Regeneration now also succeeds!
    regen_res_after = await async_client.post(
        f"/organizations/{consumer_org_id}/api-keys/{key_id}/regenerate",
        headers=cons_headers,
    )
    assert regen_res_after.status_code == 200
    new_raw_key = regen_res_after.json()["api_key"]

    verify_regen = await async_client.get(
        "/gateway/verify",
        headers={"X-API-Key": new_raw_key},
    )
    assert verify_regen.status_code == 200


# =========================================================================
# 7. MULTI-TENANCY & AUTHORIZATION
# =========================================================================

@pytest.mark.asyncio
async def test_cross_organization_payment_isolation(
    async_client, setup_payment_fixtures
):
    data = setup_payment_fixtures
    cons_headers = data["cons_headers"]
    att_headers = data["att_headers"]
    consumer_org_id = data["consumer_org_id"]
    attacker_org_id = data["attacker_org_id"]
    paid_plan_id = data["paid_plan_id"]

    # Consumer creates subscription
    sub_res = await async_client.post(
        f"/organizations/{consumer_org_id}/subscriptions",
        headers=cons_headers,
        json={"plan_id": paid_plan_id},
    )
    sub_id = sub_res.json()["id"]

    # 1. Attacker tries to initiate checkout for consumer's subscription under attacker's org -> 404
    att_checkout_res = await async_client.post(
        f"/organizations/{attacker_org_id}/subscriptions/{sub_id}/checkout",
        headers=att_headers,
        json={"provider": "razorpay"},
    )
    assert att_checkout_res.status_code == 404

    # 2. Attacker tries to initiate checkout via generic checkout route for consumer's subscription -> 403
    att_generic_checkout = await async_client.post(
        f"/payments/checkout?subscription_id={sub_id}",
        headers=att_headers,
        json={"provider": "razorpay"},
    )
    assert att_generic_checkout.status_code == 403

    # Consumer initiates checkout legitimately
    with patch("razorpay.Client") as mock_rzp:
        instance = mock_rzp.return_value
        instance.order.create.return_value = {"id": f"order_legit_{data['ts']}"}

        cons_checkout = await async_client.post(
            f"/organizations/{consumer_org_id}/subscriptions/{sub_id}/checkout",
            headers=cons_headers,
            json={"provider": "razorpay"},
        )
        payment_id = cons_checkout.json()["payment"]["id"]

    # 3. Attacker tries to get consumer's payment record -> 404
    att_get_pay = await async_client.get(
        f"/organizations/{attacker_org_id}/payments/{payment_id}",
        headers=att_headers,
    )
    assert att_get_pay.status_code == 404

    # 4. Attacker tries to verify consumer's payment record -> 404
    att_verify = await async_client.post(
        f"/organizations/{attacker_org_id}/payments/{payment_id}/verify",
        headers=att_headers,
        json={},
    )
    assert att_verify.status_code == 404
