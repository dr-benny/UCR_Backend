"""Tests for the Celery worker pipeline (_run_image_job).

This is the core batch-processing loop — progress tracking, partial-failure
isolation, parse-error handling, and the done/failed transitions — exercised
directly against an in-memory Redis with the AI call mocked out.
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

from app.services.job_service import _run_image_job
from app.services.job_store import JOB_KEY
from tests._fakes import InMemoryRedis

JOB_ID = "job-pipeline-0001"


def _valid_analysis(label: str = "x") -> dict:
    return {
        "scene_description": label,
        "urban_morphology": {"street_width": 8.0},
        "confidence_scores": {"urban_morphology": 0.9},
    }


def _request(images: list[dict], **kw) -> dict:
    base = {"images": images, "concurrency": 2, "engine": "gemini", "model": None, "samples": None}
    base.update(kw)
    return base


def _img(name: str) -> dict:
    return {"path": f"/tmp/{name}", "filename": name, "mime": "image/jpeg"}


def _state(redis: InMemoryRedis) -> dict:
    return json.loads(redis._store[JOB_KEY.format(job_id=JOB_ID)])


@patch("app.services.job_service.cleanup_images")
@patch("app.services.job_service.analyze_image_file", new_callable=AsyncMock)
@patch("app.services.job_service.aioredis.from_url")
async def test_run_job_happy_path(mock_from_url, mock_analyze, mock_cleanup):
    redis = InMemoryRedis()
    mock_from_url.return_value = redis
    mock_analyze.side_effect = [_valid_analysis("a"), _valid_analysis("b")]

    await _run_image_job(JOB_ID, _request([_img("a.jpg"), _img("b.jpg")]))

    s = _state(redis)
    assert s["status"] == "done"
    assert len(s["results"]) == 2
    assert s["failed"] == []
    assert s["progress"]["current"] == 2
    assert s["progress"]["percent"] == 100
    mock_cleanup.assert_called_once()  # images cleaned only after success


@patch("app.services.job_service.cleanup_images")
@patch("app.services.job_service.analyze_image_file", new_callable=AsyncMock)
@patch("app.services.job_service.aioredis.from_url")
async def test_run_job_partial_failure_still_completes(mock_from_url, mock_analyze, mock_cleanup):
    redis = InMemoryRedis()
    mock_from_url.return_value = redis
    # One image blows up; the other succeeds. The job should still finish 'done'.
    mock_analyze.side_effect = [_valid_analysis("ok"), RuntimeError("boom")]

    await _run_image_job(JOB_ID, _request([_img("a.jpg"), _img("b.jpg")]))

    s = _state(redis)
    assert s["status"] == "done"
    assert len(s["results"]) == 1
    assert len(s["failed"]) == 1
    assert "boom" in s["failed"][0]["reason"]


@patch("app.services.job_service.cleanup_images")
@patch("app.services.job_service.analyze_image_file", new_callable=AsyncMock)
@patch("app.services.job_service.aioredis.from_url")
async def test_run_job_parse_error_counts_as_failed(mock_from_url, mock_analyze, mock_cleanup):
    """Unparseable AI output (B2) must land in 'failed', not stored as a real result."""
    redis = InMemoryRedis()
    mock_from_url.return_value = redis
    mock_analyze.side_effect = [{"_parse_error": True, "_raw_text": "not json"}]

    await _run_image_job(JOB_ID, _request([_img("a.jpg")]))

    s = _state(redis)
    assert s["status"] == "done"
    assert s["results"] == []
    assert len(s["failed"]) == 1
    assert "unparseable" in s["failed"][0]["reason"].lower()


@patch("app.services.job_service.cleanup_images")
@patch("app.services.job_service.analyze_image_file", new_callable=AsyncMock)
@patch("app.services.job_service.aioredis.from_url")
async def test_run_job_whole_crash_marks_failed(mock_from_url, mock_analyze, mock_cleanup):
    """A crash outside the per-image guard must flip the job to 'failed', not hang."""
    redis = InMemoryRedis()
    mock_from_url.return_value = redis

    # A bad concurrency value raises before the gather; the outer handler catches it.
    await _run_image_job(JOB_ID, _request([_img("a.jpg")], concurrency="not-an-int"))

    s = _state(redis)
    assert s["status"] == "failed"
    assert s["error"]
    mock_analyze.assert_not_called()
    mock_cleanup.assert_not_called()  # nothing cleaned on a hard failure
