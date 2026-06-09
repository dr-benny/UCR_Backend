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
from app.services.ai_engines import get_engine
from app.services.analysis_service import read_capped, save_image, validate_mime
from app.services.job_service import cleanup_images
from app.services.job_store import JOB_CHANNEL, JOB_INDEX, JOB_KEY, JOB_TTL, get_state, set_state
from app.worker import celery_app

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


# ── Rate limiting ─────────────────────────────────────────────────────────────

def _client_ip(request: Request) -> str:
    """Resolve the real client IP, honoring X-Forwarded-For only behind a trusted proxy."""
    if settings.TRUST_PROXY:
        xff = request.headers.get("x-forwarded-for")
        if xff:
            # Left-most entry is the original client (proxy appends on the right).
            return xff.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


async def _rate_limit(request: Request) -> None:
    ip = _client_ip(request)
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
        samples=state.get("samples"),
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
    samples: int | None = Form(None, ge=1, description="Self-consistency samples per image (overrides default)"),
) -> JobResponse:
    """
    Submit a batch of images for async AI analysis.

    Returns immediately with a job_id. Connect to WS /api/jobs/{id}/ws
    for real-time progress, or poll GET /api/jobs/{id} for results.
    """
    if len(files) > 200:
        raise HTTPException(status_code=400, detail="Maximum 200 images per job")

    if samples is not None and samples > settings.MAX_ANALYSIS_SAMPLES:
        raise HTTPException(
            status_code=400, detail=f"samples exceeds max of {settings.MAX_ANALYSIS_SAMPLES}"
        )

    # Cost guard — reject before doing any work if the estimated AI call count
    # (images × samples) blows the budget (C1).
    effective_samples = samples or settings.ANALYSIS_SAMPLES
    estimated_calls = len(files) * effective_samples
    if estimated_calls > settings.MAX_JOB_API_CALLS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Job would make ~{estimated_calls} AI calls "
                f"({len(files)} images × {effective_samples} samples), "
                f"exceeding the limit of {settings.MAX_JOB_API_CALLS}"
            ),
        )

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
        try:
            img_bytes = await read_capped(file, settings.MAX_IMAGE_BYTES)
        except ValueError:
            mb = settings.MAX_IMAGE_BYTES // (1024 * 1024)
            raise HTTPException(status_code=400, detail=f"File '{file.filename}' exceeds {mb} MB limit")
        if not img_bytes:
            raise HTTPException(status_code=400, detail=f"File '{file.filename}' is empty")
        path = save_image(img_bytes, file.filename)
        saved.append({"path": path, "filename": file.filename, "mime": mime})

    job_id = str(uuid.uuid4())
    total = len(saved)
    submitted_at = time.time()

    resolved_engine = engine or settings.AI_ENGINE

    initial: dict[str, Any] = {
        "status": "pending",
        "progress": {"current": 0, "total": total, "percent": 0, "active_files": [], "last_completed": None},
        "engine": resolved_engine,
        "model": model,  # None means each engine uses its own default
        "samples": samples,
        "concurrency": concurrency,  # persisted so retry reuses the original setting
        "_images": saved,
        "_heartbeat": submitted_at,  # reaper marks the job failed if no worker refreshes this
    }

    redis = aioredis.from_url(settings.REDIS_URL)
    try:
        await set_state(redis, job_id, initial)
        await redis.zadd(JOB_INDEX, {job_id: submitted_at})
        result = celery_app.send_task(
            "process_image_job",
            args=[job_id, {
                "images": saved, "concurrency": concurrency,
                "engine": resolved_engine, "model": model, "samples": samples,
            }],
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
        resolved_model = model or state.get("model")  # None = engine picks its own default
        resolved_samples = state.get("samples")  # reuse the original sample count
        resolved_concurrency = state.get("concurrency") or 5  # reuse the original concurrency

        total = len(images)
        new_state: dict[str, Any] = {
            "status": "pending",
            "progress": {"current": 0, "total": total, "percent": 0, "active_files": [], "last_completed": None},
            "engine": resolved_engine,
            "model": resolved_model,
            "samples": resolved_samples,
            "concurrency": resolved_concurrency,
            "_images": images,
            "_heartbeat": time.time(),
        }
        await set_state(redis, job_id, new_state)

        result = celery_app.send_task(
            "process_image_job",
            args=[job_id, {
                "images": images, "concurrency": resolved_concurrency,
                "engine": resolved_engine, "model": resolved_model,
                "samples": resolved_samples,
            }],
        )
        new_state["_task_id"] = result.id
        await set_state(redis, job_id, new_state)

        submitted_at = time.time()
        await redis.zadd(JOB_INDEX, {job_id: submitted_at})
        logger.info("Retrying job %s engine=%s model=%s (task %s)", job_id, resolved_engine, resolved_model, result.id)
    finally:
        await redis.aclose()

    return _to_response(job_id, new_state, submitted_at)


@router.get("/{job_id}/export")
async def export_job(
    job_id: str,
    format: str = Query("json", description="Export format: json or csv"),
) -> Response:
    """Export completed job results as JSON or CSV."""
    if format not in ("json", "csv"):
        raise HTTPException(status_code=400, detail=f"Unsupported format '{format}'. Use 'json' or 'csv'")

    redis = aioredis.from_url(settings.REDIS_URL)
    try:
        state = await get_state(redis, job_id)
    finally:
        await redis.aclose()

    if not state:
        raise HTTPException(status_code=404, detail="Job not found")
    if state.get("status") != "done":
        raise HTTPException(
            status_code=400,
            detail=f"Job not complete (status: {state.get('status')})",
        )

    results: list[dict[str, Any]] = state.get("results") or []

    if format == "json":
        return Response(
            content=json.dumps({"job_id": job_id, "results": results}, indent=2),
            media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="job_{job_id[:8]}.json"'},
        )

    import csv
    import io

    if not results:
        return Response(content="", media_type="text/csv")

    rows: list[dict[str, Any]] = []
    for r in results:
        analysis = r.get("analysis") or {}
        row: dict[str, Any] = {
            "job_id": job_id,
            "index": r.get("index", ""),
            "filename": r.get("filename", ""),
            "scene_description": analysis.get("scene_description", ""),
        }
        for cat in ("urban_morphology", "vegetation", "surface_and_flood", "health_livability"):
            for k, v in (analysis.get(cat) or {}).items():
                row[f"{cat}_{k}"] = v
        for k, v in (analysis.get("confidence_scores") or {}).items():
            row[f"confidence_{k}"] = v
        rows.append(row)

    # Union every row's keys (preserving first-seen order) so heterogeneous
    # results — e.g. one image missing a category — don't silently lose columns.
    fieldnames: list[str] = []
    seen: set[str] = set()
    for row in rows:
        for k in row:
            if k not in seen:
                seen.add(k)
                fieldnames.append(k)

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)

    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="job_{job_id[:8]}.csv"'},
    )


@router.websocket("/{job_id}/ws")
async def job_status_ws(job_id: str, websocket: WebSocket) -> None:
    await websocket.accept()

    redis = aioredis.from_url(settings.REDIS_URL)

    # Subscribe BEFORE reading state. Otherwise a "done" event published in
    # the window between get_state and subscribe would be missed, leaving the
    # client blocked on listen() forever for a job that already finished.
    pubsub = redis.pubsub()
    channel = JOB_CHANNEL.format(job_id=job_id)
    await pubsub.subscribe(channel)

    state = await get_state(redis, job_id)

    if not state:
        await pubsub.unsubscribe(channel)
        await websocket.close(code=4004, reason="Job not found")
        await redis.aclose()
        return

    await websocket.send_json(_to_response(job_id, state).model_dump())

    # Terminal already — any buffered event is redundant, close immediately.
    if state.get("status") in ("done", "failed"):
        await pubsub.unsubscribe(channel)
        await websocket.close()
        await redis.aclose()
        return

    try:
        while True:
            # Wait up to one heartbeat interval for the next event. On timeout
            # (get_message returns None) we re-read state so a job killed by the
            # reaper or a dead worker is detected, then ping to keep the socket
            # alive — never block indefinitely on a stalled job (R2).
            message = await pubsub.get_message(
                ignore_subscribe_messages=True,
                timeout=settings.WS_HEARTBEAT_INTERVAL,
            )
            if message is None:
                current = await get_state(redis, job_id)
                if not current:
                    break
                if current.get("status") in ("done", "failed"):
                    await websocket.send_json(_to_response(job_id, current).model_dump())
                    break
                await websocket.send_json({"id": job_id, "type": "heartbeat"})
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
