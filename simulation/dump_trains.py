import asyncio
from app.services.reference_data import RedisReferenceReader
import redis.asyncio as redis

async def main():
    redis_client = redis.Redis(host='redis', port=6379, db=0)
    reader = RedisReferenceReader(redis_client)
    
    ids = await reader._get_ids(reader._keys.train_ids)
    trains = await reader._get_hash_payloads(reader._keys.trains_by_id, ids)
    print("Trains in Redis:")
    for t in trains:
        print(t.get("train_number"), t.get("id"))

asyncio.run(main())
