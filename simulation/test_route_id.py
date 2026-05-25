import asyncio

import redis.asyncio as redis

from app.services.reference_data import RedisReferenceReader


async def main():
    redis_client = redis.Redis(host='redis', port=6379, db=0)
    reader = RedisReferenceReader(redis_client)
    await reader.get_train_by_number("111")

asyncio.run(main())
