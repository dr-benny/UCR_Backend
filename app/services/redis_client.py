"""Process-wide shared Redis client.

The API process used to call `aioredis.from_url()` on every request and
`aclose()` immediately after — building and tearing down a connection pool
(and a TCP connection) per call. Under load that churn dominates latency.

This module hands out ONE lazily-created client, reused for the life of the
process and closed once at shutdown (see app.main.lifespan).

NOTE: the Celery worker deliberately does NOT use this — it runs each task
under its own `asyncio.run()` (a fresh event loop), so it creates a
short-lived client per task instead of sharing one bound to a dead loop.
"""
from __future__ import annotations

import redis.asyncio as aioredis

from app.core.config import settings

_client: aioredis.Redis | None = None


def get_redis() -> aioredis.Redis:
    """Return the shared client, creating it on first use."""
    global _client
    if _client is None:
        _client = aioredis.from_url(settings.REDIS_URL)
    return _client


async def close_redis() -> None:
    """Close the shared client. Safe to call when it was never created."""
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None
