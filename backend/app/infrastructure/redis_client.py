"""Redis client utilities for LAB 05."""

import os
from typing import Any

from redis.asyncio import Redis

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

_client: Any = None


def get_redis() -> Redis:
    """
    Singleton async Redis.

    В тестах (``PYTEST_USE_FAKEREDIS=1``) — in-memory fakeredis, без сети.
    """
    global _client
    if _client is not None:
        return _client
    if os.getenv("PYTEST_USE_FAKEREDIS") == "1":
        import fakeredis.aioredis as fa
        _client = fa.FakeRedis(decode_responses=True)
    else:
        _client = Redis.from_url(REDIS_URL, decode_responses=True)
    return _client
