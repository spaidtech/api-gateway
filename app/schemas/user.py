import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr


class UserUpdate(BaseModel):
    first_name: str | None = None
    last_name: str | None = None


class UserResponse(BaseModel):
    id: uuid.UUID
    email: EmailStr
    first_name: str | None
    last_name: str | None
    is_active: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)