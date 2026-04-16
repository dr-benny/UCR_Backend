"""Router registry — aggregates all sub-routers into a single include-able router."""

from fastapi import APIRouter

from app.api.v1.routes import router as routes_router
from app.api.v1.analyze import router as analyze_router
from app.api.v1.upload import router as upload_router

router = APIRouter()
router.include_router(routes_router)
router.include_router(analyze_router)
router.include_router(upload_router)
