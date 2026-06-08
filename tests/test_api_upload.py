"""Tests for POST /api/analyze and GET /api/engines."""
from __future__ import annotations

from io import BytesIO
from unittest.mock import patch

FAKE_ANALYSIS = {
    "image_id": "test-img-001",
    "observation_id": "obs-001",
    "street_id": "street-001",
    "point_order": 1,
    "gps_status": "extracted",
    "gps_evidence": {"metadata_checked": True},
    "reference_scale": {"type": "person"},
    "left": {"boundary_type": "wall"},
    "right": {"boundary_type": "building"},
    "street_width_m": 8.0,
    "confidence_score": 0.85,
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
    assert r.json()["image_id"] == FAKE_ANALYSIS["image_id"]
    assert r.json()["street_width_m"] == FAKE_ANALYSIS["street_width_m"]
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
