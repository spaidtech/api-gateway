from uuid import UUID
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.organization import Organization
from app.models.user import User
from app.repositories.organization import OrganizationRepository
from app.repositories.role import RoleRepository
from app.repositories.organization_member import OrganizationMemberRepository

class OrganizationService:
    def __init__(
        self,
        db: AsyncSession,
        organization_repository: OrganizationRepository,
        membership_repository: OrganizationMemberRepository,
        role_repository: RoleRepository,
    ):
        self.db = db
        self.repository = organization_repository
        self.membership_repository = membership_repository
        self.role_repository = role_repository


    async def get_by_id(self, organization_id: UUID) -> Organization | None:
        return await self.repository.get_by_id(organization_id)

    async def get_by_slug(self, slug: str) -> Organization | None:
        return await self.repository.get_by_slug(slug)

    async def create(
            self,
            *,
            owner: User,
            name: str,
            slug: str,
            description: str | None = None
    ):
        slug = slug.lower().strip()

        existing_organization = await self.repository.get_by_slug(slug)

        if existing_organization:
            raise ValueError(
                "An organization with this slug already exists."
            )

        owner_role = await self.role_repository.get_by_name("owner")

        if owner_role is None:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Owner role is not configured",
            )


        organization = await self.repository.create(
            name=name,
            slug=slug,
            description=description
        )

        await self.membership_repository.create(
            organization_id=organization.id,
            user_id=owner.id,
            role_id=owner_role.id
        )

        await self.db.commit()

        return organization

    async def update(
        self,
        organization: Organization,
        *,
        name: str | None = None,
        slug: str | None = None,
        description: str | None = None,
    ) -> Organization:
        if slug is not None:
            slug = slug.lower().strip()

            existing_organization = await self.repository.get_by_slug(
                slug
            )

            if (
                existing_organization
                and existing_organization.id != organization.id
            ):
                raise ValueError(
                    "An organization with this slug already exists."
                )

        updated_org = await self.repository.update(
            organization,
            name=name,
            slug=slug,
            description=description,
        )
        
        # Commit the transaction
        await self.db.commit()
        
        return updated_org

    # async def delete(
    #     self,
    #     organization: Organization,
    # ) -> None:
    #     await self.repository.delete(organization)

    async def deactivate(
            self,
            organization: Organization
    ) -> Organization:
        organization.is_active = False

        await self.db.commit()
        await self.db.refresh(organization)

        return organization