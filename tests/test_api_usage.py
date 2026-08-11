"""Tests for the public, self-service GET /api/usage lookup."""
from __future__ import annotations

from unittest.mock import patch

import pytest

from app.core.config import settings
from app.services import api_key_store
from tests._fakes import InMemoryRedis


@pytest.fixture
def key_dir(tmp_path):
    with patch.object(settings, "API_KEY_DIR", str(tmp_path)):
        yield tmp_path


def test_usage_unknown_key_returns_401(client, key_dir):
    r = client.get("/api/usage", params={"key": "no-such-key"})
    assert r.status_code == 401


@patch("app.api.v1.usage.get_redis")
def test_usage_returns_name_and_quota(mock_redis, client, key_dir):
    mock_redis.return_value = InMemoryRedis()
    key = api_key_store.create_key("choky", daily_limit=300, max_samples=1)

    r = client.get("/api/usage", params={"key": key["key"]})
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "choky"
    assert body["daily_limit"] == 300
    assert body["used_today"] == 0
    assert body["remaining_today"] == 300
    assert body["max_samples"] == 1


@patch("app.api.v1.usage.get_redis")
@patch("app.api.v1.upload.get_redis")
@patch("app.api.v1.upload.analyze_image_bytes", return_value={"ok": True})
def test_usage_reflects_consumption(mock_analyze, mock_upload_redis, mock_usage_redis, client, key_dir):
    redis = InMemoryRedis()
    mock_upload_redis.return_value = redis
    mock_usage_redis.return_value = redis
    key = api_key_store.create_key("choky", daily_limit=10, max_samples=1)

    from io import BytesIO
    client.post(
        "/api/analyze",
        headers={"Authorization": f"Bearer {key['key']}"},
        files={"file": ("p.jpg", BytesIO(b"bytes"), "image/jpeg")},
    )

    r = client.get("/api/usage", params={"key": key["key"]})
    body = r.json()
    assert body["used_today"] == 1
    assert body["remaining_today"] == 9
