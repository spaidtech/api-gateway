import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class SubscriptionCreate(BaseModel):
    plan_id: uuid.UUID


class SubscriptionResponse(BaseModel):
    id: uuid.UUID
    plan_id: uuid.UUID
    consumer_organization_id: uuid.UUID
    status: str
    starts_at: datetime
    ends_at: datetime | None

    model_config = ConfigDict(from_attributes=True)