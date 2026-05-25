"""
Async job endpoints.

POST /api/jobs/route    → submit a multi-point route, get a job id back immediately.
GET  /api/jobs/{id}     → one-shot poll: current status, progress, result.
WS   /api/jobs/{id}/ws  → real-time stream: server pushes every status change via
                          Redis Pub/Sub — no client polling needed.
GET  /api/jobs          → list recent jobs (optional ?status= filter).
"""

from __future__ import annotations

import json
import logging
from typing import Optional

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session

from app.core.config import settings
from app.dao.job_dao import JobDAO
from app.db.database import get_db
from app.schemas.job import JobResponse, RouteJobCreate
from app.worker import celery_app

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/jobs", tags=["jobs"])

_JOB_CHANNEL = "job:{job_id}"


@router.post("/route", response_model=JobResponse, status_code=202)
def submit_route_job(
    body: RouteJobCreate,
    db: Session = Depends(get_db),
):
    """
    Submit a route for asynchronous analysis.

    Returns immediately with `id` and `status="pending"`. Connect to
    WS /api/jobs/{id}/ws to receive live progress without polling.
    """
    request_data = body.model_dump()
    job = JobDAO.create_job(
        db,
        job_type="route_analysis",
        request_data=request_data,
        progress_total=len(body.points),
    )

    celery_app.send_task("process_route_job", args=[job.id, request_data])
    logger.info("Enqueued route job %s (%d points) to Celery/Redis", job.id, len(body.points))

    return JobResponse.from_orm_model(job)


@router.websocket("/{job_id}/ws")
async def job_status_ws(job_id: str, websocket: WebSocket, db: Session = Depends(get_db)):
    """
    Real-time job status stream over WebSocket.

    On connect: sends current snapshot immediately.
    While running: pushes every status change the worker publishes to Redis.
    On done/failed: sends final message then closes the connection.

    The worker publishes to Redis channel `job:{id}` after every
    mark_started / increment_progress / mark_done / mark_failed call,
    so latency between DB write and client notification is under 100ms.
    """
    await websocket.accept()

    job = JobDAO.get_by_id(db, job_id)
    if not job:
        await websocket.close(code=4004, reason="Job not found")
        return

    # Send current state so the client doesn't start blank
    await websocket.send_json(JobResponse.from_orm_model(job).model_dump(mode="json"))

    # Already finished — nothing to stream
    if job.status in ("done", "failed"):
        await websocket.close()
        return

    redis = aioredis.from_url(settings.REDIS_URL)
    pubsub = redis.pubsub()
    channel = _JOB_CHANNEL.format(job_id=job_id)
    await pubsub.subscribe(channel)

    try:
        async for message in pubsub.listen():
            if message["type"] != "message":
                continue
            data = json.loads(message["data"])
            await websocket.send_json(data)
            if data.get("status") in ("done", "failed"):
                break
    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected from job %s", job_id)
    finally:
        await pubsub.unsubscribe(channel)
        await redis.aclose()


@router.get("/{job_id}", response_model=JobResponse)
def get_job(job_id: str, db: Session = Depends(get_db)):
    job = JobDAO.get_by_id(db, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return JobResponse.from_orm_model(job)


@router.get("", response_model=list[JobResponse])
def list_jobs(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    status: Optional[str] = Query(
        None,
        description="Filter by status: pending, processing, done, failed",
    ),
    db: Session = Depends(get_db),
):
    jobs = JobDAO.list_jobs(db, skip=skip, limit=limit, status=status)
    return [JobResponse.from_orm_model(j) for j in jobs]
