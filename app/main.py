from __future__ import annotations

import asyncio
import json
import logging
import time
from contextlib import asynccontextmanager, suppress
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import router as v1_router
from app.core.config import settings
from app.services.job_store import JOB_CHANNEL, JOB_TTL
from app.services.redis_client import close_redis, get_redis

logger = logging.getLogger(__name__)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s │ %(levelname)-8s │ %(name)s │ %(message)s",
)


async def _orphaned_image_cleanup() -> None:
    """
    Hourly: delete image files on disk that are no longer referenced
    by any active job in Redis. Handles images from failed jobs whose
    Redis state expired before the job was deleted.
    """
    images_dir = Path(settings.IMAGE_DIR)
    redis = get_redis()
    try:
        # SCAN instead of KEYS — KEYS is O(N) and blocks the whole Redis instance.
        referenced: set[str] = set()
        async for key in redis.scan_iter(match="job:*", count=100):
            raw = await redis.get(key)
            if raw:
                state = json.loads(raw)
                for img in state.get("_images", []):
                    referenced.add(img["path"])

        if not images_dir.exists():
            return
        deleted = 0
        for f in images_dir.iterdir():
            if f.is_file() and str(f) not in referenced:
                f.unlink(missing_ok=True)
                deleted += 1
        if deleted:
            logger.info("Orphaned image cleanup: deleted %d files", deleted)
    except Exception:
        logger.exception("Orphaned image cleanup failed")


async def _cleanup_loop() -> None:
    while True:
        await asyncio.sleep(3600)  # run every hour
        await _orphaned_image_cleanup()


async def _reap_stuck_jobs() -> None:
    """
    Mark jobs as failed when their worker has gone silent (R1).

    A job is "stuck" if it is still pending/processing but its _heartbeat
    (refreshed at submit, at processing start, and after every image) is
    older than STUCK_JOB_TIMEOUT — i.e. the worker crashed, was killed, or
    was never picked up. Without this, such jobs sit in "processing" until
    their 24h TTL expires and any WebSocket client waits forever.
    """
    redis = get_redis()
    try:
        now = time.time()
        async for key in redis.scan_iter(match="job:*", count=100):
            raw = await redis.get(key)
            if not raw:
                continue
            state = json.loads(raw)
            if state.get("status") not in ("pending", "processing"):
                continue
            hb = state.get("_heartbeat")
            if hb is None or (now - hb) <= settings.STUCK_JOB_TIMEOUT:
                continue

            key_str = key if isinstance(key, str) else key.decode()
            job_id = key_str.split("job:", 1)[-1]
            state["status"] = "failed"
            state["error"] = "Job stalled — worker stopped responding"
            await redis.set(key_str, json.dumps(state), ex=JOB_TTL)
            await redis.publish(
                JOB_CHANNEL.format(job_id=job_id),
                json.dumps({"status": "failed", "error": state["error"]}),
            )
            logger.warning("Reaped stuck job %s (idle %.0fs)", job_id, now - hb)
    except Exception:
        logger.exception("Stuck-job reaper failed")


async def _reaper_loop() -> None:
    while True:
        await asyncio.sleep(settings.STUCK_JOB_REAPER_INTERVAL)
        await _reap_stuck_jobs()


@asynccontextmanager
async def lifespan(app: FastAPI):
    tasks = [
        asyncio.create_task(_cleanup_loop()),
        asyncio.create_task(_reaper_loop()),
    ]
    yield
    for task in tasks:
        task.cancel()
    for task in tasks:
        with suppress(asyncio.CancelledError):
            await task
    await close_redis()


app = FastAPI(
    title="Urban Microclimate Analyzer",
    description="Extracts walkway geometry, shade, and heat-risk indicators from uploaded street-level images using pluggable AI vision engines (Gemini, Claude).",
    version="2.0.0",
    lifespan=lifespan,
)

_cors_origins = [o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()]
_allow_all_origins = _cors_origins == ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    # Browsers reject wildcard origin together with credentials, so only
    # enable credentials when explicit origins are configured.
    allow_credentials=not _allow_all_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(v1_router)


@app.get("/health", tags=["system"])
def health_check():
    """Liveness — process is up. Does not check dependencies."""
    return {"status": "ok", "service": "Urban Microclimate Analyzer"}


@app.get("/health/ready", tags=["system"])
async def readiness_check():
    """Readiness — verifies Redis is reachable. Use this for LB/k8s probes."""
    redis = get_redis()
    try:
        await redis.ping()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Redis unavailable: {exc}")
    return {"status": "ready", "redis": "ok"}
