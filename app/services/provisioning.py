from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.repositories.organization import OrganizationRepository
from app.repositories.organization_member import OrganizationMemberRepository
from app.repositories.role import RoleRepository
from app.repositories.user import UserRepository


class RoleNotFoundError(Exception):
    pass


class UserProvisioningService:
    def __init__(self, db: AsyncSession):
        self.user_repository = UserRepository(db)
        self.organization_repository = OrganizationRepository(db)
        self.organization_member_repository = OrganizationMemberRepository(db)
        self.role_repository = RoleRepository(db)

    @staticmethod
    def generate_slug(name: str) -> str:
        return "-".join(name.lower().strip().split())

    @staticmethod
    def default_organization_name(
        email: str,
        first_name: str | None = None,
        last_name: str | None = None,
    ) -> str:
        full_name = " ".join(
            part.strip()
            for part in (first_name, last_name)
            if part and part.strip()
        )
        return full_name or email.split("@", 1)[0]

    async def create_user_with_owner_organization(
        self,
        *,
        email: str,
        password_hash: str | None,
        organization_name: str | None = None,
        first_name: str | None = None,
        last_name: str | None = None,
    ) -> User:
        # Use default organization name if not provided
        if not organization_name:
            organization_name = self.default_organization_name(
                email, first_name, last_name
            )
        
        user = await self.user_repository.create(
            email=email,
            password_hash=password_hash,
            first_name=first_name,
            last_name=last_name,
        )

        organization_slug = self.generate_slug(organization_name)
        if await self.organization_repository.get_by_slug(organization_slug):
            organization_slug = f"{organization_slug}-{str(user.id)[:8]}"

        organization = await self.organization_repository.create(
            name=organization_name,
            slug=organization_slug,
        )

        owner_role = await self.role_repository.get_by_name("owner")
        if owner_role is None:
            raise RoleNotFoundError("Owner role does not exist")

        await self.organization_member_repository.create(
            user_id=user.id,
            organization_id=organization.id,
            role_id=owner_role.id,
        )

        return user
