from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, create_refresh_token
from app.models.oauth_account import OAuthAccount
from app.models.user import User
from app.repositories.oauth_account import OAuthAccountRepository
from app.repositories.user import UserRepository
from app.schemas.auth import TokenResponse
from app.services.provisioning import UserProvisioningService


class OAuthService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.user_repository = UserRepository(db)
        self.oauth_repository = OAuthAccountRepository(db)
        self.provisioning_service = UserProvisioningService(db)

    @staticmethod
    def _create_tokens(user: User) -> TokenResponse:
        access_token = create_access_token(subject=str(user.id))
        refresh_token = create_refresh_token(subject=str(user.id))

        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token
        )

    async def authenticate(
            self,
            *,
            provider: str,
            provider_user_id: str,
            email: str,
            first_name: str | None = None,
            last_name: str | None = None
    ) -> TokenResponse:

        oauth_account = await self.oauth_repository.get_by_provider_account(
            provider=provider,
            provider_user_id=provider_user_id
        )

        if oauth_account is not None:
            user = await self.user_repository.get_by_id(oauth_account.user_id)

            if user is None or not user.is_active:
                raise ValueError(
                    "OAuth account is associated with an unavailable user"
                )
            return self._create_tokens(user)

        user = await self.user_repository.get_by_email(email)

        try:
            if user is None:
                organization_name = UserProvisioningService.default_organization_name(
                    email,
                    first_name,
                    last_name,
                )
                user = await self.provisioning_service.create_user_with_owner_organization(
                    email=email,
                    password_hash=None,
                    organization_name=organization_name,
                    first_name=first_name,
                    last_name=last_name,
                )
            elif not user.is_active:
                raise ValueError("User account is inactive")

            await self.oauth_repository.create(
                user_id=user.id,
                provider=provider,
                provider_user_id=provider_user_id
            )

            await self.db.commit()

            return self._create_tokens(user)

        except Exception:
            await self.db.rollback()
            raise