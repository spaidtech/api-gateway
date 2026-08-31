from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class UpstreamCreate(BaseModel):
    name: str = Field(
        min_length=1,
        max_length=100,
    )

    base_url: str = Field(
        min_length=1,
        max_length=500,
    )


class UpstreamUpdate(BaseModel):
    name: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
    )

    base_url: str | None = Field(
        default=None,
        min_length=1,
        max_length=500,
    )

    is_active: bool | None = None


class UpstreamResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    name: str
    base_url: str
    is_active: bool
    created_at: datetime