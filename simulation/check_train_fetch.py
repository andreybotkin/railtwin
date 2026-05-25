import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from app.repositories.train import TrainRepository
from app.core.config import settings

async def main():
    engine = create_async_engine(str(settings.database_url))
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session() as session:
        repo = TrainRepository(session)
        trains = await repo.get_all_with_route(limit=500)
        print("Trains fetched:", len(trains))

asyncio.run(main())
