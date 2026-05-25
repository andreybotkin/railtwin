import asyncio
from app.services.reference_data import RedisReferenceReader
from app.core.config import settings
import redis.asyncio as redis
import json

async def main():
    redis_client = redis.Redis(host='redis', port=6379, db=0)
    reader = RedisReferenceReader(redis_client)
    route_data = await reader._redis.get(f"{settings.reference_data_namespace}:route_geometry:by_route:2") # Northern line is probably 2, let's just get it from Train 111
    
    train_payload = await reader.get_train_by_number("111")
    route_id = int(train_payload["current_route_id"])
    route_data = await reader._redis.get(f"{settings.reference_data_namespace}:route_geometry:by_route:{route_id}")
    route_data = json.loads(route_data)
    coords = route_data["coords"]
    print(f"First 5 coords of route {route_id}: {coords[:5]}")

asyncio.run(main())
