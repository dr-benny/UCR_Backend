"""
Unit tests for StreetAnalysis computed properties.

WKTElement works with geoalchemy2.shape.to_shape() without a real DB
connection — it parses the WKT string directly via shapely.
"""
import pytest
from geoalchemy2.elements import WKTElement
from app.models.analysis import StreetAnalysis


def _make(geom_wkt="POINT(100.5 13.8)", **kwargs) -> StreetAnalysis:
    a = StreetAnalysis(geom=WKTElement(geom_wkt, srid=4326))
    for k, v in kwargs.items():
        setattr(a, k, v)
    return a


# ── latitude / longitude ──────────────────────────────────────

def test_longitude_extracted_from_geom():
    a = _make("POINT(100.523 13.737)")
    assert abs(a.longitude - 100.523) < 1e-6


def test_latitude_extracted_from_geom():
    a = _make("POINT(100.523 13.737)")
    assert abs(a.latitude - 13.737) < 1e-6


# ── heat_risk_proxy ───────────────────────────────────────────

def test_heat_risk_high_when_score_above_threshold():
    a = _make(confidence_scores={"urban_morphology": 0.85})
    assert a.heat_risk_proxy == "high"


def test_heat_risk_medium_when_score_at_or_below_threshold():
    a = _make(confidence_scores={"urban_morphology": 0.8})
    assert a.heat_risk_proxy == "medium"


def test_heat_risk_medium_when_score_below_threshold():
    a = _make(confidence_scores={"urban_morphology": 0.5})
    assert a.heat_risk_proxy == "medium"


def test_heat_risk_none_when_no_confidence_scores():
    a = _make(confidence_scores=None)
    assert a.heat_risk_proxy is None


def test_heat_risk_medium_when_key_missing_from_scores():
    # urban_morphology key absent → score defaults to 0 → medium
    a = _make(confidence_scores={"vegetation": 0.9})
    assert a.heat_risk_proxy == "medium"


# ── walkway_width_m ───────────────────────────────────────────

def test_walkway_width_numeric():
    a = _make(urban_morphology={"street_width": 8.5})
    assert a.walkway_width_m == 8.5


def test_walkway_width_integer_coerced_to_float():
    a = _make(urban_morphology={"street_width": 6})
    assert a.walkway_width_m == 6.0


@pytest.mark.parametrize("label,expected", [
    ("very_narrow", 0.5),
    ("narrow", 1.5),
    ("moderate", 3.0),
    ("wide", 6.0),
    ("very_wide", 10.0),
])
def test_walkway_width_string_labels(label, expected):
    a = _make(urban_morphology={"street_width": label})
    assert a.walkway_width_m == expected


def test_walkway_width_none_when_no_urban_morphology():
    a = _make(urban_morphology=None)
    assert a.walkway_width_m is None


def test_walkway_width_none_when_key_missing():
    a = _make(urban_morphology={"building_height_est_m": 10})
    assert a.walkway_width_m is None


def test_walkway_width_none_for_unknown_string():
    a = _make(urban_morphology={"street_width": "unknown_label"})
    assert a.walkway_width_m is None


# ── sky_view_factor_est ───────────────────────────────────────

def test_sky_view_factor_numeric():
    a = _make(urban_morphology={"sky_view_factor": 0.72})
    assert a.sky_view_factor_est == 0.72


def test_sky_view_factor_none_when_no_urban_morphology():
    a = _make(urban_morphology=None)
    assert a.sky_view_factor_est is None


def test_sky_view_factor_none_when_key_missing():
    a = _make(urban_morphology={"street_width": 5.0})
    assert a.sky_view_factor_est is None


# ── trash_bin_status ──────────────────────────────────────────

def test_trash_bin_status_present():
    a = _make(health_livability={"trash_bin_presence": "present"})
    assert a.trash_bin_status == "present"


def test_trash_bin_status_none_when_no_health_livability():
    a = _make(health_livability=None)
    assert a.trash_bin_status is None
