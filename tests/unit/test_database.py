import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_async_session, engine, async_session_maker
from unittest.mock import AsyncMock, patch


@pytest.mark.asyncio
async def test_get_async_session():
    """Тестирование получения асинхронной сессии"""
    session = await anext(get_async_session())
    assert isinstance(session, AsyncSession)


@pytest.mark.asyncio
async def test_engine_creation():
    assert engine is not None
    assert engine.url.database is not None


@pytest.mark.asyncio
async def test_async_session_maker():
    """Проверяем создание сессии через async_session_maker"""
    async with async_session_maker() as session:
        assert isinstance(session, AsyncSession)
