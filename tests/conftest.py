"""
Shared fixtures and test setup.

Env vars must be set before any app imports because pydantic-settings
reads them at class definition time.
"""
import os
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

# ── Environment variables (before any app import) ─────────────
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost:5432/test_arch")
os.environ.setdefault("GOOGLE_MAPS_API_KEY", "test-google-key")
os.environ.setdefault("GEMINI_API_KEY", "test-gemini-key")
os.environ.setdefault("IMAGE_DIR", "/tmp/test_images")
os.environ.setdefault("AI_ENGINE", "gemini")
os.environ.setdefault("GEMINI_MODEL", "gemini-2.5-flash")
os.environ.setdefault("STREETVIEW_SIZE", "640x640")
os.environ.setdefault("STREETVIEW_DEFAULT_FOV", "90")
os.environ.setdefault("STREETVIEW_DEFAULT_PITCH", "0")

# Create image dir so StaticFiles mount doesn't raise
os.makedirs("/tmp/test_images", exist_ok=True)

# Patch MetaData.create_all before importing app (it's called at module level
# in app/main.py and would try to connect to a real database)
_create_all_patcher = patch("sqlalchemy.MetaData.create_all")
_create_all_patcher.start()

# ── App imports (safe after patches above) ────────────────────
import pytest
from fastapi.testclient import TestClient
from geoalchemy2.elements import WKTElement

from app.db.database import get_db
from app.main import app
from app.models.analysis import StreetAnalysis
from app.models.route import SurveyRoute


# ── Mock session factory ───────────────────────────────────────

def make_mock_session(first_return=None, all_return=None, scalar_return=None):
    """Return a MagicMock SQLAlchemy session with a chainable query mock."""
    session = MagicMock()
    query = MagicMock()
    query.filter.return_value = query
    query.order_by.return_value = query
    query.offset.return_value = query
    query.limit.return_value = query
    query.first.return_value = first_return
    query.all.return_value = all_return if all_return is not None else (
        [first_return] if first_return is not None else []
    )
    query.scalar.return_value = scalar_return
    session.query.return_value = query
    return session


# ── Fixtures ──────────────────────────────────────────────────

@pytest.fixture
def db():
    """Default mock DB session (empty results)."""
    return make_mock_session()


@pytest.fixture
def mock_route():
    """A fully-populated SurveyRoute instance (no real DB needed)."""
    route = SurveyRoute(name="Test Route BKK", description="Bangkok walking survey")
    route.id = 1
    route.analyses = []
    route.created_at = datetime(2025, 1, 1, tzinfo=timezone.utc)
    route.updated_at = datetime(2025, 1, 1, tzinfo=timezone.utc)
    return route


@pytest.fixture
def mock_analysis():
    """A fully-populated StreetAnalysis instance (no real DB needed)."""
    a = StreetAnalysis(
        geom=WKTElement("POINT(100.523186 13.736717)", srid=4326),
        route_id=1,
        order_index=1,
        heading=90.0,
        pitch=0.0,
        fov=90.0,
        streetview_image_url="LOCAL_ONLY",
        image_path="/tmp/test_images/test.jpg",
        urban_morphology={
            "street_width": 8.0,
            "building_height_est_m": 12.0,
            "height_width_ratio": 1.5,
            "sky_view_factor": 0.65,
            "road_slope": "flat",
            "sidewalk_height": "0.15m",
        },
        vegetation={
            "green_view_index": 0.3,
            "tree_canopy_coverage": "moderate",
            "shade_fraction": 0.4,
        },
        surface_and_flood={
            "surface_material": "asphalt",
            "impervious_surface_ratio": 0.8,
            "drainage_infrastructure_presence": "present",
            "drainage_obstruction": "none",
            "water_body_proximity": "none",
        },
        health_livability={
            "walkability_obstruction": "low",
            "waste_accumulation": "none",
            "lighting_infrastructure": "present",
            "trash_bin_presence": "present",
        },
        scene_description="A typical Bangkok street with moderate tree cover.",
        observed_features=["buildings", "trees", "road"],
        reference_objects=["street lamp", "parked cars"],
        evidence={"urban_morphology": "Wide road clearly visible"},
        confidence_scores={"urban_morphology": 0.9, "vegetation": 0.85},
    )
    a.id = 1
    a.created_at = datetime(2025, 1, 1, tzinfo=timezone.utc)
    a.updated_at = datetime(2025, 1, 1, tzinfo=timezone.utc)
    return a


@pytest.fixture
def client(db):
    """TestClient with DB dependency overridden to the mock session."""
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
