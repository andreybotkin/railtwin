from abc import ABC, abstractmethod

from app.domain.delays.entities import TrainDelay


class DelayRepository(ABC):
    """Abstract repository for train delay persistence."""

    @abstractmethod
    async def store_delays(self, delays: list[TrainDelay]) -> None:
        """Persist delay map (overwrites existing data)."""
        ...

    @abstractmethod
    async def get_all_delays(self) -> list[TrainDelay]:
        """Retrieve all currently stored delays."""
        ...
