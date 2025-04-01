import pytest
import pytest_asyncio
from unittest.mock import AsyncMock
from sqlalchemy.ext.asyncio import AsyncSession
from app.redis import set_cache
from datetime import timedelta, datetime
from httpx import AsyncClient, ASGITransport
from main import app
from unittest.mock import AsyncMock, MagicMock, patch
from handlers import (
    shorten_link,
    update_short_link,
    redirect_link,
    generate_short_code,
    update_stats_cache,
    get_expired_links,
    link_stats,
    delete_short_link,
    search_link_by_url,
    ShortenLinkRequest,
    RedirectResponse
)
from fastapi import HTTPException, BackgroundTasks
import asyncio
import uuid


def test_generate_short_code():
    short_code = generate_short_code()
    assert isinstance(short_code, str)
    assert len(short_code) == 8


@pytest.mark.asyncio
async def test_update_stats_cache(mocker):
    mock_set_cache = mocker.patch("handlers.set_cache", new_callable=AsyncMock)

    key = "abc123"
    click_count = 5
    last_accessed_at = "2024-03-31T12:00:00"

    await update_stats_cache(key, click_count, last_accessed_at)

    mock_set_cache.assert_called_once_with(
        "stats:abc123",
        {
            "click_count": 5,
            "last_accessed_at": last_accessed_at,
        },
        expire=300,
    )


@pytest.mark.asyncio
async def test_link_stats_cache_hit(mocker):
    short_code = "short_code"
    cached_stats = {
        "original_url": "http://example.com",
        "created_at": "2025-31-03",
        "click_count": 100,
        "last_accessed_at": "2025-04-01",
    }

    mock_get_cache = mocker.patch("handlers.get_cache", new_callable=AsyncMock)
    mock_get_cache.return_value = cached_stats

    # Мокаем сессию
    session = AsyncMock()
    session.execute.return_value = make_fake_result(
        []
    ) 

    current_user = MagicMock()
    current_user.id = uuid.uuid4()

    stats = await link_stats(short_code, session=session, current_user=current_user)

    assert stats == cached_stats
    session.execute.assert_not_called()


# Функция, повторяющая структура вызова из базы данных (иначе coroutine' object has no attribute 'first')
def make_fake_result(first_return):
    fake_scalars = MagicMock()
    fake_scalars.first.return_value = first_return
    fake_result = MagicMock()
    fake_result.scalars.return_value = fake_scalars
    return fake_result


@pytest.mark.asyncio
async def test_shorten_link_random_alias_loop():
    session = AsyncMock()
    current_user = MagicMock()
    current_user.id = 1

    session.execute.side_effect = [
        make_fake_result(MagicMock()),  # первый вызов — конфликт alias
        make_fake_result(None),  # второй вызов — alias уникальный
    ]

    # Мок Redis set_cache:
    with patch("handlers.generate_short_code", side_effect=["alias1", "alias2"]):
        with patch("handlers.set_cache", new_callable=AsyncMock) as mock_set_cache:
            request = MagicMock()
            request.custom_alias = None
            request.original_url = "https://example.com"
            request.expires_at = None

            result = await shorten_link(
                request, session=session, current_user=current_user
            )
            mock_set_cache.assert_called_once()
            assert "alias2" in result["short_url"]


@pytest.mark.asyncio
async def test_redirect_link_not_found(mocker):
     session = AsyncMock()
     background_tasks = BackgroundTasks()
     # Симулируем, что кэш отсутствует и в базе ничего не найдено
     session.execute.return_value = make_fake_result(None)

     # Мокируем redis_client и его метод get
     mock_redis_client = mocker.patch("app.redis.redis_client", new_callable=AsyncMock)
     mock_redis_client.get.return_value = None

     with pytest.raises(HTTPException) as exc:
         await redirect_link(
             "nonexistent", session=session, background_tasks=background_tasks
         )
     assert exc.value.status_code == 404
     assert exc.value.detail == "Short link not found"


@pytest.mark.asyncio
async def test_update_short_link_while_loop():
    session = AsyncMock()
    current_user = MagicMock()
    current_user.id = 1

    link_to_update = MagicMock()
    link_to_update.user_id = 1
    link_to_update.short_code = "oldalias"
    link_to_update.updated_at = datetime.utcnow()

    initial_result = make_fake_result(link_to_update)
    conflict_result = make_fake_result(MagicMock()) 
    unique_result = make_fake_result(None)  # уникальный alias

    session.execute.side_effect = [initial_result, conflict_result, unique_result]

    with patch(
        "handlers.generate_short_code", side_effect=["alias_conflict", "unique_alias"]
    ):
        from handlers import UpdateLinkRequest

        request = UpdateLinkRequest(custom_alias=None, expires_at=None)
        response = await update_short_link(
            "oldalias", request=request, session=session, current_user=current_user
        )
        assert "unique_alias" in response["new_short_url"]


@pytest.mark.asyncio
async def test_update_short_link_not_found():
    session = AsyncMock()
    session.execute.return_value = make_fake_result(None)
    current_user = MagicMock()
    current_user.id = uuid.uuid4()

    with pytest.raises(HTTPException) as exc:
        from handlers import UpdateLinkRequest

        request = UpdateLinkRequest(custom_alias="new_alias", expires_at=None)
        await update_short_link(
            "nonexistent", request=request, session=session, current_user=current_user
        )

    assert exc.value.status_code == 404
    assert exc.value.detail == "Short link not found"


@pytest.mark.asyncio
async def test_update_short_link_forbidden():
    session = AsyncMock()
    link = MagicMock()
    link.user_id = uuid.uuid4()
    session.execute.return_value = make_fake_result(link)

    current_user = MagicMock()
    current_user.id = uuid.uuid4()  # UUID для текущего пользователя

    with pytest.raises(HTTPException) as exc:
        from handlers import UpdateLinkRequest

        request = UpdateLinkRequest(custom_alias="new_alias", expires_at=None)
        await update_short_link(
            "existing_alias",
            request=request,
            session=session,
            current_user=current_user,
        )

    assert exc.value.status_code == 403
    assert exc.value.detail == "Not authorized to update this link"


@pytest.mark.asyncio
async def test_link_stats_forbidden(mocker):
    mock_redis_client = mocker.patch("app.redis.redis_client", new_callable=AsyncMock)
    mock_redis_client.get.return_value = None

    session = AsyncMock()
    link = MagicMock()
    link.user_id = uuid.uuid4()
    session.execute.return_value = make_fake_result(link)

    current_user = MagicMock()
    current_user.id = uuid.uuid4()

    with pytest.raises(HTTPException) as exc:
        await link_stats("shortcode123", session=session, current_user=current_user)

    assert exc.value.status_code == 403
    assert exc.value.detail == "Not authorized to view this link's stats"


@pytest.mark.asyncio
async def test_delete_short_link_not_found():
    session = AsyncMock()
    session.execute.return_value = make_fake_result(None) 
    current_user = MagicMock()
    current_user.id = uuid.uuid4()
    with pytest.raises(HTTPException) as exc:
        await delete_short_link(
            "nonexistent", session=session, current_user=current_user
        )

    assert exc.value.status_code == 404
    assert exc.value.detail == "Short link not found"


@pytest.mark.asyncio
async def test_delete_short_link_forbidden():
    session = AsyncMock()
    link = MagicMock()
    link.user_id = uuid.uuid4()  # UUID чужого пользователя
    session.execute.return_value = make_fake_result(link)

    current_user = MagicMock()
    current_user.id = uuid.uuid4()  # UUID текущего пользователя

    with pytest.raises(HTTPException) as exc:
        await delete_short_link("existing_alias", session=session, current_user=current_user)

    assert exc.value.status_code == 403
    assert exc.value.detail == "Not authorized to delete this link"


@pytest.mark.asyncio
async def test_search_link_by_url_forbidden():
    session = AsyncMock()
    link = MagicMock()
    link.user_id = uuid.uuid4()
    session.execute.return_value = make_fake_result([link])

    current_user = MagicMock()
    current_user.id = uuid.uuid4()  # UUID текущего пользователя

    with pytest.raises(HTTPException) as exc:
        await search_link_by_url(
            "https://example.com", session=session, current_user=current_user
        )

    assert exc.value.status_code == 403
    assert exc.value.detail == "Not authorized to search for this link"


@pytest.mark.asyncio
async def test_redirect_link(mocker):
    session = AsyncMock()
    background_tasks = BackgroundTasks()
    link = MagicMock()
    link.original_url = "https://example.com"
    link.expires_at = None
    link.click_count = 0
    session.execute.return_value = make_fake_result(link)

    # Мокируем Redis get
    mock_redis_client = mocker.patch("app.redis.redis_client", new_callable=AsyncMock)
    mock_redis_client.get.return_value = None

    result = await redirect_link(
        "valid_short_code", session=session, background_tasks=background_tasks
    )

    assert result.status_code == 307
    assert result.headers["Location"] == "https://example.com"
    assert link.click_count == 1


@pytest.mark.asyncio
async def test_delete_short_link_not_found():
    session = AsyncMock()
    session.execute.return_value = make_fake_result(None)  # Ссылка не найдена
    current_user = MagicMock()
    current_user.id = uuid.uuid4()

    with pytest.raises(HTTPException) as exc:
        await delete_short_link(
            "nonexistent", session=session, current_user=current_user
        )

    assert exc.value.status_code == 404
    assert exc.value.detail == "Short link not found"


@pytest.mark.asyncio
async def test_search_link_by_url_not_found():
    session = AsyncMock()
    session.execute.return_value = make_fake_result([])  # Ссылки не найдены
    current_user = MagicMock()
    current_user.id = uuid.uuid4()

    with pytest.raises(HTTPException) as exc:
        await search_link_by_url(
            "https://nonexistentlink.com", session=session, current_user=current_user
        )

    assert exc.value.status_code == 404
    assert exc.value.detail == "Link not found"


@pytest.mark.asyncio
async def test_redirect_link_from_cache(mocker):
    session = AsyncMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    background_tasks = BackgroundTasks()
    mock_get_cache = mocker.patch("handlers.get_cache", new_callable=AsyncMock)
    mock_get_cache.return_value = {"original_url": "https://example.com/cached"}

    session.execute.return_value = make_fake_result(
        MagicMock(
            original_url="https://example.com/cached",
            expires_at=None,
            click_count=0,
            last_accessed_at=None,
        )
    )

    response = await redirect_link(
        "cached_alias", session=session, background_tasks=background_tasks
    )
    assert isinstance(response, RedirectResponse)
    assert response.headers["location"] == "https://example.com/cached"
    session.execute.assert_called()
