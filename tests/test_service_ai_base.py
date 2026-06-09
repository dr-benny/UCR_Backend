"""
Unit tests for BaseAIEngine._extract_json and the AI-call timeout (R3).
"""
import asyncio

import pytest

from app.services.ai_engines import base as ai_base
from app.services.ai_engines.base import BaseAIEngine


extract = BaseAIEngine._extract_json


# ── Direct JSON ───────────────────────────────────────────────

def test_parses_direct_json_object():
    text = '{"urban_morphology": {"street_width": 8.0}, "vegetation": {}}'
    result = extract(text)
    assert result["urban_morphology"]["street_width"] == 8.0


def test_parses_direct_json_with_whitespace():
    text = '  \n{"key": "value"}\n  '
    result = extract(text)
    assert result["key"] == "value"


# ── Markdown code block ───────────────────────────────────────

def test_parses_json_inside_markdown_json_block():
    text = '```json\n{"scene_description": "A street"}\n```'
    result = extract(text)
    assert result["scene_description"] == "A street"


def test_parses_json_inside_bare_markdown_block():
    text = '```\n{"confidence_scores": {"urban_morphology": 0.9}}\n```'
    result = extract(text)
    assert result["confidence_scores"]["urban_morphology"] == 0.9


def test_parses_markdown_block_with_surrounding_text():
    text = (
        "Here is the analysis:\n"
        "```json\n"
        '{"vegetation": {"green_view_index": 0.4}}\n'
        "```\n"
        "Hope this helps."
    )
    result = extract(text)
    assert result["vegetation"]["green_view_index"] == 0.4


# ── Embedded JSON (fallback regex) ────────────────────────────

def test_parses_json_embedded_in_prose():
    text = 'The result is {"street_width": 10.0} as measured.'
    result = extract(text)
    assert result["street_width"] == 10.0


# ── Fallback (unparseable) ────────────────────────────────────

def test_returns_raw_text_when_unparseable():
    text = "I cannot parse this as JSON at all."
    result = extract(text)
    assert result["_parse_error"] is True
    assert "_raw_text" in result


def test_returns_raw_text_for_empty_string():
    result = extract("")
    assert result["_parse_error"] is True


# ── Nested JSON correctness ───────────────────────────────────

def test_preserves_nested_structure():
    data = {
        "urban_morphology": {"street_width": 6.0, "sky_view_factor": 0.7},
        "observed_features": ["trees", "road"],
        "confidence_scores": {"urban_morphology": 0.85},
    }
    import json
    result = extract(json.dumps(data))
    assert result["urban_morphology"]["sky_view_factor"] == 0.7
    assert "trees" in result["observed_features"]


# ── R3: AI-call timeout ───────────────────────────────────────

class _SlowEngine(BaseAIEngine):
    name = "slow"

    async def _call_api(self, img_bytes, mime_type, temperature=None, prompt=None):
        await asyncio.sleep(5)  # longer than the patched timeout
        return "{}"


class _FastEngine(BaseAIEngine):
    name = "fast"

    async def _call_api(self, img_bytes, mime_type, temperature=None, prompt=None):
        return '{"ok": true}'


async def test_call_with_timeout_raises_on_slow_provider(monkeypatch):
    monkeypatch.setattr(ai_base.settings, "AI_CALL_TIMEOUT", 0.05)
    with pytest.raises(asyncio.TimeoutError):
        await _SlowEngine()._call_with_timeout(b"x", "image/jpeg")


async def test_call_with_timeout_passes_through_fast_provider(monkeypatch):
    monkeypatch.setattr(ai_base.settings, "AI_CALL_TIMEOUT", 5)
    result = await _FastEngine()._call_with_timeout(b"x", "image/jpeg")
    assert result == '{"ok": true}'


# ── B4: skip multi-sampling when the model can't vary temperature ─

class _CountingEngine(BaseAIEngine):
    name = "counting"

    def __init__(self, supports: bool) -> None:
        self._supports = supports
        self.calls = 0

    def _supports_sampling(self) -> bool:
        return self._supports

    async def _call_api(self, img_bytes, mime_type, temperature=None, prompt=None):
        self.calls += 1
        return '{"urban_morphology": {"street_width": 8.0}}'


async def test_sampling_collapses_to_one_when_unsupported():
    """samples=5 on a model that ignores temperature should make ONE call, not five."""
    engine = _CountingEngine(supports=False)
    await engine.analyze_image_bytes(b"x", "image/jpeg", samples=5)
    assert engine.calls == 1


async def test_sampling_runs_n_when_supported():
    engine = _CountingEngine(supports=True)
    await engine.analyze_image_bytes(b"x", "image/jpeg", samples=5)
    assert engine.calls == 5


# ── Custom prompt reaches the provider call ───────────────────

class _PromptCapturingEngine(BaseAIEngine):
    name = "capture"

    def __init__(self) -> None:
        self.seen_prompt = "<unset>"

    async def _call_api(self, img_bytes, mime_type, temperature=None, prompt=None):
        self.seen_prompt = prompt
        return '{"ok": true}'


async def test_custom_prompt_reaches_call_api():
    engine = _PromptCapturingEngine()
    await engine.analyze_image_bytes(b"x", "image/jpeg", samples=1, prompt="CUSTOM PROMPT")
    assert engine.seen_prompt == "CUSTOM PROMPT"


async def test_no_prompt_passes_none_to_call_api():
    engine = _PromptCapturingEngine()
    await engine.analyze_image_bytes(b"x", "image/jpeg", samples=1)
    assert engine.seen_prompt is None
