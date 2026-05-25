import asyncio

import redis.asyncio as redis

from app.core.config import settings
from app.services import schedule_utils
from app.services.reference_data import RedisReferenceReader
from app.services.trajectory_service import build_trajectory


async def main():
    redis_client = redis.Redis(host='redis', port=6379, db=0)
    reader = RedisReferenceReader(redis_client)
    train_payload = await reader.get_train_by_number("111")
    train_id = int(train_payload["id"])
    schedules = await reader._redis.get(f"{settings.reference_data_namespace}:schedules:by_train:{train_id}")
    import json

    from app.services.reference_data import (
        schedule_payloads_to_domain,
        train_payload_to_domain,
    )
    schedules = json.loads(schedules)
    sched_domain = schedule_payloads_to_domain(schedules)

    route_id = int(train_payload["current_route_id"])
    route_data = await reader._redis.get(f"{settings.reference_data_namespace}:route_geometry:by_route:{route_id}")
    route_data = json.loads(route_data)
    coords = route_data["coords"]
    distance_km = route_data["distance_km"]

    train_domain = train_payload_to_domain(train_payload)

    current_minutes = schedule_utils.get_current_time_minutes()

    traj = build_trajectory(
        train_domain,
        sched_domain,
        route_coords=coords,
        route_distance_km=distance_km,
        delay=0,
        current_minutes=current_minutes,
    )

    if traj:
        for _i, _f in enumerate(traj.frames[:5]):
            pass
    else:
        pass

asyncio.run(main())
