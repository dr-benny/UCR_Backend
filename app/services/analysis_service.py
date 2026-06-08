from __future__ import annotations

import logging
import mimetypes
import os
import uuid
from typing import TYPE_CHECKING, Any

from app.core.config import settings
from app.services.ai_engines import get_engine

if TYPE_CHECKING:
    from fastapi import UploadFile

logger = logging.getLogger(__name__)

ALLOWED_MIME_TYPES: set[str] = {"image/jpeg", "image/png", "image/webp"}

_READ_CHUNK = 1024 * 1024  # 1 MB


def validate_mime(mime: str) -> None:
    if mime not in ALLOWED_MIME_TYPES:
        raise ValueError(
            f"Unsupported image type '{mime}'. Allowed: {', '.join(sorted(ALLOWED_MIME_TYPES))}"
        )


async def read_capped(file: UploadFile, max_bytes: int) -> bytes:
    """
    Read an upload in chunks, aborting as soon as it exceeds max_bytes (P2).

    Avoids loading a huge (e.g. multi-GB) upload fully into RAM just to reject
    it afterwards. Peak memory is bounded to max_bytes + one chunk.

    Raises ValueError if the stream exceeds the limit.
    """
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(_READ_CHUNK)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise ValueError("File exceeds size limit")
        chunks.append(chunk)
    return b"".join(chunks)


def save_image(img_bytes: bytes, original_filename: str | None = None) -> str:
    os.makedirs(settings.IMAGE_DIR, exist_ok=True)
    ext = os.path.splitext(original_filename or "upload.jpg")[1] or ".jpg"
    path = os.path.join(settings.IMAGE_DIR, f"{uuid.uuid4().hex[:12]}{ext}")
    with open(path, "wb") as f:
        f.write(img_bytes)
    return path


async def analyze_image_file(
    path: str,
    mime_type: str | None = None,
    engine: str | None = None,
    model: str | None = None,
    samples: int | None = None,
) -> dict[str, Any]:
    # Fall back to the file extension (e.g. old jobs saved before mime was
    # tracked), then to JPEG. Never hardcode — Claude rejects mismatched media_type.
    mt = mime_type or mimetypes.guess_type(path)[0] or "image/jpeg"
    return await get_engine(engine, model).analyze_image(path, mime_type=mt, samples=samples)


async def analyze_image_bytes(
    img_bytes: bytes,
    mime_type: str = "image/jpeg",
    engine: str | None = None,
    model: str | None = None,
    samples: int | None = None,
) -> dict[str, Any]:
    return await get_engine(engine, model).analyze_image_bytes(
        img_bytes, mime_type=mime_type, samples=samples
    )
