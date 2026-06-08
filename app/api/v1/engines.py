from __future__ import annotations

from fastapi import APIRouter

from app.core.config import settings
from app.services.ai_engines import list_engines

router = APIRouter(prefix="/api/engines", tags=["engines"])


@router.get("")
def get_engines() -> dict:
    """List all available AI engines and their supported models."""
    return {
        "default_engine": settings.AI_ENGINE,
        "default_model": settings.GEMINI_MODEL,
        "engines": list_engines(),
    }
