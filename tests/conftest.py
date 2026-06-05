import os

os.environ.setdefault("GOOGLE_MAPS_API_KEY", "test-google-key")
os.environ.setdefault("GEMINI_API_KEY", "test-gemini-key")
os.environ.setdefault("IMAGE_DIR", "/tmp/test_images")
os.environ.setdefault("AI_ENGINE", "gemini")
os.environ.setdefault("GEMINI_MODEL", "gemini-2.5-flash")
os.environ.setdefault("STREETVIEW_SIZE", "640x640")
os.environ.setdefault("STREETVIEW_DEFAULT_FOV", "90")
os.environ.setdefault("STREETVIEW_DEFAULT_PITCH", "0")

os.makedirs("/tmp/test_images", exist_ok=True)

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c
