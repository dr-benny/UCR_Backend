from typing import Optional
from datetime import datetime, timezone
from sqlalchemy import (
    Column,
    Integer,
    Float,
    Text,
    DateTime,
    ForeignKey,
)
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import JSONB
from geoalchemy2 import Geometry
from geoalchemy2.shape import to_shape
from app.db.database import Base

class StreetAnalysis(Base):
    """Stores a single street-view analysis result."""

    __tablename__ = "street_analyses"

    id = Column(Integer, primary_key=True, index=True)

    # ── Route Grouping ─────────────────────────────────────────
    route_id = Column(Integer, ForeignKey("survey_routes.id", ondelete="CASCADE"), nullable=True, index=True)
    order_index = Column(Integer, default=0) 
    route = relationship("SurveyRoute", back_populates="analyses")

    # ── Location (PostGIS Point) ───────────────────────────────
    geom = Column(Geometry("POINT", srid=4326), nullable=False)

    @property
    def latitude(self) -> float:
        """Extracts latitude from the geom point."""
        return to_shape(self.geom).y

    @property
    def longitude(self) -> float:
        """Extracts longitude from the geom point."""
        return to_shape(self.geom).x

    heading = Column(Float, nullable=True)
    pitch = Column(Float, default=0)
    fov = Column(Float, default=90)

    # ── Image ─────────────────────────────────────────────────
    streetview_image_url = Column(Text, nullable=True)
    image_path = Column(Text, nullable=True) 

    # ── AI Analysis Data (Structured JSON) ──────────────────
    urban_morphology = Column(JSONB, nullable=True)
    vegetation = Column(JSONB, nullable=True)
    surface_and_flood = Column(JSONB, nullable=True)
    health_livability = Column(JSONB, nullable=True)

    # ── Context Metadata ─────────────────────────────────────
    scene_description = Column(Text, nullable=True)
    observed_features = Column(JSONB, nullable=True)
    reference_objects = Column(JSONB, nullable=True)

    # ── New structured outputs ───────────────────────────────
    evidence = Column(JSONB, nullable=True)
    confidence_scores = Column(JSONB, nullable=True)

    # ── Raw AI Output (Backup) ───────────────────────────────
    raw_ai_response = Column(JSONB, nullable=True)

    @property
    def heat_risk_proxy(self) -> Optional[str]:
        if self.confidence_scores:
            score = self.confidence_scores.get("urban_morphology", 0)
            return "high" if score > 0.8 else "medium"
        return None

    @property
    def walkway_width_m(self) -> Optional[float]:
        if self.urban_morphology:
             val = self.urban_morphology.get("street_width")
             if isinstance(val, (int, float)): return float(val)
        return None

    @property
    def sky_view_factor_est(self) -> Optional[float]:
        if self.urban_morphology:
            val = self.urban_morphology.get("sky_view_factor")
            if isinstance(val, (int, float)): return float(val)
        return None

    @property
    def trash_bin_status(self) -> Optional[str]:
        if self.health_livability:
            return self.health_livability.get("trash_bin_presence")
        return None

    # ── Timestamps ────────────────────────────────────────────
    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
