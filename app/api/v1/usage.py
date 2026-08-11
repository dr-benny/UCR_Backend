"""Self-service lookup so a key holder can check their own name + quota.

Public on purpose — the key itself (passed as a query param, not a header)
is what identifies which key's usage to return, so there's nothing extra to
gate behind require_api_key.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.services import api_key_store, quota
from app.services.redis_client import get_redis

router = APIRouter(prefix="/api", tags=["usage"])


@router.get("/usage")
async def get_usage(key: str = Query(..., description="Your API key")) -> dict:
    """Look up a key's name and how much of its daily quota is left."""
    record = api_key_store.find_by_secret(key)
    if record is None:
        raise HTTPException(status_code=401, detail="Invalid API key")

    usage = await quota.get_usage(get_redis(), record)
    return {
        "name": record["name"],
        "id": record["id"],
        "max_samples": record.get("max_samples"),
        **usage,
    }
