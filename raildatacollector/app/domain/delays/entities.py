from dataclasses import dataclass
from datetime import datetime


@dataclass
class TrainDelay:
    """Domain entity representing a real-time delay for a specific train."""

    train_number: str
    delay_minutes: int
    fetched_at: datetime
