import json
from datetime import datetime

import redis.asyncio as aioredis

from app.core.config import settings
from app.core.logging import get_logger
from app.domain.delays.entities import TrainDelay
from app.domain.delays.repository import DelayRepository

logger = get_logger(__name__)


class RedisDelayRepository(DelayRepository):
    """Redis implementation of the delay repository.

    Stores delays in the same Redis key used by the simulation service
    service so that train position interpolation picks up delay corrections
    immediately.
    """

    def __init__(self, redis_client: aioredis.Redis) -> None:
        self._redis = redis_client

    async def store_delays(self, delays: list[TrainDelay]) -> None:
        payload = {d.train_number: d.delay_minutes for d in delays}
        await self._redis.set(
            settings.tts_delays_redis_key,
            json.dumps(payload),
            ex=settings.tts_delays_redis_ttl,
        )
        logger.info("Delays stored in Redis", count=len(delays))

    async def get_all_delays(self) -> list[TrainDelay]:
        raw = await self._redis.get(settings.tts_delays_redis_key)
        if not raw:
            return []
        data: dict[str, int] = json.loads(raw)
        now = datetime.utcnow()
        return [
            TrainDelay(train_number=k, delay_minutes=v, fetched_at=now)
            for k, v in data.items()
        ]
