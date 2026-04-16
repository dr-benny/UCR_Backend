"""Street View analysis endpoints — images fetched from Google."""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.dao.analysis_dao import AnalysisDAO
from app.schemas import AnalysisListItem, AnalysisResponse, AnalyzeRequest
from app.services.analysis_service import AnalysisInput, analyze_from_streetview, reanalyze_record

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["analysis"])


# ── Single ────────────────────────────────────────────────────

@router.post("/analyze", response_model=AnalysisResponse, status_code=201)
async def analyze_location(body: AnalyzeRequest, db: Session = Depends(get_db)):
    """
    Full Street View pipeline:
    check coverage → fetch image → Gemini → save.
    """
    inp = AnalysisInput(
        latitude=body.latitude,
        longitude=body.longitude,
        heading=body.heading,
        pitch=body.pitch,
        fov=body.fov,
        route_id=body.route_id,
        order_index=body.order_index,
    )

    try:
        record = await analyze_from_streetview(db, inp)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    except Exception as exc:
        logger.exception("Gemini analysis failed")
        raise HTTPException(status_code=502, detail=f"AI analysis failed: {exc}")

    return AnalysisResponse.from_orm_model(record)


# ── Batch ─────────────────────────────────────────────────────

@router.post("/analyze/batch", response_model=list[AnalysisResponse], status_code=201)
async def analyze_batch(
    locations: list[AnalyzeRequest],
    route_id: Optional[int] = Query(None, description="Global route ID for this batch"),
    db: Session = Depends(get_db),
):
    """
    Analyze multiple Street View locations.

    - **route_id**: If provided in query, acts as the default for all locations.
    - **order_index**: If 0 or missing in loc, it will be auto-assigned 0, 1, 2...
    """
    if len(locations) > 20:
        raise HTTPException(status_code=400, detail="Maximum 20 locations per batch request")

    results: list[AnalysisResponse] = []
    for idx, loc in enumerate(locations):
        # logic: ใช้ค่าจาก json ถ้ามี, ถ้าไม่มีใช้ค่า global หรือลำดับ index
        final_route_id = loc.route_id or route_id
        final_order = loc.order_index if loc.order_index != 0 else idx

        inp = AnalysisInput(
            latitude=loc.latitude,
            longitude=loc.longitude,
            heading=loc.heading,
            pitch=loc.pitch,
            fov=loc.fov,
            route_id=final_route_id,
            order_index=final_order,
        )
        try:
            record = await analyze_from_streetview(db, inp)
            results.append(AnalysisResponse.from_orm_model(record))
        except LookupError:
            logger.warning("No coverage at (%s, %s) — skipping", loc.latitude, loc.longitude)
        except Exception as exc:
            logger.exception("Failed to process (%s, %s)", loc.latitude, loc.longitude)

    return results


# ── CRUD (read / delete) ─────────────────────────────────────

@router.get("/analyses", response_model=list[AnalysisListItem])
def list_analyses(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    heat_risk: Optional[str] = Query(None, description="Filter by heat_risk_proxy"),
    db: Session = Depends(get_db),
):
    """List analyses via DAO."""
    return AnalysisDAO.list_analyses(db, skip=skip, limit=limit, heat_risk=heat_risk)


@router.get("/analyses/{analysis_id}", response_model=AnalysisResponse)
def get_analysis(analysis_id: int, db: Session = Depends(get_db)):
    """Get single analysis via DAO."""
    record = AnalysisDAO.get_by_id(db, analysis_id)
    if not record:
        raise HTTPException(status_code=404, detail="Analysis not found")
    return AnalysisResponse.from_orm_model(record)


@router.delete("/analyses/{analysis_id}", status_code=204)
def delete_analysis(analysis_id: int, db: Session = Depends(get_db)):
    """Delete analysis via DAO."""
    success = AnalysisDAO.delete_analysis(db, analysis_id)
    if not success:
        raise HTTPException(status_code=404, detail="Analysis not found")


# ── Re-analyze ────────────────────────────────────────────────

@router.post("/analyses/{analysis_id}/reanalyze", response_model=AnalysisResponse)
async def reanalyze_single(analysis_id: int, db: Session = Depends(get_db)):
    """
    Re-run Gemini analysis on an existing record's saved image.

    The image is read from disk — no re-upload or re-fetch needed.
    """
    record = AnalysisDAO.get_by_id(db, analysis_id)
    if not record:
        raise HTTPException(status_code=404, detail="Analysis not found")

    try:
        updated = await reanalyze_record(db, record)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        logger.exception("Re-analysis failed for analysis #%d", analysis_id)
        raise HTTPException(status_code=502, detail=f"AI analysis failed: {exc}")

    return AnalysisResponse.from_orm_model(updated)

