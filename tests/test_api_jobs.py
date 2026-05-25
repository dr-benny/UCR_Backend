"""
Integration-style tests for /api/jobs/* endpoints.

The background task (process_route_job) is patched out — these tests only
check the HTTP contract: validation, ID generation, status codes, polling.
"""
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from app.models.job import Job


def _swallow_coro(coro):
    """Close the coroutine so we don't get a 'never awaited' warning."""
    coro.close()
    return MagicMock()


@pytest.fixture
def mock_job():
    j = Job(
        job_type="route_analysis",
        status="pending",
        request_data={"points": []},
        progress_current=0,
        progress_total=2,
    )
    j.id = "a" * 32
    j.route_id = None
    j.created_at = datetime(2026, 5, 14, tzinfo=timezone.utc)
    j.updated_at = datetime(2026, 5, 14, tzinfo=timezone.utc)
    j.started_at = None
    j.completed_at = None
    j.result_data = None
    j.error = None
    return j


@pytest.fixture
def valid_route_request():
    return {
        "name": "Test Route",
        "description": "Async test",
        "points": [
            {"latitude": 13.736, "longitude": 100.523},
            {"latitude": 13.737, "longitude": 100.524},
        ],
        "concurrency": 2,
    }


# ── POST /api/jobs/route ──────────────────────────────────────

def test_submit_route_job_returns_202(valid_route_request, mock_job, client):
    with patch("app.api.v1.jobs.JobDAO.create_job", return_value=mock_job), \
         patch("app.api.v1.jobs.asyncio.create_task", side_effect=_swallow_coro) as mock_task:
        response = client.post("/api/jobs/route", json=valid_route_request)

    assert response.status_code == 202
    mock_task.assert_called_once()


def test_submit_route_job_response_shape(valid_route_request, mock_job, client):
    with patch("app.api.v1.jobs.JobDAO.create_job", return_value=mock_job), \
         patch("app.api.v1.jobs.asyncio.create_task", side_effect=_swallow_coro):
        data = client.post("/api/jobs/route", json=valid_route_request).json()

    assert data["id"] == "a" * 32
    assert data["status"] == "pending"
    assert data["progress"] == {"current": 0, "total": 2}
    assert data["job_type"] == "route_analysis"


def test_submit_route_job_persists_total(valid_route_request, mock_job, client):
    """progress_total must match the number of points submitted."""
    captured = {}

    def fake_create_job(db, *, job_type, request_data, progress_total):
        captured["progress_total"] = progress_total
        captured["request_data"] = request_data
        return mock_job

    with patch("app.api.v1.jobs.JobDAO.create_job", side_effect=fake_create_job), \
         patch("app.api.v1.jobs.asyncio.create_task", side_effect=_swallow_coro):
        client.post("/api/jobs/route", json=valid_route_request)

    assert captured["progress_total"] == 2
    assert len(captured["request_data"]["points"]) == 2


def test_submit_route_job_empty_points_returns_422(client):
    response = client.post(
        "/api/jobs/route",
        json={"points": [], "concurrency": 5},
    )
    assert response.status_code == 422


def test_submit_route_job_concurrency_out_of_range_returns_422(valid_route_request, client):
    valid_route_request["concurrency"] = 99
    response = client.post("/api/jobs/route", json=valid_route_request)
    assert response.status_code == 422


def test_submit_route_job_missing_latitude_returns_422(client):
    response = client.post(
        "/api/jobs/route",
        json={"points": [{"longitude": 100.0}], "concurrency": 5},
    )
    assert response.status_code == 422


# ── GET /api/jobs/{id} ────────────────────────────────────────

def test_get_job_returns_200_when_found(mock_job, client):
    with patch("app.api.v1.jobs.JobDAO.get_by_id", return_value=mock_job):
        response = client.get(f"/api/jobs/{mock_job.id}")
    assert response.status_code == 200


def test_get_job_returns_404_when_missing(client):
    with patch("app.api.v1.jobs.JobDAO.get_by_id", return_value=None):
        response = client.get("/api/jobs/nonexistent")
    assert response.status_code == 404


def test_get_job_returns_result_when_done(mock_job, client):
    mock_job.status = "done"
    mock_job.result_data = {"route_id": 1, "analysis_ids": [10, 11], "succeeded": 2, "failed": 0}
    mock_job.progress_current = 2

    with patch("app.api.v1.jobs.JobDAO.get_by_id", return_value=mock_job):
        data = client.get(f"/api/jobs/{mock_job.id}").json()

    assert data["status"] == "done"
    assert data["result"]["analysis_ids"] == [10, 11]
    assert data["progress"]["current"] == 2


def test_get_job_returns_error_when_failed(mock_job, client):
    mock_job.status = "failed"
    mock_job.error = "DB connection lost"

    with patch("app.api.v1.jobs.JobDAO.get_by_id", return_value=mock_job):
        data = client.get(f"/api/jobs/{mock_job.id}").json()

    assert data["status"] == "failed"
    assert data["error"] == "DB connection lost"


# ── GET /api/jobs ─────────────────────────────────────────────

def test_list_jobs_returns_list(mock_job, client):
    with patch("app.api.v1.jobs.JobDAO.list_jobs", return_value=[mock_job]):
        data = client.get("/api/jobs").json()
    assert len(data) == 1
    assert data[0]["id"] == "a" * 32


def test_list_jobs_empty(client):
    with patch("app.api.v1.jobs.JobDAO.list_jobs", return_value=[]):
        assert client.get("/api/jobs").json() == []


def test_list_jobs_invalid_limit_returns_422(client):
    response = client.get("/api/jobs?limit=999")
    assert response.status_code == 422
