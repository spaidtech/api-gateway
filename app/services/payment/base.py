from abc import ABC, abstractmethod
from decimal import Decimal

class PaymentProviderBase(ABC):

    @abstractmethod
    async def create_payment(
        self,
        *,
        payment_id: str,
        amount: Decimal,
        currency: str,
        description: str,
        metadata: dict | None = None,
    ) -> dict:
        """
        Create a provider-side payment/order/checkout session.
        Returns dict with provider_payment_id and checkout_data.
        """

    @abstractmethod
    async def verify_webhook(
        self,
        *,
        payload: bytes,
        signature: str,
    ) -> dict:
        """
        Verify and parse an incoming provider webhook payload.
        """

    @abstractmethod
    async def verify_payment(
        self,
        *,
        provider_payment_id: str,
        extra_data: dict | None = None,
    ) -> bool:
        """
        Verify payment state with provider directly.
        """