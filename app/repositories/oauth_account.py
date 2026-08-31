from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.oauth_account import OAuthAccount

class OAuthAccountRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_provider_account(self, provider: str, provider_user_id: str) -> OAuthAccount | None:
        stmt = select(OAuthAccount).where(
            OAuthAccount.provider == provider,
            OAuthAccount.provider_user_id == provider_user_id
        )

        result = await self.db.execute(stmt)

        return result.scalar_one_or_none()

    async def get_user_by_id(self, user_id: UUID) -> list[OAuthAccount]:
        stmt = select(OAuthAccount).where(OAuthAccount.user_id == user_id)

        results = await self.db.execute(stmt)

        return list(results.scalars().all())

    async def create(
            self,
            *,
            user_id: UUID,
            provider: str,
            provider_user_id: str
    ) -> OAuthAccount:
        account = OAuthAccount(
            user_id=user_id,
            provider=provider,
            provider_user_id=provider_user_id
        )

        self.db.add(account)
        await self.db.flush()
        await self.db.refresh(account)

        return account

    async def delete(self, account: OAuthAccount) -> None:
        await self.db.delete(account)
        await self.db.flush()