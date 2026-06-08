from __future__ import annotations

import logging
import os
import uuid
from typing import Any

from app.core.config import settings
from app.services.ai_engines import get_engine

logger = logging.getLogger(__name__)

ALLOWED_MIME_TYPES: set[str] = {"image/jpeg", "image/png", "image/webp"}


def validate_mime(mime: str) -> None:
    if mime not in ALLOWED_MIME_TYPES:
        raise ValueError(
            f"Unsupported image type '{mime}'. Allowed: {', '.join(sorted(ALLOWED_MIME_TYPES))}"
        )


def save_image(img_bytes: bytes, original_filename: str | None = None) -> str:
    os.makedirs(settings.IMAGE_DIR, exist_ok=True)
    ext = os.path.splitext(original_filename or "upload.jpg")[1] or ".jpg"
    path = os.path.join(settings.IMAGE_DIR, f"{uuid.uuid4().hex[:12]}{ext}")
    with open(path, "wb") as f:
        f.write(img_bytes)
    return path


async def analyze_image_file(
    path: str,
    engine: str | None = None,
    model: str | None = None,
) -> dict[str, Any]:
    return await get_engine(engine, model).analyze_image(path)


async def analyze_image_bytes(
    img_bytes: bytes,
    mime_type: str = "image/jpeg",
    engine: str | None = None,
    model: str | None = None,
) -> dict[str, Any]:
    return await get_engine(engine, model).analyze_image_bytes(img_bytes, mime_type=mime_type)
