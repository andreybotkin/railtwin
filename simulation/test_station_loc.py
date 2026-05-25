import asyncio
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
    
    schedules = json.loads(schedules)
    
    for payload in schedules[:2]:
        station_payload = payload.get("station")
        location = station_payload.get("location")
        print(f"Station {station_payload['name']}: location type={type(location)} val={location}")

asyncio.run(main())
