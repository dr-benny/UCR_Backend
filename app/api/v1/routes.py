"""Survey routes CRUD endpoints."""

from __future__ import annotations

import logging
import os
import tempfile

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.dao.analysis_dao import AnalysisDAO
from app.dao.route_dao import RouteDAO
from app.dao.sensor_reading_dao import SensorReadingDAO
from app.schemas import AnalysisResponse, RouteCreate, RouteResponse
from app.services.analysis_service import reanalyze_record
from app.services.export_service import build_route_kmz

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


@router.get("/routes/{route_id}/export/kmz")
def export_route_kmz(
    route_id: int,
    temp: bool = Query(True, description="Include temperature layer"),
    humid: bool = Query(True, description="Include humidity layer"),
    lux: bool = Query(True, description="Include lux layer"),
    uv: bool = Query(True, description="Include UV layer"),
    export_mode: str = Query("all", pattern="^(all|minmax)$", description="all = full path, minmax = path + min/max stars"),
    db: Session = Depends(get_db),
):
    """
    Export the route as a KMZ file with:
      - AI Spatial Analysis (street width, wall heights, H/W ratio, observations)
      - Environmental Sensor data (temp/humid/lux/uv as colored trajectories)

    Both layers ship with self-explanatory legends rendered as ScreenOverlays.
    """
    route = RouteDAO.get_by_id(db, route_id)
    if not route:
        raise HTTPException(status_code=404, detail="Route not found")

    analyses = AnalysisDAO.get_by_route(db, route_id)
    readings = SensorReadingDAO.list_by_route(db, route_id)
    if not analyses and not readings:
        raise HTTPException(status_code=404, detail="No analyses or sensor readings found for this route")

    out_path = os.path.join(
        tempfile.gettempdir(),
        f"route_{route_id}_{(route.name or 'export').replace(' ', '_')}.kmz",
    )
    build_route_kmz(
        route=route,
        analyses=analyses,
        sensor_readings=readings,
        out_path=out_path,
        enabled_sensors={"temp": temp, "humid": humid, "lux": lux, "uv": uv},
        export_mode=export_mode,
    )
    return FileResponse(
        out_path,
        media_type="application/vnd.google-earth.kmz",
        filename=os.path.basename(out_path),
    )

