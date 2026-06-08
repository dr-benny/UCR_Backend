"""Tests for /api/jobs endpoints."""
from __future__ import annotations

import json
import os
import time
from io import BytesIO
from unittest.mock import MagicMock, patch

from app.services.job_store import JOB_INDEX, JOB_KEY

FAKE_JOB_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
FAKE_TASK_ID = "task-0000-0000-0000-0000"


class _InMemoryRedis:
    """Minimal async Redis substitute for unit tests."""

    def __init__(self):
        self._store: dict = {}
        self._ss: dict = {}

    async def set(self, key, value, ex=None, **_):
        self._store[key] = value

    async def get(self, key):
        return self._store.get(key)

    async def delete(self, *keys):
        for k in keys:
            self._store.pop(k, None)

    async def incr(self, key):
        val = int(self._store.get(key, 0)) + 1
        self._store[key] = val
        return val

    async def expire(self, *_): pass

    async def zadd(self, name, mapping):
        ss = self._ss.setdefault(name, {})
        ss.update(mapping)

    async def zrem(self, name, *members):
        for m in members:
            self._ss.get(name, {}).pop(m, None)

    async def zcard(self, name):
        return len(self._ss.get(name, {}))

    async def zscore(self, name, member):
        return self._ss.get(name, {}).get(member)

    async def zrevrange(self, name, start, stop, withscores=False):
        items = sorted(self._ss.get(name, {}).items(), key=lambda x: -x[1])
        sliced = items[start:] if stop == -1 else items[start:stop + 1]
        if withscores:
            return [(k.encode(), v) for k, v in sliced]
        return [k.encode() for k, _ in sliced]

    async def zremrangebyscore(self, *_): pass

    async def keys(self, *_):
        return list(self._store.keys())

    async def scan_iter(self, match=None, count=None):
        import fnmatch
        for k in list(self._store.keys()):
            if match is None or fnmatch.fnmatch(k, match):
                yield k

    async def publish(self, *_): pass

    async def ping(self): return True

    async def aclose(self): pass


def _job_state(status="pending"):
    return {
        "status": status,
        "progress": {
            "current": 0, "total": 1, "percent": 0,
            "active_files": [], "last_completed": None,
        },
        "engine": "gemini",
        "model": "gemini-2.5-flash",
        "_images": [{"path": "/tmp/test_images/test.jpg", "filename": "test.jpg"}],
        "_task_id": FAKE_TASK_ID,
    }


def _done_state():
    s = _job_state("done")
    s["results"] = [
        {
            "index": 0,
            "filename": "test.jpg",
            "analysis": {
                "scene_description": "A street.",
                "urban_morphology": {"street_width": 8.0, "sky_view_factor": 0.6},
                "vegetation": {"green_view_index": 0.3},
                "surface_and_flood": {"surface_material": "asphalt"},
                "health_livability": {"walkability_obstruction": "none"},
                "confidence_scores": {"urban_morphology": 0.9, "vegetation": 0.8},
            },
        }
    ]
    return s


# ── POST /api/jobs/images ─────────────────────────────────────

@patch("app.api.v1.jobs.get_engine")
@patch("app.api.v1.jobs.celery_app.send_task")
@patch("app.api.v1.jobs.aioredis.from_url")
def test_submit_job_success(mock_from_url, mock_send_task, mock_get_engine, client):
    mock_from_url.return_value = _InMemoryRedis()
    task = MagicMock()
    task.id = FAKE_TASK_ID
    mock_send_task.return_value = task

    r = client.post(
        "/api/jobs/images",
        files=[("files", ("photo.jpg", BytesIO(b"fake-image-bytes"), "image/jpeg"))],
    )
    assert r.status_code == 202
    data = r.json()
    assert data["status"] == "pending"
    assert data["progress"]["total"] == 1
    assert "id" in data
    mock_send_task.assert_called_once()


@patch("app.api.v1.jobs.aioredis.from_url")
def test_submit_too_many_files_returns_400(mock_from_url, client):
    mock_from_url.return_value = _InMemoryRedis()
    files = [("files", (f"img{i}.jpg", BytesIO(b"b"), "image/jpeg")) for i in range(201)]
    r = client.post("/api/jobs/images", files=files)
    assert r.status_code == 400
    assert "200" in r.json()["detail"]


@patch("app.api.v1.jobs.aioredis.from_url")
def test_submit_empty_file_returns_400(mock_from_url, client):
    mock_from_url.return_value = _InMemoryRedis()
    r = client.post(
        "/api/jobs/images",
        files=[("files", ("empty.jpg", BytesIO(b""), "image/jpeg"))],
    )
    assert r.status_code == 400
    assert "empty" in r.json()["detail"].lower()


@patch("app.api.v1.jobs.aioredis.from_url")
def test_submit_oversized_file_returns_400(mock_from_url, client):
    mock_from_url.return_value = _InMemoryRedis()
    big = b"x" * (21 * 1024 * 1024)
    r = client.post(
        "/api/jobs/images",
        files=[("files", ("big.jpg", BytesIO(big), "image/jpeg"))],
    )
    assert r.status_code == 400
    assert "exceed" in r.json()["detail"].lower()


# ── GET /api/jobs/{id} ────────────────────────────────────────

@patch("app.api.v1.jobs.aioredis.from_url")
def test_get_job_found(mock_from_url, client):
    redis = _InMemoryRedis()
    redis._store[JOB_KEY.format(job_id=FAKE_JOB_ID)] = json.dumps(_job_state())
    redis._ss[JOB_INDEX] = {FAKE_JOB_ID: time.time()}
    mock_from_url.return_value = redis

    r = client.get(f"/api/jobs/{FAKE_JOB_ID}")
    assert r.status_code == 200
    data = r.json()
    assert data["id"] == FAKE_JOB_ID
    assert data["status"] == "pending"


@patch("app.api.v1.jobs.aioredis.from_url")
def test_get_job_not_found(mock_from_url, client):
    mock_from_url.return_value = _InMemoryRedis()
    r = client.get(f"/api/jobs/{FAKE_JOB_ID}")
    assert r.status_code == 404


# ── GET /api/jobs ─────────────────────────────────────────────

@patch("app.api.v1.jobs.aioredis.from_url")
def test_list_jobs(mock_from_url, client):
    redis = _InMemoryRedis()
    redis._store[JOB_KEY.format(job_id=FAKE_JOB_ID)] = json.dumps(_job_state())
    redis._ss[JOB_INDEX] = {FAKE_JOB_ID: time.time()}
    mock_from_url.return_value = redis

    r = client.get("/api/jobs")
    assert r.status_code == 200
    data = r.json()
    assert data["total"] >= 1
    assert any(j["id"] == FAKE_JOB_ID for j in data["jobs"])


@patch("app.api.v1.jobs.aioredis.from_url")
def test_list_jobs_filter_by_status(mock_from_url, client):
    redis = _InMemoryRedis()
    redis._store[JOB_KEY.format(job_id=FAKE_JOB_ID)] = json.dumps(_job_state("done"))
    redis._ss[JOB_INDEX] = {FAKE_JOB_ID: time.time()}
    mock_from_url.return_value = redis

    r = client.get("/api/jobs?status=pending")
    assert r.status_code == 200
    assert r.json()["total"] == 0


# ── DELETE /api/jobs/{id} ─────────────────────────────────────

@patch("app.api.v1.jobs.aioredis.from_url")
def test_delete_job_success(mock_from_url, client):
    redis = _InMemoryRedis()
    state = _job_state(status="processing")
    redis._store[JOB_KEY.format(job_id=FAKE_JOB_ID)] = json.dumps(state)
    redis._ss[JOB_INDEX] = {FAKE_JOB_ID: time.time()}
    mock_from_url.return_value = redis

    with (
        patch("app.api.v1.jobs.cleanup_images"),
        patch("app.api.v1.jobs.celery_app.control.revoke") as mock_revoke,
    ):
        r = client.delete(f"/api/jobs/{FAKE_JOB_ID}")

    assert r.status_code == 204
    assert JOB_KEY.format(job_id=FAKE_JOB_ID) not in redis._store
    mock_revoke.assert_called_once_with(FAKE_TASK_ID, terminate=True)


@patch("app.api.v1.jobs.aioredis.from_url")
def test_delete_job_not_found(mock_from_url, client):
    mock_from_url.return_value = _InMemoryRedis()
    r = client.delete(f"/api/jobs/{FAKE_JOB_ID}")
    assert r.status_code == 404


# ── POST /api/jobs/{id}/retry ─────────────────────────────────

@patch("app.api.v1.jobs.celery_app.send_task")
@patch("app.api.v1.jobs.aioredis.from_url")
def test_retry_failed_job(mock_from_url, mock_send_task, client):
    img_path = "/tmp/test_images/retry_test.jpg"
    with open(img_path, "wb") as f:
        f.write(b"fake-image")

    redis = _InMemoryRedis()
    state = _job_state("failed")
    state["_images"] = [{"path": img_path, "filename": "retry_test.jpg"}]
    redis._store[JOB_KEY.format(job_id=FAKE_JOB_ID)] = json.dumps(state)
    mock_from_url.return_value = redis

    task = MagicMock()
    task.id = "new-task-id"
    mock_send_task.return_value = task

    r = client.post(f"/api/jobs/{FAKE_JOB_ID}/retry")
    assert r.status_code == 202
    assert r.json()["status"] == "pending"
    mock_send_task.assert_called_once()

    os.unlink(img_path)


@patch("app.api.v1.jobs.aioredis.from_url")
def test_retry_non_failed_job_returns_400(mock_from_url, client):
    redis = _InMemoryRedis()
    redis._store[JOB_KEY.format(job_id=FAKE_JOB_ID)] = json.dumps(_job_state("pending"))
    mock_from_url.return_value = redis

    r = client.post(f"/api/jobs/{FAKE_JOB_ID}/retry")
    assert r.status_code == 400
    assert "failed" in r.json()["detail"].lower()


# ── GET /api/jobs/{id}/export ─────────────────────────────────

@patch("app.api.v1.jobs.aioredis.from_url")
def test_export_json(mock_from_url, client):
    redis = _InMemoryRedis()
    redis._store[JOB_KEY.format(job_id=FAKE_JOB_ID)] = json.dumps(_done_state())
    mock_from_url.return_value = redis

    r = client.get(f"/api/jobs/{FAKE_JOB_ID}/export?format=json")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/json")
    data = r.json()
    assert data["job_id"] == FAKE_JOB_ID
    assert len(data["results"]) == 1


@patch("app.api.v1.jobs.aioredis.from_url")
def test_export_csv(mock_from_url, client):
    redis = _InMemoryRedis()
    redis._store[JOB_KEY.format(job_id=FAKE_JOB_ID)] = json.dumps(_done_state())
    mock_from_url.return_value = redis

    r = client.get(f"/api/jobs/{FAKE_JOB_ID}/export?format=csv")
    assert r.status_code == 200
    assert "text/csv" in r.headers["content-type"]
    lines = [l for l in r.text.strip().split("\n") if l]
    assert len(lines) == 2  # header + 1 data row


@patch("app.api.v1.jobs.aioredis.from_url")
def test_export_csv_columns_include_analysis_fields(mock_from_url, client):
    redis = _InMemoryRedis()
    redis._store[JOB_KEY.format(job_id=FAKE_JOB_ID)] = json.dumps(_done_state())
    mock_from_url.return_value = redis

    r = client.get(f"/api/jobs/{FAKE_JOB_ID}/export?format=csv")
    header = r.text.split("\n")[0]
    assert "urban_morphology_street_width" in header
    assert "confidence_urban_morphology" in header


@patch("app.api.v1.jobs.aioredis.from_url")
def test_export_job_not_done_returns_400(mock_from_url, client):
    redis = _InMemoryRedis()
    redis._store[JOB_KEY.format(job_id=FAKE_JOB_ID)] = json.dumps(_job_state("processing"))
    mock_from_url.return_value = redis

    r = client.get(f"/api/jobs/{FAKE_JOB_ID}/export")
    assert r.status_code == 400
    assert "processing" in r.json()["detail"]


@patch("app.api.v1.jobs.aioredis.from_url")
def test_export_job_not_found(mock_from_url, client):
    mock_from_url.return_value = _InMemoryRedis()
    r = client.get(f"/api/jobs/{FAKE_JOB_ID}/export")
    assert r.status_code == 404


@patch("app.api.v1.jobs.aioredis.from_url")
def test_export_invalid_format_returns_400(mock_from_url, client):
    redis = _InMemoryRedis()
    redis._store[JOB_KEY.format(job_id=FAKE_JOB_ID)] = json.dumps(_done_state())
    mock_from_url.return_value = redis

    r = client.get(f"/api/jobs/{FAKE_JOB_ID}/export?format=xml")
    assert r.status_code == 400


# ── update_state merge (bug #1 regression) ────────────────────

async def test_update_state_preserves_unset_fields():
    """Worker writing status/progress must not wipe _task_id/engine/model."""
    from app.services.job_store import update_state, get_state

    redis = _InMemoryRedis()
    await redis.set(
        JOB_KEY.format(job_id=FAKE_JOB_ID),
        json.dumps({
            "status": "pending",
            "engine": "claude",
            "model": "claude-opus-4-8",
            "_task_id": FAKE_TASK_ID,
            "_images": [{"path": "/x.jpg", "filename": "x.jpg"}],
        }),
    )

    await update_state(redis, FAKE_JOB_ID, {"status": "processing", "progress": {"current": 0}})

    merged = await get_state(redis, FAKE_JOB_ID)
    assert merged["status"] == "processing"          # updated
    assert merged["_task_id"] == FAKE_TASK_ID          # preserved → delete can still revoke
    assert merged["engine"] == "claude"                # preserved → API response keeps engine
    assert merged["model"] == "claude-opus-4-8"        # preserved


# ── /health/ready ─────────────────────────────────────────────

@patch("app.main.aioredis.from_url")
def test_readiness_ok(mock_from_url, client):
    mock_from_url.return_value = _InMemoryRedis()
    r = client.get("/health/ready")
    assert r.status_code == 200
    assert r.json()["redis"] == "ok"


@patch("app.main.aioredis.from_url")
def test_readiness_redis_down_returns_503(mock_from_url, client):
    broken = _InMemoryRedis()

    async def _boom():
        raise ConnectionError("connection refused")

    broken.ping = _boom
    mock_from_url.return_value = broken

    r = client.get("/health/ready")
    assert r.status_code == 503


# ── R1: stuck-job reaper ──────────────────────────────────────

@patch("app.main.aioredis.from_url")
async def test_reaper_marks_stalled_job_failed(mock_from_url):
    import time as _t
    from app.main import _reap_stuck_jobs

    redis = _InMemoryRedis()
    stale = _job_state("processing")
    stale["_heartbeat"] = _t.time() - 9999  # way past STUCK_JOB_TIMEOUT
    redis._store[JOB_KEY.format(job_id=FAKE_JOB_ID)] = json.dumps(stale)
    mock_from_url.return_value = redis

    await _reap_stuck_jobs()

    result = json.loads(redis._store[JOB_KEY.format(job_id=FAKE_JOB_ID)])
    assert result["status"] == "failed"
    assert "stalled" in result["error"].lower()


@patch("app.main.aioredis.from_url")
async def test_reaper_leaves_fresh_job_alone(mock_from_url):
    import time as _t
    from app.main import _reap_stuck_jobs

    redis = _InMemoryRedis()
    fresh = _job_state("processing")
    fresh["_heartbeat"] = _t.time()  # just beat
    redis._store[JOB_KEY.format(job_id=FAKE_JOB_ID)] = json.dumps(fresh)
    mock_from_url.return_value = redis

    await _reap_stuck_jobs()

    result = json.loads(redis._store[JOB_KEY.format(job_id=FAKE_JOB_ID)])
    assert result["status"] == "processing"  # untouched


@patch("app.main.aioredis.from_url")
async def test_reaper_ignores_done_job(mock_from_url):
    import time as _t
    from app.main import _reap_stuck_jobs

    redis = _InMemoryRedis()
    done = _done_state()
    done["_heartbeat"] = _t.time() - 9999  # old, but already terminal
    redis._store[JOB_KEY.format(job_id=FAKE_JOB_ID)] = json.dumps(done)
    mock_from_url.return_value = redis

    await _reap_stuck_jobs()

    result = json.loads(redis._store[JOB_KEY.format(job_id=FAKE_JOB_ID)])
    assert result["status"] == "done"  # not flipped to failed
