"""
Unit tests for self-consistency aggregation in BaseAIEngine.

All tests use pure Python — no network, no database, no Gemini API.
"""
import asyncio
import pytest
from unittest.mock import AsyncMock, patch

from app.services.ai_engines.base import BaseAIEngine


# ── _aggregate_value ──────────────────────────────────────────

class TestAggregateValue:
    def test_median_of_three_floats(self):
        assert BaseAIEngine._aggregate_value([6.0, 8.0, 10.0]) == 8.0

    def test_median_of_even_count(self):
        assert BaseAIEngine._aggregate_value([4.0, 8.0]) == 6.0

    def test_median_ignores_outlier(self):
        # 100.0 is an outlier — median should stay near the cluster
        result = BaseAIEngine._aggregate_value([7.0, 8.0, 100.0])
        assert result == 8.0

    def test_majority_vote_strings(self):
        assert BaseAIEngine._aggregate_value(["flat", "flat", "slight"]) == "flat"

    def test_majority_vote_all_same(self):
        assert BaseAIEngine._aggregate_value(["asphalt", "asphalt", "asphalt"]) == "asphalt"

    def test_majority_vote_returns_original_type(self):
        result = BaseAIEngine._aggregate_value(["moderate", "moderate", "high"])
        assert isinstance(result, str)
        assert result == "moderate"

    def test_unknown_values_filtered(self):
        # Two "unknown" and one real value → real value wins
        assert BaseAIEngine._aggregate_value(["unknown", "unknown", "moderate"]) == "moderate"

    def test_all_unknown_returns_unknown(self):
        assert BaseAIEngine._aggregate_value(["unknown", "unknown"]) == "unknown"

    def test_none_values_filtered(self):
        assert BaseAIEngine._aggregate_value([None, None, 5.0]) == 5.0

    def test_empty_list_returns_unknown(self):
        assert BaseAIEngine._aggregate_value([]) == "unknown"

    def test_single_float(self):
        assert BaseAIEngine._aggregate_value([3.5]) == 3.5

    def test_numeric_rounded_to_4dp(self):
        result = BaseAIEngine._aggregate_value([0.3333333, 0.3333334, 0.3333335])
        assert isinstance(result, float)
        assert len(str(result).split(".")[-1]) <= 4


# ── _agreement_score ──────────────────────────────────────────

class TestAgreementScore:
    def test_identical_floats_score_one(self):
        assert BaseAIEngine._agreement_score([8.0, 8.0, 8.0]) == 1.0

    def test_identical_strings_score_one(self):
        assert BaseAIEngine._agreement_score(["flat", "flat", "flat"]) == 1.0

    def test_varied_floats_score_below_one(self):
        score = BaseAIEngine._agreement_score([4.0, 8.0, 12.0])
        assert score < 1.0
        assert score >= 0.3

    def test_total_disagreement_strings_score_low(self):
        score = BaseAIEngine._agreement_score(["flat", "slight", "steep"])
        assert score == pytest.approx(1 / 3, abs=0.01)

    def test_majority_strings_score_partial(self):
        score = BaseAIEngine._agreement_score(["flat", "flat", "steep"])
        assert score == pytest.approx(2 / 3, abs=0.01)

    def test_all_unknown_returns_half(self):
        assert BaseAIEngine._agreement_score(["unknown", "unknown"]) == 0.5

    def test_single_real_value_returns_one(self):
        assert BaseAIEngine._agreement_score(["flat"]) == 1.0

    def test_score_between_zero_and_one(self):
        for values in [
            [1.0, 2.0, 100.0],
            ["a", "b", "c"],
            [0.3, 0.31, 0.29],
        ]:
            score = BaseAIEngine._agreement_score(values)
            assert 0.0 <= score <= 1.0, f"Score {score} out of range for {values}"


# ── _aggregate_samples ────────────────────────────────────────

SAMPLE_A = {
    "scene_description": "Narrow Bangkok soi with shophouses.",
    "observed_features": ["buildings", "trees", "road"],
    "reference_objects": ["car (~4.5m)"],
    "urban_morphology": {
        "street_width": 8.0,
        "building_height_est_m": 12.0,
        "sky_view_factor": 0.65,
        "road_slope": "flat",
        "sidewalk_height": "raised",
    },
    "vegetation": {"green_view_index": 0.3, "tree_canopy_coverage": "moderate", "shade_fraction": 0.4},
    "surface_and_flood": {"surface_material": "asphalt", "impervious_surface_ratio": 0.8},
    "health_livability": {"walkability_obstruction": "low"},
    "evidence": {"street_width": "Car at mid-distance implies ~8m"},
    "confidence_scores": {"urban_morphology": 0.85, "vegetation": 0.80},
}

SAMPLE_B = {
    "scene_description": "Bangkok residential street.",
    "observed_features": ["buildings", "road", "motorcycle"],
    "reference_objects": ["motorcycle (~2m height)", "car (~4.5m)"],
    "urban_morphology": {
        "street_width": 9.0,
        "building_height_est_m": 12.0,
        "sky_view_factor": 0.60,
        "road_slope": "flat",
        "sidewalk_height": "raised",
    },
    "vegetation": {"green_view_index": 0.25, "tree_canopy_coverage": "moderate", "shade_fraction": 0.35},
    "surface_and_flood": {"surface_material": "asphalt", "impervious_surface_ratio": 0.85},
    "health_livability": {"walkability_obstruction": "low"},
    "evidence": {"street_width": "Motorcycle and car at same depth"},
    "confidence_scores": {"urban_morphology": 0.80, "vegetation": 0.75},
}

SAMPLE_C = {
    "scene_description": "Bangkok soi, moderate enclosure.",
    "observed_features": ["buildings", "trees"],
    "reference_objects": ["car (~4.5m)"],
    "urban_morphology": {
        "street_width": 7.0,
        "building_height_est_m": 11.0,
        "sky_view_factor": 0.70,
        "road_slope": "flat",
        "sidewalk_height": "flush",
    },
    "vegetation": {"green_view_index": 0.28, "tree_canopy_coverage": "low", "shade_fraction": 0.30},
    "surface_and_flood": {"surface_material": "concrete", "impervious_surface_ratio": 0.75},
    "health_livability": {"walkability_obstruction": "minor"},
    "evidence": {"street_width": "Car reference gives ~7m"},
    "confidence_scores": {"urban_morphology": 0.75, "vegetation": 0.70},
}


class TestAggregateSamples:
    def test_returns_single_sample_unchanged(self):
        result = BaseAIEngine._aggregate_samples([SAMPLE_A])
        assert result is SAMPLE_A

    def test_street_width_is_median(self):
        result = BaseAIEngine._aggregate_samples([SAMPLE_A, SAMPLE_B, SAMPLE_C])
        # widths: [8.0, 9.0, 7.0] → median = 8.0
        assert result["urban_morphology"]["street_width"] == 8.0

    def test_road_slope_majority_vote(self):
        result = BaseAIEngine._aggregate_samples([SAMPLE_A, SAMPLE_B, SAMPLE_C])
        # all three say "flat"
        assert result["urban_morphology"]["road_slope"] == "flat"

    def test_surface_material_majority_vote(self):
        result = BaseAIEngine._aggregate_samples([SAMPLE_A, SAMPLE_B, SAMPLE_C])
        # asphalt=2, concrete=1 → asphalt wins
        assert result["surface_and_flood"]["surface_material"] == "asphalt"

    def test_observed_features_union(self):
        result = BaseAIEngine._aggregate_samples([SAMPLE_A, SAMPLE_B, SAMPLE_C])
        features = result["observed_features"]
        assert "buildings" in features
        assert "motorcycle" in features  # only in B
        assert "trees" in features
        # No duplicates
        assert len(features) == len(set(str(f) for f in features))

    def test_reference_objects_union(self):
        result = BaseAIEngine._aggregate_samples([SAMPLE_A, SAMPLE_B, SAMPLE_C])
        refs = result["reference_objects"]
        assert any("motorcycle" in r for r in refs)
        assert any("car" in r for r in refs)

    def test_confidence_scores_overridden(self):
        result = BaseAIEngine._aggregate_samples([SAMPLE_A, SAMPLE_B, SAMPLE_C])
        conf = result["confidence_scores"]
        assert "urban_morphology" in conf
        assert "vegetation" in conf
        assert 0.0 <= conf["urban_morphology"] <= 1.0
        assert 0.0 <= conf["vegetation"] <= 1.0

    def test_high_agreement_raises_confidence(self):
        # All three agree on road_slope=flat and sidewalk=raised (A,B) or flush (C)
        # High field-level agreement → confidence should be reasonable
        result = BaseAIEngine._aggregate_samples([SAMPLE_A, SAMPLE_B, SAMPLE_C])
        conf = result["confidence_scores"]["urban_morphology"]
        assert conf >= 0.5

    def test_green_view_index_median(self):
        result = BaseAIEngine._aggregate_samples([SAMPLE_A, SAMPLE_B, SAMPLE_C])
        # [0.3, 0.25, 0.28] → sorted [0.25, 0.28, 0.3] → median = 0.28
        gvi = result["vegetation"]["green_view_index"]
        assert abs(gvi - 0.28) < 0.001

    def test_empty_list_returns_empty(self):
        assert BaseAIEngine._aggregate_samples([]) == {}

    def test_two_samples(self):
        result = BaseAIEngine._aggregate_samples([SAMPLE_A, SAMPLE_B])
        # widths [8.0, 9.0] → median = 8.5
        assert result["urban_morphology"]["street_width"] == 8.5


# ── analyze_image_bytes multi-sample path ─────────────────────

class TestAnalyzeImageBytesMultiSample:
    """Test the multi-sample orchestration in analyze_image_bytes."""

    @pytest.mark.asyncio
    async def test_calls_api_n_times(self):
        import json

        class FakeEngine(BaseAIEngine):
            name = "fake"
            call_count = 0

            async def _call_api(self, img_bytes, mime_type, temperature=None):
                self.call_count += 1
                # Return slightly varied but valid JSON each time
                return json.dumps({
                    **SAMPLE_A,
                    "urban_morphology": {
                        **SAMPLE_A["urban_morphology"],
                        "street_width": 8.0 + self.call_count,
                    }
                })

        engine = FakeEngine()
        with patch("app.services.ai_engines.base.settings") as mock_settings:
            mock_settings.ANALYSIS_SAMPLES = 3
            mock_settings.AI_MAX_CONCURRENT = 10
            result = await engine.analyze_image_bytes(b"fake-image")

        assert engine.call_count == 3

    @pytest.mark.asyncio
    async def test_falls_back_when_all_samples_parse_fail(self):
        class BrokenEngine(BaseAIEngine):
            name = "broken"
            async def _call_api(self, img_bytes, mime_type, temperature=None):
                return "not valid json at all $$$$"

        engine = BrokenEngine()
        with patch("app.services.ai_engines.base.settings") as mock_settings:
            mock_settings.ANALYSIS_SAMPLES = 3
            mock_settings.AI_MAX_CONCURRENT = 10
            result = await engine.analyze_image_bytes(b"fake")

        assert result.get("_parse_error") is True

    @pytest.mark.asyncio
    async def test_single_sample_skips_aggregation(self):
        import json

        class SimpleEngine(BaseAIEngine):
            name = "simple"
            async def _call_api(self, img_bytes, mime_type, temperature=None):
                return json.dumps(SAMPLE_A)

        engine = SimpleEngine()
        with patch("app.services.ai_engines.base.settings") as mock_settings:
            mock_settings.ANALYSIS_SAMPLES = 1
            mock_settings.AI_MAX_CONCURRENT = 10
            result = await engine.analyze_image_bytes(b"fake")

        assert result["urban_morphology"]["street_width"] == 8.0

    @pytest.mark.asyncio
    async def test_recovers_from_one_failed_sample(self):
        import json

        class SometimesBrokenEngine(BaseAIEngine):
            name = "flaky"
            call_count = 0

            async def _call_api(self, img_bytes, mime_type, temperature=None):
                self.call_count += 1
                if self.call_count == 2:
                    raise RuntimeError("API timeout")
                return json.dumps(SAMPLE_A)

        engine = SometimesBrokenEngine()
        with patch("app.services.ai_engines.base.settings") as mock_settings:
            mock_settings.ANALYSIS_SAMPLES = 3
            mock_settings.AI_MAX_CONCURRENT = 10
            result = await engine.analyze_image_bytes(b"fake")

        # Should succeed using the 2 valid samples
        assert not result.get("_parse_error")
        assert result["urban_morphology"]["street_width"] == 8.0


# ── Global semaphore (_guarded_call) ──────────────────────────

class TestGlobalSemaphore:
    """
    ทดสอบว่า _guarded_call จำกัด concurrent calls จริง

    แนวคิด: ถ้า semaphore(2) และยิง 5 calls พร้อมกัน
    จะมีสูงสุด 2 calls วิ่งในเวลาเดียวกันเท่านั้น
    """

    @pytest.mark.asyncio
    async def test_guarded_call_invokes_call_api(self):
        """_guarded_call ต้องเรียก _call_api และ return ผลเดิม"""
        import json

        class DirectEngine(BaseAIEngine):
            name = "direct"
            async def _call_api(self, img_bytes, mime_type, temperature=None):
                return json.dumps(SAMPLE_A)

        engine = DirectEngine()
        import app.services.ai_engines.base as base_module
        sem = AsyncMock()
        sem.__aenter__ = AsyncMock(return_value=None)
        sem.__aexit__ = AsyncMock(return_value=False)

        with patch.object(base_module, "_get_semaphore", return_value=sem):
            result = await engine._guarded_call(b"fake", "image/jpeg")

        assert result == json.dumps(SAMPLE_A)
        sem.__aenter__.assert_called_once()
        sem.__aexit__.assert_called_once()

    @pytest.mark.asyncio
    async def test_semaphore_limits_concurrency(self):
        """
        ยิง 6 calls พร้อมกัน แต่ semaphore(2) → สูงสุด 2 วิ่งพร้อมกัน
        วัดโดยนับ peak concurrency ขณะทำงานจริง
        """
        import app.services.ai_engines.base as base_module

        peak = 0
        current = 0

        class CountingEngine(BaseAIEngine):
            name = "counting"

            async def _call_api(self, img_bytes, mime_type, temperature=None):
                nonlocal peak, current
                current += 1
                peak = max(peak, current)
                await asyncio.sleep(0.01)  # จำลองเวลา API call
                current -= 1
                return '{"ok": true}'

        engine = CountingEngine()
        original_semaphore = base_module._api_semaphore
        base_module._api_semaphore = asyncio.Semaphore(2)  # จำกัด 2

        try:
            await asyncio.gather(*[engine._guarded_call(b"x", "image/jpeg") for _ in range(6)])
        finally:
            base_module._api_semaphore = original_semaphore  # คืนค่าเดิม

        assert peak <= 2, f"Expected peak ≤ 2 concurrent calls, got {peak}"

    @pytest.mark.asyncio
    async def test_semaphore_releases_on_exception(self):
        """ถ้า _call_api raise exception → semaphore ต้อง release (ไม่ deadlock)"""
        import app.services.ai_engines.base as base_module

        class ErrorEngine(BaseAIEngine):
            name = "error"
            async def _call_api(self, img_bytes, mime_type, temperature=None):
                raise RuntimeError("API down")

        engine = ErrorEngine()
        original_semaphore = base_module._api_semaphore
        base_module._api_semaphore = asyncio.Semaphore(1)

        try:
            with pytest.raises(RuntimeError):
                await engine._guarded_call(b"x", "image/jpeg")

            # Semaphore ต้อง release → ยิงอีกครั้งได้ปกติ ไม่ hang
            assert base_module._api_semaphore._value == 1
        finally:
            base_module._api_semaphore = original_semaphore
