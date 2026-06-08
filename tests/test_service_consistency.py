"""
Unit tests for BaseAIEngine aggregation helpers.
All pure logic — no I/O, no mocking needed.
"""
from __future__ import annotations

import pytest

from app.services.ai_engines.base import BaseAIEngine

aggregate_value = BaseAIEngine._aggregate_value
agreement_score = BaseAIEngine._agreement_score
aggregate_samples = BaseAIEngine._aggregate_samples


# ── _aggregate_value ──────────────────────────────────────────

def test_aggregate_value_numeric_median_odd():
    assert aggregate_value([1.0, 2.0, 3.0]) == 2.0


def test_aggregate_value_numeric_median_even():
    assert aggregate_value([1.0, 3.0]) == 2.0


def test_aggregate_value_string_majority():
    assert aggregate_value(["asphalt", "concrete", "asphalt"]) == "asphalt"


def test_aggregate_value_filters_none():
    assert aggregate_value([None, "asphalt", None]) == "asphalt"


def test_aggregate_value_filters_unknown():
    assert aggregate_value(["asphalt", "unknown", "asphalt"]) == "asphalt"


def test_aggregate_value_all_unknown_returns_unknown():
    assert aggregate_value(["unknown", None, "unknown"]) == "unknown"


def test_aggregate_value_all_none_returns_unknown():
    assert aggregate_value([None, None]) == "unknown"


# ── _agreement_score ──────────────────────────────────────────

def test_agreement_score_identical_numbers():
    assert agreement_score([5.0, 5.0, 5.0]) == 1.0


def test_agreement_score_varied_numbers_below_one():
    score = agreement_score([1.0, 10.0, 5.0])
    assert 0.3 <= score < 1.0


def test_agreement_score_strings_unanimous():
    assert agreement_score(["flat", "flat", "flat"]) == 1.0


def test_agreement_score_strings_split():
    score = agreement_score(["flat", "slight", "flat"])
    assert score == pytest.approx(2 / 3, rel=0.01)


def test_agreement_score_empty_returns_half():
    assert agreement_score([None, None]) == 0.5


def test_agreement_score_single_real_value_returns_one():
    assert agreement_score([5.0, None]) == 1.0


def test_agreement_score_zeros_returns_one():
    assert agreement_score([0.0, 0.0]) == 1.0


# ── _aggregate_samples ────────────────────────────────────────

def test_aggregate_samples_empty_returns_empty():
    assert aggregate_samples([]) == {}


def test_aggregate_samples_single_passthrough():
    sample = {"a": 1.0, "b": "x"}
    assert aggregate_samples([sample]) is sample


def test_aggregate_samples_floats_use_median():
    samples = [
        {"street_width": 6.0},
        {"street_width": 8.0},
        {"street_width": 10.0},
    ]
    result = aggregate_samples(samples)
    assert result["street_width"] == 8.0


def test_aggregate_samples_strings_majority_vote():
    samples = [
        {"surface": "asphalt"},
        {"surface": "concrete"},
        {"surface": "asphalt"},
    ]
    result = aggregate_samples(samples)
    assert result["surface"] == "asphalt"


def test_aggregate_samples_nested_dicts():
    samples = [
        {"urban_morphology": {"street_width": 6.0, "sky_view_factor": 0.4}},
        {"urban_morphology": {"street_width": 8.0, "sky_view_factor": 0.6}},
    ]
    result = aggregate_samples(samples)
    assert result["urban_morphology"]["street_width"] == 7.0
    assert result["urban_morphology"]["sky_view_factor"] == pytest.approx(0.5)


def test_aggregate_samples_lists_union_deduped():
    samples = [
        {"features": ["trees", "road"]},
        {"features": ["road", "buildings"]},
    ]
    result = aggregate_samples(samples)
    features = result["features"]
    assert "trees" in features
    assert "road" in features
    assert "buildings" in features
    assert features.count("road") == 1


def test_aggregate_samples_confidence_blending_perfect_agreement():
    samples = [
        {
            "urban_morphology": {"street_width": 6.0},
            "confidence_scores": {"urban_morphology": 0.9},
        },
        {
            "urban_morphology": {"street_width": 6.0},
            "confidence_scores": {"urban_morphology": 0.9},
        },
    ]
    result = aggregate_samples(samples)
    conf = result["confidence_scores"]["urban_morphology"]
    assert conf >= 0.8


def test_aggregate_samples_confidence_blending_low_agreement():
    samples = [
        {
            "urban_morphology": {"street_width": 3.0},
            "confidence_scores": {"urban_morphology": 0.9},
        },
        {
            "urban_morphology": {"street_width": 30.0},
            "confidence_scores": {"urban_morphology": 0.9},
        },
    ]
    result = aggregate_samples(samples)
    conf = result["confidence_scores"]["urban_morphology"]
    # Low agreement → conf clamped toward minimum: 0.9 * (0.4 + 0.6 * 0.3) ≈ 0.522
    # Perfect agreement upper bound: 0.9 * (0.4 + 0.6 * 1.0) = 0.9
    assert 0.3 <= conf <= 0.9
