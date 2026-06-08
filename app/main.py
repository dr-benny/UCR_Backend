from __future__ import annotations

import asyncio
import json
import logging
from contextlib import asynccontextmanager, suppress
from pathlib import Path

import redis.asyncio as aioredis
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import router as v1_router
from app.core.config import settings

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
    redis = aioredis.from_url(settings.REDIS_URL)
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
    finally:
        await redis.aclose()


async def _cleanup_loop() -> None:
    while True:
        await asyncio.sleep(3600)  # run every hour
        await _orphaned_image_cleanup()


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(_cleanup_loop())
    yield
    task.cancel()
    with suppress(asyncio.CancelledError):
        await task


app = FastAPI(
    title="Urban Microclimate Analyzer",
    description="Extracts walkway geometry, shade, and heat-risk data from Street View images using Gemini Vision AI.",
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
    redis = aioredis.from_url(settings.REDIS_URL)
    try:
        await redis.ping()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Redis unavailable: {exc}")
    finally:
        await redis.aclose()
    return {"status": "ready", "redis": "ok"}
