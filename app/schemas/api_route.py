import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class APIRouteCreate(BaseModel):
    upstream_id: uuid.UUID
    path: str = Field(min_length=1, max_length=500)
    method: str = Field(min_length=1, max_length=10)
    target_path: str | None = Field(default=None, max_length=500)
    description: str | None = None


class APIRouteUpdate(BaseModel):
    upstream_id: uuid.UUID | None = None
    path: str | None = Field(default=None, min_length=1, max_length=500)
    method: str | None = Field(default=None, min_length=1, max_length=10)
    target_path: str | None = Field(default=None, max_length=500)
    description: str | None = None


class APIRouteResponse(BaseModel):
    id: uuid.UUID
    api_id: uuid.UUID
    upstream_id: uuid.UUID
    path: str
    method: str
    target_path: str | None
    description: str | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
