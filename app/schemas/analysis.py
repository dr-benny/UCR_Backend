from __future__ import annotations
from datetime import datetime
from typing import Any, Optional, Union
from pydantic import BaseModel, Field

class UrbanMorphology(BaseModel):
    street_width: Optional[Union[str, float]] = None
    building_height_est_m: Optional[Union[str, float]] = None
    height_width_ratio: Optional[Union[str, float]] = None
    sky_view_factor: Optional[Union[str, float]] = None
    road_slope: Optional[Union[str, float]] = None
    sidewalk_height: Optional[Union[str, float]] = None

class Vegetation(BaseModel):
    green_view_index: Optional[Union[str, float]] = None
    tree_canopy_coverage: Optional[Union[str, float]] = None
    shade_fraction: Optional[Union[str, float]] = None

class SurfaceAndFlood(BaseModel):
    surface_material: Optional[Union[str, float]] = None
    impervious_surface_ratio: Optional[Union[str, float]] = None
    drainage_infrastructure_presence: Optional[Union[str, float]] = None
    drainage_obstruction: Optional[Union[str, float]] = None
    water_body_proximity: Optional[Union[str, float]] = None

class HealthLivability(BaseModel):
    walkability_obstruction: Optional[Union[str, float]] = None
    waste_accumulation: Optional[Union[str, float]] = None
    lighting_infrastructure: Optional[Union[str, float]] = None

class AnalyzeRequest(BaseModel):
    route_id: Optional[int] = Field(None, description="Link this analysis to a specific route ID")
    order_index: int = Field(0, description="Order of this point within the route")
    latitude: float = Field(..., description="Latitude of the location")
    longitude: float = Field(..., description="Longitude of the location")
    heading: Optional[float] = Field(None, description="Camera heading (0-360). None = auto.")
    pitch: float = Field(0, description="Camera pitch (-90 to 90)")
    fov: float = Field(90, description="Field of view (10-120)")

class AnalysisResponse(BaseModel):
    id: int
    route_id: Optional[int] = None
    order_index: int = 0
    latitude: float
    longitude: float
    heading: Optional[float] = None
    pitch: float
    fov: float
    streetview_image_url: Optional[str] = None
    image_path: Optional[str] = None
    scene_description: Optional[str] = None
    observed_features: list[Any] = []
    reference_objects: list[Any] = []
    urban_morphology: UrbanMorphology
    vegetation: Vegetation
    surface_and_flood: SurfaceAndFlood
    health_livability: HealthLivability
    evidence: dict[str, Any] = {}
    confidence_scores: dict[str, Any] = {}
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

    @classmethod
    def from_orm_model(cls, obj) -> "AnalysisResponse":
        return cls(
            id=obj.id,
            route_id=obj.route_id,
            order_index=obj.order_index,
            latitude=obj.latitude,
            longitude=obj.longitude,
            heading=obj.heading,
            pitch=obj.pitch,
            fov=obj.fov,
            streetview_image_url=obj.streetview_image_url,
            image_path=obj.image_path,
            urban_morphology=UrbanMorphology.model_validate(obj.urban_morphology or {}),
            vegetation=Vegetation.model_validate(obj.vegetation or {}),
            surface_and_flood=SurfaceAndFlood.model_validate(obj.surface_and_flood or {}),
            health_livability=HealthLivability.model_validate(obj.health_livability or {}),
            scene_description=obj.scene_description,
            observed_features=obj.observed_features or [],
            reference_objects=obj.reference_objects or [],
            evidence=obj.evidence or {},
            confidence_scores=obj.confidence_scores or {},
            created_at=obj.created_at,
            updated_at=obj.updated_at,
        )

class AnalysisListItem(BaseModel):
    id: int
    route_id: Optional[int] = None
    order_index: int = 0
    latitude: float
    longitude: float
    heading: Optional[float] = None
    scene_description: Optional[str] = None
    urban_morphology: Optional[dict[str, Any]] = None
    vegetation: Optional[dict[str, Any]] = None
    surface_and_flood: Optional[dict[str, Any]] = None
    health_livability: Optional[dict[str, Any]] = None
    confidence_scores: Optional[dict[str, Any]] = None
    created_at: datetime
    model_config = {"from_attributes": True}

    @classmethod
    def from_orm_model(cls, obj) -> "AnalysisListItem":
        return cls(
            id=obj.id,
            route_id=obj.route_id,
            order_index=obj.order_index,
            latitude=obj.latitude,
            longitude=obj.longitude,
            heading=obj.heading,
            scene_description=obj.scene_description,
            urban_morphology=obj.urban_morphology,
            vegetation=obj.vegetation,
            surface_and_flood=obj.surface_and_flood,
            health_livability=obj.health_livability,
            confidence_scores=obj.confidence_scores,
            created_at=obj.created_at,
        )
