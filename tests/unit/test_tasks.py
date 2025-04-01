import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timedelta
from app.tasks import delete_expired_links, periodic_task
from app.models import Link, LinkHistory
import asyncio


@pytest.mark.asyncio
async def test_delete_expired_links(mocker):
    # Мокируем сессию БД как асинхронный объект
    mock_session = AsyncMock()

    expired_link = Link(
        short_code="abc123",
        original_url="http://example.com",
        expires_at=datetime.utcnow() - timedelta(days=1),
        click_count=10,
        user_id=1,
    )

    # Создаем мок для цепочки: execute() -> scalars() -> all()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [expired_link]
    mock_session.execute = AsyncMock(return_value=mock_result)

    mock_session.add = AsyncMock()
    mock_session.commit = AsyncMock()

    await delete_expired_links(mock_session)

    mock_session.add.assert_called_once()
    args, _ = mock_session.add.call_args
    link_history = args[0]
    assert isinstance(link_history, LinkHistory)
    assert link_history.short_code == "abc123"
    assert link_history.original_url == "http://example.com"
    assert link_history.click_count == 10

    mock_session.commit.assert_called_once()
