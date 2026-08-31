from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from fastapi import HTTPException, status

from app.models.payment import (
    Payment,
    PaymentProvider,
    PaymentStatus,
)
from app.repositories.payment import PaymentRepository
from app.services.payment.base import PaymentProviderBase
from app.services.payment.razorpay import RazorpayPaymentProvider
from app.services.payment.stripe import StripePaymentProvider


class PaymentService:
    def __init__(self, repository: PaymentRepository):
        self.repository = repository
        self.providers: dict[PaymentProvider, PaymentProviderBase] = {
            PaymentProvider.RAZORPAY: RazorpayPaymentProvider(),
            PaymentProvider.STRIPE: StripePaymentProvider(),
        }

    def _get_provider(self, provider: PaymentProvider | str) -> PaymentProviderBase:
        if isinstance(provider, str):
            try:
                provider = PaymentProvider(provider.lower())
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"Unsupported payment provider: '{provider}'. Supported providers are: 'razorpay', 'stripe'.",
                )

        payment_provider = self.providers.get(provider)
        if not payment_provider:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Unsupported payment provider: '{provider}'.",
            )
        return payment_provider

    async def get_by_id(self, payment_id: UUID) -> Payment | None:
        return await self.repository.get_by_id(payment_id)

    async def get_by_provider_payment_id(
        self,
        provider_payment_id: str,
        provider: PaymentProvider | str | None = None,
    ) -> Payment | None:
        return await self.repository.get_by_provider_payment_id(
            provider_payment_id=provider_payment_id,
            provider=provider,
        )

    async def get_by_subscription_id(self, subscription_id: UUID) -> list[Payment]:
        return await self.repository.get_by_subscription_id(subscription_id)

    async def get_by_organization_id(self, organization_id: UUID) -> list[Payment]:
        return await self.repository.get_by_organization_id(organization_id)

    async def create_payment(
        self,
        *,
        organization_id: UUID,
        subscription_id: UUID,
        provider: PaymentProvider | str,
        amount: Decimal,
        currency: str,
        description: str,
        metadata: dict | None = None,
    ) -> tuple[Payment, dict]:
        if isinstance(provider, str):
            try:
                provider = PaymentProvider(provider.lower())
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"Unsupported payment provider: '{provider}'. Supported providers are: 'razorpay', 'stripe'.",
                )

        payment = await self.repository.create(
            organization_id=organization_id,
            subscription_id=subscription_id,
            provider=provider,
            amount=amount,
            currency=currency.upper(),
            status=PaymentStatus.PENDING,
        )
        await self.repository.db.commit()
        await self.repository.db.refresh(payment)

        payment_provider = self._get_provider(provider)

        try:
            provider_result = await payment_provider.create_payment(
                payment_id=str(payment.id),
                amount=amount,
                currency=currency,
                description=description,
                metadata=metadata,
            )

            payment = await self.repository.update(
                payment=payment,
                provider_payment_id=provider_result["provider_payment_id"],
            )
            await self.repository.db.commit()
            await self.repository.db.refresh(payment)

            return payment, provider_result["checkout_data"]

        except Exception as exc:
            await self.repository.update(
                payment=payment,
                status=PaymentStatus.FAILED,
                error_message=str(exc)[:500],
            )
            await self.repository.db.commit()
            raise

    async def mark_succeeded(self, payment: Payment) -> Payment:
        # Idempotency check: If already succeeded, return as is
        if payment.status == PaymentStatus.SUCCEEDED:
            return payment

        payment = await self.repository.update(
            payment=payment,
            status=PaymentStatus.SUCCEEDED,
            completed_at=datetime.now(timezone.utc),
            error_message=None,
        )
        await self.repository.db.commit()
        await self.repository.db.refresh(payment)
        return payment

    async def mark_failed(
        self,
        payment: Payment,
        error_message: str | None = None,
    ) -> Payment:
        if payment.status == PaymentStatus.SUCCEEDED:
            return payment

        payment = await self.repository.update(
            payment=payment,
            status=PaymentStatus.FAILED,
            error_message=error_message,
        )
        await self.repository.db.commit()
        await self.repository.db.refresh(payment)
        return payment

    async def verify_provider_payment(
        self,
        payment: Payment,
        extra_data: dict | None = None,
    ) -> bool:
        if not payment.provider_payment_id:
            return False
        provider = self._get_provider(payment.provider)
        return await provider.verify_payment(
            provider_payment_id=payment.provider_payment_id,
            extra_data=extra_data,
        )

