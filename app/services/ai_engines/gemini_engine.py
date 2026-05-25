"""Gemini Vision AI Engine — LEGO block #1."""

from __future__ import annotations

import asyncio
from typing import Any

import google.generativeai as genai

from app.core.config import settings
from app.services.ai_engines.base import BaseAIEngine
from app.services.prompts import ANALYSIS_PROMPT

# Configure the SDK once at import time
genai.configure(api_key=settings.GEMINI_API_KEY)

_DEFAULT_TEMPERATURE = 0.2  # deterministic for single-sample mode


class GeminiEngine(BaseAIEngine):
    """Google Gemini Vision implementation."""

    name = "gemini"

    async def _call_api(
        self,
        img_bytes: bytes,
        mime_type: str,
        temperature: float | None = None,
    ) -> str:
        """
        Send image to Gemini and return raw text.

        Runs the synchronous SDK call in a thread so the event loop stays
        free — required for true concurrency when asyncio.gather fires
        multiple samples in parallel.
        """
        temp = temperature if temperature is not None else _DEFAULT_TEMPERATURE
        model = genai.GenerativeModel(settings.GEMINI_MODEL)

        def _sync_call() -> str:
            response = model.generate_content(
                [
                    ANALYSIS_PROMPT,
                    {"mime_type": mime_type, "data": img_bytes},
                ],
                generation_config=genai.GenerationConfig(
                    temperature=temp,
                    max_output_tokens=8192,
                ),
            )
            return response.text.strip()

        # asyncio.to_thread keeps the event loop unblocked while Gemini
        # does its (synchronous) HTTP round-trip
        return await asyncio.to_thread(_sync_call)
