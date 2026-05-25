"""
Unit tests for process_route_job — the background job runner.

We mock the DB session factory and the streetview pipeline so the test
only exercises the orchestration logic (status transitions, progress,
success/failure accounting).
"""
from unittest.mock import MagicMock, AsyncMock, patch

import pytest

from app.services.job_service import process_route_job


@pytest.fixture
def fake_route():
    r = MagicMock()
    r.id = 99
    return r


@pytest.fixture
def request_payload():
    return {
        "name": "Async test route",
        "description": "x",
        "points": [
            {"latitude": 13.736, "longitude": 100.523},
            {"latitude": 13.737, "longitude": 100.524},
            {"latitude": 13.738, "longitude": 100.525},
        ],
        "concurrency": 2,
    }


async def test_happy_path_marks_done_with_result(request_payload, fake_route):
    """All 3 points succeed → mark_done called with all analysis IDs."""
    fake_records = [MagicMock(id=10), MagicMock(id=11), MagicMock(id=12)]
    analyze_mock = AsyncMock(side_effect=fake_records)

    with patch("app.services.job_service.SessionLocal") as session_local, \
         patch("app.services.job_service.RouteDAO.create_route", return_value=fake_route), \
         patch("app.services.job_service.JobDAO.mark_started") as mark_started, \
         patch("app.services.job_service.JobDAO.increment_progress") as inc, \
         patch("app.services.job_service.JobDAO.mark_done") as mark_done, \
         patch("app.services.job_service.JobDAO.mark_failed") as mark_failed, \
         patch("app.services.job_service.analyze_from_streetview", analyze_mock):
        session_local.return_value = MagicMock()
        await process_route_job("job-id", request_payload)

    mark_started.assert_called_once()
    assert mark_started.call_args.kwargs.get("route_id") == 99
    assert inc.call_count == 3
    mark_failed.assert_not_called()

    args, kwargs = mark_done.call_args
    result = kwargs.get("result_data") or args[2]
    assert result["route_id"] == 99
    assert sorted(result["analysis_ids"]) == [10, 11, 12]
    assert result["succeeded"] == 3
    assert result["failed"] == 0


async def test_partial_failure_records_failed_points(request_payload, fake_route):
    """One LookupError + two successes → still marks done with 1 failed."""
    analyze_mock = AsyncMock(
        side_effect=[
            MagicMock(id=10),
            LookupError("no coverage"),
            MagicMock(id=12),
        ]
    )

    with patch("app.services.job_service.SessionLocal") as session_local, \
         patch("app.services.job_service.RouteDAO.create_route", return_value=fake_route), \
         patch("app.services.job_service.JobDAO.mark_started"), \
         patch("app.services.job_service.JobDAO.increment_progress") as inc, \
         patch("app.services.job_service.JobDAO.mark_done") as mark_done, \
         patch("app.services.job_service.JobDAO.mark_failed") as mark_failed, \
         patch("app.services.job_service.analyze_from_streetview", analyze_mock):
        session_local.return_value = MagicMock()
        await process_route_job("job-id", request_payload)

    assert inc.call_count == 3  # increments on success AND failure
    mark_failed.assert_not_called()  # partial failure ≠ job failure

    args, kwargs = mark_done.call_args
    result = kwargs.get("result_data") or args[2]
    assert sorted(result["analysis_ids"]) == [10, 12]
    assert result["succeeded"] == 2
    assert result["failed"] == 1
    assert result["failed_points"][0]["index"] == 1
    assert "no coverage" in result["failed_points"][0]["reason"]


async def test_route_creation_failure_marks_job_failed(request_payload):
    """Crash in route creation → job is marked failed (not stuck in pending)."""
    with patch("app.services.job_service.SessionLocal") as session_local, \
         patch("app.services.job_service.RouteDAO.create_route",
               side_effect=RuntimeError("db down")), \
         patch("app.services.job_service.JobDAO.mark_done") as mark_done, \
         patch("app.services.job_service.JobDAO.mark_failed") as mark_failed:
        session_local.return_value = MagicMock()
        await process_route_job("job-id", request_payload)

    mark_done.assert_not_called()
    mark_failed.assert_called_once()
    assert "db down" in mark_failed.call_args.args[2]


async def test_empty_points_marks_done_with_zero_results(fake_route):
    """Job with [] points should still complete successfully."""
    with patch("app.services.job_service.SessionLocal") as session_local, \
         patch("app.services.job_service.RouteDAO.create_route", return_value=fake_route), \
         patch("app.services.job_service.JobDAO.mark_started"), \
         patch("app.services.job_service.JobDAO.increment_progress") as inc, \
         patch("app.services.job_service.JobDAO.mark_done") as mark_done, \
         patch("app.services.job_service.analyze_from_streetview", AsyncMock()):
        session_local.return_value = MagicMock()
        await process_route_job(
            "job-id",
            {"name": "x", "description": None, "points": [], "concurrency": 5},
        )

    inc.assert_not_called()

    args, kwargs = mark_done.call_args
    result = kwargs.get("result_data") or args[2]
    assert result["succeeded"] == 0
    assert result["failed"] == 0


async def test_db_session_is_closed_on_success(request_payload, fake_route):
    fake_session = MagicMock()
    with patch("app.services.job_service.SessionLocal", return_value=fake_session), \
         patch("app.services.job_service.RouteDAO.create_route", return_value=fake_route), \
         patch("app.services.job_service.JobDAO.mark_started"), \
         patch("app.services.job_service.JobDAO.increment_progress"), \
         patch("app.services.job_service.JobDAO.mark_done"), \
         patch("app.services.job_service.analyze_from_streetview",
               AsyncMock(return_value=MagicMock(id=1))):
        await process_route_job("job-id", request_payload)

    fake_session.close.assert_called_once()


async def test_db_session_is_closed_on_failure(request_payload):
    fake_session = MagicMock()
    with patch("app.services.job_service.SessionLocal", return_value=fake_session), \
         patch("app.services.job_service.RouteDAO.create_route",
               side_effect=RuntimeError("boom")), \
         patch("app.services.job_service.JobDAO.mark_failed"):
        await process_route_job("job-id", request_payload)

    fake_session.close.assert_called_once()
