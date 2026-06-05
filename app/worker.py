import asyncio
import logging

from celery import Celery

from app.core.config import settings

logger = logging.getLogger(__name__)

celery_app = Celery(
    "ucr",
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


@celery_app.task(name="process_image_job")
def process_image_job(job_id: str, request: dict) -> None:
    from app.services.job_service import _run_image_job
    asyncio.run(_run_image_job(job_id, request))
