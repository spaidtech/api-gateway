import time
from dataclasses import dataclass
from uuid import UUID

from redis.asyncio import Redis

@dataclass
class RateLimitResult:
    allowed: bool
    limit: int
    remaining: int
    reset_at: int

class RateLimitService:

    WINDOW_SECONDS = 60

    def __init__(self, redis: Redis):
        self.redis = redis

    async def check(
        self,
        *,
        api_key_id: UUID,
        limit: int
    ) -> RateLimitResult:
        now = int(time.time())
        window = now // self.WINDOW_SECONDS
        reset_at = (window + 1) * self.WINDOW_SECONDS

        key = f"rate_limit:{api_key_id}:{window}"

        current = await self.redis.incr(key)

        if current == 1:
            await self.redis.expire(
                key,
                self.WINDOW_SECONDS
            )
        else:
            # Fallback in case key lost TTL
            ttl = await self.redis.ttl(key)
            if ttl == -1:
                await self.redis.expire(key, self.WINDOW_SECONDS)

        allowed = current <= limit

        remaining = max(limit - current, 0)

        return RateLimitResult(
            allowed=allowed,
            limit=limit,
            remaining=remaining,
            reset_at=reset_at
        )