"""
Celery Worker — runs as a separate process, picks jobs from Redis queue.

Start with:
    celery -A app.worker worker --loglevel=info

How it works:
  1. API enqueues job via celery_app.send_task("process_route_job", args=[job_id, request])
  2. This worker process picks it up from Redis and calls process_route_job()
  3. Job survives server restarts because it lives in Redis, not in RAM
"""

import asyncio

from celery import Celery

from app.core.config import settings

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
