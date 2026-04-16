"""Survey routes CRUD endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.dao.analysis_dao import AnalysisDAO
from app.dao.route_dao import RouteDAO
from app.schemas import AnalysisResponse, RouteCreate, RouteResponse
from app.services.analysis_service import reanalyze_record

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["routes"])


@router.post("/routes", response_model=RouteResponse, status_code=201)
def create_survey_route(body: RouteCreate, db: Session = Depends(get_db)):
    """Create a new survey route."""
    return RouteDAO.create_route(db, name=body.name, description=body.description)


@router.get("/routes", response_model=list[RouteResponse])
def list_survey_routes(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1),
    db: Session = Depends(get_db),
):
    """List all available survey routes."""
    return RouteDAO.list_routes(db, skip=skip, limit=limit)


@router.get("/routes/{route_id}", response_model=RouteResponse)
def get_survey_route(route_id: int, db: Session = Depends(get_db)):
    """Get details of a specific route."""
    route = RouteDAO.get_by_id(db, route_id)
    if not route:
        raise HTTPException(status_code=404, detail="Route not found")
    return route


# ── Re-analyze entire route ──────────────────────────────────

@router.post("/routes/{route_id}/reanalyze", response_model=list[AnalysisResponse])
async def reanalyze_route(route_id: int, db: Session = Depends(get_db)):
    """
    Re-run Gemini analysis on **every point** in a route.

    Skips any point whose image file is missing (logs a warning instead).
    """
    route = RouteDAO.get_by_id(db, route_id)
    if not route:
        raise HTTPException(status_code=404, detail="Route not found")

    analyses = AnalysisDAO.get_by_route(db, route_id)
    if not analyses:
        raise HTTPException(status_code=404, detail="No analyses found for this route")

    results: list[AnalysisResponse] = []
    for record in analyses:
        try:
            updated = await reanalyze_record(db, record)
            results.append(AnalysisResponse.from_orm_model(updated))
        except FileNotFoundError:
            logger.warning("Image missing for analysis #%d — skipping", record.id)
        except Exception as exc:
            logger.exception("Re-analysis failed for analysis #%d", record.id)

    return results

