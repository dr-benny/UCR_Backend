from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from app.core.auth import require_api_key
from app.core.config import settings
from app.services import prompt_store, quota
from app.services.ai_engines import get_engine
from app.services.analysis_service import analyze_image_bytes, read_capped, validate_mime
from app.services.redis_client import get_redis

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["analyze"])


def _validate_samples(samples: int | None) -> None:
    if samples is not None and samples > settings.MAX_ANALYSIS_SAMPLES:
        raise HTTPException(
            status_code=400,
            detail=f"samples exceeds max of {settings.MAX_ANALYSIS_SAMPLES}",
        )


def _resolve_prompt(prompt_id: str | None) -> str | None:
    """Look up a stored prompt's text, turning an unknown id into a 400."""
    try:
        return prompt_store.resolve_text(prompt_id)
    except KeyError:
        raise HTTPException(status_code=400, detail=f"Unknown prompt_id '{prompt_id}'")


@router.post("/analyze")
async def analyze_single(
    file: UploadFile = File(..., description="Street-level image (JPEG/PNG/WebP)"),
    engine: str | None = Form(None, description="AI engine name (e.g. 'gemini')"),
    model: str | None = Form(None, description="Model override (e.g. 'gemini-2.5-pro')"),
    samples: int | None = Form(None, ge=1, description="Self-consistency samples (overrides default)"),
    prompt_id: str | None = Form(None, description="Stored prompt to use (see /api/prompts); defaults to the built-in"),
    key: dict[str, Any] | None = Depends(require_api_key),
) -> dict[str, Any]:
    """Analyze a single image synchronously — returns AI result immediately."""
    if engine or model:
        try:
            get_engine(engine, model)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    max_samples = key.get("max_samples") if key else None
    if max_samples is not None:
        effective_samples = min(samples or settings.ANALYSIS_SAMPLES, max_samples)
    else:
        _validate_samples(samples)
        effective_samples = samples or settings.ANALYSIS_SAMPLES

    if key is not None:
        await quota.check_and_consume(get_redis(), key, effective_samples)

    prompt_text = _resolve_prompt(prompt_id)

    mime = file.content_type or "image/jpeg"
    try:
        validate_mime(mime)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    try:
        img_bytes = await read_capped(file, settings.MAX_IMAGE_BYTES)
    except ValueError:
        mb = settings.MAX_IMAGE_BYTES // (1024 * 1024)
        raise HTTPException(status_code=400, detail=f"File exceeds {mb} MB limit")
    if not img_bytes:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    try:
        result = await analyze_image_bytes(
            img_bytes, mime_type=mime, engine=engine, model=model, samples=effective_samples, prompt=prompt_text
        )
        result["filename"] = file.filename
        result["_engine"] = engine or settings.AI_ENGINE
        result["_model"] = model
        result["_prompt_id"] = prompt_id
        return result
    except Exception as exc:
        logger.exception("Analysis failed")
        raise HTTPException(status_code=502, detail=f"AI analysis failed: {exc}")
