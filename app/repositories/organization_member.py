from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.membership import OrganizationMember


class OrganizationMemberRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(
        self,
        membership_id: UUID,
    ) -> OrganizationMember | None:
        result = await self.db.execute(
            select(OrganizationMember).where(
                OrganizationMember.id == membership_id
            )
        )
        return result.scalar_one_or_none()

    async def get_by_organization_and_user(
        self,
        organization_id: UUID,
        user_id: UUID,
    ) -> OrganizationMember | None:
        result = await self.db.execute(
            select(OrganizationMember)
            .options(
                selectinload(OrganizationMember.role)
            )
            .where(
                OrganizationMember.organization_id == organization_id,
                OrganizationMember.user_id == user_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_by_user_id(
        self,
        user_id: UUID,
    ) -> list[OrganizationMember]:
        result = await self.db.execute(
            select(OrganizationMember).where(
                OrganizationMember.user_id == user_id
            )
        )
        return list(result.scalars().all())

    async def get_by_organization_id(
        self,
        organization_id: UUID,
    ) -> list[OrganizationMember]:
        result = await self.db.execute(
            select(OrganizationMember).where(
                OrganizationMember.organization_id == organization_id
            )
        )
        return list(result.scalars().all())

    async def create(
        self,
        *,
        organization_id: UUID,
        user_id: UUID,
        role_id: UUID,
    ) -> OrganizationMember:
        membership = OrganizationMember(
            organization_id=organization_id,
            user_id=user_id,
            role_id=role_id,
        )

        self.db.add(membership)
        await self.db.flush()
        await self.db.refresh(membership)

        return membership

    async def delete(
        self,
        membership: OrganizationMember,
    ) -> None:
        # Proper way to delete in SQLAlchemy async
        await self.db.delete(membership)
        await self.db.flush()