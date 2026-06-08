from __future__ import annotations

import logging

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.core.config import settings
from app.schemas.analysis import MorphologyAnalysis
from app.services.ai_engines import get_engine
from app.services.analysis_service import analyze_image_bytes, validate_mime

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["analyze"])


@router.post("/analyze", response_model=MorphologyAnalysis)
async def analyze_single(
    file: UploadFile = File(..., description="Street-level image (JPEG/PNG/WebP)"),
    engine: str | None = Form(None, description="AI engine name (e.g. 'gemini')"),
    model: str | None = Form(None, description="Model override (e.g. 'gemini-2.5-pro')"),
) -> MorphologyAnalysis:
    """Analyze a single image synchronously — returns AI result immediately."""
    if engine or model:
        try:
            get_engine(engine, model)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    mime = file.content_type or "image/jpeg"
    try:
        validate_mime(mime)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    img_bytes = await file.read()
    if not img_bytes:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")
    if len(img_bytes) > settings.MAX_IMAGE_BYTES:
        mb = settings.MAX_IMAGE_BYTES // (1024 * 1024)
        raise HTTPException(status_code=400, detail=f"File exceeds {mb} MB limit")

    try:
        result = await analyze_image_bytes(img_bytes, mime_type=mime, engine=engine, model=model)
        return MorphologyAnalysis(**result)
    except Exception as exc:
        logger.exception("Analysis failed")
        raise HTTPException(status_code=502, detail=f"AI analysis failed: {exc}")
