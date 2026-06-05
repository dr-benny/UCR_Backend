from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import redis.asyncio as aioredis

from app.core.config import settings
from app.services.analysis_service import analyze_image_file

logger = logging.getLogger(__name__)

_JOB_KEY = "job:{job_id}"
_JOB_CHANNEL = "job:{job_id}"
_JOB_TTL = 86400  # 24h


async def _set_state(redis: aioredis.Redis, job_id: str, state: dict) -> None:
    await redis.set(_JOB_KEY.format(job_id=job_id), json.dumps(state), ex=_JOB_TTL)


async def _publish(redis: aioredis.Redis, job_id: str, payload: dict) -> None:
    await redis.publish(_JOB_CHANNEL.format(job_id=job_id), json.dumps(payload))


def _prog(current: int, total: int) -> dict:
    return {"current": current, "total": total, "percent": round(current / total * 100) if total else 0}


async def _run_image_job(job_id: str, request: dict[str, Any]) -> None:
    """Process a batch of saved image files through AI."""
    redis = aioredis.from_url(settings.REDIS_URL)

    try:
        images = request.get("images") or []  # list of {path, filename}
        concurrency = int(request.get("concurrency") or 5)
        total = len(images)

        await _set_state(redis, job_id, {"status": "processing", "progress": _prog(0, total)})
        await _publish(redis, job_id, {"status": "processing", "progress": _prog(0, total)})
        logger.info("Job %s started — %d images", job_id, total)

        sem = asyncio.Semaphore(concurrency)
        lock = asyncio.Lock()
        results: list[dict | None] = [None] * total
        failed: list[dict] = []
        counter = 0

        async def _process_one(idx: int, item: dict) -> None:
            nonlocal counter
            async with sem:
                path = item["path"]
                try:
                    ai_result = await analyze_image_file(path)
                    results[idx] = {
                        "index": idx,
                        "filename": item.get("filename", f"image_{idx}"),
                        "analysis": ai_result,
                    }
                except Exception as exc:
                    logger.exception("Job %s image %d failed", job_id, idx)
                    failed.append({"index": idx, "filename": item.get("filename"), "reason": str(exc)})
                finally:
                    async with lock:
                        counter += 1
                        prog = _prog(counter, total)
                    await _publish(redis, job_id, {"status": "processing", "progress": prog})

        await asyncio.gather(*[_process_one(i, img) for i, img in enumerate(images)])

        final_state = {
            "status": "done",
            "progress": _prog(total, total),
            "results": [r for r in results if r is not None],
            "failed": failed,
        }
        await _set_state(redis, job_id, final_state)
        await _publish(redis, job_id, {"status": "done", "progress": _prog(total, total)})
        logger.info("Job %s done — %d ok, %d failed", job_id, len([r for r in results if r]), len(failed))

    except Exception as exc:
        logger.exception("Job %s crashed", job_id)
        try:
            error_state = {"status": "failed", "error": str(exc)}
            await _set_state(redis, job_id, error_state)
            await _publish(redis, job_id, error_state)
        except Exception:
            logger.exception("Job %s: failed to record failure", job_id)
    finally:
        await redis.aclose()
