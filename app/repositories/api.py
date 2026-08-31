from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.api import API


class APIRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(
        self,
        api_id: UUID,
    ) -> API | None:
        result = await self.db.execute(
            select(API).where(API.id == api_id)
        )
        return result.scalar_one_or_none()

    async def get_by_slug(
        self,
        organization_id: UUID,
        slug: str,
    ) -> API | None:
        result = await self.db.execute(
            select(API).where(
                API.organization_id == organization_id,
                API.slug == slug,
            )
        )
        return result.scalar_one_or_none()

    async def get_by_organization_id(
        self,
        organization_id: UUID,
    ) -> list[API]:
        result = await self.db.execute(
            select(API).where(
                API.organization_id == organization_id
            )
        )
        return list(result.scalars().all())

    async def create(
        self,
        *,
        organization_id: UUID,
        name: str,
        slug: str,
        version: str,
        description: str | None = None,
        documentation: str | None = None,
        visibility=None,
        status=None,
        base_path: str | None = None,
    ) -> API:
        api = API(
            organization_id=organization_id,
            name=name,
            slug=slug,
            version=version,
            description=description,
            documentation=documentation,
            visibility=visibility,
            status=status,
            base_path=base_path,
        )

        self.db.add(api)
        await self.db.flush()
        await self.db.refresh(api)

        return api

    async def update(
        self,
        api: API,
        **fields,
    ) -> API:
        for field, value in fields.items():
            if value is not None:
                setattr(api, field, value)

        await self.db.flush()
        await self.db.refresh(api)

        return api

    async def delete(self, api: API) -> None:
        await self.db.delete(api)
        await self.db.flush()