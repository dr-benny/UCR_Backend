"""Gemini Vision AI Engine — LEGO block #1."""

from __future__ import annotations

from typing import Any

import google.generativeai as genai

from app.core.config import settings
from app.services.ai_engines.base import BaseAIEngine
from app.services.prompts import ANALYSIS_PROMPT

# Configure the SDK once at import time
genai.configure(api_key=settings.GEMINI_API_KEY)


class GeminiEngine(BaseAIEngine):
    """Google Gemini Vision implementation."""

    name = "gemini"

    async def _call_api(self, img_bytes: bytes, mime_type: str) -> str:
        """Send image to Gemini and return raw text."""
        model = genai.GenerativeModel(settings.GEMINI_MODEL)

        response = model.generate_content(
            [
                ANALYSIS_PROMPT,
                {"mime_type": mime_type, "data": img_bytes},
            ],
            generation_config=genai.GenerationConfig(
                temperature=0.2,
                max_output_tokens=8192,
            ),
        )

        return response.text.strip()
