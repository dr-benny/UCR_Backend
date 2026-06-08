"""Tests for POST /api/analyze and GET /api/engines."""
from __future__ import annotations

from io import BytesIO
from unittest.mock import patch

FAKE_ANALYSIS = {
    "scene_description": "A typical urban street with shophouses.",
    "observed_features": ["trees", "sidewalk", "motorcycle"],
    "urban_morphology": {"street_width": 8.0, "sky_view_factor": 0.6},
    "vegetation": {"green_view_index": 0.3, "tree_canopy_coverage": "low"},
    "surface_and_flood": {"surface_material": "asphalt", "impervious_surface_ratio": 0.9},
    "health_livability": {"walkability_obstruction": "none"},
    "confidence_scores": {"urban_morphology": 0.85, "vegetation": 0.8},
}


# ── GET /api/engines ──────────────────────────────────────────

def test_get_engines_returns_list(client):
    r = client.get("/api/engines")
    assert r.status_code == 200
    data = r.json()
    assert "engines" in data
    assert "default_engine" in data
    assert isinstance(data["engines"], list)


def test_get_engines_includes_gemini_and_claude(client):
    r = client.get("/api/engines")
    names = {e["name"] for e in r.json()["engines"]}
    assert "gemini" in names
    assert "claude" in names


# ── POST /api/analyze ─────────────────────────────────────────

@patch("app.api.v1.upload.analyze_image_bytes", return_value=FAKE_ANALYSIS)
def test_analyze_success(mock_analyze, client):
    r = client.post(
        "/api/analyze",
        files={"file": ("photo.jpg", BytesIO(b"fake-jpeg-bytes"), "image/jpeg")},
    )
    assert r.status_code == 200
    assert r.json()["scene_description"] == FAKE_ANALYSIS["scene_description"]
    assert r.json()["urban_morphology"]["street_width"] == 8.0
    mock_analyze.assert_called_once()


def test_analyze_empty_file_returns_400(client):
    r = client.post(
        "/api/analyze",
        files={"file": ("empty.jpg", BytesIO(b""), "image/jpeg")},
    )
    assert r.status_code == 400
    assert "empty" in r.json()["detail"].lower()


def test_analyze_oversized_file_returns_400(client):
    big = b"x" * (21 * 1024 * 1024)
    r = client.post(
        "/api/analyze",
        files={"file": ("big.jpg", BytesIO(big), "image/jpeg")},
    )
    assert r.status_code == 400
    assert "exceed" in r.json()["detail"].lower()


def test_analyze_invalid_mime_returns_400(client):
    r = client.post(
        "/api/analyze",
        files={"file": ("doc.pdf", BytesIO(b"pdfdata"), "application/pdf")},
    )
    assert r.status_code == 400


def test_analyze_bad_engine_returns_400(client):
    r = client.post(
        "/api/analyze",
        data={"engine": "totally-fake-engine"},
        files={"file": ("photo.jpg", BytesIO(b"bytes"), "image/jpeg")},
    )
    assert r.status_code == 400
    assert "totally-fake-engine" in r.json()["detail"]


@patch("app.api.v1.upload.analyze_image_bytes", return_value=FAKE_ANALYSIS)
def test_analyze_with_explicit_engine(mock_analyze, client):
    r = client.post(
        "/api/analyze",
        data={"engine": "gemini", "model": "gemini-2.5-flash"},
        files={"file": ("photo.jpg", BytesIO(b"fake-bytes"), "image/jpeg")},
    )
    assert r.status_code == 200
    mock_analyze.assert_called_once()


# ── B1: mime is threaded, not hardcoded ───────────────────────

async def test_analyze_image_file_passes_real_mime():
    """analyze_image_file must forward the file's mime to the engine, not hardcode JPEG."""
    from unittest.mock import AsyncMock, patch as p
    from app.services import analysis_service

    fake_engine = AsyncMock()
    fake_engine.analyze_image = AsyncMock(return_value={})
    with p.object(analysis_service, "get_engine", return_value=fake_engine):
        await analysis_service.analyze_image_file("/tmp/test_images/pic.png", mime_type="image/png")

    fake_engine.analyze_image.assert_awaited_once()
    _, kwargs = fake_engine.analyze_image.call_args
    assert kwargs["mime_type"] == "image/png"


async def test_analyze_image_file_infers_mime_from_extension():
    """When mime is missing (old jobs), infer it from the file extension."""
    from unittest.mock import AsyncMock, patch as p
    from app.services import analysis_service

    fake_engine = AsyncMock()
    fake_engine.analyze_image = AsyncMock(return_value={})
    with p.object(analysis_service, "get_engine", return_value=fake_engine):
        await analysis_service.analyze_image_file("/tmp/test_images/pic.webp")

    _, kwargs = fake_engine.analyze_image.call_args
    assert kwargs["mime_type"] == "image/webp"
