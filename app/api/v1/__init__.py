from fastapi import APIRouter

from app.api.v1.engines import router as engines_router
from app.api.v1.jobs import router as jobs_router
from app.api.v1.upload import router as upload_router

router = APIRouter()
router.include_router(engines_router)
router.include_router(upload_router)
router.include_router(jobs_router)
