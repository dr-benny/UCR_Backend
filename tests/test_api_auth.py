"""Tests for API-key auth (S1) and X-Forwarded-For rate limiting (S2)."""
from __future__ import annotations

from io import BytesIO
from unittest.mock import patch

from app.core.config import settings


# ── S1: auth disabled by default ──────────────────────────────

def test_engines_public_without_key(client):
    """/api/engines is intentionally public."""
    assert client.get("/api/engines").status_code == 200


@patch("app.api.v1.upload.analyze_image_bytes", return_value={"ok": True})
def test_no_key_required_when_unset(mock_analyze, client):
    """With API_KEY unset, protected routes work without a token."""
    r = client.post(
        "/api/analyze",
        files={"file": ("p.jpg", BytesIO(b"bytes"), "image/jpeg")},
    )
    assert r.status_code == 200


# ── S1: auth enforced when API_KEY is set ─────────────────────

def test_missing_key_rejected_when_enabled(client):
    with patch.object(settings, "API_KEY", "s3cret"):
        r = client.post(
            "/api/analyze",
            files={"file": ("p.jpg", BytesIO(b"bytes"), "image/jpeg")},
        )
    assert r.status_code == 401


def test_wrong_key_rejected_when_enabled(client):
    with patch.object(settings, "API_KEY", "s3cret"):
        r = client.post(
            "/api/analyze",
            headers={"Authorization": "Bearer wrong"},
            files={"file": ("p.jpg", BytesIO(b"bytes"), "image/jpeg")},
        )
    assert r.status_code == 401


@patch("app.api.v1.upload.analyze_image_bytes", return_value={"ok": True})
def test_correct_key_accepted_when_enabled(mock_analyze, client):
    with patch.object(settings, "API_KEY", "s3cret"):
        r = client.post(
            "/api/analyze",
            headers={"Authorization": "Bearer s3cret"},
            files={"file": ("p.jpg", BytesIO(b"bytes"), "image/jpeg")},
        )
    assert r.status_code == 200


def test_jobs_list_protected_when_enabled(client):
    with patch.object(settings, "API_KEY", "s3cret"):
        assert client.get("/api/jobs").status_code == 401
        assert client.get("/api/jobs", headers={"Authorization": "Bearer s3cret"}).status_code != 401


def test_engines_still_public_when_enabled(client):
    with patch.object(settings, "API_KEY", "s3cret"):
        assert client.get("/api/engines").status_code == 200


# ── S2: X-Forwarded-For client IP resolution ──────────────────

def test_client_ip_ignores_xff_when_proxy_untrusted():
    from app.api.v1.jobs import _client_ip

    class _Req:
        headers = {"x-forwarded-for": "1.2.3.4"}
        class client:
            host = "10.0.0.1"

    with patch.object(settings, "TRUST_PROXY", False):
        assert _client_ip(_Req()) == "10.0.0.1"  # spoofed header ignored


def test_client_ip_uses_xff_when_proxy_trusted():
    from app.api.v1.jobs import _client_ip

    class _Req:
        headers = {"x-forwarded-for": "1.2.3.4, 10.0.0.1"}
        class client:
            host = "10.0.0.1"

    with patch.object(settings, "TRUST_PROXY", True):
        assert _client_ip(_Req()) == "1.2.3.4"  # left-most real client
