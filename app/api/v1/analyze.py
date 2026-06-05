from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.schemas.analysis import AnalyzeRequest
from app.services.analysis_service import AnalysisInput, analyze_from_streetview

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["analysis"])


@router.post("/analyze")
async def analyze_location(body: AnalyzeRequest) -> dict[str, Any]:
    inp = AnalysisInput(
        latitude=body.latitude,
        longitude=body.longitude,
        heading=body.heading,
        pitch=body.pitch,
        fov=body.fov,
    )
    try:
        return await analyze_from_streetview(inp)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        logger.exception("Analysis failed")
        raise HTTPException(status_code=502, detail=f"AI analysis failed: {exc}")


@router.post("/analyze/batch")
async def analyze_batch(
    locations: list[AnalyzeRequest],
    concurrency: int = Query(5, ge=1, le=10),
) -> list[dict[str, Any]]:
    if len(locations) > 20:
        raise HTTPException(status_code=400, detail="Maximum 20 locations per batch")

    sem = asyncio.Semaphore(concurrency)

    async def _one(loc: AnalyzeRequest) -> dict[str, Any] | None:
        async with sem:
            inp = AnalysisInput(
                latitude=loc.latitude,
                longitude=loc.longitude,
                heading=loc.heading,
                pitch=loc.pitch,
                fov=loc.fov,
            )
            try:
                return await analyze_from_streetview(inp)
            except Exception:
                logger.warning("Skipping (%s, %s) — analysis failed", loc.latitude, loc.longitude)
                return None

    results = await asyncio.gather(*[_one(loc) for loc in locations])
    return [r for r in results if r is not None]
