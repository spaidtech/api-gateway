import uuid
from datetime import datetime
import re

from pydantic import BaseModel, ConfigDict, Field, field_validator


DOMAIN_PATTERN = re.compile(
    r"^(?:\*\.)?(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$",
    re.IGNORECASE,
)


class APIKeyDomainCreate(BaseModel):
    domain: str = Field(
        min_length=1,
        max_length=255,
    )

    @field_validator("domain")
    @classmethod
    def validate_domain(cls, value: str) -> str:
        normalized = value.lower().strip().rstrip(".")
        if not DOMAIN_PATTERN.fullmatch(normalized):
            raise ValueError("Invalid domain")
        return normalized


class APIKeyDomainResponse(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
    )

    id: uuid.UUID
    api_key_id: uuid.UUID
    domain: str
    is_active: bool
    created_at: datetime
