import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class MemberCreate(BaseModel):
    user_id: uuid.UUID
    role_id: uuid.UUID


class MemberRoleUpdate(BaseModel):
    role_id: uuid.UUID


class MembershipResponse(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    user_id: uuid.UUID
    role_id: uuid.UUID
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)