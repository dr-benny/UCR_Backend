"""Tests for the job-progress WebSocket (/api/jobs/{id}/ws).

Covers the paths that had no coverage: missing-job close, terminal-state
send-then-close, and the heartbeat re-read that detects completion when no
event arrives (R2).
"""
from __future__ import annotations

import json
from unittest.mock import patch

import pytest
from starlette.websockets import WebSocketDisconnect

from app.core.config import settings
from app.services.job_store import JOB_KEY
from tests._fakes import InMemoryRedis

FAKE_JOB_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


def _pending_state() -> dict:
    return {
        "status": "pending",
        "progress": {"current": 0, "total": 1, "percent": 0, "active_files": [], "last_completed": None},
    }


def _done_state() -> dict:
    return {
        "status": "done",
        "progress": {"current": 1, "total": 1, "percent": 100, "active_files": [], "last_completed": "a.jpg"},
        "results": [{"index": 0, "filename": "a.jpg", "analysis": {}}],
    }


@patch("app.api.v1.jobs.aioredis.from_url")
def test_ws_closes_when_job_missing(mock_from_url, client):
    mock_from_url.return_value = InMemoryRedis()
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect(f"/api/jobs/{FAKE_JOB_ID}/ws") as ws:
            ws.receive_json()
    assert exc.value.code == 4004


@patch("app.api.v1.jobs.aioredis.from_url")
def test_ws_terminal_job_sends_state_then_closes(mock_from_url, client):
    redis = InMemoryRedis()
    redis._store[JOB_KEY.format(job_id=FAKE_JOB_ID)] = json.dumps(_done_state())
    mock_from_url.return_value = redis

    with client.websocket_connect(f"/api/jobs/{FAKE_JOB_ID}/ws") as ws:
        msg = ws.receive_json()
        assert msg["id"] == FAKE_JOB_ID
        assert msg["status"] == "done"
        # A terminal job is closed right after the snapshot.
        with pytest.raises(WebSocketDisconnect):
            ws.receive_json()


@patch("app.api.v1.jobs.aioredis.from_url")
def test_ws_detects_completion_on_heartbeat_reread(mock_from_url, client):
    """With no published event, the heartbeat timeout must re-read state and
    notice the job finished (R2) — never block forever on a stalled socket."""
    redis = InMemoryRedis()
    redis._store[JOB_KEY.format(job_id=FAKE_JOB_ID)] = json.dumps(_pending_state())
    mock_from_url.return_value = redis

    with patch.object(settings, "WS_HEARTBEAT_INTERVAL", 0.05):
        with client.websocket_connect(f"/api/jobs/{FAKE_JOB_ID}/ws") as ws:
            assert ws.receive_json()["status"] == "pending"

            # Worker finishes out-of-band (no pub/sub event published).
            redis._store[JOB_KEY.format(job_id=FAKE_JOB_ID)] = json.dumps(_done_state())

            saw_done = False
            for _ in range(20):
                msg = ws.receive_json()
                if msg.get("status") == "done":
                    saw_done = True
                    break
                assert msg.get("type") == "heartbeat"  # only heartbeats until then
            assert saw_done
