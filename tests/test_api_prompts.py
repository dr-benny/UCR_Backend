"""Tests for the prompt library (/api/prompts) and prompt_id threading."""
from __future__ import annotations

from io import BytesIO
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.config import settings
from app.services import prompt_store
from tests._fakes import InMemoryRedis


@pytest.fixture
def prompt_dir(tmp_path):
    """Point the file-backed prompt store at an isolated temp dir."""
    with patch.object(settings, "PROMPT_DIR", str(tmp_path)):
        yield tmp_path


# ── CRUD ──────────────────────────────────────────────────────

def test_create_and_get_prompt(client, prompt_dir):
    r = client.post("/api/prompts", json={"name": "walkability", "text": "Analyze walkability."})
    assert r.status_code == 201
    pid = r.json()["id"]
    assert r.json()["name"] == "walkability"

    g = client.get(f"/api/prompts/{pid}")
    assert g.status_code == 200
    assert g.json()["text"] == "Analyze walkability."


def test_prompt_persists_as_file_on_disk(client, prompt_dir):
    """The whole point: a saved prompt is a durable file, not a TTL'd cache key."""
    pid = client.post("/api/prompts", json={"name": "keep", "text": "forever"}).json()["id"]
    assert (prompt_dir / f"{pid}.json").is_file()


def test_list_prompts_newest_first(client, prompt_dir):
    client.post("/api/prompts", json={"name": "a", "text": "x"})
    client.post("/api/prompts", json={"name": "b", "text": "y"})
    r = client.get("/api/prompts")
    assert r.json()["total"] == 2
    assert {p["name"] for p in r.json()["prompts"]} == {"a", "b"}


def test_update_prompt_partial(client, prompt_dir):
    pid = client.post("/api/prompts", json={"name": "a", "text": "x"}).json()["id"]
    r = client.put(f"/api/prompts/{pid}", json={"text": "new text"})
    assert r.status_code == 200
    assert r.json()["text"] == "new text"
    assert r.json()["name"] == "a"  # untouched


def test_delete_prompt(client, prompt_dir):
    pid = client.post("/api/prompts", json={"name": "a", "text": "x"}).json()["id"]
    assert client.delete(f"/api/prompts/{pid}").status_code == 204
    assert client.get(f"/api/prompts/{pid}").status_code == 404


def test_get_missing_prompt_404(client, prompt_dir):
    assert client.get("/api/prompts/nope").status_code == 404


def test_update_missing_prompt_404(client, prompt_dir):
    assert client.put("/api/prompts/nope", json={"text": "x"}).status_code == 404


def test_create_rejects_empty_name(client, prompt_dir):
    assert client.post("/api/prompts", json={"name": "", "text": "x"}).status_code == 422


def test_create_rejects_overlong_text(client, prompt_dir):
    with patch.object(settings, "MAX_PROMPT_CHARS", 5):
        r = client.post("/api/prompts", json={"name": "a", "text": "way too long"})
    assert r.status_code == 422


# ── prompt_id threading into analysis ─────────────────────────

@patch("app.api.v1.upload.analyze_image_bytes", new_callable=AsyncMock, return_value={"ok": True})
def test_analyze_uses_stored_prompt(mock_analyze, client, prompt_dir):
    rec = prompt_store.create_prompt("p", "MY CUSTOM PROMPT")
    r = client.post(
        "/api/analyze",
        data={"prompt_id": rec["id"]},
        files=[("file", ("a.jpg", BytesIO(b"x"), "image/jpeg"))],
    )
    assert r.status_code == 200
    assert mock_analyze.call_args.kwargs["prompt"] == "MY CUSTOM PROMPT"


@patch("app.api.v1.upload.analyze_image_bytes", new_callable=AsyncMock, return_value={"ok": True})
def test_analyze_without_prompt_id_passes_none(mock_analyze, client, prompt_dir):
    r = client.post("/api/analyze", files=[("file", ("a.jpg", BytesIO(b"x"), "image/jpeg"))])
    assert r.status_code == 200
    assert mock_analyze.call_args.kwargs["prompt"] is None


def test_analyze_unknown_prompt_id_returns_400(client, prompt_dir):
    r = client.post(
        "/api/analyze",
        data={"prompt_id": "doesnotexist"},
        files=[("file", ("a.jpg", BytesIO(b"x"), "image/jpeg"))],
    )
    assert r.status_code == 400
    assert "prompt_id" in r.json()["detail"].lower()


@patch("app.api.v1.jobs.celery_app.send_task")
@patch("app.api.v1.jobs.get_redis")
def test_submit_job_snapshots_prompt(mock_redis, mock_send, client, prompt_dir):
    mock_redis.return_value = InMemoryRedis()
    task = MagicMock()
    task.id = "task-x"
    mock_send.return_value = task

    rec = prompt_store.create_prompt("p", "JOB PROMPT TEXT")
    r = client.post(
        "/api/jobs/images",
        data={"prompt_id": rec["id"]},
        files=[("files", ("a.jpg", BytesIO(b"x"), "image/jpeg"))],
    )
    assert r.status_code == 202
    assert r.json()["prompt_id"] == rec["id"]
    # The worker receives the snapshotted text, not just the id.
    sent_request = mock_send.call_args.kwargs["args"][1]
    assert sent_request["prompt"] == "JOB PROMPT TEXT"


@patch("app.api.v1.jobs.get_redis")
def test_submit_job_unknown_prompt_id_returns_400(mock_redis, client, prompt_dir):
    mock_redis.return_value = InMemoryRedis()
    r = client.post(
        "/api/jobs/images",
        data={"prompt_id": "nope"},
        files=[("files", ("a.jpg", BytesIO(b"x"), "image/jpeg"))],
    )
    assert r.status_code == 400
