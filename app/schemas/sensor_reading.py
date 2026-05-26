"""Pydantic schemas for sensor readings."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class SensorReadingIn(BaseModel):
    """Single reading on JSON ingest."""

    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    recorded_at: datetime
    temp_c: Optional[float] = None
    humidity_pct: Optional[float] = None
    lux: Optional[float] = None
    uv_index: Optional[float] = None


class SensorBulkUpload(BaseModel):
    """Bulk JSON upload payload."""

    dataset_name: str = Field(..., min_length=1, max_length=128)
    readings: list[SensorReadingIn] = Field(..., min_length=1, max_length=100_000)


class SensorReadingOut(BaseModel):
    id: int
    route_id: int
    dataset_name: str
    latitude: float
    longitude: float
    recorded_at: datetime
    temp_c: Optional[float] = None
    humidity_pct: Optional[float] = None
    lux: Optional[float] = None
    uv_index: Optional[float] = None

    @classmethod
    def from_orm_model(cls, r) -> "SensorReadingOut":
        return cls(
            id=r.id,
            route_id=r.route_id,
            dataset_name=r.dataset_name,
            latitude=r.latitude,
            longitude=r.longitude,
            recorded_at=r.recorded_at,
            temp_c=r.temp_c,
            humidity_pct=r.humidity_pct,
            lux=r.lux,
            uv_index=r.uv_index,
        )


class DatasetSummary(BaseModel):
    dataset_name: str
    count: int
    first_at: datetime
    last_at: datetime


class BulkUploadResult(BaseModel):
    inserted: int
    dataset_name: str
    route_id: int
