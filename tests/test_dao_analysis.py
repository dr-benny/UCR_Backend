"""Unit tests for AnalysisDAO — all DB interactions are mocked."""
import pytest
from unittest.mock import MagicMock, call

from tests.conftest import make_mock_session
from app.dao.analysis_dao import AnalysisDAO
from app.models.analysis import StreetAnalysis

LAT, LON = 13.736717, 100.523186

SAMPLE_DATA = {
    "heading": 90.0,
    "pitch": 0.0,
    "fov": 90.0,
    "image_url": "LOCAL_ONLY",
    "image_path": "/tmp/test_images/test.jpg",
    "urban_morphology": {"street_width": 8.0},
    "vegetation": {"green_view_index": 0.3},
    "surface_and_flood": {"surface_material": "asphalt"},
    "health_livability": {"walkability_obstruction": "low"},
    "scene_description": "Test street",
    "observed_features": ["road"],
    "reference_objects": [],
    "evidence": {},
    "confidence_scores": {"urban_morphology": 0.9},
    "raw_ai_response": {},
}


# ── create_analysis ───────────────────────────────────────────

def test_create_analysis_adds_and_commits():
    db = make_mock_session()
    result = AnalysisDAO.create_analysis(db, SAMPLE_DATA, LAT, LON)
    db.add.assert_called_once()
    db.commit.assert_called_once()
    db.refresh.assert_called_once()
    assert isinstance(result, StreetAnalysis)


def test_create_analysis_sets_route_id():
    db = make_mock_session()
    result = AnalysisDAO.create_analysis(db, SAMPLE_DATA, LAT, LON, route_id=5)
    assert result.route_id == 5


def test_create_analysis_auto_increments_order_index_when_zero():
    # scalar() returns 3 → next order_index should be 4
    db = make_mock_session(scalar_return=3)
    result = AnalysisDAO.create_analysis(
        db, SAMPLE_DATA, LAT, LON, route_id=1, order_index=0
    )
    assert result.order_index == 4


def test_create_analysis_keeps_explicit_order_index():
    db = make_mock_session()
    result = AnalysisDAO.create_analysis(
        db, SAMPLE_DATA, LAT, LON, route_id=1, order_index=7
    )
    assert result.order_index == 7


def test_create_analysis_no_route_skips_auto_increment():
    db = make_mock_session()
    AnalysisDAO.create_analysis(db, SAMPLE_DATA, LAT, LON, route_id=None)
    # query().scalar() should NOT have been called for auto-increment
    db.query.return_value.filter.return_value.scalar.assert_not_called()


# ── get_by_id ─────────────────────────────────────────────────

def test_get_by_id_returns_record(mock_analysis):
    db = make_mock_session(first_return=mock_analysis)
    result = AnalysisDAO.get_by_id(db, 1)
    assert result is mock_analysis


def test_get_by_id_returns_none_when_missing():
    db = make_mock_session(first_return=None)
    result = AnalysisDAO.get_by_id(db, 999)
    assert result is None


# ── list_analyses ─────────────────────────────────────────────

def test_list_analyses_returns_list(mock_analysis):
    db = make_mock_session(all_return=[mock_analysis])
    results = AnalysisDAO.list_analyses(db, skip=0, limit=10)
    assert len(results) == 1
    assert results[0] is mock_analysis


def test_list_analyses_empty():
    db = make_mock_session(all_return=[])
    assert AnalysisDAO.list_analyses(db) == []


# ── delete_analysis ───────────────────────────────────────────

def test_delete_analysis_returns_true_when_found(mock_analysis):
    db = make_mock_session(first_return=mock_analysis)
    result = AnalysisDAO.delete_analysis(db, 1)
    assert result is True
    db.delete.assert_called_once_with(mock_analysis)
    db.commit.assert_called_once()


def test_delete_analysis_returns_false_when_not_found():
    db = make_mock_session(first_return=None)
    result = AnalysisDAO.delete_analysis(db, 999)
    assert result is False
    db.delete.assert_not_called()


# ── update_ai_result ──────────────────────────────────────────

def test_update_ai_result_overwrites_fields(mock_analysis):
    db = make_mock_session()
    new_result = {
        "urban_morphology": {"street_width": 12.0},
        "vegetation": {"green_view_index": 0.5},
        "surface_and_flood": {"surface_material": "concrete"},
        "health_livability": {"walkability_obstruction": "high"},
        "scene_description": "Updated description",
        "observed_features": ["new_feature"],
        "reference_objects": ["new_ref"],
        "evidence": {"key": "val"},
        "confidence_scores": {"urban_morphology": 0.95},
    }
    result = AnalysisDAO.update_ai_result(db, mock_analysis, new_result)
    assert result.urban_morphology == {"street_width": 12.0}
    assert result.scene_description == "Updated description"
    assert result.raw_ai_response == new_result
    db.commit.assert_called_once()
    db.refresh.assert_called_once()


# ── get_by_route ──────────────────────────────────────────────

def test_get_by_route_returns_ordered_list(mock_analysis):
    db = make_mock_session(all_return=[mock_analysis])
    results = AnalysisDAO.get_by_route(db, route_id=1)
    assert len(results) == 1
    assert results[0] is mock_analysis


def test_get_by_route_empty_when_no_analyses():
    db = make_mock_session(all_return=[])
    assert AnalysisDAO.get_by_route(db, route_id=999) == []
