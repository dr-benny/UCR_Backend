from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel


class JobProgress(BaseModel):
    current: int
    total: int
    percent: int = 0


class JobResponse(BaseModel):
    id: str
    status: str
    progress: JobProgress
    results: Optional[list[dict[str, Any]]] = None
    failed: Optional[list[dict[str, Any]]] = None
    error: Optional[str] = None
