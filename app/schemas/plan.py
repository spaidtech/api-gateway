from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class APIPlanCreate(BaseModel):
    name: str = Field(
        min_length=1,
        max_length=100,
    )

    price: float = Field(
        ge=0,
    )

    billing_period: str = Field(
        min_length=1,
        max_length=20,
    )

    request_limit: int | None = Field(
        default=None,
        ge=1,
    )


class APIPlanUpdate(BaseModel):
    name: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
    )

    price: float | None = Field(
        default=None,
        ge=0,
    )

    billing_period: str | None = Field(
        default=None,
        max_length=20,
    )

    request_limit: int | None = Field(
        default=None,
        ge=1,
    )

    is_active: bool | None = None


class APIPlanResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    api_id: UUID
    name: str
    price: float
    billing_period: str
    request_limit: int | None
    is_active: bool
    created_at: datetime