"""Tests for the hourly orphaned-image cleanup (main._orphaned_image_cleanup)."""
from __future__ import annotations

import json
from unittest.mock import patch

from app.core.config import settings
from app.main import _orphaned_image_cleanup
from app.services.job_store import JOB_KEY
from tests._fakes import InMemoryRedis


@patch("app.main.aioredis.from_url")
async def test_cleanup_deletes_unreferenced_images(mock_from_url, tmp_path):
    keep = tmp_path / "keep.jpg"
    keep.write_bytes(b"a")
    orphan = tmp_path / "orphan.jpg"
    orphan.write_bytes(b"b")

    redis = InMemoryRedis()
    redis._store[JOB_KEY.format(job_id="j1")] = json.dumps({
        "status": "done",
        "_images": [{"path": str(keep), "filename": "keep.jpg"}],
    })
    mock_from_url.return_value = redis

    with patch.object(settings, "IMAGE_DIR", str(tmp_path)):
        await _orphaned_image_cleanup()

    assert keep.exists()          # still referenced by a job
    assert not orphan.exists()    # no job references it → removed


@patch("app.main.aioredis.from_url")
async def test_cleanup_keeps_all_referenced_images(mock_from_url, tmp_path):
    a = tmp_path / "a.jpg"
    a.write_bytes(b"a")
    b = tmp_path / "b.jpg"
    b.write_bytes(b"b")

    redis = InMemoryRedis()
    redis._store[JOB_KEY.format(job_id="j1")] = json.dumps({
        "status": "processing",
        "_images": [
            {"path": str(a), "filename": "a.jpg"},
            {"path": str(b), "filename": "b.jpg"},
        ],
    })
    mock_from_url.return_value = redis

    with patch.object(settings, "IMAGE_DIR", str(tmp_path)):
        await _orphaned_image_cleanup()

    assert a.exists()
    assert b.exists()


@patch("app.main.aioredis.from_url")
async def test_cleanup_no_images_dir_is_safe(mock_from_url, tmp_path):
    redis = InMemoryRedis()
    mock_from_url.return_value = redis

    missing = tmp_path / "does_not_exist"
    with patch.object(settings, "IMAGE_DIR", str(missing)):
        await _orphaned_image_cleanup()  # must not raise
