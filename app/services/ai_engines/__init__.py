"""
AI Engine Registry & Factory.

Usage:
    from app.services.ai_engines import get_engine

    engine = get_engine()            # Uses default from settings.AI_ENGINE
    engine = get_engine("gemini")    # Explicit choice
    result = await engine.analyze_image("path/to/img.jpg")
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.core.config import settings

if TYPE_CHECKING:
    from app.services.ai_engines.base import BaseAIEngine

logger = logging.getLogger(__name__)

# ── Engine Registry ───────────────────────────────────────────
# Key = name used in config/API, Value = import path + class
_REGISTRY: dict[str, tuple[str, str]] = {
    "gemini": ("services.ai_engines.gemini_engine", "GeminiEngine"),
    # Future engines:
    # "claude": ("services.ai_engines.claude_engine", "ClaudeEngine"),
    # "gpt4":  ("services.ai_engines.gpt_engine",    "GPTEngine"),
}

# Cache: instantiated engines (one per name, reused)
_instances: dict[str, BaseAIEngine] = {}


def get_engine(name: str | None = None) -> BaseAIEngine:
    """
    Get an AI engine instance by name.

    - If name is None, uses settings.AI_ENGINE (default).
    - Engines are instantiated once and cached.

    Raises:
        ValueError: if the engine name is not registered.
    """
    engine_name = (name or settings.AI_ENGINE).lower()

    # Return cached instance if available
    if engine_name in _instances:
        return _instances[engine_name]

    # Look up in registry
    if engine_name not in _REGISTRY:
        available = ", ".join(sorted(_REGISTRY.keys()))
        raise ValueError(
            f"Unknown AI engine '{engine_name}'. Available: {available}"
        )

    module_path, class_name = _REGISTRY[engine_name]

    # Lazy import — only loads the engine when first requested
    import importlib
    module = importlib.import_module(module_path)
    engine_class = getattr(module, class_name)
    instance = engine_class()

    _instances[engine_name] = instance
    logger.info("AI engine initialized: %s (%s.%s)", engine_name, module_path, class_name)
    return instance


def list_engines() -> list[str]:
    """Return all registered engine names."""
    return sorted(_REGISTRY.keys())
