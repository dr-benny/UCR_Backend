"""
Background job runner.

How it works:
  1. POST /api/jobs/route creates a Job row (status=pending) and
     schedules `process_route_job(job_id, request)` via asyncio.create_task.
  2. The request returns immediately with the job id.
  3. The task opens its own DB session (the request's session is closed by then),
     creates a SurveyRoute, then runs the points through analyze_from_streetview
     in parallel — capped per-job by `concurrency` and globally by the
     AI_MAX_CONCURRENT semaphore inside the engine.
  4. Each finished point bumps progress_current so GET /api/jobs/{id} sees
     live status.
  5. Final commit: status=done with result_data, or status=failed with error.

Failure model:
  - Individual point failures (no coverage, AI error) are logged and counted —
    they don't crash the whole job.
  - A whole-job crash (DB connection, programming bug) is caught and marked
    as failed so the row never sits in 'processing' forever.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.dao.job_dao import JobDAO
from app.dao.route_dao import RouteDAO
from app.db.database import SessionLocal
from app.services.analysis_service import AnalysisInput, analyze_from_streetview

logger = logging.getLogger(__name__)


async def _run_route_job(job_id: str, request: dict[str, Any]) -> None:
    """
    Run a route-analysis job to completion.

    Called by the Celery worker task in app/worker.py via asyncio.run().
    `request` is the persisted request_data from the Job row — a plain dict
    so we don't depend on any Pydantic models being importable later.
    Expected shape:
      {
        "name": str | None,
        "description": str | None,
        "points": [{"latitude": ..., "longitude": ..., ...}, ...],
        "concurrency": int,
      }
    """
    db = SessionLocal()
    try:
        name = request.get("name")
        description = request.get("description")
        points = request.get("points") or []
        concurrency = int(request.get("concurrency") or 5)

        # Create the route first so progress UIs can link to it immediately.
        route_name = name or f"Job {job_id[:8]}"
        route = RouteDAO.create_route(db, name=route_name, description=description)
        JobDAO.mark_started(db, job_id, route_id=route.id)
        logger.info("Job %s started — route=%d, points=%d", job_id, route.id, len(points))

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
                    JobDAO.increment_progress(db, job_id)

        await asyncio.gather(*[_process_one(i, p) for i, p in enumerate(points)])

        JobDAO.mark_done(
            db,
            job_id,
            result_data={
                "route_id": route.id,
                "analysis_ids": sorted(analysis_ids),
                "succeeded": len(analysis_ids),
                "failed": len(failed_points),
                "failed_points": failed_points,
            },
        )
        logger.info(
            "Job %s done — %d ok, %d failed",
            job_id, len(analysis_ids), len(failed_points),
        )

    except Exception as exc:
        logger.exception("Job %s crashed", job_id)
        try:
            JobDAO.mark_failed(db, job_id, str(exc))
        except Exception:
            logger.exception("Job %s: failed to record failure", job_id)
    finally:
        db.close()
