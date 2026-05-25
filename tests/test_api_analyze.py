"""
Integration-style tests for /api/analyze and /api/analyses endpoints.
"""
import pytest
from unittest.mock import AsyncMock, patch

from app.schemas.analysis import AnalysisResponse


# ── GET /api/analyses ─────────────────────────────────────────

def test_list_analyses_returns_200(mock_analysis, client):
    with patch("app.api.v1.analyze.AnalysisDAO.list_analyses", return_value=[mock_analysis]):
        response = client.get("/api/analyses")

    assert response.status_code == 200


def test_list_analyses_returns_list_of_items(mock_analysis, client):
    with patch("app.api.v1.analyze.AnalysisDAO.list_analyses", return_value=[mock_analysis]):
        data = client.get("/api/analyses").json()

    assert isinstance(data, list)
    assert len(data) == 1
    assert data[0]["id"] == 1


def test_list_analyses_empty_list(client):
    with patch("app.api.v1.analyze.AnalysisDAO.list_analyses", return_value=[]):
        data = client.get("/api/analyses").json()

    assert data == []


def test_list_analyses_invalid_limit_returns_422(client):
    response = client.get("/api/analyses?limit=0")
    assert response.status_code == 422


# ── GET /api/analyses/{analysis_id} ──────────────────────────

def test_get_analysis_returns_200_when_found(mock_analysis, client):
    with patch("app.api.v1.analyze.AnalysisDAO.get_by_id", return_value=mock_analysis):
        response = client.get("/api/analyses/1")

    assert response.status_code == 200


def test_get_analysis_response_has_expected_fields(mock_analysis, client):
    with patch("app.api.v1.analyze.AnalysisDAO.get_by_id", return_value=mock_analysis):
        data = client.get("/api/analyses/1").json()

    assert data["id"] == 1
    assert "latitude" in data
    assert "longitude" in data
    assert "urban_morphology" in data


def test_get_analysis_lat_lon_correct(mock_analysis, client):
    with patch("app.api.v1.analyze.AnalysisDAO.get_by_id", return_value=mock_analysis):
        data = client.get("/api/analyses/1").json()

    assert abs(data["latitude"] - 13.736717) < 1e-4
    assert abs(data["longitude"] - 100.523186) < 1e-4


def test_get_analysis_returns_404_when_not_found(client):
    with patch("app.api.v1.analyze.AnalysisDAO.get_by_id", return_value=None):
        response = client.get("/api/analyses/999")

    assert response.status_code == 404


# ── DELETE /api/analyses/{analysis_id} ───────────────────────

def test_delete_analysis_returns_204_when_found(client):
    with patch("app.api.v1.analyze.AnalysisDAO.delete_analysis", return_value=True):
        response = client.delete("/api/analyses/1")

    assert response.status_code == 204


def test_delete_analysis_returns_404_when_not_found(client):
    with patch("app.api.v1.analyze.AnalysisDAO.delete_analysis", return_value=False):
        response = client.delete("/api/analyses/999")

    assert response.status_code == 404


# ── POST /api/analyze ─────────────────────────────────────────

def test_analyze_location_returns_201_on_success(mock_analysis, client):
    with patch(
        "app.api.v1.analyze.analyze_from_streetview",
        new=AsyncMock(return_value=mock_analysis),
    ):
        response = client.post(
            "/api/analyze",
            json={"latitude": 13.736717, "longitude": 100.523186},
        )

    assert response.status_code == 201


def test_analyze_location_response_has_id(mock_analysis, client):
    with patch(
        "app.api.v1.analyze.analyze_from_streetview",
        new=AsyncMock(return_value=mock_analysis),
    ):
        data = client.post(
            "/api/analyze",
            json={"latitude": 13.736717, "longitude": 100.523186},
        ).json()

    assert data["id"] == 1


def test_analyze_location_returns_404_when_no_coverage(client):
    with patch(
        "app.api.v1.analyze.analyze_from_streetview",
        new=AsyncMock(side_effect=LookupError("No Street View coverage")),
    ):
        response = client.post(
            "/api/analyze",
            json={"latitude": 0.0, "longitude": 0.0},
        )

    assert response.status_code == 404
    assert "coverage" in response.json()["detail"].lower()


def test_analyze_location_returns_502_on_ai_failure(client):
    with patch(
        "app.api.v1.analyze.analyze_from_streetview",
        new=AsyncMock(side_effect=RuntimeError("Gemini quota exceeded")),
    ):
        response = client.post(
            "/api/analyze",
            json={"latitude": 13.736717, "longitude": 100.523186},
        )

    assert response.status_code == 502


def test_analyze_location_missing_coordinates_returns_422(client):
    response = client.post("/api/analyze", json={"heading": 90})
    assert response.status_code == 422


# ── POST /api/analyze/batch ───────────────────────────────────

def test_analyze_batch_returns_201(mock_analysis, client):
    with patch(
        "app.api.v1.analyze.analyze_from_streetview",
        new=AsyncMock(return_value=mock_analysis),
    ):
        response = client.post(
            "/api/analyze/batch",
            json=[{"latitude": 13.736717, "longitude": 100.523186}],
        )

    assert response.status_code == 201


def test_analyze_batch_over_limit_returns_400(client):
    locations = [{"latitude": 13.0 + i * 0.001, "longitude": 100.5} for i in range(21)]
    response = client.post("/api/analyze/batch", json=locations)
    assert response.status_code == 400


def test_analyze_batch_skips_no_coverage_locations(mock_analysis, client):
    # First location fails (no coverage), second succeeds
    side_effects = [LookupError("no coverage"), mock_analysis]
    with patch(
        "app.api.v1.analyze.analyze_from_streetview",
        new=AsyncMock(side_effect=side_effects),
    ):
        response = client.post(
            "/api/analyze/batch",
            json=[
                {"latitude": 0.0, "longitude": 0.0},
                {"latitude": 13.736717, "longitude": 100.523186},
            ],
        )

    # Returns 201 with only the successful result
    assert response.status_code == 201
    assert len(response.json()) == 1


# ── Parallel batch behavior ───────────────────────────────────

def test_analyze_batch_respects_concurrency_param(mock_analysis, client):
    """ส่ง concurrency=2 ต้องไม่ error (Semaphore รับค่าได้)"""
    with patch(
        "app.api.v1.analyze.analyze_from_streetview",
        new=AsyncMock(return_value=mock_analysis),
    ):
        response = client.post(
            "/api/analyze/batch?concurrency=2",
            json=[
                {"latitude": 13.736717, "longitude": 100.523186},
                {"latitude": 13.737000, "longitude": 100.524000},
                {"latitude": 13.737500, "longitude": 100.525000},
            ],
        )
    assert response.status_code == 201
    assert len(response.json()) == 3


def test_analyze_batch_concurrency_out_of_range_returns_422(client):
    """concurrency ต้องอยู่ใน 1–10 ถ้าเกินต้อง 422"""
    response = client.post(
        "/api/analyze/batch?concurrency=99",
        json=[{"latitude": 13.0, "longitude": 100.0}],
    )
    assert response.status_code == 422


def test_analyze_batch_all_fail_returns_empty_list(client):
    """ถ้าทุก point fail → return [] ไม่ใช่ error 500"""
    with patch(
        "app.api.v1.analyze.analyze_from_streetview",
        new=AsyncMock(side_effect=Exception("all broken")),
    ):
        response = client.post(
            "/api/analyze/batch",
            json=[
                {"latitude": 0.0, "longitude": 0.0},
                {"latitude": 1.0, "longitude": 1.0},
            ],
        )
    assert response.status_code == 201
    assert response.json() == []


def test_analyze_batch_preserves_order(mock_analysis, client):
    """
    ผลลัพธ์ต้องอยู่ในลำดับเดียวกับ input แม้วิ่ง parallel
    asyncio.gather รับประกัน order ของ results ตาม index ที่ส่งไป
    """
    import copy
    a1 = copy.copy(mock_analysis)
    a1.id = 1
    a2 = copy.copy(mock_analysis)
    a2.id = 2

    with patch(
        "app.api.v1.analyze.analyze_from_streetview",
        new=AsyncMock(side_effect=[a1, a2]),
    ):
        response = client.post(
            "/api/analyze/batch",
            json=[
                {"latitude": 13.736717, "longitude": 100.523186},
                {"latitude": 13.737000, "longitude": 100.524000},
            ],
        )
    assert response.status_code == 201
    data = response.json()
    assert data[0]["id"] == 1
    assert data[1]["id"] == 2


# ── POST /api/analyses/{id}/reanalyze ────────────────────────

def test_reanalyze_single_returns_200(mock_analysis, client):
    with (
        patch("app.api.v1.analyze.AnalysisDAO.get_by_id", return_value=mock_analysis),
        patch(
            "app.api.v1.analyze.reanalyze_record",
            new=AsyncMock(return_value=mock_analysis),
        ),
    ):
        response = client.post("/api/analyses/1/reanalyze")

    assert response.status_code == 200


def test_reanalyze_single_returns_404_when_not_found(client):
    with patch("app.api.v1.analyze.AnalysisDAO.get_by_id", return_value=None):
        response = client.post("/api/analyses/999/reanalyze")

    assert response.status_code == 404


def test_reanalyze_single_returns_404_when_image_missing(mock_analysis, client):
    with (
        patch("app.api.v1.analyze.AnalysisDAO.get_by_id", return_value=mock_analysis),
        patch(
            "app.api.v1.analyze.reanalyze_record",
            new=AsyncMock(side_effect=FileNotFoundError("Image missing")),
        ),
    ):
        response = client.post("/api/analyses/1/reanalyze")

    assert response.status_code == 404
