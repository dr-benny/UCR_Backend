"""
Base AI Engine Interface.

Every AI provider (Gemini, Claude, GPT, etc.) must implement this
abstract class so the rest of the system can swap them like LEGO blocks.

Self-consistency sampling (Wang et al., 2022):
  When ANALYSIS_SAMPLES > 1, the engine calls the API N times with a
  higher temperature for diversity, then aggregates results:
    - floats  → median  (robust against outliers)
    - strings → majority vote
    - lists   → union   (deduplicated, order-preserved)
    - confidence_scores → blended from original AI confidence × inter-sample agreement
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from abc import ABC, abstractmethod
from collections import Counter
from pathlib import Path
from typing import Any

from tenacity import AsyncRetrying, before_sleep_log, stop_after_attempt, wait_exponential

from app.core.config import settings

logger = logging.getLogger(__name__)

# Temperature used when drawing diverse samples for self-consistency
_SAMPLING_TEMPERATURE = 0.7

# Global semaphore — shared across ALL engines and ALL callers (batch + sampling).
# Lazy-init on first use so it's always created inside a running event loop.
# asyncio.Semaphore must be created on the loop that will use it, and at import
# time there may be no loop yet (e.g. during test collection).
_api_semaphore: asyncio.Semaphore | None = None


def _get_semaphore() -> asyncio.Semaphore:
    global _api_semaphore
    if _api_semaphore is None:
        _api_semaphore = asyncio.Semaphore(settings.AI_MAX_CONCURRENT)
    return _api_semaphore


class BaseAIEngine(ABC):
    """
    Contract that all AI engines must follow.

    Subclasses only need to implement `_call_api()`.
    Multi-sampling, JSON parsing, and aggregation are handled here.
    """

    name: str = "base"

    # ── Public API ────────────────────────────────────────────

    async def analyze_image(
        self,
        image_path: str,
        mime_type: str = "image/jpeg",
        samples: int | None = None,
    ) -> dict[str, Any]:
        """Read a local image file and analyze it. mime_type must match the file bytes."""
        img_bytes = Path(image_path).read_bytes()
        return await self.analyze_image_bytes(img_bytes, mime_type=mime_type, samples=samples)

    async def analyze_image_bytes(
        self,
        img_bytes: bytes,
        mime_type: str = "image/jpeg",
        samples: int | None = None,
    ) -> dict[str, Any]:
        """
        Analyze raw image bytes.

        When samples > 1, calls _call_api N times concurrently with a higher
        temperature (for diversity), then aggregates via median / majority vote.
        """
        n = samples if samples is not None else settings.ANALYSIS_SAMPLES

        if n <= 1:
            raw = await self._guarded_call(img_bytes, mime_type)
            logger.info("--- %s RAW RESPONSE ---\n%s\n---", self.name.upper(), raw)
            result = self._extract_json(raw)
            logger.info("Parsed JSON keys: %s", list(result.keys()))
            return result

        # ── Multi-sample path ─────────────────────────────────
        logger.info("Self-consistency: requesting %d samples from %s", n, self.name)
        raw_results = await asyncio.gather(
            *[self._guarded_call(img_bytes, mime_type, temperature=_SAMPLING_TEMPERATURE) for _ in range(n)],
            return_exceptions=True,
        )

        parsed: list[dict[str, Any]] = []
        for i, raw in enumerate(raw_results):
            if isinstance(raw, Exception):
                logger.warning("Sample %d/%d raised: %s", i + 1, n, raw)
                continue
            result = self._extract_json(raw)
            if result.get("_parse_error"):
                logger.warning("Sample %d/%d: JSON parse failed", i + 1, n)
            else:
                parsed.append(result)
                logger.info("Sample %d/%d: OK (keys=%s)", i + 1, n, list(result.keys()))

        if not parsed:
            logger.error("All %d samples invalid — falling back to first raw result", n)
            first = next((r for r in raw_results if not isinstance(r, Exception)), None)
            return self._extract_json(first or "")

        if len(parsed) == 1:
            return parsed[0]

        aggregated = self._aggregate_samples(parsed)
        logger.info(
            "Self-consistency: aggregated %d/%d valid samples", len(parsed), n
        )
        return aggregated

    # ── Abstract (each engine implements this) ────────────────

    @abstractmethod
    async def _call_api(
        self,
        img_bytes: bytes,
        mime_type: str,
        temperature: float | None = None,
    ) -> str:
        """
        Send image bytes to the AI provider and return raw text.

        `temperature` overrides the engine default — pass a higher value
        (e.g. 0.7) when drawing diverse samples for self-consistency.
        """
        ...

    async def _guarded_call(
        self,
        img_bytes: bytes,
        mime_type: str,
        temperature: float | None = None,
    ) -> str:
        """
        Wrapper around _call_api with global semaphore + automatic retry.

        Semaphore: caps total concurrent AI API calls across the whole app.
        Retry: on transient failures (rate limit, timeout, network error),
        backs off exponentially and retries up to 3 times before giving up.

        The semaphore is acquired inside each attempt so it is released
        during backoff — other callers can proceed while we wait to retry.
        """
        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=1, min=2, max=30),
            before_sleep=before_sleep_log(logger, logging.WARNING),
            reraise=True,
        ):
            with attempt:
                async with _get_semaphore():
                    return await self._call_api(img_bytes, mime_type, temperature)

    # ── Aggregation ───────────────────────────────────────────

    @classmethod
    def _aggregate_samples(cls, samples: list[dict[str, Any]]) -> dict[str, Any]:
        """
        Merge N parsed results into a single consensus dict.

        Walks the structure recursively:
          - nested dict → recurse per key
          - list        → ordered union, deduplicated
          - scalar      → _aggregate_value (median or majority)
        Then overrides confidence_scores with agreement-weighted values.
        """
        if not samples:
            return {}
        if len(samples) == 1:
            return samples[0]

        def _merge(nodes: list[Any]) -> Any:
            if not nodes:
                return None

            if all(isinstance(n, dict) for n in nodes):
                all_keys: set[str] = set().union(*nodes)
                return {
                    k: _merge([n[k] for n in nodes if k in n])
                    for k in all_keys
                }

            if all(isinstance(n, list) for n in nodes):
                seen: set[str] = set()
                merged: list[Any] = []
                for lst in nodes:
                    for item in lst:
                        key = str(item)
                        if key not in seen:
                            seen.add(key)
                            merged.append(item)
                return merged

            return cls._aggregate_value(nodes)

        aggregated = _merge(samples)

        # Replace confidence_scores with agreement-aware values
        category_keys = [
            "urban_morphology",
            "vegetation",
            "surface_and_flood",
            "health_livability",
        ]
        conf_override: dict[str, float] = {}

        for cat in category_keys:
            cat_dicts = [s.get(cat) for s in samples if isinstance(s.get(cat), dict)]
            if not cat_dicts:
                continue

            all_fields: set[str] = set().union(*cat_dicts)
            field_agreements = [
                cls._agreement_score([d.get(f) for d in cat_dicts if f in d])
                for f in all_fields
            ]
            cat_agreement = (
                sum(field_agreements) / len(field_agreements) if field_agreements else 0.7
            )

            orig_confs = [
                s.get("confidence_scores", {}).get(cat)
                for s in samples
                if isinstance(s.get("confidence_scores", {}).get(cat), (int, float))
            ]
            mean_conf = sum(orig_confs) / len(orig_confs) if orig_confs else 0.7

            # Blend: original confidence modulated by inter-sample agreement
            conf_override[cat] = round(min(1.0, mean_conf * (0.4 + 0.6 * cat_agreement)), 3)

        if conf_override:
            if not isinstance(aggregated.get("confidence_scores"), dict):
                aggregated["confidence_scores"] = {}
            aggregated["confidence_scores"].update(conf_override)

        return aggregated

    @staticmethod
    def _aggregate_value(values: list[Any]) -> Any:
        """
        Reduce a list of same-field values to a single consensus value.

        - Filters out None / "unknown" if real values exist.
        - All numeric  → median (rounded to 4 dp)
        - Otherwise    → majority vote (returns original-typed winner)
        """
        real = [v for v in values if v is not None and v != "unknown"]
        if not real:
            return "unknown"

        numeric = [v for v in real if isinstance(v, (int, float))]
        if len(numeric) == len(real):
            s = sorted(numeric)
            mid = len(s) // 2
            median = s[mid] if len(s) % 2 else (s[mid - 1] + s[mid]) / 2
            return round(float(median), 4)

        # Majority vote — return value with original type
        counter = Counter(str(v) for v in real)
        winner_str = counter.most_common(1)[0][0]
        for v in real:
            if str(v) == winner_str:
                return v
        return winner_str

    @staticmethod
    def _agreement_score(values: list[Any]) -> float:
        """
        Return 0.0–1.0 measuring how consistent values are across samples.

        - Numeric: 1 − (coefficient of variation), clamped [0.3, 1.0]
        - String:  fraction of values matching the majority
        """
        real = [v for v in values if v is not None and v != "unknown"]
        if not real:
            return 0.5
        if len(real) == 1:
            return 1.0

        numeric = [v for v in real if isinstance(v, (int, float))]
        if len(numeric) == len(real):
            mean = sum(numeric) / len(numeric)
            if mean == 0:
                return 1.0 if all(v == 0 for v in numeric) else 0.5
            std = (sum((v - mean) ** 2 for v in numeric) / len(numeric)) ** 0.5
            cv = std / abs(mean)
            return round(max(0.3, min(1.0, 1.0 - cv * 1.5)), 3)

        counter = Counter(str(v) for v in real)
        majority_count = counter.most_common(1)[0][1]
        return round(majority_count / len(real), 3)

    # ── JSON extraction ───────────────────────────────────────

    @staticmethod
    def _extract_json(text: str) -> dict[str, Any]:
        """Best-effort extraction of a JSON object from any AI response.

        If the model returns a JSON array, the first element is unwrapped so
        callers always receive a dict (prompts that return batch arrays still
        work when images are sent one-at-a-time).
        """
        text = text.strip()

        def _unwrap(value: Any) -> dict[str, Any]:
            if isinstance(value, list) and value and isinstance(value[0], dict):
                return value[0]
            if isinstance(value, dict):
                return value
            return {"_raw_text": str(value), "_parse_error": True}

        try:
            return _unwrap(json.loads(text))
        except json.JSONDecodeError:
            pass

        match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
        if match:
            try:
                return _unwrap(json.loads(match.group(1)))
            except json.JSONDecodeError:
                pass

        match = re.search(r"[\[{].*[\]}]", text, re.DOTALL)
        if match:
            try:
                return _unwrap(json.loads(match.group(0)))
            except json.JSONDecodeError:
                pass

        return {"_raw_text": text, "_parse_error": True}
