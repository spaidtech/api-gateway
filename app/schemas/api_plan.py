import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class APIPlanCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str | None = None
    price: Decimal = Field(ge=0)
    currency: str = Field(default="INR", min_length=3, max_length=3)
    billing_interval: str = Field(min_length=1, max_length=20)
    rate_limit: int = Field(ge=0)
    monthly_quota: int = Field(ge=0)


class APIPlanUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    price: Decimal | None = Field(default=None, ge=0)
    rate_limit: int | None = Field(default=None, ge=0)
    monthly_quota: int | None = Field(default=None, ge=0)
    is_active: bool | None = None


class APIPlanResponse(BaseModel):
    id: uuid.UUID
    api_id: uuid.UUID
    name: str
    description: str | None
    price: Decimal
    currency: str
    billing_interval: str
    rate_limit: int
    monthly_quota: int
    is_active: bool

    model_config = ConfigDict(from_attributes=True)
