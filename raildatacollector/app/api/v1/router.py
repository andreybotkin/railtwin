from fastapi import APIRouter

from app.api.v1.endpoints.collect import router as collect_router
from app.api.v1.endpoints.status import router as status_router

router = APIRouter()
router.include_router(status_router, prefix="/status", tags=["status"])
router.include_router(collect_router, prefix="/collect", tags=["collect"])
