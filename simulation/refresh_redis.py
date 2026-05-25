import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from app.services.reference_data import refresh_reference_data
from app.core.config import settings
import redis.asyncio as redis

async def main():
    engine = create_async_engine(str(settings.database_url))
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    redis_client = redis.Redis(host='redis', port=6379, db=0)
    
    async with async_session() as session:
        print("Refreshing reference data in Redis...")
        meta = await refresh_reference_data(session, redis_client)
        print("Done!", meta)

asyncio.run(main())
