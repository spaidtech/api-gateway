from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import HTTPException, status

from app.models.subscription import Subscription
from app.repositories.subscription import SubscriptionRepository


def calculate_duration(billing_interval: str | None) -> timedelta:
    interval = (billing_interval or "monthly").lower()
    if interval in {"yearly", "annual", "year"}:
        return timedelta(days=365)
    elif interval in {"weekly", "week"}:
        return timedelta(days=7)
    elif interval in {"daily", "day"}:
        return timedelta(days=1)
    else:  # default monthly
        return timedelta(days=30)


class SubscriptionService:
    def __init__(self, repository: SubscriptionRepository):
        self.repository = repository

    async def get_by_id(self, subscription_id: UUID) -> Subscription | None:
        return await self.repository.get_by_id(subscription_id)

    async def get_by_consumer_organization(
        self, organization_id: UUID
    ) -> list[Subscription]:
        return await self.repository.get_by_consumer_organization_id(
            organization_id
        )

    async def get_by_plan(self, plan_id: UUID) -> list[Subscription]:
        return await self.repository.get_by_plan_id(plan_id)

    async def create(
        self,
        *,
        consumer_organization_id: UUID,
        plan_id: UUID,
        status: str = "active",
        starts_at: datetime | None = None,
        ends_at: datetime | None = None,
    ) -> Subscription:
        if starts_at is None:
            starts_at = datetime.now(timezone.utc)

        sub = await self.repository.create(
            consumer_organization_id=consumer_organization_id,
            plan_id=plan_id,
            status=status,
            starts_at=starts_at,
            ends_at=ends_at,
        )
        await self.repository.db.commit()
        await self.repository.db.refresh(sub)
        return sub

    async def activate(
        self,
        subscription_id: UUID,
        billing_interval: str = "monthly",
    ) -> Subscription | None:
        subscription = await self.repository.get_by_id(subscription_id)
        if not subscription:
            return None

        now = datetime.now(timezone.utc)
        duration = calculate_duration(billing_interval)

        current_ends_at = subscription.ends_at
        if current_ends_at is not None and current_ends_at.tzinfo is None:
            current_ends_at = current_ends_at.replace(tzinfo=timezone.utc)

        if subscription.status == "active" and current_ends_at and current_ends_at > now:
            # Renew in advance: extend from current ends_at
            new_ends_at = current_ends_at + duration
            new_starts_at = subscription.starts_at
        else:
            # New or expired/cancelled reactivation: start from now
            new_starts_at = now
            new_ends_at = now + duration

        sub = await self.repository.update(
            subscription,
            status="active",
            starts_at=new_starts_at,
            ends_at=new_ends_at,
        )
        await self.repository.db.commit()
        await self.repository.db.refresh(sub)
        return sub

    async def update(
        self,
        subscription: Subscription,
        **data,
    ) -> Subscription:
        sub = await self.repository.update(subscription, **data)
        await self.repository.db.commit()
        await self.repository.db.refresh(sub)
        return sub

    async def cancel(self, subscription: Subscription) -> Subscription:
        sub = await self.repository.update(
            subscription,
            status="cancelled",
        )
        await self.repository.db.commit()
        await self.repository.db.refresh(sub)
        return sub

    async def validate(self, subscription: Subscription) -> Subscription:
        if subscription.status != "active":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Subscription is not active (current status: {subscription.status})",
            )

        now = datetime.now(timezone.utc)
        if subscription.ends_at is not None:
            ends_at = subscription.ends_at
            if ends_at.tzinfo is None:
                ends_at = ends_at.replace(tzinfo=timezone.utc)
            if ends_at <= now:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Subscription has expired",
                )

        return subscription