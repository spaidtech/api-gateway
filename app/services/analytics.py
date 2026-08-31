from datetime import datetime
from uuid import UUID

from app.repositories.usage_record import UsageRecordRepository


class AnalyticsService:

    def __init__(
        self,
        usage_repository: UsageRecordRepository,
    ):
        self.usage_repository = usage_repository

    async def get_organization_summary(
        self,
        organization_id: UUID,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> dict:
        summary = await self.usage_repository.get_summary(
            organization_id=organization_id,
            start=start,
            end=end,
        )
        status_rows = await self.usage_repository.get_status_distribution(
            organization_id=organization_id,
            start=start,
            end=end,
        )
        status_distribution = {
            str(status_code): count
            for status_code, count in status_rows
        }
        return {
            "total_requests": summary.total_requests or 0,
            "average_response_time_ms": float(summary.average_response_time_ms or 0),
            "status_distribution": status_distribution,
        }

    async def get_api_summary(
        self,
        api_id: UUID,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> dict:
        summary = await self.usage_repository.get_summary(
            api_id=api_id,
            start=start,
            end=end,
        )
        status_rows = await self.usage_repository.get_status_distribution(
            api_id=api_id,
            start=start,
            end=end,
        )
        status_distribution = {
            str(status_code): count
            for status_code, count in status_rows
        }
        return {
            "total_requests": summary.total_requests or 0,
            "average_response_time_ms": float(summary.average_response_time_ms or 0),
            "status_distribution": status_distribution,
        }

    async def get_route_summary(
        self,
        route_id: UUID,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> dict:
        summary = await self.usage_repository.get_summary(
            route_id=route_id,
            start=start,
            end=end,
        )
        status_rows = await self.usage_repository.get_status_distribution(
            route_id=route_id,
            start=start,
            end=end,
        )
        status_distribution = {
            str(status_code): count
            for status_code, count in status_rows
        }
        return {
            "total_requests": summary.total_requests or 0,
            "average_response_time_ms": float(summary.average_response_time_ms or 0),
            "status_distribution": status_distribution,
        }

    async def get_api_key_summary(
        self,
        api_key_id: UUID,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> dict:
        summary = await self.usage_repository.get_summary(
            api_key_id=api_key_id,
            start=start,
            end=end,
        )
        status_rows = await self.usage_repository.get_status_distribution(
            api_key_id=api_key_id,
            start=start,
            end=end,
        )
        status_distribution = {
            str(status_code): count
            for status_code, count in status_rows
        }
        return {
            "total_requests": summary.total_requests or 0,
            "average_response_time_ms": float(summary.average_response_time_ms or 0),
            "status_distribution": status_distribution,
        }