from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.payment import Payment, PaymentProvider, PaymentStatus


class PaymentRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(
        self,
        payment_id: UUID,
    ) -> Payment | None:
        result = await self.db.execute(
            select(Payment).where(Payment.id == payment_id)
        )

        return result.scalar_one_or_none()

    async def get_by_provider_payment_id(
        self,
        provider_payment_id: str,
        provider: PaymentProvider | str | None = None,
    ) -> Payment | None:
        query = select(Payment).where(Payment.provider_payment_id == provider_payment_id)
        if provider is not None:
            query = query.where(Payment.provider == provider)
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def get_by_subscription_id(
        self,
        subscription_id: UUID,
    ) -> list[Payment]:
        result = await self.db.execute(
            select(Payment)
            .where(Payment.subscription_id == subscription_id)
            .order_by(Payment.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_by_organization_id(
        self,
        organization_id: UUID,
    ) -> list[Payment]:
        result = await self.db.execute(
            select(Payment)
            .where(Payment.organization_id == organization_id)
            .order_by(Payment.created_at.desc())
        )
        return list(result.scalars().all())

    async def create(
        self,
        **data,
    ) -> Payment:
        payment = Payment(**data)

        self.db.add(payment)

        await self.db.flush()
        await self.db.refresh(payment)

        return payment

    async def update(
            self,
            payment: Payment,
            **fields
    ) -> Payment:
        for field, value in fields.items():
            if value is not None:
                setattr(payment, field, value)

        await self.db.flush()
        await self.db.refresh(payment)

        return payment