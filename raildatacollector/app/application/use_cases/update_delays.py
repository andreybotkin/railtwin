"""Use case: 30-minute update of train delays from TTS real-time system."""

from app.core.logging import get_logger
from app.domain.delays.repository import DelayRepository
from app.domain.delays.service import DelayDomainService
from app.infrastructure.scrapers.tts_scraper import fetch_tts_delays

logger = get_logger(__name__)


class UpdateDelaysUseCase:
    def __init__(self, repository: DelayRepository) -> None:
        self._svc = DelayDomainService(repository)

    async def execute(self) -> dict:
        logger.info("Starting delay update from TTS")
        raw = await fetch_tts_delays()
        if raw is None:
            logger.warning("TTS returned no data; cached delays remain unchanged")
            return {"success": False, "reason": "tts_unavailable"}

        delayed_count = await self._svc.update_delays(raw)
        logger.info(
            "Delay update complete",
            delayed_trains=delayed_count,
            total_trains=len(raw),
        )
        return {
            "success": True,
            "delayed_trains": delayed_count,
            "total_trains": len(raw),
        }
