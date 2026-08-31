from collections.abc import Callable
from uuid import UUID

from fastapi import Depends, Path

from app.core.database import get_db
from app.dependencies.auth import get_current_user
from app.models.membership import OrganizationMember
from app.models.user import User
from app.repositories.organization_member import OrganizationMemberRepository
from app.services.authorization import AuthorizationService

def get_authorization_service(
    db=Depends(get_db)
) -> AuthorizationService:
    membership_repository = OrganizationMemberRepository(db)

    return AuthorizationService(
        membership_repository=membership_repository
    )

def require_organization_roles(*roles: str) -> Callable:
    allowed_roles = set(roles)

    async def dependency(
        organization_id: UUID = Path(...),
        current_user: User = Depends(get_current_user),
        authorization_service: AuthorizationService = Depends(get_authorization_service)
    ) -> OrganizationMember:
        return await authorization_service.require_roles(
            user=current_user,
            organization_id=organization_id,
            allowed_roles=allowed_roles
        )

    return dependency