"""Durable, file-backed store for the custom prompt library.

Each prompt is one JSON file under settings.PROMPT_DIR (`<id>.json`). Files on
disk have no TTL and aren't subject to Redis eviction, so a saved prompt won't
silently vanish — the reason this is NOT kept in Redis (which the app uses only
for ephemeral, 24h-TTL job state).

Writes are atomic (temp file + os.replace) so a crash can't leave a half-written
prompt. CRUD is low-frequency and only touches one file per call, so no locking
is needed for realistic usage; concurrent edits to the *same* prompt are
last-write-wins.
"""
from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path
from typing import Any

from app.core.config import settings


def _dir() -> Path:
    d = Path(settings.PROMPT_DIR)
    d.mkdir(parents=True, exist_ok=True)
    return d


def _path(prompt_id: str) -> Path:
    return _dir() / f"{prompt_id}.json"


def _write(prompt_id: str, record: dict[str, Any]) -> None:
    path = _path(prompt_id)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)  # atomic on POSIX


def _read(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def create_prompt(name: str, text: str) -> dict[str, Any]:
    prompt_id = uuid.uuid4().hex[:12]
    now = time.time()
    record = {"id": prompt_id, "name": name, "text": text, "created_at": now, "updated_at": now}
    _write(prompt_id, record)
    return record


def get_prompt(prompt_id: str) -> dict[str, Any] | None:
    path = _path(prompt_id)
    return _read(path) if path.is_file() else None


def list_prompts() -> list[dict[str, Any]]:
    records = [r for f in _dir().glob("*.json") if (r := _read(f)) is not None]
    records.sort(key=lambda r: r.get("created_at", 0), reverse=True)  # newest first
    return records


def update_prompt(prompt_id: str, name: str | None = None, text: str | None = None) -> dict[str, Any] | None:
    record = get_prompt(prompt_id)
    if record is None:
        return None
    if name is not None:
        record["name"] = name
    if text is not None:
        record["text"] = text
    record["updated_at"] = time.time()
    _write(prompt_id, record)
    return record


def delete_prompt(prompt_id: str) -> bool:
    path = _path(prompt_id)
    if not path.is_file():
        return False
    path.unlink(missing_ok=True)
    return True


def resolve_text(prompt_id: str | None) -> str | None:
    """Return a stored prompt's text, or None when no id is given.

    Raises KeyError if an id is supplied but no such prompt exists, so callers
    can reject the request instead of silently using the built-in prompt.
    """
    if not prompt_id:
        return None
    record = get_prompt(prompt_id)
    if record is None:
        raise KeyError(prompt_id)
    return record["text"]
