from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from config import DB_HOST, DB_NAME, DB_PASS, DB_PORT, DB_USER, DATABASE_URL

engine = create_async_engine(DATABASE_URL, echo=True)

async_session_maker = async_sessionmaker(engine, expire_on_commit=False)

async def get_async_session() -> AsyncSession:
    async with async_session_maker() as session:
        yield session
        
