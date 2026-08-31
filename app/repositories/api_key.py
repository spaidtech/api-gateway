from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.api_key import APIKey


class APIKeyRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(
        self,
        api_key_id: UUID,
    ) -> APIKey | None:
        result = await self.db.execute(
            select(APIKey).where(APIKey.id == api_key_id)
        )
        return result.scalar_one_or_none()

    async def get_by_key_hash(
        self,
        key_hash: str,
    ) -> APIKey | None:
        result = await self.db.execute(
            select(APIKey).where(
                APIKey.key_hash == key_hash
            )
        )
        return result.scalar_one_or_none()

    async def get_by_organization_id(
        self,
        organization_id: UUID,
    ) -> list[APIKey]:
        result = await self.db.execute(
            select(APIKey).where(
                APIKey.organization_id == organization_id
            )
        )
        return list(result.scalars().all())

    async def get_by_subscription_id(
        self,
        subscription_id: UUID,
    ) -> list[APIKey]:
        result = await self.db.execute(
            select(APIKey).where(
                APIKey.subscription_id == subscription_id
            )
        )
        return list(result.scalars().all())

    async def create(
        self,
        **data,
    ) -> APIKey:
        api_key = APIKey(**data)

        self.db.add(api_key)
        await self.db.flush()
        await self.db.refresh(api_key)

        return api_key

    async def update(
        self,
        api_key: APIKey,
        **fields,
    ) -> APIKey:
        for field, value in fields.items():
            setattr(api_key, field, value)

        await self.db.flush()
        await self.db.refresh(api_key)

        return api_key

    async def delete(self, api_key: APIKey) -> None:
        await self.db.delete(api_key)
        await self.db.flush()
