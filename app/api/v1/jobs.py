"""
Async job endpoints.

POST /api/jobs/route  → submit a multi-point route, get a job id back
                        immediately. Work runs in the background via ARQ + Redis.
GET  /api/jobs/{id}   → poll status, progress, and final result.
GET  /api/jobs        → list recent jobs (optional ?status= filter).
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.dao.job_dao import JobDAO
from app.db.database import get_db
from app.schemas.job import JobResponse, RouteJobCreate
from app.worker import celery_app

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


@router.post("/route", response_model=JobResponse, status_code=202)
def submit_route_job(
    body: RouteJobCreate,
    db: Session = Depends(get_db),
):
    """
    Submit a route for asynchronous analysis.

    Returns immediately with `id` and `status="pending"`. The work runs
    in the Celery worker process; poll GET /api/jobs/{id} to track progress
    and fetch results once `status == "done"`.
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
