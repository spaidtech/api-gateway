import asyncio
from decimal import Decimal

import stripe

from app.core.config import settings
from app.services.payment.base import PaymentProviderBase


class StripePaymentProvider(PaymentProviderBase):

    def __init__(self):
        stripe.api_key = settings.STRIPE_SECRET_KEY

    async def create_payment(
        self,
        *,
        payment_id: str,
        amount: Decimal,
        currency: str,
        description: str,
        metadata: dict | None = None,
    ) -> dict:
        amount_in_smallest_unit = int(amount * 100)
        session_metadata = {"payment_id": payment_id}
        if metadata:
            session_metadata.update(metadata)

        session = await asyncio.to_thread(
            stripe.checkout.Session.create,
            mode="payment",
            payment_method_types=["card"],
            line_items=[
                {
                    "price_data": {
                        "currency": currency.lower(),
                        "product_data": {
                            "name": description,
                        },
                        "unit_amount": amount_in_smallest_unit,
                    },
                    "quantity": 1,
                }
            ],
            metadata=session_metadata,
            success_url=(
                f"{settings.PAYMENT_SUCCESS_URL}"
                f"?payment_id={payment_id}&session_id={{CHECKOUT_SESSION_ID}}"
            ),
            cancel_url=(
                f"{settings.PAYMENT_CANCEL_URL}"
                f"?payment_id={payment_id}"
            ),
        )

        return {
            "provider_payment_id": session.id,
            "checkout_data": {
                "checkout_url": session.url,
                "session_id": session.id,
            },
        }

    async def verify_webhook(
        self,
        *,
        payload: bytes,
        signature: str,
    ) -> dict:
        event = await asyncio.to_thread(
            stripe.Webhook.construct_event,
            payload,
            signature,
            settings.STRIPE_WEBHOOK_SECRET,
        )

        return event

    async def verify_payment(
        self,
        *,
        provider_payment_id: str,
        extra_data: dict | None = None,
    ) -> bool:
        try:
            session = await asyncio.to_thread(
                stripe.checkout.Session.retrieve,
                provider_payment_id,
            )
            return session.payment_status == "paid"
        except Exception:
            return False