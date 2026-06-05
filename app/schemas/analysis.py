from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class AnalyzeRequest(BaseModel):
    latitude: float
    longitude: float
    heading: Optional[float] = None
    pitch: float = 0
    fov: float = 90
