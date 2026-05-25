"""
Unit tests for BaseAIEngine._extract_json.

This is a pure static method with no external dependencies.
"""
import pytest
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
