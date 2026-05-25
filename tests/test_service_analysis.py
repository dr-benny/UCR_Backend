"""
Unit tests for analysis_service.py.

External dependencies (Google Street View, Gemini, DAO) are mocked so
these tests run without network or database access.
"""
import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.analysis_service import (
    AnalysisInput,
    _build_dao_data,
    analyze_from_streetview,
    analyze_from_upload,
    reanalyze_record,
    save_upload,
    validate_mime,
)

LAT, LON = 13.736717, 100.523186

AI_RESULT = {
    "urban_morphology": {"street_width": 8.0},
    "vegetation": {"green_view_index": 0.3},
    "surface_and_flood": {"surface_material": "asphalt"},
    "health_livability": {"walkability_obstruction": "low"},
    "scene_description": "A Bangkok street",
    "observed_features": ["road"],
    "reference_objects": [],
    "evidence": {},
    "confidence_scores": {"urban_morphology": 0.9},
}


def _inp(**kwargs) -> AnalysisInput:
    defaults = dict(latitude=LAT, longitude=LON)
    defaults.update(kwargs)
    return AnalysisInput(**defaults)


# ── validate_mime ─────────────────────────────────────────────

@pytest.mark.parametrize("mime", ["image/jpeg", "image/png", "image/webp"])
def test_validate_mime_allows_supported_types(mime):
    validate_mime(mime)  # should not raise


def test_validate_mime_raises_for_unsupported_type():
    with pytest.raises(ValueError, match="Unsupported image type"):
        validate_mime("image/gif")


def test_validate_mime_raises_for_pdf():
    with pytest.raises(ValueError):
        validate_mime("application/pdf")


# ── save_upload ───────────────────────────────────────────────

def test_save_upload_writes_bytes_to_disk(tmp_path):
    with patch("app.services.analysis_service.settings") as mock_settings:
        mock_settings.IMAGE_DIR = str(tmp_path)
        path = save_upload(b"fake-image-data", "photo.jpg")

    assert os.path.isfile(path)
    assert open(path, "rb").read() == b"fake-image-data"


def test_save_upload_uses_jpg_extension_as_default(tmp_path):
    with patch("app.services.analysis_service.settings") as mock_settings:
        mock_settings.IMAGE_DIR = str(tmp_path)
        path = save_upload(b"data")

    assert path.endswith(".jpg")


def test_save_upload_preserves_png_extension(tmp_path):
    with patch("app.services.analysis_service.settings") as mock_settings:
        mock_settings.IMAGE_DIR = str(tmp_path)
        path = save_upload(b"data", "image.png")

    assert path.endswith(".png")


# ── _build_dao_data ───────────────────────────────────────────

def test_build_dao_data_maps_fields_correctly():
    inp = _inp(heading=180.0, pitch=5.0, fov=90.0)
    data = _build_dao_data(AI_RESULT, image_url="url", image_path="/path/img.jpg", inp=inp)

    assert data["heading"] == 180.0
    assert data["pitch"] == 5.0
    assert data["image_url"] == "url"
    assert data["image_path"] == "/path/img.jpg"
    assert data["urban_morphology"] == AI_RESULT["urban_morphology"]
    assert data["raw_ai_response"] == AI_RESULT


# ── analyze_from_streetview ───────────────────────────────────

@pytest.mark.asyncio
async def test_analyze_from_streetview_happy_path(mock_analysis):
    db = MagicMock()

    mock_engine = AsyncMock()
    mock_engine.analyze_image.return_value = AI_RESULT

    with (
        patch("app.services.analysis_service.check_streetview_coverage", new=AsyncMock(return_value=True)),
        patch("app.services.analysis_service.fetch_streetview_image", new=AsyncMock(return_value=("url", "/tmp/img.jpg"))),
        patch("app.services.analysis_service.get_engine", return_value=mock_engine),
        patch("app.services.analysis_service.AnalysisDAO.create_analysis", return_value=mock_analysis),
    ):
        result = await analyze_from_streetview(db, _inp())

    assert result is mock_analysis


@pytest.mark.asyncio
async def test_analyze_from_streetview_raises_lookup_when_no_coverage():
    db = MagicMock()

    with patch(
        "app.services.analysis_service.check_streetview_coverage",
        new=AsyncMock(return_value=False),
    ):
        with pytest.raises(LookupError, match="No Street View coverage"):
            await analyze_from_streetview(db, _inp())


@pytest.mark.asyncio
async def test_analyze_from_streetview_passes_model_name_to_engine(mock_analysis):
    db = MagicMock()
    mock_engine = AsyncMock()
    mock_engine.analyze_image.return_value = AI_RESULT

    with (
        patch("app.services.analysis_service.check_streetview_coverage", new=AsyncMock(return_value=True)),
        patch("app.services.analysis_service.fetch_streetview_image", new=AsyncMock(return_value=("url", "/tmp/img.jpg"))),
        patch("app.services.analysis_service.get_engine", return_value=mock_engine) as mock_get_engine,
        patch("app.services.analysis_service.AnalysisDAO.create_analysis", return_value=mock_analysis),
    ):
        await analyze_from_streetview(db, _inp(), model_name="gemini")

    mock_get_engine.assert_called_once_with("gemini")


# ── analyze_from_upload ───────────────────────────────────────

@pytest.mark.asyncio
async def test_analyze_from_upload_happy_path(mock_analysis, tmp_path):
    db = MagicMock()
    mock_engine = AsyncMock()
    mock_engine.analyze_image_bytes.return_value = AI_RESULT

    with (
        patch("app.services.analysis_service.save_upload", return_value="/tmp/upload.jpg"),
        patch("app.services.analysis_service.get_engine", return_value=mock_engine),
        patch("app.services.analysis_service.AnalysisDAO.create_analysis", return_value=mock_analysis),
    ):
        result = await analyze_from_upload(
            db, _inp(), img_bytes=b"fake-image", mime_type="image/jpeg"
        )

    assert result is mock_analysis


@pytest.mark.asyncio
async def test_analyze_from_upload_calls_analyze_image_bytes(mock_analysis):
    db = MagicMock()
    mock_engine = AsyncMock()
    mock_engine.analyze_image_bytes.return_value = AI_RESULT

    with (
        patch("app.services.analysis_service.save_upload", return_value="/tmp/upload.jpg"),
        patch("app.services.analysis_service.get_engine", return_value=mock_engine),
        patch("app.services.analysis_service.AnalysisDAO.create_analysis", return_value=mock_analysis),
    ):
        await analyze_from_upload(
            db, _inp(), img_bytes=b"data", mime_type="image/png"
        )

    mock_engine.analyze_image_bytes.assert_called_once_with(b"data", mime_type="image/png")


# ── reanalyze_record ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_reanalyze_record_happy_path(mock_analysis, tmp_path):
    db = MagicMock()
    # Create the image file so os.path.isfile returns True
    img_path = tmp_path / "test.jpg"
    img_path.write_bytes(b"img")
    mock_analysis.image_path = str(img_path)

    mock_engine = AsyncMock()
    mock_engine.analyze_image.return_value = AI_RESULT

    with (
        patch("app.services.analysis_service.get_engine", return_value=mock_engine),
        patch("app.services.analysis_service.AnalysisDAO.update_ai_result", return_value=mock_analysis),
    ):
        result = await reanalyze_record(db, mock_analysis)

    assert result is mock_analysis


@pytest.mark.asyncio
async def test_reanalyze_record_raises_when_image_missing(mock_analysis):
    db = MagicMock()
    mock_analysis.image_path = "/non/existent/path.jpg"

    with pytest.raises(FileNotFoundError, match="Image file not found"):
        await reanalyze_record(db, mock_analysis)


@pytest.mark.asyncio
async def test_reanalyze_record_raises_when_image_path_is_none(mock_analysis):
    db = MagicMock()
    mock_analysis.image_path = None

    with pytest.raises(FileNotFoundError):
        await reanalyze_record(db, mock_analysis)
