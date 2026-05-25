import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from app.models.database.models import Train, Schedule
from app.services.trajectory_service import _stop_fractions
from app.services.reference_data import RedisReferenceReader
from app.core.config import settings
import redis.asyncio as redis

async def main():
    redis_client = redis.Redis(host='redis', port=6379, db=0)
    reader = RedisReferenceReader(redis_client)
    train_payload = await reader.get_train_by_number("136")
    train_id = int(train_payload["id"])
    schedules = await reader._redis.get(f"{settings.reference_data_namespace}:schedules:by_train:{train_id}")
    import json
    from app.services.reference_data import schedule_payloads_to_domain, train_payload_to_domain
    schedules = json.loads(schedules)
    sched_domain = schedule_payloads_to_domain(schedules)
    
    route_id = int(train_payload["current_route_id"])
    route_data = await reader._redis.get(f"{settings.reference_data_namespace}:route_geometry:by_route:{route_id}")
    route_data = json.loads(route_data)
    coords = route_data["coords"]
    distance_km = route_data["distance_km"]
    
    fractions = _stop_fractions(sched_domain, coords, distance_km)
    for i, s in enumerate(sched_domain):
        print(f"{i:2d} | {s.station_name:25s} | {fractions[i]:.4f}")
    
asyncio.run(main())
