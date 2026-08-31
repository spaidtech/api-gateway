from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class APIKeyDomainCreate(BaseModel):
    domain: str = Field(
        min_length=1,
        max_length=255,
    )


class APIKeyDomainResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    api_key_id: UUID
    domain: str
    created_at: datetime