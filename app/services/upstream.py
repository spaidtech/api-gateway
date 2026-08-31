from uuid import UUID
from sqlalchemy.exc import IntegrityError

from app.models.upstream import Upstream
from app.repositories.upstream import UpstreamRepository


class UpstreamService:
    def __init__(self, repository: UpstreamRepository):
        self.repository = repository

    async def get_by_id(
        self,
        upstream_id: UUID,
    ) -> Upstream | None:
        return await self.repository.get_by_id(upstream_id)

    async def get_by_organization(
        self,
        organization_id: UUID,
    ) -> list[Upstream]:
        return await self.repository.get_by_organization_id(
            organization_id
        )

    async def create(
        self,
        **data,
    ) -> Upstream:
        upstream = await self.repository.create(**data)
        await self.repository.db.commit()
        await self.repository.db.refresh(upstream)
        return upstream

    async def update(
        self,
        upstream: Upstream,
        **data,
    ) -> Upstream:
        upstream = await self.repository.update(
            upstream,
            **data,
        )
        await self.repository.db.commit()
        await self.repository.db.refresh(upstream)
        return upstream

    async def delete(
        self,
        upstream: Upstream,
    ) -> None:
        try:
            await self.repository.delete(upstream)
            await self.repository.db.commit()
        except IntegrityError as exc:
            await self.repository.db.rollback()
            raise ValueError(
                "Cannot delete upstream because it is referenced by existing routes or resources."
            ) from exc
