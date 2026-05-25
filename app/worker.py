"""
Celery Worker — runs as a separate process, picks jobs from Redis queue.

Start with:
    celery -A app.worker worker --loglevel=info

How it works:
  1. API enqueues job via celery_app.send_task("process_route_job", args=[job_id, request])
  2. This worker process picks it up from Redis and calls process_route_job()
  3. Job survives server restarts because it lives in Redis, not in RAM
  4. On startup, worker sweeps for stuck jobs and re-queues them automatically
"""

import asyncio
import logging

from celery import Celery
from celery.signals import worker_ready

from app.core.config import settings

logger = logging.getLogger(__name__)

celery_app = Celery(
    "architecture",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    worker_max_tasks_per_child=100,
    broker_connection_retry_on_startup=True,
)


@celery_app.task(name="process_route_job")
def process_route_job(job_id: str, request: dict) -> None:
    """Sync Celery task — wraps the async job runner for compatibility."""
    from app.services.job_service import _run_route_job
    asyncio.run(_run_route_job(job_id, request))


@worker_ready.connect
def resume_stuck_jobs(sender, **kwargs) -> None:
    """
    On worker boot: find jobs stuck in 'processing' (worker crashed mid-run)
    or 'pending' (Redis was flushed while jobs were queued), then re-queue them.

    'processing' jobs are reset to 'pending' first so progress starts clean.
    'pending' jobs are re-queued as-is — their request_data is still valid.

    worker_ready fires once in the main worker process, not per child,
    so jobs are never re-queued more than once even with --concurrency > 1.
    """
    from app.dao.job_dao import JobDAO
    from app.db.database import SessionLocal

    db = SessionLocal()
    try:
        stuck = JobDAO.get_resumable_jobs(db)
        if not stuck:
            logger.info("Startup sweep: no stuck jobs")
            return

        logger.info("Startup sweep: %d job(s) need re-queuing", len(stuck))
        for job in stuck:
            if job.status == "processing":
                JobDAO.reset_to_pending(db, job.id)
                logger.info("  job %s: processing → pending (worker crashed)", job.id)
            else:
                logger.info("  job %s: pending (Redis was flushed)", job.id)
            celery_app.send_task("process_route_job", args=[job.id, job.request_data])

        logger.info("Startup sweep: re-queued %d job(s)", len(stuck))
    except Exception:
        logger.exception("Startup sweep failed — stuck jobs were NOT re-queued")
    finally:
        db.close()
