"""API key authentication.

Looks up the presented key against the file-backed key store
(app/services/api_key_store.py). No keys on disk == auth disabled, so local
dev and tests run without a key.

Accepts the key two ways so it works for both HTTP and WebSocket clients:
  - HTTP:      Authorization: Bearer <key>
  - WebSocket: ?token=<key>   (browsers can't set headers on the WS handshake)

Returns the matched key record so callers that also need to enforce a usage
quota (see app/services/quota.py) can use it without looking the key up twice.
"""
from __future__ import annotations

from typing import Any

from fastapi import Header, HTTPException, Query

from app.services import api_key_store


def require_api_key(
    authorization: str | None = Header(None),
    token: str | None = Query(None, description="API key (WebSocket / query-string clients)"),
) -> dict[str, Any] | None:
    if not api_key_store.list_keys():
        return None  # auth disabled — no keys configured

    provided: str | None = None
    if authorization and authorization.startswith("Bearer "):
        provided = authorization[len("Bearer "):]
    elif token:
        provided = token

    if not provided:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")

    matched = api_key_store.find_by_secret(provided)
    if matched is None:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")
    return matched
