from uuid import UUID
from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.membership import OrganizationMember
from app.repositories.organization_member import (
    OrganizationMemberRepository,
)
from app.repositories.role import RoleRepository
from app.repositories.user import UserRepository


class OrganizationMemberService:
    def __init__(
        self,
        db: AsyncSession,
        repository: OrganizationMemberRepository,
        role_repository: RoleRepository,
        user_repository: UserRepository,
    ):
        self.db = db
        self.repository = repository
        self.role_repository = role_repository
        self.user_repository = user_repository

    async def get_member(
        self,
        organization_id: UUID,
        user_id: UUID,
    ) -> OrganizationMember | None:
        return await self.repository.get_by_organization_and_user(
            organization_id,
            user_id,
        )

    async def get_by_organization(
        self,
        organization_id: UUID,
    ) -> list[OrganizationMember]:
        return await self.repository.get_by_organization_id(
            organization_id
        )

    async def get_by_user(
        self,
        user_id: UUID,
    ) -> list[OrganizationMember]:
        return await self.repository.get_by_user_id(user_id)

    async def add_member(
        self,
        *,
        organization_id: UUID,
        user_id: UUID,
        role_id: UUID,
    ) -> OrganizationMember:
        existing_member = await self.repository.get_by_organization_and_user(
            organization_id,
            user_id,
        )

        if existing_member:
            raise ValueError(
                "User is already a member of this organization."
            )

        user = await self.user_repository.get_by_id(user_id)

        if user is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found",
            )

        role = await self.role_repository.get_by_id(role_id)

        if not role:
            raise ValueError("Role does not exist.")

        try:
            new_member = await self.repository.create(
                organization_id=organization_id,
                user_id=user_id,
                role_id=role_id,
            )
            await self.db.commit()
            await self.db.refresh(new_member)
        except IntegrityError as exc:
            await self.db.rollback()
            raise ValueError(
                "User is already a member of this organization."
            ) from exc
        
        return new_member

    async def update_role(
            self,
            *,
            membership: OrganizationMember,
            role_id: UUID
    ) -> OrganizationMember:
        role = await self.role_repository.get_by_id(role_id)

        if role is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Role not found",
            )

        membership.role_id = role_id

        await self.db.commit()
        await self.db.refresh(membership)

        return membership


    async def remove_member(
        self,
        membership: OrganizationMember,
    ) -> None:
        await self.repository.delete(membership)
        await self.db.commit()
