"""Google Street View Static API integration."""

from __future__ import annotations

import os
import uuid
from pathlib import Path

import httpx

from app.core.config import settings


async def fetch_streetview_image(
    latitude: float,
    longitude: float,
    heading: float | None = None,
    pitch: float = 0,
    fov: int = 90,
) -> tuple[str, str]:
    """
    Download a Street View image and save it locally.

    Returns:
        (image_url, local_file_path)
    """
    # Build the API URL
    params: dict = {
        "size": settings.STREETVIEW_SIZE,
        "location": f"{latitude},{longitude}",
        "pitch": str(pitch),
        "fov": str(fov),
        "key": settings.GOOGLE_MAPS_API_KEY,
        "return_error_code": "true",
    }
    if heading is not None:
        params["heading"] = str(heading)

    url = "https://maps.googleapis.com/maps/api/streetview"

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(url, params=params)

    if resp.status_code != 200:
        raise RuntimeError(
            f"Street View API returned HTTP {resp.status_code}: {resp.text}"
        )

    # Check content type — API returns image/jpeg on success
    content_type = resp.headers.get("content-type", "")
    if "image" not in content_type:
        raise RuntimeError(
            f"Street View API did not return an image (content-type={content_type}). "
            "The location may not have Street View coverage."
        )

    # Save to disk
    img_dir = Path(settings.IMAGE_DIR)
    img_dir.mkdir(parents=True, exist_ok=True)

    filename = f"{uuid.uuid4().hex}.jpg"
    filepath = img_dir / filename
    filepath.write_bytes(resp.content)

    # Build the public URL (without the API key for storage)
    safe_params = {k: v for k, v in params.items() if k != "key"}
    public_url = f"{url}?{'&'.join(f'{k}={v}' for k, v in safe_params.items())}"

    return public_url, str(filepath)


async def check_streetview_coverage(
    latitude: float,
    longitude: float,
) -> bool:
    """Check whether Street View coverage exists at the given coordinates."""
    url = "https://maps.googleapis.com/maps/api/streetview/metadata"
    params = {
        "location": f"{latitude},{longitude}",
        "key": settings.GOOGLE_MAPS_API_KEY,
    }

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(url, params=params)

    if resp.status_code != 200:
        return False

    data = resp.json()
    return data.get("status") == "OK"
