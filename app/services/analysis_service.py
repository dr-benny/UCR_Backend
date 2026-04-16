"""
Analysis Service — central orchestrator for the image-analysis pipeline.

All business logic lives here.  Routers only handle HTTP concerns
(validation, serialisation, status codes) and delegate to this module.
"""

from __future__ import annotations

import logging
import os
import uuid
from dataclasses import dataclass
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.core.config import settings
from app.dao.analysis_dao import AnalysisDAO
from app.models import StreetAnalysis
from app.services.ai_engines import get_engine
from app.services.google_streetview import check_streetview_coverage, fetch_streetview_image

logger = logging.getLogger(__name__)

# ── Allowed upload MIME types ─────────────────────────────────
ALLOWED_MIME_TYPES: set[str] = {"image/jpeg", "image/png", "image/webp"}


# ── Value object shared across every pipeline ─────────────────
@dataclass
class AnalysisInput:
    """Common parameters fed into every analysis pipeline."""
    latitude: float
    longitude: float
    heading: Optional[float] = None
    pitch: float = 0
    fov: float = 90
    route_id: Optional[int] = None
    order_index: int = 0


# ── Internal helpers ──────────────────────────────────────────

def _build_dao_data(
    ai_result: dict[str, Any],
    *,
    image_url: str,
    image_path: str,
    inp: AnalysisInput,
) -> dict[str, Any]:
    """
    Build the flat dict that AnalysisDAO.create_analysis expects.

    Centralises the mapping so that every endpoint uses the same structure.
    """
    return {
        "heading": inp.heading,
        "pitch": inp.pitch,
        "fov": inp.fov,
        "image_url": image_url,
        "image_path": image_path,
        **ai_result,
        "raw_ai_response": ai_result,
    }


def _persist(
    db: Session,
    dao_data: dict[str, Any],
    inp: AnalysisInput,
) -> StreetAnalysis:
    """Persist an analysis record through the DAO."""
    return AnalysisDAO.create_analysis(
        db=db,
        analysis_data=dao_data,
        latitude=inp.latitude,
        longitude=inp.longitude,
        route_id=inp.route_id,
        order_index=inp.order_index,
    )


def save_upload(img_bytes: bytes, original_filename: str | None = None) -> str:
    """Save uploaded image bytes to IMAGE_DIR and return the local path."""
    os.makedirs(settings.IMAGE_DIR, exist_ok=True)
    ext = os.path.splitext(original_filename or "upload.jpg")[1] or ".jpg"
    filename = f"upload_{uuid.uuid4().hex[:12]}{ext}"
    path = os.path.join(settings.IMAGE_DIR, filename)
    with open(path, "wb") as f:
        f.write(img_bytes)
    return path


def validate_mime(mime: str) -> None:
    """Raise ValueError when the MIME type is not whitelisted."""
    if mime not in ALLOWED_MIME_TYPES:
        raise ValueError(
            f"Unsupported image type '{mime}'. "
            f"Allowed: {', '.join(sorted(ALLOWED_MIME_TYPES))}"
        )


# ── Public pipeline methods ───────────────────────────────────

async def analyze_from_streetview(
    db: Session,
    inp: AnalysisInput,
    model_name: str | None = None,
) -> StreetAnalysis:
    """
    Full Street View pipeline:
    1. Check for duplicates (Nearby analysis in same route)
    2. Check coverage
    3. Fetch image
    4. Analyse with AI engine (configurable)
    5. Persist
    """
    # 0 — Duplicate Detection
    # if inp.route_id:
    #     existing = AnalysisDAO.find_nearby_analysis(
    #         db, inp.latitude, inp.longitude, inp.route_id
    #     )
    #     if existing:
    #         logger.info("Duplicate found for Route %s at (%s, %s). Returning existing analysis #%s.", 
    #                     inp.route_id, inp.latitude, inp.longitude, existing.id)
    #         return existing

    # 1 — Coverage
    has_coverage = await check_streetview_coverage(inp.latitude, inp.longitude)
    if not has_coverage:
        raise LookupError(
            f"No Street View coverage at ({inp.latitude}, {inp.longitude})"
        )

    # 2 — Fetch image
    _, local_path = await fetch_streetview_image(
        latitude=inp.latitude,
        longitude=inp.longitude,
        heading=inp.heading,
        pitch=inp.pitch,
        fov=int(inp.fov),
    )

    # 3 — AI Analysis (LEGO: uses whichever engine is configured)
    engine = get_engine(model_name)
    ai_result = await engine.analyze_image(local_path)

    # 4 — Persist
    dao_data = _build_dao_data(
        ai_result, image_url="LOCAL_ONLY", image_path=local_path, inp=inp,
    )
    return _persist(db, dao_data, inp)


async def analyze_from_upload(
    db: Session,
    inp: AnalysisInput,
    img_bytes: bytes,
    mime_type: str = "image/jpeg",
    original_filename: str | None = None,
    model_name: str | None = None,
) -> StreetAnalysis:
    """
    Upload pipeline:
    1. Check for duplicates (Nearby analysis in same route)
    2. Save image to disk
    3. Analyse with AI engine (configurable)
    4. Persist
    """
    # 0 — Duplicate Detection
    # if inp.route_id:
    #     existing = AnalysisDAO.find_nearby_analysis(
    #         db, inp.latitude, inp.longitude, inp.route_id
    #     )
    #     if existing:
    #         logger.info("Duplicate found for Route %s at (%s, %s). Returning existing analysis #%s.", 
    #                     inp.route_id, inp.latitude, inp.longitude, existing.id)
    #         return existing

    local_path = save_upload(img_bytes, original_filename)

    # AI Analysis (LEGO: uses whichever engine is configured)
    engine = get_engine(model_name)
    ai_result = await engine.analyze_image_bytes(img_bytes, mime_type=mime_type)

    dao_data = _build_dao_data(
        ai_result, image_url="UPLOADED", image_path=local_path, inp=inp,
    )
    return _persist(db, dao_data, inp)



async def reanalyze_record(
    db: Session,
    record: StreetAnalysis,
    model_name: str | None = None,
) -> StreetAnalysis:
    """
    Re-analysis pipeline:
    1. Read the existing image from disk
    2. Send to AI engine (configurable)
    3. Update the same DB record with fresh AI results

    Raises:
        FileNotFoundError: if the saved image no longer exists on disk.
    """
    image_path = record.image_path
    if not image_path or not os.path.isfile(image_path):
        raise FileNotFoundError(
            f"Image file not found for analysis #{record.id}: {image_path}"
        )

    engine = get_engine(model_name)
    ai_result = await engine.analyze_image(image_path)
    return AnalysisDAO.update_ai_result(db, record, ai_result)

