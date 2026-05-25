"""Pydantic schemas for the async job queue."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class JobPoint(BaseModel):
    """One coordinate to analyze as part of a route job."""
    latitude: float
    longitude: float
    heading: Optional[float] = None
    pitch: float = 0
    fov: float = 90


class RouteJobCreate(BaseModel):
    """Request body for POST /api/jobs/route."""
    name: Optional[str] = Field(None, description="Survey route name")
    description: Optional[str] = Field(None, description="Survey route description")
    points: list[JobPoint] = Field(..., min_length=1, max_length=200)
    concurrency: int = Field(5, ge=1, le=10, description="Parallel Gemini calls (1–10)")


class JobProgress(BaseModel):
    current: int
    total: int


class JobResponse(BaseModel):
    """Response body for POST /api/jobs/route and GET /api/jobs/{id}."""
    id: str
    job_type: str
    status: str
    progress: JobProgress
    route_id: Optional[int] = None
    result: Optional[dict[str, Any]] = None
    error: Optional[str] = None
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    model_config = {"from_attributes": True}

    @classmethod
    def from_orm_model(cls, job) -> "JobResponse":
        return cls(
            id=job.id,
            job_type=job.job_type,
            status=job.status,
            progress=JobProgress(
                current=job.progress_current or 0,
                total=job.progress_total or 0,
            ),
            route_id=job.route_id,
            result=job.result_data,
            error=job.error,
            created_at=job.created_at,
            started_at=job.started_at,
            completed_at=job.completed_at,
        )
