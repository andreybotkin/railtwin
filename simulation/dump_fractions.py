import asyncio

import redis.asyncio as redis

from app.core.config import settings
from app.services.reference_data import RedisReferenceReader
from app.services.trajectory_service import _stop_fractions


async def main():
    redis_client = redis.Redis(host='redis', port=6379, db=0)
    reader = RedisReferenceReader(redis_client)
    train_payload = await reader.get_train_by_number("136")
    train_id = int(train_payload["id"])
    schedules = await reader._redis.get(f"{settings.reference_data_namespace}:schedules:by_train:{train_id}")
    import json

    from app.services.reference_data import (
        schedule_payloads_to_domain,
    )
    schedules = json.loads(schedules)
    sched_domain = schedule_payloads_to_domain(schedules)

    route_id = int(train_payload["current_route_id"])
    route_data = await reader._redis.get(f"{settings.reference_data_namespace}:route_geometry:by_route:{route_id}")
    route_data = json.loads(route_data)
    coords = route_data["coords"]
    distance_km = route_data["distance_km"]

    _stop_fractions(sched_domain, coords, distance_km)
    for _i, _s in enumerate(sched_domain):
        pass

asyncio.run(main())
