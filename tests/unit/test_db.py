import pytest
from db import get_user_db, create_db_and_tables
from app.models import User
from unittest.mock import AsyncMock, patch
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import engine

@pytest.mark.asyncio
async def test_get_user_db():
    mock_session = AsyncMock(spec=AsyncSession)
    async_gen = get_user_db(mock_session)
    user_db = await anext(async_gen)

    assert user_db is not None
    assert user_db.session == mock_session
    assert user_db.user_table == User
