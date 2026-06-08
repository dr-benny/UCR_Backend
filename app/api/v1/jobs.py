from __future__ import annotations

import json
import logging
import os
import time
import uuid
from typing import Any

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, Response, UploadFile, WebSocket, WebSocketDisconnect

from app.core.config import settings
from app.schemas.job import JobListResponse, JobProgress, JobResponse
from app.services.ai_engines import get_engine, list_engines
from app.services.analysis_service import save_image, validate_mime
from app.services.job_service import cleanup_images
from app.services.job_store import JOB_CHANNEL, JOB_INDEX, JOB_KEY, JOB_TTL, get_state, set_state
from app.worker import celery_app

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


# ── Rate limiting ─────────────────────────────────────────────────────────────

async def _rate_limit(request: Request) -> None:
    ip = request.client.host if request.client else "unknown"
    key = f"ratelimit:submit:{ip}"
    redis = aioredis.from_url(settings.REDIS_URL)
    try:
        count = await redis.incr(key)
        if count == 1:
            await redis.expire(key, 60)
        if count > settings.SUBMIT_RATE_LIMIT:
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit exceeded — max {settings.SUBMIT_RATE_LIMIT} job submissions per minute",
            )
    finally:
        await redis.aclose()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _to_response(job_id: str, state: dict, submitted_at: float | None = None) -> JobResponse:
    prog = state.get("progress", {"current": 0, "total": 0, "percent": 0})
    return JobResponse(
        id=job_id,
        status=state.get("status", "unknown"),
        progress=JobProgress(**prog),
        submitted_at=submitted_at,
        engine=state.get("engine"),
        model=state.get("model"),
        results=state.get("results"),
        failed=state.get("failed"),
        error=state.get("error"),
    )


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/images", response_model=JobResponse, status_code=202, dependencies=[Depends(_rate_limit)])
async def submit_image_job(
    files: list[UploadFile] = File(..., description="One or more images to analyze"),
    concurrency: int = Form(5, ge=1, le=10),
    engine: str | None = Form(None, description="AI engine name (e.g. 'gemini')"),
    model: str | None = Form(None, description="Model override (e.g. 'gemini-2.5-pro')"),
) -> JobResponse:
    """
    Submit a batch of images for async AI analysis.

    Returns immediately with a job_id. Connect to WS /api/jobs/{id}/ws
    for real-time progress, or poll GET /api/jobs/{id} for results.
    """
    if len(files) > 200:
        raise HTTPException(status_code=400, detail="Maximum 200 images per job")

    # Validate engine/model early before touching any files
    try:
        get_engine(engine, model)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    saved: list[dict[str, Any]] = []
    for file in files:
        mime = file.content_type or "image/jpeg"
        try:
            validate_mime(mime)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        img_bytes = await file.read()
        if not img_bytes:
            raise HTTPException(status_code=400, detail=f"File '{file.filename}' is empty")
        if len(img_bytes) > settings.MAX_IMAGE_BYTES:
            mb = settings.MAX_IMAGE_BYTES // (1024 * 1024)
            raise HTTPException(status_code=400, detail=f"File '{file.filename}' exceeds {mb} MB limit")
        path = save_image(img_bytes, file.filename)
        saved.append({"path": path, "filename": file.filename})

    job_id = str(uuid.uuid4())
    total = len(saved)
    submitted_at = time.time()

    resolved_engine = engine or settings.AI_ENGINE
    resolved_model = model or settings.GEMINI_MODEL

    initial: dict[str, Any] = {
        "status": "pending",
        "progress": {"current": 0, "total": total, "percent": 0, "active_files": [], "last_completed": None},
        "engine": resolved_engine,
        "model": resolved_model,
        "_images": saved,
    }

    redis = aioredis.from_url(settings.REDIS_URL)
    try:
        await set_state(redis, job_id, initial)
        await redis.zadd(JOB_INDEX, {job_id: submitted_at})
        result = celery_app.send_task(
            "process_image_job",
            args=[job_id, {"images": saved, "concurrency": concurrency, "engine": engine, "model": model}],
        )
        initial["_task_id"] = result.id
        await set_state(redis, job_id, initial)
    finally:
        await redis.aclose()

    logger.info("Enqueued job %s (%d images, task %s)", job_id, total, result.id)
    return _to_response(job_id, initial, submitted_at)


@router.get("", response_model=JobListResponse)
async def list_jobs(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    status: str | None = Query(None, description="Filter by status: pending, processing, done, failed"),
) -> JobListResponse:
    """List all jobs, newest first. Optionally filter by status."""
    redis = aioredis.from_url(settings.REDIS_URL)
    try:
        # Remove entries older than job TTL — their Redis state is already gone
        cutoff = time.time() - JOB_TTL
        await redis.zremrangebyscore(JOB_INDEX, "-inf", cutoff)

        # Fetch all when filtering by status (can't filter in sorted set)
        fetch_end = -1 if status else offset + limit - 1
        entries = await redis.zrevrange(JOB_INDEX, 0 if status else offset, fetch_end, withscores=True)

        jobs: list[JobResponse] = []
        stale: list[str] = []
        for job_id_bytes, score in entries:
            job_id = job_id_bytes if isinstance(job_id_bytes, str) else job_id_bytes.decode()
            state = await get_state(redis, job_id)
            if not state:
                stale.append(job_id)
                continue
            if status and state.get("status") != status:
                continue
            jobs.append(_to_response(job_id, state, submitted_at=score))

        if stale:
            await redis.zrem(JOB_INDEX, *stale)

        # Total is always calculated after cleanup for accuracy (#9)
        total = len(jobs) if status else await redis.zcard(JOB_INDEX)

        if status:
            jobs = jobs[offset: offset + limit]
    finally:
        await redis.aclose()

    return JobListResponse(jobs=jobs, total=total)


@router.get("/{job_id}", response_model=JobResponse)
async def get_job(job_id: str) -> JobResponse:
    redis = aioredis.from_url(settings.REDIS_URL)
    try:
        state = await get_state(redis, job_id)
        score = await redis.zscore(JOB_INDEX, job_id)
    finally:
        await redis.aclose()

    if not state:
        raise HTTPException(status_code=404, detail="Job not found")
    return _to_response(job_id, state, submitted_at=score)


@router.delete("/{job_id}")
async def delete_job(job_id: str) -> Response:
    """Delete a job, revoke it if still running, and clean up its images."""
    redis = aioredis.from_url(settings.REDIS_URL)
    try:
        state = await get_state(redis, job_id)
        if not state:
            raise HTTPException(status_code=404, detail="Job not found")

        task_id = state.get("_task_id")
        if task_id and state.get("status") in ("pending", "processing"):
            celery_app.control.revoke(task_id, terminate=True)
            logger.info("Revoked task %s for job %s", task_id, job_id)

        cleanup_images(state.get("_images", []))

        await redis.delete(JOB_KEY.format(job_id=job_id))
        await redis.zrem(JOB_INDEX, job_id)
        logger.info("Deleted job %s", job_id)
    finally:
        await redis.aclose()

    return Response(status_code=204)


@router.post("/{job_id}/retry", response_model=JobResponse, status_code=202)
async def retry_job(
    job_id: str,
    engine: str | None = Form(None, description="Override AI engine for this retry"),
    model: str | None = Form(None, description="Override model for this retry"),
) -> JobResponse:
    """Re-queue a failed job using its original images. Optionally override engine/model."""
    if engine or model:
        try:
            get_engine(engine, model)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    redis = aioredis.from_url(settings.REDIS_URL)
    try:
        state = await get_state(redis, job_id)
        if not state:
            raise HTTPException(status_code=404, detail="Job not found")
        if state.get("status") != "failed":
            raise HTTPException(
                status_code=400,
                detail=f"Only failed jobs can be retried (current: {state.get('status')})",
            )

        images = state.get("_images", [])
        if not images:
            raise HTTPException(status_code=400, detail="No images available to retry")

        missing = [img["filename"] for img in images if not os.path.exists(img["path"])]
        if missing:
            raise HTTPException(status_code=400, detail=f"Image files no longer on disk: {missing}")

        resolved_engine = engine or state.get("engine") or settings.AI_ENGINE
        resolved_model = model or state.get("model") or settings.GEMINI_MODEL

        total = len(images)
        new_state: dict[str, Any] = {
            "status": "pending",
            "progress": {"current": 0, "total": total, "percent": 0, "active_files": [], "last_completed": None},
            "engine": resolved_engine,
            "model": resolved_model,
            "_images": images,
        }
        await set_state(redis, job_id, new_state)

        result = celery_app.send_task(
            "process_image_job",
            args=[job_id, {"images": images, "engine": engine, "model": model}],
        )
        new_state["_task_id"] = result.id
        await set_state(redis, job_id, new_state)

        submitted_at = time.time()
        await redis.zadd(JOB_INDEX, {job_id: submitted_at})
        logger.info("Retrying job %s engine=%s model=%s (task %s)", job_id, resolved_engine, resolved_model, result.id)
    finally:
        await redis.aclose()

    return _to_response(job_id, new_state, submitted_at)


@router.websocket("/{job_id}/ws")
async def job_status_ws(job_id: str, websocket: WebSocket) -> None:
    await websocket.accept()

    redis = aioredis.from_url(settings.REDIS_URL)
    state = await get_state(redis, job_id)

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
    channel = JOB_CHANNEL.format(job_id=job_id)
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
