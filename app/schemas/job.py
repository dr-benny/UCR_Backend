from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class JobPoint(BaseModel):
    latitude: float
    longitude: float
    heading: Optional[float] = None
    pitch: float = 0
    fov: float = 90


class RouteJobCreate(BaseModel):
    name: Optional[str] = None
    points: list[JobPoint] = Field(..., min_length=1, max_length=200)
    concurrency: int = Field(5, ge=1, le=10)


class JobProgress(BaseModel):
    current: int
    total: int
    percent: int = 0


class JobResponse(BaseModel):
    id: str
    status: str
    progress: JobProgress
    results: Optional[list[dict[str, Any]]] = None
    failed_points: Optional[list[dict[str, Any]]] = None
    error: Optional[str] = None
