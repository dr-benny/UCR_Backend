from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Optional

from app.services.ai_engines import get_engine
from app.services.google_streetview import check_streetview_coverage, fetch_streetview_image

logger = logging.getLogger(__name__)

ALLOWED_MIME_TYPES: set[str] = {"image/jpeg", "image/png", "image/webp"}


@dataclass
class AnalysisInput:
    latitude: float
    longitude: float
    heading: Optional[float] = None
    pitch: float = 0
    fov: float = 90


def validate_mime(mime: str) -> None:
    if mime not in ALLOWED_MIME_TYPES:
        raise ValueError(
            f"Unsupported image type '{mime}'. Allowed: {', '.join(sorted(ALLOWED_MIME_TYPES))}"
        )


async def analyze_from_streetview(
    inp: AnalysisInput,
    model_name: str | None = None,
) -> dict[str, Any]:
    has_coverage = await check_streetview_coverage(inp.latitude, inp.longitude)
    if not has_coverage:
        raise LookupError(f"No Street View coverage at ({inp.latitude}, {inp.longitude})")

    _, local_path = await fetch_streetview_image(
        latitude=inp.latitude,
        longitude=inp.longitude,
        heading=inp.heading,
        pitch=inp.pitch,
        fov=int(inp.fov),
    )

    engine = get_engine(model_name)
    return await engine.analyze_image(local_path)


async def analyze_from_upload(
    img_bytes: bytes,
    mime_type: str = "image/jpeg",
    model_name: str | None = None,
) -> dict[str, Any]:
    engine = get_engine(model_name)
    return await engine.analyze_image_bytes(img_bytes, mime_type=mime_type)
