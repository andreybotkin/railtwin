from datetime import datetime

from app.domain.delays.entities import TrainDelay
from app.domain.delays.repository import DelayRepository


class DelayDomainService:
    """Domain service for train delay management."""

    def __init__(self, repository: DelayRepository) -> None:
        self._repo = repository

    async def update_delays(self, raw: dict[str, int]) -> int:
        """Convert raw {train_number: delay_minutes} mapping and persist.

        Only stores trains with a positive delay.
        Returns the number of delayed trains stored.
        """
        now = datetime.utcnow()
        delays = [
            TrainDelay(train_number=k, delay_minutes=v, fetched_at=now)
            for k, v in raw.items()
            if v > 0
        ]
        await self._repo.store_delays(delays)
        return len(delays)
