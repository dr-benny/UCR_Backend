"""
Sensor reading model — time-series environmental measurements along a route.

One reading = one point in time + space with up to 4 measurements.
A route can have multiple datasets (e.g. "morning_walk", "afternoon_walk")
collected by different sensors or sessions.
"""

from datetime import datetime, timezone

from geoalchemy2 import Geometry
from geoalchemy2.shape import to_shape
from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from app.db.database import Base


class SensorReading(Base):
    __tablename__ = "sensor_readings"

    id = Column(Integer, primary_key=True, index=True)

    route_id = Column(
        Integer,
        ForeignKey("survey_routes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    route = relationship("SurveyRoute", back_populates="sensor_readings")

    # Multiple sensor sessions can coexist in one route (e.g. morning vs afternoon walks)
    dataset_name = Column(String(128), nullable=False, index=True)

    geom = Column(Geometry("POINT", srid=4326), nullable=False)
    recorded_at = Column(DateTime(timezone=True), nullable=False, index=True)

    # All optional — sensor packs vary
    temp_c = Column(Float, nullable=True)
    humidity_pct = Column(Float, nullable=True)
    lux = Column(Float, nullable=True)
    uv_index = Column(Float, nullable=True)

    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    @property
    def latitude(self) -> float:
        return to_shape(self.geom).y

    @property
    def longitude(self) -> float:
        return to_shape(self.geom).x
