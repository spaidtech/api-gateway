import asyncio
from redis.asyncio import ConnectionPool, Redis

from app.core.config import settings

_pool: ConnectionPool | None = None
_pool_loop: asyncio.AbstractEventLoop | None = None


def get_redis_pool() -> ConnectionPool:
    global _pool, _pool_loop
    try:
        current_loop = asyncio.get_running_loop()
    except RuntimeError:
        current_loop = None

    if _pool is None or (_pool_loop is not None and _pool_loop != current_loop):
        _pool = ConnectionPool.from_url(
            url=settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
            max_connections=50,
        )
        _pool_loop = current_loop
    return _pool


async def get_redis() -> Redis:
    pool = get_redis_pool()
    return Redis(connection_pool=pool)


async def close_redis() -> None:
    global _pool, _pool_loop
    if _pool is not None:
        try:
            await _pool.disconnect()
        except Exception:
            pass
        _pool = None
        _pool_loop = None