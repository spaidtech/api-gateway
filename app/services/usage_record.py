import logging
from uuid import UUID

from app.core.database import AsyncSessionLocal
from app.models.usage_record import UsageRecord
from app.repositories.usage_record import UsageRecordRepository

logger = logging.getLogger(__name__)


class UsageRecordService:
    def __init__(self, repository: UsageRecordRepository):
        self.repository = repository

    async def record(
        self,
        *,
        organization_id: UUID,
        api_id: UUID,
        route_id: UUID,
        api_key_id: UUID,
        status_code: int,
        latency_ms: int,
        domain: str | None = None,
    ) -> UsageRecord:
        record = await self.repository.create(
            organization_id=organization_id,
            api_id=api_id,
            route_id=route_id,
            api_key_id=api_key_id,
            status_code=status_code,
            latency_ms=latency_ms,
            domain=domain,
        )
        await self.repository.db.commit()
        return record


async def record_usage_in_background(
    *,
    organization_id: UUID,
    api_id: UUID,
    route_id: UUID,
    api_key_id: UUID,
    status_code: int,
    latency_ms: int,
    domain: str | None = None,
) -> None:
    """
    Safely records gateway request metrics in a background task using
    an isolated database session so it does not rely on request-scoped sessions.
    """
    try:
        async with AsyncSessionLocal() as session:
            repository = UsageRecordRepository(session)
            service = UsageRecordService(repository)
            await service.record(
                organization_id=organization_id,
                api_id=api_id,
                route_id=route_id,
                api_key_id=api_key_id,
                status_code=status_code,
                latency_ms=latency_ms,
                domain=domain,
            )
    except Exception as exc:
        logger.error("Failed to record gateway usage in background: %s", exc, exc_info=True)