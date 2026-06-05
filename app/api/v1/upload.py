from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.services.analysis_service import ALLOWED_MIME_TYPES, analyze_from_upload, validate_mime

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["upload"])


@router.post("/analyze/upload")
async def analyze_upload_single(
    file: UploadFile = File(...),
) -> dict[str, Any]:
    mime = file.content_type or "image/jpeg"
    try:
        validate_mime(mime)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    img_bytes = await file.read()
    if not img_bytes:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    try:
        return await analyze_from_upload(img_bytes, mime_type=mime)
    except Exception as exc:
        logger.exception("Upload analysis failed")
        raise HTTPException(status_code=502, detail=f"AI analysis failed: {exc}")


@router.post("/analyze/upload/batch")
async def analyze_upload_batch(
    files: list[UploadFile] = File(...),
    metadata: str = Form(..., description='JSON array: [{"latitude":13.7,"longitude":100.5}, ...]'),
    concurrency: int = Form(5, ge=1, le=10),
) -> list[dict[str, Any]]:
    try:
        meta_list: list[dict] = json.loads(metadata)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON in 'metadata'")

    if len(files) != len(meta_list):
        raise HTTPException(
            status_code=400,
            detail=f"files ({len(files)}) ≠ metadata entries ({len(meta_list)})",
        )
    if len(files) > 20:
        raise HTTPException(status_code=400, detail="Maximum 20 images per batch")

    file_contents: list[tuple[bytes, str]] = await asyncio.gather(*[_read(f) for f in files])

    sem = asyncio.Semaphore(concurrency)

    async def _one(i: int, img_bytes: bytes, mime: str) -> dict[str, Any] | None:
        async with sem:
            try:
                validate_mime(mime)
                return await analyze_from_upload(img_bytes, mime_type=mime)
            except Exception:
                logger.warning("Batch upload: file #%d failed", i)
                return None

    raw = await asyncio.gather(*[_one(i, b, m) for i, (b, m) in enumerate(file_contents)])
    return [r for r in raw if r is not None]


async def _read(file: UploadFile) -> tuple[bytes, str]:
    mime = file.content_type or "image/jpeg"
    return await file.read(), mime
