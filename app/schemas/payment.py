import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from app.models.payment import (
    PaymentProvider,
    PaymentStatus,
)


class PaymentCreate(BaseModel):
    provider: PaymentProvider


class PaymentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    subscription_id: uuid.UUID
    provider: PaymentProvider
    provider_payment_id: str | None
    amount: Decimal
    currency: str
    status: PaymentStatus
    error_message: str | None = None
    created_at: datetime
    completed_at: datetime | None = None


class PaymentCheckoutResponse(BaseModel):
    payment: PaymentResponse
    checkout_data: dict


class PaymentVerifyRequest(BaseModel):
    provider_payment_id: str | None = None
    razorpay_payment_id: str | None = None
    razorpay_order_id: str | None = None
    razorpay_signature: str | None = None