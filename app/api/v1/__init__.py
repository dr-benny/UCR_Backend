from fastapi import APIRouter, Depends

from app.api.v1.engines import router as engines_router
from app.api.v1.jobs import router as jobs_router
from app.api.v1.upload import router as upload_router
from app.core.auth import require_api_key

router = APIRouter()

# /api/engines stays public (only lists model names).
router.include_router(engines_router)

# Data + cost-bearing routes require an API key (no-op when API_KEY is unset).
router.include_router(upload_router, dependencies=[Depends(require_api_key)])
router.include_router(jobs_router, dependencies=[Depends(require_api_key)])
