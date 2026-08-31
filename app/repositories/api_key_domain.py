from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.api_key_domain import APIKeyDomain


class APIKeyDomainRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(
        self,
        domain_id: UUID,
    ) -> APIKeyDomain | None:
        result = await self.db.execute(
            select(APIKeyDomain).where(
                APIKeyDomain.id == domain_id
            )
        )
        return result.scalar_one_or_none()

    async def get_by_api_key_id(
        self,
        api_key_id: UUID,
    ) -> list[APIKeyDomain]:
        result = await self.db.execute(
            select(APIKeyDomain).where(
                APIKeyDomain.api_key_id == api_key_id
            )
        )
        return list(result.scalars().all())

    async def get_by_domain(
        self,
        api_key_id: UUID,
        domain: str,
    ) -> APIKeyDomain | None:
        result = await self.db.execute(
            select(APIKeyDomain).where(
                APIKeyDomain.api_key_id == api_key_id,
                APIKeyDomain.domain == domain,
            )
        )
        return result.scalar_one_or_none()

    async def create(
        self,
        *,
        api_key_id: UUID,
        domain: str,
    ) -> APIKeyDomain:
        domain_record = APIKeyDomain(
            api_key_id=api_key_id,
            domain=domain,
        )

        self.db.add(domain_record)
        await self.db.flush()
        await self.db.refresh(domain_record)

        return domain_record

    async def delete(
        self,
        domain_record: APIKeyDomain,
    ) -> None:
        await self.db.delete(domain_record)
        await self.db.flush()