from app.models.oauth_account import OAuthAccount
from app.repositories.oauth_account import OAuthAccountRepository

class OAuthService:
    def __init__(self, repository: OAuthAccountRepository):
        self.repository = repository

    async def get_by_provider_account(
            self,
            *,
            provider: str,
            provider_account_id: str
    ) -> OAuthAccount | None:
        return await self.repository.get_by_provider_account(
            provider=provider,
            provider_user_id=provider_account_id
        )

    async def link_account(
            self,
            **data
    ) -> OAuthAccount:
        existing_account = (
            await self.get_by_provider_account(
                provider=data["provider"],
                provider_account_id=data["provider_account_id"]
            )
        )

        if existing_account is not None:
            return existing_account

        return await self.repository.create(**data)