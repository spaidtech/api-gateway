from uuid import UUID

from app.models.oauth_account import OAuthAccount
from app.repositories.oauth_account import OAuthAccountRepository


class OAuthAccountService:
    def __init__(
        self,
        repository: OAuthAccountRepository,
    ):
        self.repository = repository

    async def get_by_id(
        self,
        oauth_account_id: UUID,
    ) -> OAuthAccount | None:
        return await self.repository.get_by_id(
            oauth_account_id
        )

    async def get_by_user(
        self,
        user_id: UUID,
    ) -> list[OAuthAccount]:
        return await self.repository.get_by_user_id(
            user_id
        )

    async def get_by_provider_account(
        self,
        *,
        provider: str,
        provider_account_id: str,
    ) -> OAuthAccount | None:
        return await self.repository.get_by_provider_account(
            provider=provider,
            provider_account_id=provider_account_id,
        )

    async def create(
        self,
        *,
        user_id: UUID,
        provider: str,
        provider_account_id: str,
        **data,
    ) -> OAuthAccount:
        existing_account = (
            await self.repository.get_by_provider_account(
                provider=provider,
                provider_account_id=provider_account_id,
            )
        )

        if existing_account is not None:
            raise ValueError(
                "This OAuth account is already connected."
            )

        return await self.repository.create(
            user_id=user_id,
            provider=provider,
            provider_account_id=provider_account_id,
            **data,
        )

    async def update(
        self,
        oauth_account: OAuthAccount,
        **data,
    ) -> OAuthAccount:
        return await self.repository.update(
            oauth_account,
            **data,
        )

    async def delete(
        self,
        oauth_account: OAuthAccount,
    ) -> None:
        await self.repository.delete(oauth_account)