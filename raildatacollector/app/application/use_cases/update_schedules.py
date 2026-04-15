"""Use case: periodic update of timetable cache from external timetable sources.

On each run:
  1. Fetches the latest timetable (local cache → TTS remote).
    2. Saves the timetable as a dated JSON file in schedule/.
    3. Caches per-train schedule data in Redis (TTL 48 h) so the simulation
     simulation can query timetable data without hitting the database.

The database remains owned by raildbsetup and is seeded only from
raildbsetup/schedule/raw/*.json.
"""

import json
from datetime import datetime

import redis.asyncio as aioredis

from app.core.config import settings
from app.core.logging import get_logger
from app.domain.schedule.entities import TrainData
from app.infrastructure.scrapers.timetable_scraper import fetch_timetable

logger = get_logger(__name__)

_TIMETABLE_TTL = 48 * 3600  # 48 hours
_TIMETABLE_TRAIN_KEY_PREFIX = "timetable:train:"
_TIMETABLE_META_KEY = "timetable:metadata"


def _serialize_train(train: TrainData) -> str:
    return json.dumps(
        {
            "train_number": train.train_number,
            "train_type": train.train_type,
            "route_type": train.route_type,
            "name": train.name,
            "operator": train.operator,
            "stops": [
                {
                    "station_name": s.station_name,
                    "sequence": s.sequence,
                    "arrival_time": s.arrival_time,
                    "departure_time": s.departure_time,
                    "arrival_day_offset": s.arrival_day_offset,
                    "departure_day_offset": s.departure_day_offset,
                    "day_of_week": s.day_of_week,
                    "platform": s.platform,
                    "distance_from_origin_km": s.distance_from_origin_km,
                }
                for s in train.stops
            ],
        },
        ensure_ascii=False,
    )


class UpdateSchedulesUseCase:
    def __init__(self, redis_client: aioredis.Redis | None = None) -> None:
        self._redis = redis_client

    async def execute(self) -> dict:
        logger.info("Starting periodic schedule update")
        trains = await fetch_timetable()
        if not trains:
            logger.warning("No timetable data available, schedule update skipped")
            return {"success": False, "reason": "no_data"}

        if self._redis is not None:
            cached = await self._cache_to_redis(trains)
            logger.info("Schedules cached in Redis", trains=cached)

        return {
            "success": True,
            "trains_cached": len(trains),
            "redis_cached": self._redis is not None,
        }

    async def _cache_to_redis(self, trains: list[TrainData]) -> int:
        """Store per-train schedule data in Redis with a 48 h TTL."""
        if self._redis is None:
            return 0
        try:
            pipe = self._redis.pipeline()
            for train in trains:
                key = f"{_TIMETABLE_TRAIN_KEY_PREFIX}{train.train_number}"
                pipe.set(key, _serialize_train(train), ex=_TIMETABLE_TTL)
            pipe.set(
                _TIMETABLE_META_KEY,
                json.dumps(
                    {
                        "updated_at": datetime.utcnow().isoformat(),
                        "trains_count": len(trains),
                        "source": settings.app_name,
                    }
                ),
                ex=_TIMETABLE_TTL,
            )
            await pipe.execute()
            return len(trains)
        except Exception as exc:
            logger.error("Failed to cache schedules in Redis", error=str(exc))
            return 0
