from __future__ import annotations

import json
import logging
import uuid

import redis.asyncio as aioredis
from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect

from app.core.config import settings
from app.schemas.job import JobProgress, JobResponse, RouteJobCreate
from app.worker import celery_app

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/jobs", tags=["jobs"])

_JOB_KEY = "job:{job_id}"
_JOB_CHANNEL = "job:{job_id}"
_JOB_TTL = 86400  # 24h


async def _get_state(redis: aioredis.Redis, job_id: str) -> dict | None:
    raw = await redis.get(_JOB_KEY.format(job_id=job_id))
    return json.loads(raw) if raw else None


def _to_response(job_id: str, state: dict) -> JobResponse:
    prog = state.get("progress", {"current": 0, "total": 0, "percent": 0})
    return JobResponse(
        id=job_id,
        status=state.get("status", "unknown"),
        progress=JobProgress(**prog),
        results=state.get("results"),
        failed_points=state.get("failed_points"),
        error=state.get("error"),
    )


@router.post("/route", response_model=JobResponse, status_code=202)
async def submit_route_job(body: RouteJobCreate) -> JobResponse:
    job_id = str(uuid.uuid4())
    request_data = body.model_dump()
    total = len(body.points)

    initial = {
        "status": "pending",
        "progress": {"current": 0, "total": total, "percent": 0},
    }

    redis = aioredis.from_url(settings.REDIS_URL)
    try:
        await redis.set(_JOB_KEY.format(job_id=job_id), json.dumps(initial), ex=_JOB_TTL)
    finally:
        await redis.aclose()

    celery_app.send_task("process_route_job", args=[job_id, request_data])
    logger.info("Enqueued job %s (%d points)", job_id, total)

    return _to_response(job_id, initial)


@router.get("/{job_id}", response_model=JobResponse)
async def get_job(job_id: str) -> JobResponse:
    redis = aioredis.from_url(settings.REDIS_URL)
    try:
        state = await _get_state(redis, job_id)
    finally:
        await redis.aclose()

    if not state:
        raise HTTPException(status_code=404, detail="Job not found")

    return _to_response(job_id, state)


@router.websocket("/{job_id}/ws")
async def job_status_ws(job_id: str, websocket: WebSocket) -> None:
    await websocket.accept()

    redis = aioredis.from_url(settings.REDIS_URL)
    state = await _get_state(redis, job_id)

    if not state:
        await websocket.close(code=4004, reason="Job not found")
        await redis.aclose()
        return

    await websocket.send_json(_to_response(job_id, state).model_dump())

    if state.get("status") in ("done", "failed"):
        await websocket.close()
        await redis.aclose()
        return

    pubsub = redis.pubsub()
    channel = _JOB_CHANNEL.format(job_id=job_id)
    await pubsub.subscribe(channel)

    try:
        async for message in pubsub.listen():
            if message["type"] != "message":
                continue
            payload = json.loads(message["data"])
            await websocket.send_json({"id": job_id, **payload})
            if payload.get("status") in ("done", "failed"):
                break
    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected from job %s", job_id)
    finally:
        await pubsub.unsubscribe(channel)
        await redis.aclose()
