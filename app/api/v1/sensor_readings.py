"""
Sensor readings endpoints — time-series environmental measurements per route.

POST /api/routes/{route_id}/sensor-readings        → JSON bulk insert
POST /api/routes/{route_id}/sensor-readings/upload → CSV upload (multipart)
GET  /api/routes/{route_id}/sensor-readings        → list (filter by ?dataset=)
GET  /api/routes/{route_id}/sensor-readings/datasets → distinct dataset summary
DELETE /api/routes/{route_id}/sensor-readings/{dataset_name} → wipe one dataset

CSV columns expected (header row required, any subset of metric columns allowed):
  latitude, longitude, recorded_at, temp_c, humidity_pct, lux, uv_index
"""

from __future__ import annotations

import csv
import io
import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

from app.dao.route_dao import RouteDAO
from app.dao.sensor_reading_dao import SensorReadingDAO
from app.db.database import get_db
from app.schemas import (
    BulkUploadResult,
    DatasetSummary,
    SensorBulkUpload,
    SensorReadingOut,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/routes", tags=["sensor-readings"])


def _require_route(db: Session, route_id: int):
    route = RouteDAO.get_by_id(db, route_id)
    if not route:
        raise HTTPException(status_code=404, detail="Route not found")
    return route


@router.post(
    "/{route_id}/sensor-readings",
    response_model=BulkUploadResult,
    status_code=201,
)
def upload_readings_json(
    route_id: int,
    body: SensorBulkUpload,
    db: Session = Depends(get_db),
):
    _require_route(db, route_id)
    rows = [r.model_dump() for r in body.readings]
    inserted = SensorReadingDAO.bulk_create(db, route_id, body.dataset_name, rows)
    return BulkUploadResult(inserted=inserted, dataset_name=body.dataset_name, route_id=route_id)


@router.post(
    "/{route_id}/sensor-readings/upload",
    response_model=BulkUploadResult,
    status_code=201,
)
async def upload_readings_csv(
    route_id: int,
    dataset_name: str = Form(..., min_length=1, max_length=128),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    _require_route(db, route_id)

    raw = await file.read()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("latin-1")

    reader = csv.DictReader(io.StringIO(text))
    rows: list[dict] = []
    for i, row in enumerate(reader):
        try:
            ts_str = row.get("recorded_at") or row.get("time") or row.get("timestamp")
            if not ts_str:
                continue
            rows.append({
                "latitude": float(row["latitude"]),
                "longitude": float(row["longitude"]),
                "recorded_at": _parse_ts(ts_str),
                "temp_c": _to_float(row.get("temp_c") or row.get("temp")),
                "humidity_pct": _to_float(row.get("humidity_pct") or row.get("humid")),
                "lux": _to_float(row.get("lux")),
                "uv_index": _to_float(row.get("uv_index") or row.get("uv")),
            })
        except (ValueError, KeyError) as exc:
            logger.warning("CSV row %d skipped: %s", i + 2, exc)

    if not rows:
        raise HTTPException(status_code=400, detail="No valid rows found in CSV")

    inserted = SensorReadingDAO.bulk_create(db, route_id, dataset_name, rows)
    return BulkUploadResult(inserted=inserted, dataset_name=dataset_name, route_id=route_id)


@router.get(
    "/{route_id}/sensor-readings",
    response_model=list[SensorReadingOut],
)
def list_readings(
    route_id: int,
    dataset: Optional[str] = Query(None, description="Filter by dataset_name"),
    db: Session = Depends(get_db),
):
    _require_route(db, route_id)
    rows = SensorReadingDAO.list_by_route(db, route_id, dataset_name=dataset)
    return [SensorReadingOut.from_orm_model(r) for r in rows]


@router.get(
    "/{route_id}/sensor-readings/datasets",
    response_model=list[DatasetSummary],
)
def list_datasets(route_id: int, db: Session = Depends(get_db)):
    _require_route(db, route_id)
    return SensorReadingDAO.list_datasets(db, route_id)


@router.delete(
    "/{route_id}/sensor-readings/{dataset_name}",
    status_code=204,
)
def delete_dataset(route_id: int, dataset_name: str, db: Session = Depends(get_db)):
    _require_route(db, route_id)
    deleted = SensorReadingDAO.delete_dataset(db, route_id, dataset_name)
    if deleted == 0:
        raise HTTPException(status_code=404, detail="Dataset not found")
    return None


def _to_float(v) -> Optional[float]:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _parse_ts(s: str) -> datetime:
    """Parse common timestamp formats: ISO 8601, 'YYYY-MM-DD HH:MM:SS', etc."""
    s = s.strip()
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return datetime.fromisoformat(s.replace("Z", "+00:00"))
