from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, File, HTTPException, UploadFile

from app.services.analysis_service import analyze_image_bytes, validate_mime

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["analyze"])


@router.post("/analyze")
async def analyze_single(
    file: UploadFile = File(..., description="Street-level image (JPEG/PNG/WebP)"),
) -> dict[str, Any]:
    """Analyze a single image synchronously — returns AI result immediately."""
    mime = file.content_type or "image/jpeg"
    try:
        validate_mime(mime)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    img_bytes = await file.read()
    if not img_bytes:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    try:
        return await analyze_image_bytes(img_bytes, mime_type=mime)
    except Exception as exc:
        logger.exception("Analysis failed")
        raise HTTPException(status_code=502, detail=f"AI analysis failed: {exc}")
