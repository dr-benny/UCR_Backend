from datetime import datetime, timezone
from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    DateTime,
)
from sqlalchemy.orm import relationship
from app.db.database import Base

class SurveyRoute(Base):
    """Stores a conceptual route or path consisting of multiple analysis points."""

    __tablename__ = "survey_routes"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=True)
    description = Column(Text, nullable=True)

    # ── Timestamps ────────────────────────────────────────────
    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # ── Relationships ─────────────────────────────────────────
    analyses = relationship(
        "StreetAnalysis", 
        back_populates="route", 
        cascade="all, delete-orphan", 
        order_by="StreetAnalysis.order_index"
    )
