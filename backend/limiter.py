"""Rate limiting utilities using a token bucket strategy."""
from __future__ import annotations

import asyncio
import time
from typing import Protocol

try:  # pragma: no cover - prefer real redis client
    import redis.asyncio as redis
except ImportError:  # pragma: no cover - offline stub
    class _DummyRedis:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def eval(self, *args, **kwargs) -> int:
            return 1

    class redis:  # type: ignore
        @staticmethod
        def from_url(url: str):
            return _DummyRedis()


class LimiterBackend(Protocol):
    async def allow(self, key: str, rate: int, cost: int = 1, window_seconds: int = 60) -> bool:
        ...


class InMemoryTokenBucket:
    """Simple in-memory token bucket for low traffic deployments."""

    def __init__(self) -> None:
        self._buckets: dict[str, tuple[float, float]] = {}
        self._lock = asyncio.Lock()

    async def allow(self, key: str, rate: int, cost: int = 1, window_seconds: int = 60) -> bool:
        now = time.monotonic()
        capacity = float(rate)
        refill_rate = capacity / window_seconds
        async with self._lock:
            tokens, last = self._buckets.get(key, (capacity, now))
            tokens = min(capacity, tokens + (now - last) * refill_rate)
            allowed = tokens >= cost
            if allowed:
                tokens -= cost
            self._buckets[key] = (tokens, now)
        return allowed


REDIS_SCRIPT = """
local bucket_key = KEYS[1]
local now = tonumber(ARGV[1])
local rate = tonumber(ARGV[2])
local window = tonumber(ARGV[3])
local cost = tonumber(ARGV[4])
local capacity = rate
local refill = capacity / window
local data = redis.call('HMGET', bucket_key, 'tokens', 'timestamp')
local tokens = tonumber(data[1])
local last = tonumber(data[2])
if tokens == nil then
  tokens = capacity
  last = now
else
  tokens = math.min(capacity, tokens + (now - last) * refill)
end
local allowed = 0
if tokens >= cost then
  allowed = 1
  tokens = tokens - cost
end
redis.call('HMSET', bucket_key, 'tokens', tokens, 'timestamp', now)
redis.call('EXPIRE', bucket_key, window)
return allowed
"""


class RedisTokenBucket:
    """Redis backed token bucket for multi-process deployments."""

    def __init__(self, client: redis.Redis) -> None:
        self._client = client

    async def allow(self, key: str, rate: int, cost: int = 1, window_seconds: int = 60) -> bool:
        now = time.monotonic()
        result = await self._client.eval(REDIS_SCRIPT, 1, key, now, rate, window_seconds, cost)
        return bool(result)


class RateLimiter:
    """High level limiter orchestrating user/tenant checks."""

    def __init__(self, backend: LimiterBackend) -> None:
        self._backend = backend

    async def hit(self, scope: str, rate: int) -> bool:
        return await self._backend.allow(scope, rate)


async def create_limiter(backend: str, redis_url: str | None) -> RateLimiter:
    """Factory returning a rate limiter instance."""

    if backend == "redis" and redis_url:
        client = redis.from_url(redis_url)
        return RateLimiter(RedisTokenBucket(client))
    return RateLimiter(InMemoryTokenBucket())
