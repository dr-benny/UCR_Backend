"""Gemini Vision AI Engine — LEGO block #1."""

from __future__ import annotations

import asyncio

import google.generativeai as genai

from app.core.config import settings
from app.services.ai_engines.base import BaseAIEngine
from app.services.prompts import ANALYSIS_PROMPT

genai.configure(api_key=settings.GEMINI_API_KEY)

_DEFAULT_TEMPERATURE = 0.2


class GeminiEngine(BaseAIEngine):
    """Google Gemini Vision implementation."""

    name = "gemini"

    def __init__(self, model: str | None = None) -> None:
        self._model_name = model or settings.GEMINI_MODEL

    async def _call_api(
        self,
        img_bytes: bytes,
        mime_type: str,
        temperature: float | None = None,
        prompt: str | None = None,
    ) -> str:
        temp = temperature if temperature is not None else _DEFAULT_TEMPERATURE
        text_prompt = prompt or ANALYSIS_PROMPT
        gemini_model = genai.GenerativeModel(self._model_name)

        def _sync_call() -> str:
            response = gemini_model.generate_content(
                [
                    text_prompt,
                    {"mime_type": mime_type, "data": img_bytes},
                ],
                generation_config=genai.GenerationConfig(
                    temperature=temp,
                    max_output_tokens=8192,
                ),
            )
            return response.text.strip()

        return await asyncio.to_thread(_sync_call)
