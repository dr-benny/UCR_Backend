"""Durable, file-backed store for issued API keys.

Each key is one JSON file under settings.API_KEY_DIR (`<id>.json`), the same
pattern as services/prompt_store.py: plain files on disk (no TTL, not subject
to Redis eviction) so a key won't silently vanish, manageable by hand or via
scripts/manage_api_keys.py. The secret itself is stored in cleartext, same
trust level as the .env file that already holds the AI provider keys.

No keys on disk = auth disabled (dev/local default), mirroring the old
single-shared-key behavior when API_KEY was unset.
"""
from __future__ import annotations

import json
import os
import secrets
import time
import uuid
from pathlib import Path
from typing import Any

from app.core.config import settings


def _dir() -> Path:
    d = Path(settings.API_KEY_DIR)
    d.mkdir(parents=True, exist_ok=True)
    return d


def _path(key_id: str) -> Path:
    return _dir() / f"{key_id}.json"


def _write(key_id: str, record: dict[str, Any]) -> None:
    path = _path(key_id)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)  # atomic on POSIX


def _read(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def create_key(name: str, daily_limit: int | None = None, max_samples: int | None = None) -> dict[str, Any]:
    """Generate a new key and persist it. The secret is only ever returned here."""
    key_id = uuid.uuid4().hex[:12]
    record = {
        "id": key_id,
        "key": secrets.token_urlsafe(32),
        "name": name,
        "daily_limit": daily_limit,  # None = use settings.DEFAULT_DAILY_AI_CALL_LIMIT, counted in AI calls
        # Caps the samples-per-image a caller may request with this key — they
        # can still ask for fewer. None = the caller's `samples` field (capped
        # only by the server-wide MAX_ANALYSIS_SAMPLES) applies as normal.
        "max_samples": max_samples,
        "created_at": time.time(),
    }
    _write(key_id, record)
    return record


def get_key(key_id: str) -> dict[str, Any] | None:
    path = _path(key_id)
    return _read(path) if path.is_file() else None


def list_keys() -> list[dict[str, Any]]:
    records = [r for f in _dir().glob("*.json") if (r := _read(f)) is not None]
    records.sort(key=lambda r: r.get("created_at", 0), reverse=True)  # newest first
    return records


def delete_key(key_id: str) -> bool:
    path = _path(key_id)
    if not path.is_file():
        return False
    path.unlink(missing_ok=True)
    return True


def find_by_secret(secret: str) -> dict[str, Any] | None:
    """Return the key record matching a presented secret, or None.

    Compares against every key with secrets.compare_digest (constant-time per
    comparison) rather than short-circuiting on the first match, so timing
    doesn't reveal which key (if any) is closest to the provided value.
    """
    match: dict[str, Any] | None = None
    for record in list_keys():
        if secrets.compare_digest(record["key"], secret):
            match = record
    return match
