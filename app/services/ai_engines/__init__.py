"""
AI Engine Registry & Factory.

Usage:
    from app.services.ai_engines import get_engine, list_engines

    engine = get_engine()                            # default from settings
    engine = get_engine("gemini")                    # explicit engine
    engine = get_engine("gemini", "gemini-2.5-pro") # explicit engine + model
    result = await engine.analyze_image("path/to/img.jpg")
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.core.config import settings

if TYPE_CHECKING:
    from app.services.ai_engines.base import BaseAIEngine

logger = logging.getLogger(__name__)

# ── Engine Registry ───────────────────────────────────────────────────────────
# key → (module_path, class_name, known_models)
# known_models: empty list means any model string is accepted without validation
_REGISTRY: dict[str, tuple[str, str, list[str]]] = {
    "gemini": (
        "app.services.ai_engines.gemini_engine",
        "GeminiEngine",
        [
            "gemini-2.5-flash",
            "gemini-2.5-pro",
            "gemini-2.0-flash",
            "gemini-1.5-flash",
            "gemini-1.5-pro",
        ],
    ),
    # Future engines — uncomment and add engine file when ready:
    # "claude": ("app.services.ai_engines.claude_engine", "ClaudeEngine", [
    #     "claude-opus-4-8", "claude-sonnet-4-6", "claude-haiku-4-5-20251001",
    # ]),
    # "gpt4": ("app.services.ai_engines.gpt_engine", "GPTEngine", [
    #     "gpt-4o", "gpt-4o-mini",
    # ]),
}

# Cache: one instance per (engine_name, model_name) pair
_instances: dict[str, BaseAIEngine] = {}


def get_engine(name: str | None = None, model: str | None = None) -> BaseAIEngine:
    """
    Return a (cached) engine instance for the given name + model.

    Args:
        name:  Engine name (e.g. "gemini"). Defaults to settings.AI_ENGINE.
        model: Model override (e.g. "gemini-2.5-pro"). Defaults to engine default.

    Raises:
        ValueError: unknown engine name or model not in known list.
    """
    engine_name = (name or settings.AI_ENGINE).lower()

    if engine_name not in _REGISTRY:
        available = ", ".join(sorted(_REGISTRY.keys()))
        raise ValueError(f"Unknown AI engine '{engine_name}'. Available: {available}")

    _, _, known_models = _REGISTRY[engine_name]
    if model and known_models and model not in known_models:
        raise ValueError(
            f"Unknown model '{model}' for engine '{engine_name}'. "
            f"Available: {', '.join(known_models)}"
        )

    cache_key = f"{engine_name}:{model or ''}"
    if cache_key in _instances:
        return _instances[cache_key]

    module_path, class_name, _ = _REGISTRY[engine_name]
    import importlib
    module = importlib.import_module(module_path)
    engine_class = getattr(module, class_name)
    instance = engine_class(model=model)

    _instances[cache_key] = instance
    logger.info("AI engine initialized: %s (model=%s)", engine_name, model or "default")
    return instance


def list_engines() -> list[dict]:
    """Return all registered engines with their known models."""
    result = []
    for engine_name, (_, _, known_models) in sorted(_REGISTRY.items()):
        result.append({"name": engine_name, "models": known_models})
    return result
