"""
SensorReadingDAO — CRUD for time-series sensor readings.

Bulk insert is the hot path here (a CSV can have thousands of rows),
so it uses SQLAlchemy's bulk_save_objects to skip the per-row ORM overhead.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from geoalchemy2.elements import WKTElement
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import SensorReading


class SensorReadingDAO:
    @staticmethod
    def bulk_create(
        db: Session,
        route_id: int,
        dataset_name: str,
        rows: list[dict],
    ) -> int:
        """
        Bulk insert sensor readings. Returns the count inserted.

        Each `row` must have: latitude, longitude, recorded_at.
        Optional: temp_c, humidity_pct, lux, uv_index.
        """
        objects = []
        for r in rows:
            lat = r.get("latitude")
            lon = r.get("longitude")
            ts = r.get("recorded_at")
            if lat is None or lon is None or ts is None:
                continue
            if float(lat) == 0 and float(lon) == 0:
                continue
            objects.append(
                SensorReading(
                    route_id=route_id,
                    dataset_name=dataset_name,
                    geom=WKTElement(f"POINT({lon} {lat})", srid=4326),
                    recorded_at=ts,
                    temp_c=r.get("temp_c"),
                    humidity_pct=r.get("humidity_pct"),
                    lux=r.get("lux"),
                    uv_index=r.get("uv_index"),
                )
            )
        if not objects:
            return 0
        db.bulk_save_objects(objects)
        db.commit()
        return len(objects)

    @staticmethod
    def list_by_route(
        db: Session,
        route_id: int,
        dataset_name: Optional[str] = None,
    ) -> list[SensorReading]:
        q = db.query(SensorReading).filter(SensorReading.route_id == route_id)
        if dataset_name:
            q = q.filter(SensorReading.dataset_name == dataset_name)
        return q.order_by(SensorReading.recorded_at.asc()).all()

    @staticmethod
    def list_datasets(db: Session, route_id: int) -> list[dict]:
        """Return distinct dataset_name + count per route, for UI dropdowns."""
        rows = (
            db.query(
                SensorReading.dataset_name,
                func.count(SensorReading.id).label("count"),
                func.min(SensorReading.recorded_at).label("first_at"),
                func.max(SensorReading.recorded_at).label("last_at"),
            )
            .filter(SensorReading.route_id == route_id)
            .group_by(SensorReading.dataset_name)
            .all()
        )
        return [
            {
                "dataset_name": r.dataset_name,
                "count": r.count,
                "first_at": r.first_at,
                "last_at": r.last_at,
            }
            for r in rows
        ]

    @staticmethod
    def delete_dataset(db: Session, route_id: int, dataset_name: str) -> int:
        deleted = (
            db.query(SensorReading)
            .filter(
                SensorReading.route_id == route_id,
                SensorReading.dataset_name == dataset_name,
            )
            .delete(synchronize_session=False)
        )
        db.commit()
        return deleted
