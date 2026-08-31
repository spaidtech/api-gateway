import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class HealthCheckResponse(BaseModel):
    id: uuid.UUID
    api_id: uuid.UUID
    upstream_id: uuid.UUID
    status: str
    response_time_ms: int | None
    status_code: int | None
    checked_at: datetime

    model_config = ConfigDict(from_attributes=True)