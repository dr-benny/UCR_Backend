from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import redis.asyncio as aioredis

from app.core.config import settings
from app.services.analysis_service import AnalysisInput, analyze_from_streetview

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


async def _run_route_job(job_id: str, request: dict[str, Any]) -> None:
    redis = aioredis.from_url(settings.REDIS_URL)

    try:
        points = request.get("points") or []
        concurrency = int(request.get("concurrency") or 5)
        total = len(points)

        await _set_state(redis, job_id, {"status": "processing", "progress": _prog(0, total)})
        await _publish(redis, job_id, {"status": "processing", "progress": _prog(0, total)})
        logger.info("Job %s started — %d points", job_id, total)

        sem = asyncio.Semaphore(concurrency)
        lock = asyncio.Lock()
        results: list[dict | None] = [None] * total
        failed_points: list[dict] = []
        counter = 0

        async def _process_one(idx: int, point: dict) -> None:
            nonlocal counter
            async with sem:
                inp = AnalysisInput(
                    latitude=point["latitude"],
                    longitude=point["longitude"],
                    heading=point.get("heading"),
                    pitch=point.get("pitch", 0),
                    fov=point.get("fov", 90),
                )
                try:
                    ai_result = await analyze_from_streetview(inp)
                    results[idx] = {
                        "index": idx,
                        "latitude": point["latitude"],
                        "longitude": point["longitude"],
                        "analysis": ai_result,
                    }
                except LookupError as exc:
                    logger.warning("Job %s point %d: %s", job_id, idx, exc)
                    failed_points.append({"index": idx, "reason": str(exc)})
                except Exception as exc:
                    logger.exception("Job %s point %d failed", job_id, idx)
                    failed_points.append({"index": idx, "reason": str(exc)})
                finally:
                    async with lock:
                        counter += 1
                        prog = _prog(counter, total)
                    await _publish(redis, job_id, {"status": "processing", "progress": prog})

        await asyncio.gather(*[_process_one(i, p) for i, p in enumerate(points)])

        final_state = {
            "status": "done",
            "progress": _prog(total, total),
            "results": [r for r in results if r is not None],
            "failed_points": failed_points,
        }
        await _set_state(redis, job_id, final_state)
        await _publish(redis, job_id, {"status": "done", "progress": _prog(total, total)})
        logger.info("Job %s done — %d ok, %d failed", job_id, len([r for r in results if r]), len(failed_points))

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
