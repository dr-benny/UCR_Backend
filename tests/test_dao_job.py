"""Unit tests for JobDAO — DB interactions are mocked."""
from datetime import datetime, timezone

import pytest

from tests.conftest import make_mock_session
from app.dao.job_dao import JobDAO
from app.models.job import Job


@pytest.fixture
def mock_job():
    j = Job(
        job_type="route_analysis",
        status="pending",
        request_data={"points": []},
        progress_current=0,
        progress_total=5,
    )
    j.id = "abc123" + "0" * 26
    j.created_at = datetime(2026, 5, 14, tzinfo=timezone.utc)
    j.updated_at = datetime(2026, 5, 14, tzinfo=timezone.utc)
    return j


# ── create_job ────────────────────────────────────────────────

def test_create_job_persists_with_defaults():
    db = make_mock_session()
    db.refresh.side_effect = lambda obj: setattr(obj, "id", "x" * 32)

    result = JobDAO.create_job(
        db,
        job_type="route_analysis",
        request_data={"points": [1, 2, 3]},
        progress_total=3,
    )

    db.add.assert_called_once()
    db.commit.assert_called_once()
    assert isinstance(result, Job)
    assert result.job_type == "route_analysis"
    assert result.status == "pending"
    assert result.progress_total == 3


def test_create_job_zero_progress_total_default():
    db = make_mock_session()
    result = JobDAO.create_job(db, job_type="x", request_data={})
    assert result.progress_total == 0


# ── get_by_id ─────────────────────────────────────────────────

def test_get_by_id_returns_job(mock_job):
    db = make_mock_session(first_return=mock_job)
    assert JobDAO.get_by_id(db, mock_job.id) is mock_job


def test_get_by_id_returns_none_when_missing():
    db = make_mock_session(first_return=None)
    assert JobDAO.get_by_id(db, "missing") is None


# ── list_jobs ─────────────────────────────────────────────────

def test_list_jobs_returns_list(mock_job):
    db = make_mock_session(first_return=mock_job)
    results = JobDAO.list_jobs(db, skip=0, limit=10)
    assert results == [mock_job]


def test_list_jobs_filters_by_status(mock_job):
    db = make_mock_session(first_return=mock_job)
    JobDAO.list_jobs(db, status="done")
    # filter chain was called at least once (for status filter)
    assert db.query.return_value.filter.called


# ── mark_started ──────────────────────────────────────────────

def test_mark_started_sets_processing_and_route(mock_job):
    db = make_mock_session(first_return=mock_job)
    result = JobDAO.mark_started(db, mock_job.id, route_id=42)
    assert result.status == "processing"
    assert result.route_id == 42
    assert result.started_at is not None
    db.commit.assert_called_once()


def test_mark_started_missing_job_returns_none():
    db = make_mock_session(first_return=None)
    assert JobDAO.mark_started(db, "missing") is None


# ── increment_progress ────────────────────────────────────────

def test_increment_progress_bumps_counter(mock_job):
    mock_job.progress_current = 2
    db = make_mock_session(first_return=mock_job)
    result = JobDAO.increment_progress(db, mock_job.id)
    assert result.progress_current == 3
    db.commit.assert_called_once()


def test_increment_progress_from_zero(mock_job):
    mock_job.progress_current = 0
    db = make_mock_session(first_return=mock_job)
    result = JobDAO.increment_progress(db, mock_job.id)
    assert result.progress_current == 1


# ── mark_done ─────────────────────────────────────────────────

def test_mark_done_sets_result_and_completed_at(mock_job):
    db = make_mock_session(first_return=mock_job)
    result = JobDAO.mark_done(db, mock_job.id, result_data={"ok": True})
    assert result.status == "done"
    assert result.result_data == {"ok": True}
    assert result.completed_at is not None


# ── mark_failed ───────────────────────────────────────────────

def test_mark_failed_sets_error_and_completed_at(mock_job):
    db = make_mock_session(first_return=mock_job)
    result = JobDAO.mark_failed(db, mock_job.id, error="boom")
    assert result.status == "failed"
    assert result.error == "boom"
    assert result.completed_at is not None
