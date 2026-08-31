from datetime import datetime

from pydantic import BaseModel


class UsageSummary(BaseModel):
    total_requests: int
    successful_requests: int
    failed_requests: int
    average_latency_ms: float


class UsageRecordResponse(BaseModel):
    timestamp: datetime
    domain: str | None
    status_code: int
    latency_ms: int