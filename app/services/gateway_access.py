from fastapi import HTTPException, status

from app.models.api_key import APIKey
from app.schemas.gateway_access import GatewayAccessContext
from app.services.subscription import SubscriptionService
from app.services.api_plan import APIPlanService

class GatewayAccessService:

    def __init__(
        self,
        subscription_service: SubscriptionService,
        api_plan_service: APIPlanService,
    ):
        self.subscription_service = subscription_service
        self.api_plan_service = api_plan_service

    async def get_access_context(self, api_key: APIKey) -> GatewayAccessContext:

        # API key without a subscription is supported
        if api_key.subscription_id is None:
            return GatewayAccessContext(
                api_key=api_key,
                subscription=None,
                plan=None,
            )

        subscription = await self.subscription_service.get_by_id(api_key.subscription_id)

        if subscription is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Subscription not found",
            )

        if subscription.consumer_organization_id != api_key.organization_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Subscription does not belong to this organization",
            )

        await self.subscription_service.validate(subscription)

        plan = await self.api_plan_service.get_by_id(subscription.plan_id)

        if plan is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="API plan not found",
            )

        if not plan.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="API plan is not active",
            )

        return GatewayAccessContext(
            api_key=api_key,
            subscription=subscription,
            plan=plan,
        )