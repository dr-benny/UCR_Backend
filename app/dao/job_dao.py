"""
Job CRUD — all writes commit immediately so polling endpoints always
see fresh state.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models import Job


class JobDAO:
    @staticmethod
    def create_job(
        db: Session,
        job_type: str,
        request_data: dict,
        progress_total: int = 0,
    ) -> Job:
        job = Job(
            job_type=job_type,
            status="pending",
            request_data=request_data,
            progress_total=progress_total,
        )
        db.add(job)
        db.commit()
        db.refresh(job)
        return job

    @staticmethod
    def get_by_id(db: Session, job_id: str) -> Optional[Job]:
        return db.query(Job).filter(Job.id == job_id).first()

    @staticmethod
    def list_jobs(
        db: Session,
        skip: int = 0,
        limit: int = 50,
        status: Optional[str] = None,
    ) -> list[Job]:
        query = db.query(Job).order_by(Job.created_at.desc())
        if status:
            query = query.filter(Job.status == status)
        return query.offset(skip).limit(limit).all()

    @staticmethod
    def mark_started(db: Session, job_id: str, route_id: Optional[int] = None) -> Optional[Job]:
        job = db.query(Job).filter(Job.id == job_id).first()
        if not job:
            return None
        job.status = "processing"
        job.started_at = datetime.now(timezone.utc)
        if route_id is not None:
            job.route_id = route_id
        db.commit()
        db.refresh(job)
        return job

    @staticmethod
    def increment_progress(db: Session, job_id: str) -> Optional[Job]:
        """Bump progress_current by 1 — called once per processed point."""
        job = db.query(Job).filter(Job.id == job_id).first()
        if not job:
            return None
        job.progress_current = (job.progress_current or 0) + 1
        db.commit()
        db.refresh(job)
        return job

    @staticmethod
    def mark_done(db: Session, job_id: str, result_data: dict) -> Optional[Job]:
        job = db.query(Job).filter(Job.id == job_id).first()
        if not job:
            return None
        job.status = "done"
        job.result_data = result_data
        job.completed_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(job)
        return job

    @staticmethod
    def mark_failed(db: Session, job_id: str, error: str) -> Optional[Job]:
        job = db.query(Job).filter(Job.id == job_id).first()
        if not job:
            return None
        job.status = "failed"
        job.error = error
        job.completed_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(job)
        return job

    @staticmethod
    def get_resumable_jobs(db: Session) -> list[Job]:
        """Return pending/processing jobs left over from a previous server run."""
        return (
            db.query(Job)
            .filter(Job.status.in_(["pending", "processing"]))
            .order_by(Job.created_at.asc())
            .all()
        )

    @staticmethod
    def reset_to_pending(db: Session, job_id: str) -> Optional[Job]:
        """Reset a stuck processing job so it can be re-queued cleanly."""
        job = db.query(Job).filter(Job.id == job_id).first()
        if not job:
            return None
        job.status = "pending"
        job.progress_current = 0
        job.started_at = None
        db.commit()
        db.refresh(job)
        return job
