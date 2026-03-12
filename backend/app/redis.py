"""
Attora — Redis Connection Layer

Async Redis client for caching, rate limiting, and session storage.
"""

from collections.abc import AsyncGenerator

import redis.asyncio as aioredis

from app.config import settings

# Global Redis connection pool
_redis_pool: aioredis.Redis | None = None


async def init_redis() -> aioredis.Redis:
    """Initialize the Redis connection pool. Called on app startup."""
    global _redis_pool
    _redis_pool = aioredis.from_url(
        settings.redis_url,
        encoding="utf-8",
        decode_responses=True,
        max_connections=20,
    )
    return _redis_pool


async def close_redis() -> None:
    """Close the Redis connection pool. Called on app shutdown."""
    global _redis_pool
    if _redis_pool is not None:
        await _redis_pool.close()
        _redis_pool = None


def get_redis_pool() -> aioredis.Redis:
    """Get the active Redis connection pool."""
    if _redis_pool is None:
        raise RuntimeError("Redis pool not initialized. Call init_redis() first.")
    return _redis_pool


async def get_redis() -> AsyncGenerator[aioredis.Redis, None]:
    """FastAPI dependency that yields a Redis client."""
    yield get_redis_pool()
