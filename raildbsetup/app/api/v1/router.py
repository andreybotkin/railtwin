from fastapi import APIRouter

from app.api.v1.endpoints.setup import router as setup_router

router = APIRouter()
router.include_router(setup_router, prefix="/setup", tags=["setup"])
