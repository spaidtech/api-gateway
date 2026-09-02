from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.organization import Organization
from app.models.membership import OrganizationMember

class OrganizationRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(self, organisation_id: UUID) -> Organization | None:
        stmt = select(Organization).where(Organization.id == organisation_id)
        result = await self.db.execute(stmt)

        return result.scalar_one_or_none()

    async def get_by_user_id(self, user_id: UUID) -> list[Organization]:
        stmt = (
            select(Organization)
            .join(
                OrganizationMember,
                OrganizationMember.organization_id == Organization.id
            )
            .where(
                OrganizationMember.user_id == user_id,
                Organization.is_active.is_(True)
            )
            .order_by(Organization.created_at.desc())
        )

        result = await self.db.execute(stmt)

        return list(result.scalars().all())

    async def get_by_slug(self, slug: str) -> Organization | None:
        stmt = select(Organization).where(Organization.slug == slug)

        result = await self.db.execute(stmt)

        return result.scalar_one_or_none()

    async def create(
            self,
            *,
            name: str,
            slug: str,
            description: str | None  = None
    ) -> Organization:
        
        organization = Organization(
            name=name,
            slug=slug,
            description=description,
        )

        self.db.add(organization)
        await self.db.flush()
        await self.db.refresh(organization)

        return organization

    async def update(
            self,
            organization: Organization,
            **fields
    ) -> Organization:

        for field, value in fields.items():
            if value is not None:
                setattr(organization, field, value)


        await self.db.flush()
        await self.db.refresh(organization)

        return organization

    async def delete(
        self,
        organization: Organization,
    ) -> None:
        await self.db.delete(organization)
        await self.db.flush()
