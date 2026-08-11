"""Per-key daily AI-call quota, enforced in Redis.

Usage is tracked per UTC calendar day (`usage:{key_id}:{YYYY-MM-DD}`) so it
resets automatically at 00:00 UTC without a separate reset job — the counter
just expires and the next day starts a fresh key.
"""
from __future__ import annotations

import time
from typing import Any

from fastapi import HTTPException
from redis.asyncio import Redis

from app.core.config import settings

_USAGE_KEY = "usage:{key_id}:{day}"
_USAGE_TTL = 90000  # 25h — outlives the day it counts, covers clock skew


def _today() -> str:
    return time.strftime("%Y-%m-%d", time.gmtime())


async def check_and_consume(redis: Redis, key: dict[str, Any], calls: int) -> None:
    """Raise 429 if `calls` more AI calls would exceed this key's daily budget,
    otherwise record them as used."""
    limit = key.get("daily_limit") or settings.DEFAULT_DAILY_AI_CALL_LIMIT
    usage_key = _USAGE_KEY.format(key_id=key["id"], day=_today())

    current = int(await redis.get(usage_key) or 0)
    if current + calls > limit:
        raise HTTPException(
            status_code=429,
            detail=(
                f"Daily AI-call quota exceeded for this key "
                f"({current}/{limit} used, {calls} requested); resets at 00:00 UTC"
            ),
        )

    new_total = await redis.incrby(usage_key, calls)
    if new_total == calls:  # first increment of the day — start its expiry
        await redis.expire(usage_key, _USAGE_TTL)


async def get_usage(redis: Redis, key: dict[str, Any]) -> dict[str, int]:
    """Today's usage for a key, without consuming any of it."""
    limit = key.get("daily_limit") or settings.DEFAULT_DAILY_AI_CALL_LIMIT
    usage_key = _USAGE_KEY.format(key_id=key["id"], day=_today())
    used = int(await redis.get(usage_key) or 0)
    return {"daily_limit": limit, "used_today": used, "remaining_today": max(limit - used, 0)}
