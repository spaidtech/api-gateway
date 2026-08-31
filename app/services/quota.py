from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

from redis.asyncio import Redis

@dataclass
class QuotaResult:
    allowed: bool
    quota: int
    used: int
    remaining: int


class QuotaService:
    def __init__(self, redis: Redis):
        self.redis = redis

    def _get_key(self, subscription_id: UUID) -> str:
        now = datetime.now(timezone.utc)

        return (
            f"quota:{subscription_id}:{now.year}:{now.month}"
        )

    async def check(
            self,
            *,
            subscription_id: UUID,
            monthly_quota: int
    ) -> QuotaResult:
        key = self._get_key(subscription_id)

        current = await self.redis.get(key)
        used = int(current or 0)

        remaining = max(monthly_quota - used, 0)

        return QuotaResult(
            allowed = used < monthly_quota,
            quota=monthly_quota,
            used=used,
            remaining=remaining
        )

    async def consume(
        self,
        *,
        subscription_id: UUID,
        monthly_quota: int
    ) -> QuotaResult:
        key = self._get_key(subscription_id)

        used = await self.redis.incr(key)

        now = datetime.now(timezone.utc)

        if now.month == 12:
            next_month = datetime(
                now.year + 1,
                1,
                1,
                tzinfo=timezone.utc
            )
        else:
            next_month = datetime(
                now.year,
                now.month + 1,
                1,
                tzinfo=timezone.utc
            )

        ttl = int(
            (next_month - now).total_seconds()
        )

        if used == 1:
            await self.redis.expire(key, ttl)

        remaining = max(monthly_quota - used, 0)

        return QuotaResult(
            allowed=used <= monthly_quota,
            quota=monthly_quota,
            used=used,
            remaining=remaining,
        )

