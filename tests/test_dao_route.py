"""Unit tests for RouteDAO — all DB interactions are mocked."""
import pytest
from unittest.mock import MagicMock

from tests.conftest import make_mock_session
from app.dao.route_dao import RouteDAO
from app.models.route import SurveyRoute


# ── create_route ──────────────────────────────────────────────

def test_create_route_adds_and_commits(mock_route):
    db = make_mock_session()
    db.refresh.side_effect = lambda obj: setattr(obj, "id", 1)

    result = RouteDAO.create_route(db, name="Bangkok Route", description="Test")

    db.add.assert_called_once()
    db.commit.assert_called_once()
    db.refresh.assert_called_once()
    assert isinstance(result, SurveyRoute)
    assert result.name == "Bangkok Route"


def test_create_route_without_description():
    db = make_mock_session()
    result = RouteDAO.create_route(db, name="No Desc Route")
    assert result.description is None


# ── get_by_id ─────────────────────────────────────────────────

def test_get_by_id_returns_route_when_found(mock_route):
    db = make_mock_session(first_return=mock_route)
    result = RouteDAO.get_by_id(db, 1)
    assert result is mock_route


def test_get_by_id_returns_none_when_not_found():
    db = make_mock_session(first_return=None)
    result = RouteDAO.get_by_id(db, 999)
    assert result is None


# ── list_routes ───────────────────────────────────────────────

def test_list_routes_returns_list(mock_route):
    db = make_mock_session(first_return=mock_route)
    results = RouteDAO.list_routes(db, skip=0, limit=10)
    assert isinstance(results, list)
    assert len(results) == 1
    assert results[0] is mock_route


def test_list_routes_empty_when_no_routes():
    db = make_mock_session(all_return=[])
    results = RouteDAO.list_routes(db)
    assert results == []


# ── delete_route ──────────────────────────────────────────────

def test_delete_route_returns_true_when_found(mock_route):
    db = make_mock_session(first_return=mock_route)
    result = RouteDAO.delete_route(db, 1)
    assert result is True
    db.delete.assert_called_once_with(mock_route)
    db.commit.assert_called_once()


def test_delete_route_returns_false_when_not_found():
    db = make_mock_session(first_return=None)
    result = RouteDAO.delete_route(db, 999)
    assert result is False
    db.delete.assert_not_called()
    db.commit.assert_not_called()
