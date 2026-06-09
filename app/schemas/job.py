from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel


class JobProgress(BaseModel):
    current: int
    total: int
    percent: int = 0
    active_files: list[str] = []      # filenames currently being processed
    last_completed: Optional[str] = None  # most recently finished filename


class JobResponse(BaseModel):
    id: str
    status: str
    progress: JobProgress
    submitted_at: Optional[float] = None
    engine: Optional[str] = None
    model: Optional[str] = None
    samples: Optional[int] = None
    prompt_id: Optional[str] = None
    results: Optional[list[dict[str, Any]]] = None
    failed: Optional[list[dict[str, Any]]] = None
    error: Optional[str] = None


class JobListResponse(BaseModel):
    jobs: list[JobResponse]
    total: int
