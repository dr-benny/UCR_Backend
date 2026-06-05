from fastapi import APIRouter

from app.api.v1.analyze import router as analyze_router
from app.api.v1.upload import router as upload_router
from app.api.v1.jobs import router as jobs_router

router = APIRouter()
router.include_router(analyze_router)
router.include_router(upload_router)
router.include_router(jobs_router)
