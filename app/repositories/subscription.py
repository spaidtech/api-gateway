from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.subscription import Subscription


class SubscriptionRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(
        self,
        subscription_id: UUID,
    ) -> Subscription | None:
        result = await self.db.execute(
            select(Subscription).where(
                Subscription.id == subscription_id
            )
        )
        return result.scalar_one_or_none()

    async def get_by_consumer_organization_id(
        self,
        organization_id: UUID,
    ) -> list[Subscription]:
        result = await self.db.execute(
            select(Subscription).where(
                Subscription.consumer_organization_id == organization_id
            )
        )
        return list(result.scalars().all())

    async def get_by_plan_id(
        self,
        plan_id: UUID,
    ) -> list[Subscription]:
        result = await self.db.execute(
            select(Subscription).where(
                Subscription.plan_id == plan_id
            )
        )
        return list(result.scalars().all())

    async def create(
        self,
        **data,
    ) -> Subscription:
        subscription = Subscription(**data)

        self.db.add(subscription)
        await self.db.flush()
        await self.db.refresh(subscription)

        return subscription

    async def update(
        self,
        subscription: Subscription,
        **fields,
    ) -> Subscription:
        for field, value in fields.items():
            if value is not None:
                setattr(subscription, field, value)

        await self.db.flush()
        await self.db.refresh(subscription)

        return subscription