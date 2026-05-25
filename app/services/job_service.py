"""
Background job runner.

How it works:
  1. POST /api/jobs/route creates a Job row (status=pending) and enqueues
     a Celery task via Redis.
  2. The request returns immediately with the job id.
  3. The Celery worker runs _run_route_job: opens its own DB + Redis connection,
     creates a SurveyRoute, runs points through analyze_from_streetview in
     parallel — capped per-job by `concurrency` and globally by AI_MAX_CONCURRENT.
  4. After every status change (started / per-point progress / done / failed),
     the worker publishes a small JSON payload to the Redis channel `job:{id}`.
  5. The WebSocket endpoint (GET /api/jobs/{id}/ws) subscribes to that channel
     and streams updates to the client in real time — no polling needed.

Failure model:
  - Individual point failures (no coverage, AI error) are logged and counted —
    they don't crash the whole job.
  - A whole-job crash (DB connection, programming bug) is caught, marked
    failed in the DB, and published so connected WebSocket clients are notified.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import redis.asyncio as aioredis

from app.core.config import settings
from app.dao.job_dao import JobDAO
from app.dao.route_dao import RouteDAO
from app.db.database import SessionLocal
from app.services.analysis_service import AnalysisInput, analyze_from_streetview

logger = logging.getLogger(__name__)

_JOB_CHANNEL = "job:{job_id}"


async def _run_route_job(job_id: str, request: dict[str, Any]) -> None:
    """
    Run a route-analysis job to completion.

    Called by the Celery worker task in app/worker.py via asyncio.run().
    """
    db = SessionLocal()
    redis = aioredis.from_url(settings.REDIS_URL)

    async def publish(payload: dict) -> None:
        channel = _JOB_CHANNEL.format(job_id=job_id)
        await redis.publish(channel, json.dumps(payload))

    try:
        name = request.get("name")
        description = request.get("description")
        points = request.get("points") or []
        concurrency = int(request.get("concurrency") or 5)
        total = len(points)

        route_name = name or f"Job {job_id[:8]}"
        route = RouteDAO.create_route(db, name=route_name, description=description)
        JobDAO.mark_started(db, job_id, route_id=route.id)
        await publish({"status": "processing", "progress": {"current": 0, "total": total}, "route_id": route.id})
        logger.info("Job %s started — route=%d, points=%d", job_id, route.id, total)

        sem = asyncio.Semaphore(concurrency)
        analysis_ids: list[int] = []
        failed_points: list[dict[str, Any]] = []

        async def _process_one(idx: int, point: dict[str, Any]) -> None:
            async with sem:
                inp = AnalysisInput(
                    latitude=point["latitude"],
                    longitude=point["longitude"],
                    heading=point.get("heading"),
                    pitch=point.get("pitch", 0),
                    fov=point.get("fov", 90),
                    route_id=route.id,
                    order_index=idx,
                )
                try:
                    record = await analyze_from_streetview(db, inp)
                    analysis_ids.append(record.id)
                except LookupError as exc:
                    logger.warning("Job %s point %d: %s", job_id, idx, exc)
                    failed_points.append({"index": idx, "reason": str(exc)})
                except Exception as exc:
                    logger.exception("Job %s point %d failed", job_id, idx)
                    failed_points.append({"index": idx, "reason": str(exc)})
                finally:
                    job = JobDAO.increment_progress(db, job_id)
                    current = job.progress_current if job else idx + 1
                    await publish({"status": "processing", "progress": {"current": current, "total": total}, "route_id": route.id})

        await asyncio.gather(*[_process_one(i, p) for i, p in enumerate(points)])

        result_data = {
            "route_id": route.id,
            "analysis_ids": sorted(analysis_ids),
            "succeeded": len(analysis_ids),
            "failed": len(failed_points),
            "failed_points": failed_points,
        }
        JobDAO.mark_done(db, job_id, result_data=result_data)
        await publish({"status": "done", "progress": {"current": total, "total": total}, "route_id": route.id, "result": result_data})
        logger.info("Job %s done — %d ok, %d failed", job_id, len(analysis_ids), len(failed_points))

    except Exception as exc:
        logger.exception("Job %s crashed", job_id)
        try:
            JobDAO.mark_failed(db, job_id, str(exc))
            await publish({"status": "failed", "error": str(exc)})
        except Exception:
            logger.exception("Job %s: failed to record failure", job_id)
    finally:
        db.close()
        await redis.aclose()
