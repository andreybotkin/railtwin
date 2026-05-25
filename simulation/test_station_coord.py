import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from app.models.database.models import Train, Schedule
from app.services.trajectory_service import _station_coord
from app.services.reference_data import RedisReferenceReader
from app.core.config import settings
import redis.asyncio as redis
import json

async def main():
    redis_client = redis.Redis(host='redis', port=6379, db=0)
    reader = RedisReferenceReader(redis_client)
    train_payload = await reader.get_train_by_number("111")
    train_id = int(train_payload["id"])
    schedules = await reader._redis.get(f"{settings.reference_data_namespace}:schedules:by_train:{train_id}")
    
    from app.services.reference_data import schedule_payloads_to_domain
    schedules = json.loads(schedules)
    sched_domain = schedule_payloads_to_domain(schedules)
    
    for i, sched in enumerate(sched_domain[:5]):
        coord = _station_coord(sched)
        print(f"Station {sched.station_name}: coord={coord}")

asyncio.run(main())
