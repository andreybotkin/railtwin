import asyncio

import redis.asyncio as redis
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.services.reference_data import refresh_reference_data


async def main():
    engine = create_async_engine(str(settings.database_url))
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    redis_client = redis.Redis(host='redis', port=6379, db=0)

    async with async_session() as session:
        await refresh_reference_data(session, redis_client)

asyncio.run(main())
