from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.health_check import HealthCheck


class HealthCheckRepository:

    def __init__(
        self,
        db: AsyncSession,
    ):
        self.db = db

    async def create(
        self,
        **data,
    ) -> HealthCheck:
        health_check = HealthCheck(**data)

        self.db.add(health_check)

        await self.db.flush()
        await self.db.refresh(health_check)

        return health_check

    async def get_latest_by_upstream(
        self,
        upstream_id: UUID,
    ) -> HealthCheck | None:
        stmt = (
            select(HealthCheck)
            .where(
                HealthCheck.upstream_id
                == upstream_id
            )
            .order_by(
                HealthCheck.checked_at.desc()
            )
            .limit(1)
        )

        result = await self.db.execute(stmt)

        return result.scalar_one_or_none()

    async def get_history(
        self,
        upstream_id: UUID,
        limit: int = 50,
    ) -> list[HealthCheck]:
        stmt = (
            select(HealthCheck)
            .where(
                HealthCheck.upstream_id
                == upstream_id
            )
            .order_by(
                HealthCheck.checked_at.desc()
            )
            .limit(limit)
        )

        result = await self.db.execute(stmt)

        return list(
            result.scalars().all()
        )