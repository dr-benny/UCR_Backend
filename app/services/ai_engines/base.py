"""
Base AI Engine Interface.

Every AI provider (Gemini, Claude, GPT, etc.) must implement this
abstract class so the rest of the system can swap them like LEGO blocks.
"""

from __future__ import annotations

import json
import re
import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class BaseAIEngine(ABC):
    """
    Contract that all AI engines must follow.

    Subclasses only need to implement `_call_api()`.
    Everything else (file reading, JSON parsing) is handled here.
    """

    name: str = "base"  # Human-readable engine name (e.g., "gemini", "claude")

    # ── Public API (shared by ALL engines) ────────────────────

    async def analyze_image(self, image_path: str) -> dict[str, Any]:
        """Read a local image file and analyze it."""
        img_bytes = Path(image_path).read_bytes()
        return await self.analyze_image_bytes(img_bytes, mime_type="image/jpeg")

    async def analyze_image_bytes(
        self,
        img_bytes: bytes,
        mime_type: str = "image/jpeg",
    ) -> dict[str, Any]:
        """
        Analyze raw image bytes — the main entry point.

        1. Calls the provider-specific API (implemented by subclass)
        2. Extracts JSON from the raw text response
        3. Returns a structured dict
        """
        raw_text = await self._call_api(img_bytes, mime_type)

        logger.info("--- %s RAW RESPONSE ---\n%s", self.name.upper(), raw_text)
        logger.info("---------------------------")

        parsed = self._extract_json(raw_text)
        logger.info("Parsed JSON keys: %s", list(parsed.keys()))
        return parsed

    # ── Abstract method (each engine implements this) ─────────

    @abstractmethod
    async def _call_api(
        self,
        img_bytes: bytes,
        mime_type: str,
    ) -> str:
        """
        Send image bytes to the AI provider and return the raw text response.

        This is the ONLY method each engine needs to implement.
        Everything else (file I/O, JSON parsing, logging) is inherited.
        """
        ...

    # ── Shared utilities ──────────────────────────────────────

    @staticmethod
    def _extract_json(text: str) -> dict[str, Any]:
        """Best-effort extraction of a JSON object from any AI's response."""
        text = text.strip()

        # 1. Direct parse
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # 2. Markdown code block
        match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass

        # 3. First { … } block
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass

        # 4. Give up — return raw text wrapped
        return {"_raw_text": text, "_parse_error": True}
