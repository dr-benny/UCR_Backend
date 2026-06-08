from __future__ import annotations

import json

import redis.asyncio as aioredis

JOB_KEY = "job:{job_id}"
JOB_CHANNEL = "job:{job_id}"
JOB_TTL = 86400  # 24h
JOB_INDEX = "jobs:index"  # sorted set: score = submitted_at timestamp


async def get_state(redis: aioredis.Redis, job_id: str) -> dict | None:
    raw = await redis.get(JOB_KEY.format(job_id=job_id))
    return json.loads(raw) if raw else None


async def set_state(redis: aioredis.Redis, job_id: str, state: dict) -> None:
    await redis.set(JOB_KEY.format(job_id=job_id), json.dumps(state), ex=JOB_TTL)


async def publish_event(redis: aioredis.Redis, job_id: str, payload: dict) -> None:
    await redis.publish(JOB_CHANNEL.format(job_id=job_id), json.dumps(payload))
