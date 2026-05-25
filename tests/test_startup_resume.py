"""
Tests for the lifespan startup: stuck job resume logic.

On server start, pending/processing jobs left over from a previous run
must be re-queued automatically via asyncio.create_task.

10 stuck jobs total: 5 pending + 5 processing.
"""
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.main import app
from app.models.job import Job


# ── Helpers ───────────────────────────────────────────────────

def _make_job(job_id: str, status: str) -> Job:
    j = Job(
        job_type="route_analysis",
        status=status,
        request_data={
            "name": f"Route {job_id}",
            "description": None,
            "points": [{"latitude": 13.736, "longitude": 100.523}],
            "concurrency": 2,
        },
        progress_current=0,
        progress_total=1,
    )
    j.id = job_id
    j.route_id = None
    j.created_at = datetime(2026, 5, 25, tzinfo=timezone.utc)
    j.updated_at = datetime(2026, 5, 25, tzinfo=timezone.utc)
    j.started_at = None
    j.completed_at = None
    j.result_data = None
    j.error = None
    return j


def _make_10_stuck_jobs() -> list[Job]:
    """5 pending + 5 processing = 10 stuck jobs."""
    return [
        *[_make_job(f"pending{i:02d}" + "x" * 22, "pending") for i in range(5)],
        *[_make_job(f"process{i:02d}" + "x" * 21, "processing") for i in range(5)],
    ]


def _swallow_coro(coro):
    """Close the coroutine so we don't get a 'never awaited' warning."""
    coro.close()
    return MagicMock()


# ── Tests ─────────────────────────────────────────────────────

def test_startup_requeues_all_10_stuck_jobs():
    """All 10 stuck jobs must each get one asyncio.create_task call on startup."""
    stuck_jobs = _make_10_stuck_jobs()
    task_calls = []

    def capture_task(coro):
        task_calls.append(coro)
        coro.close()
        return MagicMock()

    with patch("app.main.SessionLocal", return_value=MagicMock()), \
         patch("app.main.JobDAO.get_resumable_jobs", return_value=stuck_jobs), \
         patch("app.main.JobDAO.reset_to_pending"), \
         patch("app.main.asyncio.create_task", side_effect=capture_task):
        with TestClient(app):
            pass

    assert len(task_calls) == 10, f"Expected 10 tasks, got {len(task_calls)}"


def test_startup_resets_only_processing_jobs():
    """Only 'processing' jobs must be reset — 'pending' ones were never started."""
    stuck_jobs = _make_10_stuck_jobs()
    processing_ids = {j.id for j in stuck_jobs if j.status == "processing"}
    pending_ids = {j.id for j in stuck_jobs if j.status == "pending"}
    reset_ids = []

    with patch("app.main.SessionLocal", return_value=MagicMock()), \
         patch("app.main.JobDAO.get_resumable_jobs", return_value=stuck_jobs), \
         patch("app.main.JobDAO.reset_to_pending", side_effect=lambda db, jid: reset_ids.append(jid)), \
         patch("app.main.asyncio.create_task", side_effect=_swallow_coro):
        with TestClient(app):
            pass

    assert set(reset_ids) == processing_ids, "Only processing jobs should be reset"
    assert not any(jid in reset_ids for jid in pending_ids), "Pending jobs must NOT be reset"


def test_startup_resets_exactly_5_processing_jobs():
    """Exactly 5 reset calls — one per processing job, none for pending."""
    stuck_jobs = _make_10_stuck_jobs()
    reset_count = []

    with patch("app.main.SessionLocal", return_value=MagicMock()), \
         patch("app.main.JobDAO.get_resumable_jobs", return_value=stuck_jobs), \
         patch("app.main.JobDAO.reset_to_pending", side_effect=lambda db, jid: reset_count.append(jid)), \
         patch("app.main.asyncio.create_task", side_effect=_swallow_coro):
        with TestClient(app):
            pass

    assert len(reset_count) == 5, f"Expected 5 resets (processing jobs), got {len(reset_count)}"


def test_startup_no_stuck_jobs_creates_no_tasks():
    """When there are no stuck jobs, no tasks should be created."""
    with patch("app.main.SessionLocal", return_value=MagicMock()), \
         patch("app.main.JobDAO.get_resumable_jobs", return_value=[]), \
         patch("app.main.asyncio.create_task") as create_task:
        with TestClient(app):
            pass

    create_task.assert_not_called()


def test_startup_closes_db_session_always():
    """DB session must be closed after startup regardless of job count."""
    mock_session = MagicMock()

    with patch("app.main.SessionLocal", return_value=mock_session), \
         patch("app.main.JobDAO.get_resumable_jobs", return_value=[]):
        with TestClient(app):
            pass

    mock_session.close.assert_called_once()


def test_startup_closes_db_even_with_stuck_jobs():
    """DB session must be closed even when re-queuing jobs."""
    mock_session = MagicMock()
    stuck_jobs = _make_10_stuck_jobs()

    with patch("app.main.SessionLocal", return_value=mock_session), \
         patch("app.main.JobDAO.get_resumable_jobs", return_value=stuck_jobs), \
         patch("app.main.JobDAO.reset_to_pending"), \
         patch("app.main.asyncio.create_task", side_effect=_swallow_coro):
        with TestClient(app):
            pass

    mock_session.close.assert_called_once()
