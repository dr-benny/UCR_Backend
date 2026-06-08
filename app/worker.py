import asyncio
import logging

from celery import Celery

from app.core.config import settings

logger = logging.getLogger(__name__)

celery_app = Celery("ucr", broker=settings.REDIS_URL)  # no result backend — we store state ourselves

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    worker_max_tasks_per_child=100,
    broker_connection_retry_on_startup=True,
)


@celery_app.task(name="process_image_job")
def process_image_job(job_id: str, request: dict) -> None:
    import app.services.ai_engines.base as ai_base
    ai_base._api_semaphore = None  # reset so it binds to the fresh event loop from asyncio.run()
    from app.services.job_service import _run_image_job
    asyncio.run(_run_image_job(job_id, request))
