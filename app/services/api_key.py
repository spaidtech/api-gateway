import hashlib
import secrets
from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError

from app.models.api_key import APIKey
from app.repositories.api_key import APIKeyRepository
from app.repositories.api_plan import APIPlanRepository
from app.repositories.subscription import SubscriptionRepository


class APIKeyService:
    def __init__(
        self,
        repository: APIKeyRepository,
        subscription_repository: SubscriptionRepository | None = None,
        api_plan_repository: APIPlanRepository | None = None,
    ):
        self.repository = repository
        self.subscription_repository = subscription_repository
        self.api_plan_repository = api_plan_repository

    async def get_by_id(self, api_key_id: UUID) -> APIKey | None:
        return await self.repository.get_by_id(api_key_id)

    async def get_by_organization(self, organization_id: UUID) -> list[APIKey]:
        return await self.repository.get_by_organization_id(organization_id)

    async def get_by_subscription(self, subscription_id: UUID):
        return await self.repository.get_by_subscription_id(subscription_id)

    async def get_by_key_hash(self, key_hash: str):
        return await self.repository.get_by_key_hash(key_hash)

    async def validate(self, api_key: APIKey) -> APIKey:
        if api_key.status != "active":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="API key is not active",
            )

        if api_key.expires_at is not None:
            now = datetime.now(timezone.utc)
            expires_at = api_key.expires_at
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)

            if expires_at <= now:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="API key has expired",
                )

        return api_key

    def generate_secret_key(self) -> str:
        return f"ak_live_{secrets.token_urlsafe(32)}"

    def hash_key(self, raw_key: str) -> str:
        return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()

    async def _validate_subscription_for_key(
        self,
        subscription_id: UUID,
        organization_id: UUID,
    ) -> None:
        sub_repo = self.subscription_repository or SubscriptionRepository(self.repository.db)
        subscription = await sub_repo.get_by_id(subscription_id)
        if subscription is None:
            raise ValueError("Subscription not found.")
        if subscription.consumer_organization_id != organization_id:
            raise ValueError("Subscription does not belong to this organization.")
        if subscription.status != "active":
            raise ValueError(f"Cannot associate API key: Subscription is not active (status: '{subscription.status}'). Payment required.")

        now = datetime.now(timezone.utc)
        if subscription.ends_at is not None:
            ends_at = subscription.ends_at
            if ends_at.tzinfo is None:
                ends_at = ends_at.replace(tzinfo=timezone.utc)
            if ends_at <= now:
                raise ValueError("Cannot associate API key: Subscription has expired. Please renew first.")

        plan_repo = self.api_plan_repository or APIPlanRepository(self.repository.db)
        plan = await plan_repo.get_by_id(subscription.plan_id)
        if plan is None or not plan.is_active:
            raise ValueError("Cannot associate API key: Associated API plan is not active.")

    async def create(
        self,
        *,
        organization_id: UUID,
        name: str,
        subscription_id: UUID | None = None,
        expires_at: datetime | None = None,
    ) -> tuple[APIKey, str]:
        if subscription_id is not None:
            await self._validate_subscription_for_key(
                subscription_id=subscription_id,
                organization_id=organization_id,
            )

        raw_key = self.generate_secret_key()
        key_prefix = raw_key[:12]

        try:
            api_key = await self.repository.create(
                organization_id=organization_id,
                subscription_id=subscription_id,
                name=name,
                key_prefix=key_prefix,
                key_hash=self.hash_key(raw_key),
                expires_at=expires_at,
            )
            await self.repository.db.commit()
            await self.repository.db.refresh(api_key)
            return api_key, raw_key
        except IntegrityError as exc:
            await self.repository.db.rollback()
            raise ValueError(
                "Invalid subscription or organization reference."
            ) from exc

    async def regenerate(self, api_key: APIKey) -> tuple[APIKey, str]:
        if api_key.subscription_id is not None:
            await self._validate_subscription_for_key(
                subscription_id=api_key.subscription_id,
                organization_id=api_key.organization_id,
            )

        raw_key = self.generate_secret_key()
        key_prefix = raw_key[:12]

        updated_api_key = await self.repository.update(
            api_key,
            key_hash=self.hash_key(raw_key),
            key_prefix=key_prefix,
            status="active",
            revoked_at=None,
        )
        await self.repository.db.commit()
        await self.repository.db.refresh(updated_api_key)

        return updated_api_key, raw_key

    async def revoke(self, api_key: APIKey) -> APIKey:
        api_key = await self.repository.update(
            api_key,
            status="revoked",
            revoked_at=datetime.now(timezone.utc),
        )
        await self.repository.db.commit()
        await self.repository.db.refresh(api_key)
        return api_key

    async def mark_used(self, api_key: APIKey) -> APIKey:
        api_key = await self.repository.update(
            api_key=api_key,
            last_used_at=datetime.now(timezone.utc),
        )
        await self.repository.db.commit()
        return api_key
