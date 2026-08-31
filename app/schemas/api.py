import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.api import APIStatus, APIVisibility


class APICreate(BaseModel):
    name: str
    slug: str
    version: str = "v1"
    description: str | None = None
    documentation: str | None = None
    visibility: APIVisibility = APIVisibility.PRIVATE
    base_path: str


class APIUpdate(BaseModel):
    name: str | None = None
    slug: str | None = None
    description: str | None = None
    documentation: str | None = None
    visibility: APIVisibility | None = None
    status: APIStatus | None = None


class APIResponse(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    name: str
    slug: str
    version: str
    description: str | None
    visibility: APIVisibility
    status: APIStatus
    base_path: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
