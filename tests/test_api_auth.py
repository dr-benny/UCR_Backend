"""Tests for API-key auth + per-key daily quota (S1) and X-Forwarded-For rate limiting (S2)."""
from __future__ import annotations

from io import BytesIO
from unittest.mock import patch

import pytest

from app.core.config import settings
from app.services import api_key_store
from tests._fakes import InMemoryRedis


@pytest.fixture
def key_dir(tmp_path):
    """Point the key store at an empty temp dir — no keys means auth disabled."""
    with patch.object(settings, "API_KEY_DIR", str(tmp_path)):
        yield tmp_path


@pytest.fixture
def issued_key(key_dir):
    """A single issued key with a small daily quota, easy to exhaust in tests."""
    return api_key_store.create_key("test-client", daily_limit=5)


# ── S1: auth disabled when no keys exist ──────────────────────

def test_engines_public_without_key(client):
    """/api/engines is intentionally public."""
    assert client.get("/api/engines").status_code == 200


@patch("app.api.v1.upload.analyze_image_bytes", return_value={"ok": True})
def test_no_key_required_when_none_configured(mock_analyze, client, key_dir):
    """With no keys on disk, protected routes work without a token."""
    r = client.post(
        "/api/analyze",
        files={"file": ("p.jpg", BytesIO(b"bytes"), "image/jpeg")},
    )
    assert r.status_code == 200


# ── S1: auth enforced once a key exists ───────────────────────

def test_missing_key_rejected_when_enabled(client, issued_key):
    r = client.post(
        "/api/analyze",
        files={"file": ("p.jpg", BytesIO(b"bytes"), "image/jpeg")},
    )
    assert r.status_code == 401


def test_wrong_key_rejected_when_enabled(client, issued_key):
    r = client.post(
        "/api/analyze",
        headers={"Authorization": "Bearer wrong"},
        files={"file": ("p.jpg", BytesIO(b"bytes"), "image/jpeg")},
    )
    assert r.status_code == 401


@patch("app.api.v1.upload.analyze_image_bytes", return_value={"ok": True})
@patch("app.api.v1.upload.get_redis")
def test_correct_key_accepted_when_enabled(mock_redis, mock_analyze, client, issued_key):
    mock_redis.return_value = InMemoryRedis()
    r = client.post(
        "/api/analyze",
        headers={"Authorization": f"Bearer {issued_key['key']}"},
        files={"file": ("p.jpg", BytesIO(b"bytes"), "image/jpeg")},
    )
    assert r.status_code == 200


def test_jobs_list_protected_when_enabled(client, issued_key):
    assert client.get("/api/jobs").status_code == 401
    ok = client.get("/api/jobs", headers={"Authorization": f"Bearer {issued_key['key']}"})
    assert ok.status_code != 401


def test_engines_still_public_when_enabled(client, issued_key):
    assert client.get("/api/engines").status_code == 200


# ── Per-key daily quota ────────────────────────────────────────

@patch("app.api.v1.upload.analyze_image_bytes", return_value={"ok": True})
@patch("app.api.v1.upload.get_redis")
def test_quota_exceeded_rejected_with_429(mock_redis, mock_analyze, client, issued_key):
    """issued_key has daily_limit=5; samples=5 on the first call exhausts it."""
    redis = InMemoryRedis()
    mock_redis.return_value = redis
    headers = {"Authorization": f"Bearer {issued_key['key']}"}

    ok = client.post(
        "/api/analyze",
        headers=headers,
        data={"samples": "5"},
        files={"file": ("p.jpg", BytesIO(b"bytes"), "image/jpeg")},
    )
    assert ok.status_code == 200

    over = client.post(
        "/api/analyze",
        headers=headers,
        data={"samples": "1"},
        files={"file": ("p.jpg", BytesIO(b"bytes"), "image/jpeg")},
    )
    assert over.status_code == 429


@patch("app.api.v1.upload.analyze_image_bytes", return_value={"ok": True})
@patch("app.api.v1.upload.get_redis")
def test_quota_is_per_key(mock_redis, mock_analyze, client, key_dir):
    """One key's usage doesn't count against another key's budget."""
    redis = InMemoryRedis()
    mock_redis.return_value = redis
    key_a = api_key_store.create_key("client-a", daily_limit=1)
    key_b = api_key_store.create_key("client-b", daily_limit=1)

    r_a = client.post(
        "/api/analyze",
        headers={"Authorization": f"Bearer {key_a['key']}"},
        data={"samples": "1"},
        files={"file": ("p.jpg", BytesIO(b"bytes"), "image/jpeg")},
    )
    assert r_a.status_code == 200

    r_b = client.post(
        "/api/analyze",
        headers={"Authorization": f"Bearer {key_b['key']}"},
        data={"samples": "1"},
        files={"file": ("p.jpg", BytesIO(b"bytes"), "image/jpeg")},
    )
    assert r_b.status_code == 200


# ── Per-key max_samples (caps samples-per-image, caller may request fewer) ──

@patch("app.api.v1.upload.analyze_image_bytes", return_value={"ok": True})
@patch("app.api.v1.upload.get_redis")
def test_key_max_samples_caps_caller_value(mock_redis, mock_analyze, client, key_dir):
    """A key with max_samples=3 clamps a caller's higher request down to 3."""
    mock_redis.return_value = InMemoryRedis()
    key = api_key_store.create_key("capped", daily_limit=100, max_samples=3)

    r = client.post(
        "/api/analyze",
        headers={"Authorization": f"Bearer {key['key']}"},
        data={"samples": "10"},  # clamped to 3
        files={"file": ("p.jpg", BytesIO(b"bytes"), "image/jpeg")},
    )
    assert r.status_code == 200
    assert mock_analyze.call_args.kwargs["samples"] == 3


@patch("app.api.v1.upload.analyze_image_bytes", return_value={"ok": True})
@patch("app.api.v1.upload.get_redis")
def test_key_max_samples_allows_caller_to_request_fewer(mock_redis, mock_analyze, client, key_dir):
    """A caller may still ask for fewer samples than the key's cap."""
    mock_redis.return_value = InMemoryRedis()
    key = api_key_store.create_key("capped", daily_limit=100, max_samples=3)

    r = client.post(
        "/api/analyze",
        headers={"Authorization": f"Bearer {key['key']}"},
        data={"samples": "1"},
        files={"file": ("p.jpg", BytesIO(b"bytes"), "image/jpeg")},
    )
    assert r.status_code == 200
    assert mock_analyze.call_args.kwargs["samples"] == 1


@patch("app.api.v1.upload.analyze_image_bytes", return_value={"ok": True})
@patch("app.api.v1.upload.get_redis")
def test_key_max_samples_quota_counts_actual_ai_calls(mock_redis, mock_analyze, client, key_dir):
    """daily_limit still counts images x samples actually used, not images alone."""
    mock_redis.return_value = InMemoryRedis()
    key = api_key_store.create_key("capped", daily_limit=3, max_samples=3)
    headers = {"Authorization": f"Bearer {key['key']}"}

    used_all = client.post(
        "/api/analyze",
        headers=headers,
        data={"samples": "10"},  # clamped to 3, consumes the whole daily_limit=3 in one call
        files={"file": ("p.jpg", BytesIO(b"bytes"), "image/jpeg")},
    )
    assert used_all.status_code == 200

    over = client.post(
        "/api/analyze",
        headers=headers,
        data={"samples": "1"},
        files={"file": ("p.jpg", BytesIO(b"bytes"), "image/jpeg")},
    )
    assert over.status_code == 429


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
