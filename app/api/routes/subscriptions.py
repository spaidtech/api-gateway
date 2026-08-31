from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from datetime import datetime, timezone

from app.dependencies.auth import get_current_user
from app.dependencies.authorization import require_organization_roles
from app.dependencies.services import (
    get_api_plan_service,
    get_subscription_service,
)
from app.models.membership import OrganizationMember
from app.models.user import User
from app.schemas.subscription import SubscriptionCreate, SubscriptionResponse
from app.services.api_plan import APIPlanService
from app.services.subscription import SubscriptionService, calculate_duration

router = APIRouter(
    prefix="/organizations/{organization_id}/subscriptions",
    tags=["Subscriptions"],
)


@router.post(
    "",
    response_model=SubscriptionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_subscription(
    organization_id: UUID,
    data: SubscriptionCreate,
    current_user: User = Depends(get_current_user),
    _membership: OrganizationMember = Depends(
        require_organization_roles("owner", "admin")
    ),
    plan_service: APIPlanService = Depends(get_api_plan_service),
    subscription_service: SubscriptionService = Depends(
        get_subscription_service
    ),
):
    plan = await plan_service.get_by_id(data.plan_id)
    if plan is None or not plan.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="API plan not found or is inactive",
        )

    now = datetime.now(timezone.utc)
    if plan.price == 0:
        ends_at = now + calculate_duration(plan.billing_interval)
        return await subscription_service.create(
            consumer_organization_id=organization_id,
            plan_id=data.plan_id,
            status="active",
            starts_at=now,
            ends_at=ends_at,
        )
    else:
        return await subscription_service.create(
            consumer_organization_id=organization_id,
            plan_id=data.plan_id,
            status="pending",
            starts_at=now,
            ends_at=None,
        )


@router.get(
    "",
    response_model=list[SubscriptionResponse],
)
async def list_subscriptions(
    organization_id: UUID,
    current_user: User = Depends(get_current_user),
    _membership: OrganizationMember = Depends(
        require_organization_roles("owner", "admin", "member")
    ),
    subscription_service: SubscriptionService = Depends(
        get_subscription_service
    ),
):
    return await subscription_service.get_by_consumer_organization(
        organization_id
    )


@router.get(
    "/{subscription_id}",
    response_model=SubscriptionResponse,
)
async def get_subscription(
    organization_id: UUID,
    subscription_id: UUID,
    current_user: User = Depends(get_current_user),
    _membership: OrganizationMember = Depends(
        require_organization_roles("owner", "admin", "member")
    ),
    subscription_service: SubscriptionService = Depends(
        get_subscription_service
    ),
):
    subscription = await subscription_service.get_by_id(subscription_id)
    if (
        not subscription
        or subscription.consumer_organization_id != organization_id
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Subscription not found",
        )
    return subscription


@router.post(
    "/{subscription_id}/cancel",
    response_model=SubscriptionResponse,
)
async def cancel_subscription(
    organization_id: UUID,
    subscription_id: UUID,
    current_user: User = Depends(get_current_user),
    _membership: OrganizationMember = Depends(
        require_organization_roles("owner", "admin")
    ),
    subscription_service: SubscriptionService = Depends(
        get_subscription_service
    ),
):
    subscription = await subscription_service.get_by_id(subscription_id)
    if (
        not subscription
        or subscription.consumer_organization_id != organization_id
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Subscription not found",
        )
    return await subscription_service.cancel(subscription)
