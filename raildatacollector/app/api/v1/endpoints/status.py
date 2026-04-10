from fastapi import APIRouter

from app.application.scheduler import get_status

router = APIRouter()


@router.get(
    "",
    summary="Collector job status",
    description=(
        "Returns the last run timestamp and result for each collection job: "
        "railroad initialization, daily schedule update, and 30-min delay update."
    ),
)
async def get_collector_status() -> dict:
    return get_status()
