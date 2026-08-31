from uuid import UUID

from fastapi import HTTPException, status

from app.models.membership import OrganizationMember
from app.models.user import User
from app.repositories.organization_member import OrganizationMemberRepository


class AuthorizationService:
    def __init__(self, membership_repository: OrganizationMemberRepository):
        self.repository = membership_repository

    async def get_membership(
            self,
            *,
            user_id: UUID,
            organization_id: UUID
    ) -> OrganizationMember:
        membership = await self.repository.get_by_organization_and_user(
            organization_id,
            user_id
        )

        if membership is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not a member of this organization",
            )

        return membership

    async def require_roles(
            self,
            *,
            user: User,
            organization_id: UUID,
            allowed_roles: set[str]
    ) -> OrganizationMember:
        membership = await self.get_membership(
            user_id=user.id,
            organization_id=organization_id
        )

        if membership.role.name not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to perform this action",
            )

        return membership
