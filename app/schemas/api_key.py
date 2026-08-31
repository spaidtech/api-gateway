import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class APIKeyCreate(BaseModel):
    name: str
    subscription_id: uuid.UUID | None = None
    expires_at: datetime | None = None


class APIKeyResponse(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    subscription_id: uuid.UUID | None
    name: str
    key_prefix: str
    status: str
    expires_at: datetime | None
    last_used_at: datetime | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class APIKeyCreatedResponse(APIKeyResponse):
    """
    Raw API key is returned only once during creation.
    """

    api_key: str