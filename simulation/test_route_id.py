import asyncio
from app.services.reference_data import RedisReferenceReader
from app.core.config import settings
import redis.asyncio as redis

async def main():
    redis_client = redis.Redis(host='redis', port=6379, db=0)
    reader = RedisReferenceReader(redis_client)
    train_payload = await reader.get_train_by_number("111")
    print("route_id:", train_payload["current_route_id"])

asyncio.run(main())
