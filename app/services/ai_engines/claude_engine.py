"""Claude Vision AI Engine."""
from __future__ import annotations

import base64

import anthropic

from app.services.ai_engines.base import BaseAIEngine
from app.services.prompts import ANALYSIS_PROMPT

# Models that accept sampling parameters (temperature, top_p, top_k).
# Opus 4.7+ removed these — passing temperature returns HTTP 400.
_TEMPERATURE_SUPPORTED = frozenset({
    "claude-opus-4-6",
    "claude-sonnet-4-6",
    "claude-haiku-4-5",
    "claude-haiku-4-5-20251001",
})


class ClaudeEngine(BaseAIEngine):
    """Anthropic Claude Vision implementation."""

    name = "claude"

    def __init__(self, model: str | None = None) -> None:
        self._model_name = model or "claude-opus-4-8"
        self._client = anthropic.AsyncAnthropic()

    def _supports_sampling(self) -> bool:
        # Models that reject/ignore temperature gain nothing from N samples.
        return self._model_name in _TEMPERATURE_SUPPORTED

    async def _call_api(
        self,
        img_bytes: bytes,
        mime_type: str,
        temperature: float | None = None,
        prompt: str | None = None,
    ) -> str:
        image_data = base64.standard_b64encode(img_bytes).decode("utf-8")

        kwargs: dict = {
            "model": self._model_name,
            "max_tokens": 8192,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": mime_type,
                                "data": image_data,
                            },
                        },
                        {"type": "text", "text": prompt or ANALYSIS_PROMPT},
                    ],
                }
            ],
        }

        if temperature is not None and self._model_name in _TEMPERATURE_SUPPORTED:
            kwargs["temperature"] = temperature

        response = await self._client.messages.create(**kwargs)
        return response.content[0].text.strip()
