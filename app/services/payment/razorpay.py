import asyncio
import json
from decimal import Decimal

import razorpay

from app.core.config import settings
from app.services.payment.base import PaymentProviderBase


class RazorpayPaymentProvider(PaymentProviderBase):
    def __init__(self):
        self.client = razorpay.Client(
            auth=(
                settings.RAZORPAY_KEY_ID,
                settings.RAZORPAY_KEY_SECRET,
            )
        )

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
        notes = {"payment_id": payment_id, "description": description}
        if metadata:
            notes.update(metadata)

        order_params = {
            "amount": amount_in_smallest_unit,
            "currency": currency.upper(),
            "receipt": payment_id[:40],
            "notes": notes,
        }

        order = await asyncio.to_thread(
            self.client.order.create,
            order_params,
        )

        return {
            "provider_payment_id": order["id"],
            "checkout_data": {
                "key_id": settings.RAZORPAY_KEY_ID,
                "order_id": order["id"],
                "amount": amount_in_smallest_unit,
                "currency": currency.upper(),
                "name": description,
                "notes": notes,
            },
        }

    async def verify_webhook(
        self,
        *,
        payload: bytes,
        signature: str,
    ) -> dict:
        payload_text = payload.decode("utf-8")
        secret = settings.RAZORPAY_WEBHOOK_SECRET or settings.RAZORPAY_KEY_SECRET

        await asyncio.to_thread(
            self.client.utility.verify_webhook_signature,
            payload_text,
            signature,
            secret,
        )

        return json.loads(payload_text)

    async def verify_payment(
        self,
        *,
        provider_payment_id: str,
        extra_data: dict | None = None,
    ) -> bool:
        if extra_data and "razorpay_signature" in extra_data and "razorpay_payment_id" in extra_data:
            params = {
                "razorpay_order_id": provider_payment_id,
                "razorpay_payment_id": extra_data["razorpay_payment_id"],
                "razorpay_signature": extra_data["razorpay_signature"],
            }
            try:
                await asyncio.to_thread(
                    self.client.utility.verify_payment_signature,
                    params,
                )
                return True
            except Exception:
                return False

        # Fallback to fetching order status directly from Razorpay
        try:
            order = await asyncio.to_thread(
                self.client.order.fetch,
                provider_payment_id,
            )
            return order.get("status") == "paid"
        except Exception:
            return False