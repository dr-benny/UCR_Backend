"""
Async Job model — tracks long-running analysis work.

Submission flow:
  client POSTs job → row created with status="pending" → asyncio.create_task
  background coroutine flips it to "processing" → updates progress per point
  → final "done" with result_data, or "failed" with error.

Why a DB row instead of in-memory dict:
  - Survives server restarts (well, the row does; the running task does not).
  - Multiple workers/instances can share state later.
  - Clients poll by id and always get a consistent answer.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB

from app.db.database import Base


def _new_job_id() -> str:
    return uuid.uuid4().hex


class Job(Base):
    """One async analysis job."""

    __tablename__ = "jobs"

    # UUID hex (32 chars) — avoids exposing sequential IDs and lets clients
    # generate IDs upfront if they ever need to.
    id = Column(String(32), primary_key=True, default=_new_job_id)

    job_type = Column(String(32), nullable=False, index=True)
    status = Column(String(16), nullable=False, default="pending", index=True)

    request_data = Column(JSONB, nullable=False)
    result_data = Column(JSONB, nullable=True)
    error = Column(Text, nullable=True)

    progress_current = Column(Integer, default=0, nullable=False)
    progress_total = Column(Integer, default=0, nullable=False)

    # Set once a SurveyRoute is created during processing
    route_id = Column(
        Integer, ForeignKey("survey_routes.id", ondelete="SET NULL"), nullable=True
    )

    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
