"""
API key authentication.

A single shared key, checked in constant time. Disabled (no-op) when
settings.API_KEY is unset so local dev and tests run without a key.

Accepts the key two ways so it works for both HTTP and WebSocket clients:
  - HTTP:      Authorization: Bearer <key>
  - WebSocket: ?token=<key>   (browsers can't set headers on the WS handshake)
"""
from __future__ import annotations

import secrets

from fastapi import Header, HTTPException, Query

from app.core.config import settings


def require_api_key(
    authorization: str | None = Header(None),
    token: str | None = Query(None, description="API key (WebSocket / query-string clients)"),
) -> None:
    expected = settings.API_KEY
    if not expected:
        return  # auth disabled

    provided: str | None = None
    if authorization and authorization.startswith("Bearer "):
        provided = authorization[len("Bearer "):]
    elif token:
        provided = token

    if not provided or not secrets.compare_digest(provided, expected):
        raise HTTPException(status_code=401, detail="Invalid or missing API key")
