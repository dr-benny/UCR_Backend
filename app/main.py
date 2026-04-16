"""
Urban Microclimate Street Analysis API

Fetches Google Street View images and uses Gemini Vision AI
to extract architectural and thermal-comfort data.
"""

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.core.config import settings
from app.db.database import Base, engine
from app.api.v1 import router as analysis_router

# ── Logging ───────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s │ %(levelname)-8s │ %(name)s │ %(message)s",
)
logger = logging.getLogger(__name__)

# ── Create tables ─────────────────────────────────────────────
Base.metadata.create_all(bind=engine)

# ── FastAPI app ───────────────────────────────────────────────
app = FastAPI(
    title="Urban Microclimate Analyzer",
    description=(
        "Extracts walkway geometry, materials, shade, sky-view factor, "
        "and heat-risk data from Google Street View images using Gemini Vision AI."
    ),
    version="1.0.0",
)

# CORS — allow all origins for development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Mount static files (Images) ──────────────────────────────
app.mount("/static/images", StaticFiles(directory=settings.IMAGE_DIR), name="static-images")

# ── Register routers ─────────────────────────────────────────
app.include_router(analysis_router)


# ── Health check ──────────────────────────────────────────────
@app.get("/health", tags=["system"])
def health_check():
    return {"status": "ok", "service": "urban-microclimate-analyzer"}
