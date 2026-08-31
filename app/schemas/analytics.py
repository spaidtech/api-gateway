from pydantic import BaseModel


class AnalyticsSummaryResponse(BaseModel):
    total_requests: int
    average_response_time_ms: float
    status_distribution: dict[str, int]