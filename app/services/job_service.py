from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Any

import redis.asyncio as aioredis

from app.core.config import settings
from app.services.analysis_service import analyze_image_file
from app.services.job_store import publish_event, update_state

logger = logging.getLogger(__name__)


def _prog(current: int, total: int, active: list[str] | None = None, last_completed: str | None = None) -> dict:
    return {
        "current": current,
        "total": total,
        "percent": round(current / total * 100) if total else 0,
        "active_files": active or [],
        "last_completed": last_completed,
    }


def cleanup_images(images: list[dict]) -> None:
    for item in images:
        try:
            os.unlink(item["path"])
        except OSError:
            pass


async def _run_image_job(job_id: str, request: dict[str, Any]) -> None:
    """Process a batch of saved image files through AI."""
    redis = aioredis.from_url(settings.REDIS_URL)
    images: list[dict] = request.get("images") or []
    engine: str | None = request.get("engine")
    model: str | None = request.get("model")
    samples: int | None = request.get("samples")
    prompt: str | None = request.get("prompt")

    try:
        concurrency = int(request.get("concurrency") or 5)
        total = len(images)

        await update_state(redis, job_id, {
            "status": "processing", "progress": _prog(0, total),
            "_images": images, "_heartbeat": time.time(),
        })
        await publish_event(redis, job_id, {"status": "processing", "progress": _prog(0, total)})
        logger.info("Job %s started — %d images, engine=%s model=%s", job_id, total, engine, model)

        sem = asyncio.Semaphore(concurrency)
        lock = asyncio.Lock()
        results: list[dict | None] = [None] * total
        failed: list[dict] = []
        counter = 0
        active_files: dict[int, str] = {}
        last_completed: str | None = None

        async def _process_one(idx: int, item: dict) -> None:
            nonlocal counter, last_completed
            filename = item.get("filename", f"image_{idx}")
            async with sem:
                async with lock:
                    active_files[idx] = filename
                    start_prog = _prog(counter, total, list(active_files.values()), last_completed)
                await publish_event(redis, job_id, {"status": "processing", "progress": start_prog})
                logger.info("Job %s → starting %s (%d/%d)", job_id, filename, counter, total)

                try:
                    ai_result = await analyze_image_file(
                        item["path"], mime_type=item.get("mime"),
                        engine=engine, model=model, samples=samples, prompt=prompt,
                    )
                    if ai_result.get("_parse_error"):
                        # AI returned text we couldn't parse into JSON — count it as
                        # a failure instead of storing the garbage as a real result.
                        failed.append({"index": idx, "filename": filename,
                                       "reason": "AI returned unparseable output"})
                    else:
                        results[idx] = {"index": idx, "filename": filename, "analysis": ai_result}
                except Exception as exc:
                    logger.exception("Job %s image %d failed", job_id, idx)
                    failed.append({"index": idx, "filename": filename, "reason": str(exc)})
                finally:
                    async with lock:
                        counter += 1
                        last_completed = filename
                        active_files.pop(idx, None)
                        prog = _prog(counter, total, list(active_files.values()), last_completed)
                    await publish_event(redis, job_id, {"status": "processing", "progress": prog})
                    # Persist progress + heartbeat: lets REST pollers see progress
                    # (not just WS) and tells the reaper the worker is alive (R1/R4).
                    await update_state(redis, job_id, {"progress": prog, "_heartbeat": time.time()})
                    logger.info("Job %s → done %s (%d/%d, %d%%)", job_id, filename, counter, total, prog["percent"])

        await asyncio.gather(*[_process_one(i, img) for i, img in enumerate(images)])

        final_prog = _prog(total, total, [], last_completed)
        await update_state(redis, job_id, {
            "status": "done",
            "progress": final_prog,
            "results": [r for r in results if r is not None],
            "failed": failed,
        })
        await publish_event(redis, job_id, {"status": "done", "progress": final_prog})
        logger.info("Job %s done — %d ok, %d failed", job_id, len([r for r in results if r]), len(failed))
        cleanup_images(images)

    except Exception as exc:
        logger.exception("Job %s crashed", job_id)
        try:
            await update_state(redis, job_id, {"status": "failed", "error": str(exc), "_images": images})
            await publish_event(redis, job_id, {"status": "failed", "error": str(exc)})
        except Exception:
            logger.exception("Job %s: failed to record failure", job_id)
    finally:
        await redis.aclose()
