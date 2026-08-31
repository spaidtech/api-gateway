from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.upstream import Upstream


class UpstreamRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(
        self,
        upstream_id: UUID,
    ) -> Upstream | None:
        result = await self.db.execute(
            select(Upstream).where(
                Upstream.id == upstream_id
            )
        )
        return result.scalar_one_or_none()

    async def get_by_organization_id(
        self,
        organization_id: UUID,
    ) -> list[Upstream]:
        result = await self.db.execute(
            select(Upstream).where(
                Upstream.organization_id == organization_id
            )
        )
        return list(result.scalars().all())

    async def create(
        self,
        **data,
    ) -> Upstream:
        upstream = Upstream(**data)

        self.db.add(upstream)
        await self.db.flush()
        await self.db.refresh(upstream)

        return upstream

    async def update(
        self,
        upstream: Upstream,
        **fields,
    ) -> Upstream:
        for field, value in fields.items():
            if value is not None:
                setattr(upstream, field, value)

        await self.db.flush()
        await self.db.refresh(upstream)

        return upstream

    async def delete(self, upstream: Upstream) -> None:
        await self.db.delete(upstream)
        await self.db.flush()