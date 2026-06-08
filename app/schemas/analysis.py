from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class GPSEvidence(BaseModel):
    metadata_checked: bool = False
    raw_latitude: Optional[str] = None
    raw_longitude: Optional[str] = None
    gps_ref: Optional[str] = None
    conversion_notes: Optional[str] = None


class ReferenceScale(BaseModel):
    type: str = "none"
    assumed_height_m: float = 1.70
    position: Optional[str] = None
    same_depth: Optional[bool] = None
    quality: Optional[str] = None
    notes: Optional[str] = None


class BoundarySide(BaseModel):
    boundary_type: str = "unclear"
    wall_height_m: float = 0
    structure_height_m: float = 0
    effective_enclosure_height_m: float = 0
    opening_ratio: float = 0
    setback_m: Optional[float] = None
    notes: Optional[str] = None


class MorphologyAnalysis(BaseModel):
    image_id: str
    observation_id: str
    street_id: str
    point_order: int
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    gps_status: str
    gps_evidence: GPSEvidence
    reference_scale: ReferenceScale
    street_width_m: Optional[float] = None
    left: BoundarySide
    right: BoundarySide
    roof_cover_ratio: float = 0
    shade_ratio_visible: float = 0
    obstruction_ratio: float = 0
    hw_effective_left: Optional[float] = None
    hw_effective_right: Optional[float] = None
    hw_effective_avg: Optional[float] = None
    enclosure_class: str = "unknown"
    confidence_score: float = 0.0
    evidence_notes: Optional[str] = None
