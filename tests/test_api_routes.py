"""
Integration-style tests for /api/routes endpoints.

The DB dependency is replaced by a mock session via conftest.client.
Service calls that hit external systems are patched per-test.
"""
import pytest
from unittest.mock import AsyncMock, patch

from tests.conftest import make_mock_session
from app.db.database import get_db
from app.main import app


# ── POST /api/routes ──────────────────────────────────────────

def test_create_route_returns_201(mock_route, client):
    with patch("app.api.v1.routes.RouteDAO.create_route", return_value=mock_route):
        response = client.post("/api/routes", json={"name": "Bangkok Route", "description": "Test"})

    assert response.status_code == 201


def test_create_route_response_has_name(mock_route, client):
    with patch("app.api.v1.routes.RouteDAO.create_route", return_value=mock_route):
        data = client.post("/api/routes", json={"name": "Bangkok Route"}).json()

    assert data["name"] == "Test Route BKK"


def test_create_route_without_description_succeeds(mock_route, client):
    with patch("app.api.v1.routes.RouteDAO.create_route", return_value=mock_route):
        response = client.post("/api/routes", json={"name": "No Desc"})

    assert response.status_code == 201


def test_create_route_non_json_body_returns_422(client):
    # name is Optional so missing name is fine; but a non-object body is 422
    response = client.post("/api/routes", content="not-json", headers={"Content-Type": "application/json"})
    assert response.status_code == 422


# ── GET /api/routes ───────────────────────────────────────────

def test_list_routes_returns_200(mock_route, client):
    with patch("app.api.v1.routes.RouteDAO.list_routes", return_value=[mock_route]):
        response = client.get("/api/routes")

    assert response.status_code == 200


def test_list_routes_returns_list(mock_route, client):
    with patch("app.api.v1.routes.RouteDAO.list_routes", return_value=[mock_route]):
        data = client.get("/api/routes").json()

    assert isinstance(data, list)
    assert len(data) == 1


def test_list_routes_empty_when_none(client):
    with patch("app.api.v1.routes.RouteDAO.list_routes", return_value=[]):
        data = client.get("/api/routes").json()

    assert data == []


# ── GET /api/routes/{route_id} ────────────────────────────────

def test_get_route_returns_200_when_found(mock_route, client):
    with patch("app.api.v1.routes.RouteDAO.get_by_id", return_value=mock_route):
        response = client.get("/api/routes/1")

    assert response.status_code == 200


def test_get_route_returns_correct_id(mock_route, client):
    with patch("app.api.v1.routes.RouteDAO.get_by_id", return_value=mock_route):
        data = client.get("/api/routes/1").json()

    assert data["id"] == 1


def test_get_route_returns_404_when_not_found(client):
    with patch("app.api.v1.routes.RouteDAO.get_by_id", return_value=None):
        response = client.get("/api/routes/999")

    assert response.status_code == 404


# ── POST /api/routes/{route_id}/reanalyze ─────────────────────

def test_reanalyze_route_returns_404_when_route_not_found(client):
    with patch("app.api.v1.routes.RouteDAO.get_by_id", return_value=None):
        response = client.post("/api/routes/999/reanalyze")

    assert response.status_code == 404


def test_reanalyze_route_returns_404_when_no_analyses(mock_route, client):
    with (
        patch("app.api.v1.routes.RouteDAO.get_by_id", return_value=mock_route),
        patch("app.api.v1.routes.AnalysisDAO.get_by_route", return_value=[]),
    ):
        response = client.post("/api/routes/1/reanalyze")

    assert response.status_code == 404


def test_reanalyze_route_returns_200_with_results(mock_route, mock_analysis, client):
    with (
        patch("app.api.v1.routes.RouteDAO.get_by_id", return_value=mock_route),
        patch("app.api.v1.routes.AnalysisDAO.get_by_route", return_value=[mock_analysis]),
        patch("app.api.v1.routes.reanalyze_record", new=AsyncMock(return_value=mock_analysis)),
    ):
        response = client.post("/api/routes/1/reanalyze")

    assert response.status_code == 200
    assert isinstance(response.json(), list)


# ── GET /api/routes/{route_id}/export/kml ─────────────────────

def test_export_kml_returns_404_when_route_not_found(client):
    with patch("app.api.v1.routes.RouteDAO.get_by_id", return_value=None):
        response = client.get("/api/routes/999/export/kml")

    assert response.status_code == 404


def test_export_kml_returns_404_when_no_analyses(mock_route, client):
    with (
        patch("app.api.v1.routes.RouteDAO.get_by_id", return_value=mock_route),
        patch("app.api.v1.routes.AnalysisDAO.get_by_route", return_value=[]),
    ):
        response = client.get("/api/routes/1/export/kml")

    assert response.status_code == 404


def test_export_kml_returns_kml_content_type(mock_route, mock_analysis, client):
    kml_content = b"<?xml version='1.0'?><kml></kml>"
    with (
        patch("app.api.v1.routes.RouteDAO.get_by_id", return_value=mock_route),
        patch("app.api.v1.routes.AnalysisDAO.get_by_route", return_value=[mock_analysis]),
        patch("app.api.v1.routes.KMLService.generate_street_width_kml", return_value=kml_content),
    ):
        response = client.get("/api/routes/1/export/kml")

    assert response.status_code == 200
    assert "kml" in response.headers["content-type"]
