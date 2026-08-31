from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Request,
    status,
)

from app.dependencies.auth import get_current_user
from app.dependencies.authorization import require_organization_roles
from app.dependencies.services import (
    get_api_plan_service,
    get_organization_member_service,
    get_payment_service,
    get_subscription_service,
)
from app.models.membership import OrganizationMember
from app.models.payment import (
    PaymentProvider,
    PaymentStatus,
)
from app.models.user import User
from app.schemas.payment import (
    PaymentCheckoutResponse,
    PaymentCreate,
    PaymentResponse,
    PaymentVerifyRequest,
)
from app.services.api_plan import APIPlanService
from app.services.organization_member import OrganizationMemberService
from app.services.payment.service import PaymentService
from app.services.subscription import SubscriptionService

router = APIRouter(tags=["Payments"])


# =========================================================================
# Organization-scoped Checkout and Payment Management
# =========================================================================

@router.post(
    "/organizations/{organization_id}/subscriptions/{subscription_id}/checkout",
    response_model=PaymentCheckoutResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_organization_subscription_checkout(
    organization_id: UUID,
    subscription_id: UUID,
    payload: PaymentCreate,
    current_user: User = Depends(get_current_user),
    _membership: OrganizationMember = Depends(
        require_organization_roles("owner", "admin")
    ),
    subscription_service: SubscriptionService = Depends(get_subscription_service),
    plan_service: APIPlanService = Depends(get_api_plan_service),
    payment_service: PaymentService = Depends(get_payment_service),
):
    subscription = await subscription_service.get_by_id(subscription_id)
    if not subscription or subscription.consumer_organization_id != organization_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Subscription not found for this organization.",
        )

    plan = await plan_service.get_by_id(subscription.plan_id)
    if not plan or not plan.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Subscription plan is invalid or inactive.",
        )

    payment, checkout_data = await payment_service.create_payment(
        organization_id=subscription.consumer_organization_id,
        subscription_id=subscription.id,
        provider=payload.provider,
        amount=plan.price,
        currency=plan.currency,
        description=f"{plan.name} Subscription",
        metadata={
            "organization_id": str(organization_id),
            "subscription_id": str(subscription_id),
            "plan_id": str(plan.id),
        },
    )

    return PaymentCheckoutResponse(
        payment=PaymentResponse.model_validate(payment),
        checkout_data=checkout_data,
    )


@router.post(
    "/payments/checkout",
    response_model=PaymentCheckoutResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_checkout(
    subscription_id: UUID,
    payload: PaymentCreate,
    current_user: User = Depends(get_current_user),
    subscription_service: SubscriptionService = Depends(get_subscription_service),
    plan_service: APIPlanService = Depends(get_api_plan_service),
    payment_service: PaymentService = Depends(get_payment_service),
    member_service: OrganizationMemberService = Depends(get_organization_member_service),
):
    subscription = await subscription_service.get_by_id(subscription_id)
    if not subscription:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Subscription not found.",
        )

    # Check user has owner or admin role in the subscription's consumer organization
    membership = await member_service.get_member(
        organization_id=subscription.consumer_organization_id,
        user_id=current_user.id,
    )
    if not membership:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this organization's subscriptions.",
        )

    role = await member_service.role_repository.get_by_id(membership.role_id)
    if not role or role.name not in {"owner", "admin"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions to initiate payment for this subscription.",
        )

    plan = await plan_service.get_by_id(subscription.plan_id)
    if not plan or not plan.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Subscription plan is invalid or inactive.",
        )

    payment, checkout_data = await payment_service.create_payment(
        organization_id=subscription.consumer_organization_id,
        subscription_id=subscription.id,
        provider=payload.provider,
        amount=plan.price,
        currency=plan.currency,
        description=f"{plan.name} Subscription",
        metadata={
            "organization_id": str(subscription.consumer_organization_id),
            "subscription_id": str(subscription.id),
            "plan_id": str(plan.id),
        },
    )

    return PaymentCheckoutResponse(
        payment=PaymentResponse.model_validate(payment),
        checkout_data=checkout_data,
    )


@router.get(
    "/organizations/{organization_id}/payments",
    response_model=list[PaymentResponse],
)
async def list_organization_payments(
    organization_id: UUID,
    current_user: User = Depends(get_current_user),
    _membership: OrganizationMember = Depends(
        require_organization_roles("owner", "admin", "member")
    ),
    payment_service: PaymentService = Depends(get_payment_service),
):
    payments = await payment_service.get_by_organization_id(organization_id)
    return [PaymentResponse.model_validate(p) for p in payments]


@router.get(
    "/organizations/{organization_id}/payments/{payment_id}",
    response_model=PaymentResponse,
)
async def get_organization_payment(
    organization_id: UUID,
    payment_id: UUID,
    current_user: User = Depends(get_current_user),
    _membership: OrganizationMember = Depends(
        require_organization_roles("owner", "admin", "member")
    ),
    payment_service: PaymentService = Depends(get_payment_service),
):
    payment = await payment_service.get_by_id(payment_id)
    if not payment or payment.organization_id != organization_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Payment not found.",
        )
    return PaymentResponse.model_validate(payment)


@router.post(
    "/organizations/{organization_id}/payments/{payment_id}/verify",
    response_model=PaymentResponse,
)
async def verify_payment_status(
    organization_id: UUID,
    payment_id: UUID,
    payload: PaymentVerifyRequest | None = None,
    current_user: User = Depends(get_current_user),
    _membership: OrganizationMember = Depends(
        require_organization_roles("owner", "admin")
    ),
    payment_service: PaymentService = Depends(get_payment_service),
    subscription_service: SubscriptionService = Depends(get_subscription_service),
    plan_service: APIPlanService = Depends(get_api_plan_service),
):
    payment = await payment_service.get_by_id(payment_id)
    if not payment or payment.organization_id != organization_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Payment not found.",
        )

    if payment.status == PaymentStatus.SUCCEEDED:
        return PaymentResponse.model_validate(payment)

    extra_data = payload.model_dump(exclude_none=True) if payload else {}
    is_valid = await payment_service.verify_provider_payment(payment, extra_data=extra_data)

    if is_valid:
        payment = await payment_service.mark_succeeded(payment)
        subscription = await subscription_service.get_by_id(payment.subscription_id)
        if subscription:
            plan = await plan_service.get_by_id(subscription.plan_id)
            billing_interval = plan.billing_interval if plan else "monthly"
            await subscription_service.activate(subscription.id, billing_interval=billing_interval)
    else:
        payment = await payment_service.mark_failed(
            payment,
            error_message="Payment verification with provider failed.",
        )

    return PaymentResponse.model_validate(payment)


# =========================================================================
# Webhook Handlers
# =========================================================================

@router.post("/payments/webhooks/razorpay")
@router.post("/webhooks/razorpay")
async def razorpay_webhook(
    request: Request,
    payment_service: PaymentService = Depends(get_payment_service),
    subscription_service: SubscriptionService = Depends(get_subscription_service),
    plan_service: APIPlanService = Depends(get_api_plan_service),
):
    payload = await request.body()
    signature = request.headers.get("X-Razorpay-Signature")

    if not signature:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing Razorpay signature.",
        )

    provider = payment_service._get_provider(PaymentProvider.RAZORPAY)

    try:
        event = await provider.verify_webhook(
            payload=payload,
            signature=signature,
        )
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid Razorpay webhook signature.",
        )

    event_name = event.get("event")

    if event_name in {"payment.captured", "order.paid"}:
        payment_entity = (
            event.get("payload", {}).get("payment", {}).get("entity", {})
            or event.get("payload", {}).get("order", {}).get("entity", {})
        )
        provider_payment_id = payment_entity.get("order_id") or payment_entity.get("id")
        notes = payment_entity.get("notes", {})
        payment_internal_id = notes.get("payment_id")

        payment = None
        if provider_payment_id:
            payment = await payment_service.get_by_provider_payment_id(
                provider_payment_id=provider_payment_id,
                provider=PaymentProvider.RAZORPAY,
            )
        if not payment and payment_internal_id:
            try:
                payment = await payment_service.get_by_id(UUID(payment_internal_id))
            except (ValueError, TypeError):
                pass

        if payment:
            payment = await payment_service.mark_succeeded(payment)
            subscription = await subscription_service.get_by_id(payment.subscription_id)
            if subscription:
                plan = await plan_service.get_by_id(subscription.plan_id)
                billing_interval = plan.billing_interval if plan else "monthly"
                await subscription_service.activate(
                    subscription.id,
                    billing_interval=billing_interval,
                )

    elif event_name == "payment.failed":
        payment_entity = event.get("payload", {}).get("payment", {}).get("entity", {})
        provider_payment_id = payment_entity.get("order_id") or payment_entity.get("id")
        notes = payment_entity.get("notes", {})
        payment_internal_id = notes.get("payment_id")

        payment = None
        if provider_payment_id:
            payment = await payment_service.get_by_provider_payment_id(
                provider_payment_id=provider_payment_id,
                provider=PaymentProvider.RAZORPAY,
            )
        if not payment and payment_internal_id:
            try:
                payment = await payment_service.get_by_id(UUID(payment_internal_id))
            except (ValueError, TypeError):
                pass

        if payment:
            error_description = payment_entity.get("error_description", "Payment failed")
            await payment_service.mark_failed(payment, error_message=error_description)

    return {"status": "ok"}


@router.post("/payments/webhooks/stripe")
@router.post("/webhooks/stripe")
async def stripe_webhook(
    request: Request,
    payment_service: PaymentService = Depends(get_payment_service),
    subscription_service: SubscriptionService = Depends(get_subscription_service),
    plan_service: APIPlanService = Depends(get_api_plan_service),
):
    payload = await request.body()
    signature = request.headers.get("Stripe-Signature")

    if not signature:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing Stripe signature.",
        )

    provider = payment_service._get_provider(PaymentProvider.STRIPE)

    try:
        event = await provider.verify_webhook(
            payload=payload,
            signature=signature,
        )
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid Stripe webhook signature.",
        )

    event_type = event.get("type")

    if event_type in {"checkout.session.completed", "payment_intent.succeeded"}:
        data_obj = event.get("data", {}).get("object", {})
        provider_payment_id = data_obj.get("id")
        metadata = data_obj.get("metadata", {})
        payment_internal_id = metadata.get("payment_id")

        payment = None
        if provider_payment_id:
            payment = await payment_service.get_by_provider_payment_id(
                provider_payment_id=provider_payment_id,
                provider=PaymentProvider.STRIPE,
            )
        if not payment and payment_internal_id:
            try:
                payment = await payment_service.get_by_id(UUID(payment_internal_id))
            except (ValueError, TypeError):
                pass

        if payment:
            payment = await payment_service.mark_succeeded(payment)
            subscription = await subscription_service.get_by_id(payment.subscription_id)
            if subscription:
                plan = await plan_service.get_by_id(subscription.plan_id)
                billing_interval = plan.billing_interval if plan else "monthly"
                await subscription_service.activate(
                    subscription.id,
                    billing_interval=billing_interval,
                )

    elif event_type in {"payment_intent.payment_failed", "checkout.session.expired"}:
        data_obj = event.get("data", {}).get("object", {})
        provider_payment_id = data_obj.get("id")
        metadata = data_obj.get("metadata", {})
        payment_internal_id = metadata.get("payment_id")

        payment = None
        if provider_payment_id:
            payment = await payment_service.get_by_provider_payment_id(
                provider_payment_id=provider_payment_id,
                provider=PaymentProvider.STRIPE,
            )
        if not payment and payment_internal_id:
            try:
                payment = await payment_service.get_by_id(UUID(payment_internal_id))
            except (ValueError, TypeError):
                pass

        if payment:
            last_error = data_obj.get("last_payment_error", {}).get("message", "Payment failed")
            await payment_service.mark_failed(payment, error_message=last_error)

    return {"status": "ok"}