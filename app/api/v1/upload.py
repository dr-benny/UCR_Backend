"""Upload-based analysis endpoints — user provides their own images."""

from __future__ import annotations

import json
import logging
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.schemas import AnalysisResponse
from app.services.analysis_service import (
    ALLOWED_MIME_TYPES,
    AnalysisInput,
    analyze_from_upload,
    validate_mime,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["upload"])


# ── Single ────────────────────────────────────────────────────

@router.post(
    "/analyze/upload",
    response_model=AnalysisResponse,
    status_code=201,
    summary="Analyze a single uploaded image",
)
async def analyze_upload_single(
    file: UploadFile = File(..., description="Street-level image (JPEG/PNG/WebP)"),
    latitude: float = Form(..., description="Latitude of the location"),
    longitude: float = Form(..., description="Longitude of the location"),
    heading: Optional[float] = Form(None, description="Camera heading (0-360)"),
    pitch: float = Form(0, description="Camera pitch (-90 to 90)"),
    fov: float = Form(90, description="Field of view (10-120)"),
    route_id: Optional[int] = Form(None, description="Link to a route ID"),
    order_index: int = Form(0, description="Order within the route"),
    db: Session = Depends(get_db),
):
    """Analyze a **single user-uploaded** image with its GPS coordinates."""
    mime = file.content_type or "image/jpeg"
    try:
        validate_mime(mime)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    img_bytes = await file.read()
    if not img_bytes:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    inp = AnalysisInput(
        latitude=latitude,
        longitude=longitude,
        heading=heading,
        pitch=pitch,
        fov=fov,
        route_id=route_id,
        order_index=order_index,
    )

    try:
        record = await analyze_from_upload(
            db, inp, img_bytes, mime_type=mime, original_filename=file.filename,
        )
    except Exception as exc:
        logger.exception("Gemini analysis failed for uploaded image")
        raise HTTPException(status_code=502, detail=f"AI analysis failed: {exc}")

    return AnalysisResponse.from_orm_model(record)


# ── Batch ─────────────────────────────────────────────────────

@router.post(
    "/analyze/upload/batch",
    response_model=list[AnalysisResponse],
    status_code=201,
    summary="Analyze multiple uploaded images with optimized parameters",
)
async def analyze_upload_batch(
    files: list[UploadFile] = File(..., description="One or more street-level images"),
    metadata: str = Form(
        ...,
        description=(
            'JSON array of coordinates. Example: '
            '[{"latitude":13.75,"longitude":100.50}, ...]'
        ),
    ),
    route_id: Optional[int] = Form(None, description="Global route ID for this batch"),
    db: Session = Depends(get_db),
):
    """
    Analyze **multiple user-uploaded** images.

    - **route_id**: If provided at the top level, all images use this route.
    - **metadata**: Only latitude/longitude required. Specific route_id/order_index inside here will override global values.
    """
    # ── Validate metadata ─────────────────────────────────────
    try:
        meta_list: list[dict] = json.loads(metadata)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON in 'metadata' field")

    if len(files) != len(meta_list):
        raise HTTPException(
            status_code=400,
            detail=f"Number of files ({len(files)}) ≠ metadata entries ({len(meta_list)})",
        )
    if len(files) > 20:
        raise HTTPException(status_code=400, detail="Maximum 20 images per batch request")

    # ── Process each file ─────────────────────────────────────
    results: list[AnalysisResponse] = []
    errors: list[dict] = []

    for idx, (file, meta) in enumerate(zip(files, meta_list)):
        try:
            lat = meta.get("latitude")
            lng = meta.get("longitude")
            if lat is None or lng is None:
                raise ValueError(f"metadata[{idx}] missing coordinates")

            mime = file.content_type or "image/jpeg"
            validate_mime(mime)

            img_bytes = await file.read()
            if not img_bytes:
                raise ValueError(f"File #{idx} is empty")

            # logic: ใช้ค่าจาก meta ถ้ามี, ถ้าไม่มีใช้ global (route_id) หรือ sequence (idx)
            inp = AnalysisInput(
                latitude=float(lat),
                longitude=float(lng),
                heading=meta.get("heading"),
                pitch=meta.get("pitch", 0),
                fov=meta.get("fov", 90),
                route_id=meta.get("route_id") or route_id,
                order_index=meta.get("order_index", idx),
            )

            record = await analyze_from_upload(
                db, inp, img_bytes, mime_type=mime, original_filename=file.filename,
            )
            results.append(AnalysisResponse.from_orm_model(record))

        except Exception as exc:
            logger.exception("Batch upload: failed on file #%d", idx)
            errors.append({"index": idx, "error": str(exc)})

    if errors:
        logger.warning("Batch upload completed with %d error(s): %s", len(errors), errors)

    return results
