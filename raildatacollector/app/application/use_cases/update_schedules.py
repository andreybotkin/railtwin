"""Use case: periodic (monthly) update of train schedules from timetable sources."""

from app.core.logging import get_logger
from app.domain.schedule.repository import ScheduleRepository
from app.domain.schedule.service import ScheduleDomainService
from app.infrastructure.scrapers.timetable_scraper import fetch_timetable

logger = get_logger(__name__)


class UpdateSchedulesUseCase:
    def __init__(self, repository: ScheduleRepository) -> None:
        self._svc = ScheduleDomainService(repository)

    async def execute(self) -> dict:
        logger.info("Starting periodic schedule update")
        trains = await fetch_timetable()
        if not trains:
            logger.warning("No timetable data available, schedule update skipped")
            return {"success": False, "reason": "no_data"}

        count = await self._svc.upsert_trains(trains)
        logger.info("Schedules updated", trains=count)
        return {"success": True, "trains_updated": count}
