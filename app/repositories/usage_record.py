from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.usage_record import UsageRecord


class UsageRecordRepository:

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(
        self,
        **data,
    ) -> UsageRecord:
        record = UsageRecord(**data)

        self.db.add(record)

        await self.db.flush()
        await self.db.refresh(record)

        return record

    async def get_summary(
        self,
        *,
        organization_id: UUID | None = None,
        api_id: UUID | None = None,
        route_id: UUID | None = None,
        api_key_id: UUID | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
    ):
        stmt = select(
            func.count(UsageRecord.id).label("total_requests"),
            func.avg(UsageRecord.latency_ms).label("average_response_time_ms"),
        )

        if organization_id is not None:
            stmt = stmt.where(UsageRecord.organization_id == organization_id)

        if api_id is not None:
            stmt = stmt.where(UsageRecord.api_id == api_id)

        if route_id is not None:
            stmt = stmt.where(UsageRecord.route_id == route_id)

        if api_key_id is not None:
            stmt = stmt.where(UsageRecord.api_key_id == api_key_id)

        if start is not None:
            stmt = stmt.where(UsageRecord.timestamp >= start)

        if end is not None:
            stmt = stmt.where(UsageRecord.timestamp <= end)

        result = await self.db.execute(stmt)
        return result.one()

    async def get_status_distribution(
        self,
        *,
        organization_id: UUID | None = None,
        api_id: UUID | None = None,
        route_id: UUID | None = None,
        api_key_id: UUID | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
    ):
        stmt = (
            select(
                UsageRecord.status_code,
                func.count(UsageRecord.id),
            )
            .group_by(UsageRecord.status_code)
        )

        if organization_id is not None:
            stmt = stmt.where(UsageRecord.organization_id == organization_id)

        if api_id is not None:
            stmt = stmt.where(UsageRecord.api_id == api_id)

        if route_id is not None:
            stmt = stmt.where(UsageRecord.route_id == route_id)

        if api_key_id is not None:
            stmt = stmt.where(UsageRecord.api_key_id == api_key_id)

        if start is not None:
            stmt = stmt.where(UsageRecord.timestamp >= start)

        if end is not None:
            stmt = stmt.where(UsageRecord.timestamp <= end)

        result = await self.db.execute(stmt)
        return result.all()