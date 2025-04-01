import asyncio
import pytest
import pytest_asyncio
import uuid
from httpx import AsyncClient, ASGITransport
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from app.models import Base
from app.database import get_async_session
from main import app
from auth import get_current_user, get_current_user_optional


class DummyUser:
    id = uuid.uuid4()


dummy_user = DummyUser()


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"
engine = create_async_engine(TEST_DATABASE_URL, echo=True)
TestingSessionLocal = sessionmaker(
    bind=engine, class_=AsyncSession, expire_on_commit=False
)


# Фикстура для базы данных (создание и удаление таблиц)
@pytest_asyncio.fixture(scope="function", autouse=True)
async def test_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session = TestingSessionLocal()
    yield session
    await session.close()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture(autouse=True)
async def override_get_db(test_db: AsyncSession):
    async def _get_test_db() -> AsyncSession:
        yield test_db

    app.dependency_overrides[get_async_session] = _get_test_db
    yield
    app.dependency_overrides.pop(get_async_session, None)


@pytest_asyncio.fixture(autouse=True)
async def override_auth():
    app.dependency_overrides[get_current_user] = lambda: dummy_user
    app.dependency_overrides[get_current_user_optional] = lambda: dummy_user
    yield
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_current_user_optional, None)


@pytest_asyncio.fixture
async def async_client():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client


# Тесты для пользователей с авторизацией или без ошибок Not authorized
@pytest.mark.asyncio
async def test_create_short_link(async_client):
    response = await async_client.post(
        "/links/shorten", json={"original_url": "https://example.com"}
    )
    assert response.status_code == 200
    assert "short_url" in response.json()


@pytest.mark.asyncio
async def test_create_short_link_duplicate_alias(async_client):
    await async_client.post(
        "/links/shorten",
        json={"original_url": "https://example.com", "custom_alias": "testalias"},
    )
    response = await async_client.post(
        "/links/shorten",
        json={"original_url": "https://example2.com", "custom_alias": "testalias"},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Custom alias is already taken"


@pytest.mark.asyncio
async def test_redirect_short_link(async_client):
    create_response = await async_client.post(
        "/links/shorten", json={"original_url": "https://example.com"}
    )
    assert create_response.status_code == 200
    short_url = create_response.json()["short_url"].split("/")[-1]
    response = await async_client.get(f"/{short_url}", follow_redirects=False)
    assert response.status_code == 307
    assert response.headers["location"].rstrip("/") == "https://example.com"


@pytest.mark.asyncio
async def test_redirect_short_link_not_found(async_client):
    response = await async_client.get("/nonexistent", follow_redirects=False)
    assert response.status_code == 404
    assert response.json()["detail"] == "Short link not found"


@pytest.mark.asyncio
async def test_register_and_login(async_client: AsyncClient):
    register_resp = await async_client.post(
        "/register", json={"email": "test@example.com", "password": "testpassword"}
    )
    assert register_resp.status_code == 201
    register_data = register_resp.json()
    assert register_data["msg"] == "User successfully registered"
    assert register_data["email"] == "test@example.com"

    login_data = {"username": "test@example.com", "password": "testpassword"}
    token_resp = await async_client.post("/token", data=login_data)
    assert token_resp.status_code == 200
    token_json = token_resp.json()
    assert "access_token" in token_json
    token = token_json["access_token"]

    headers = {"Authorization": f"Bearer {token}"}
    create_resp = await async_client.post(
        "/links/shorten",
        json={"original_url": "https://example.com", "custom_alias": "authalias"},
        headers=headers,
    )
    assert create_resp.status_code == 200
    data = create_resp.json()
    assert "short_url" in data


@pytest.mark.asyncio
async def test_update_short_link_authorized(async_client):
    create_response = await async_client.post(
        "/links/shorten", json={"original_url": "https://example.com"}
    )
    assert create_response.status_code == 200
    short_code = create_response.json()["short_url"].split("/")[-1]
    response = await async_client.put(
        f"/links/{short_code}", json={"custom_alias": "newalias"}
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_delete_short_link_authorized(async_client):
    create_response = await async_client.post(
        "/links/shorten", json={"original_url": "https://example.com"}
    )
    assert create_response.status_code == 200
    short_code = create_response.json()["short_url"].split("/")[-1]
    response = await async_client.delete(f"/links/{short_code}")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_get_link_stats_authorized(async_client: AsyncClient):
    await async_client.post(
        "/register", json={"email": "stats@example.com", "password": "testpassword"}
    )
    login_data = {"username": "stats@example.com", "password": "testpassword"}
    token_resp = await async_client.post("/token", data=login_data)
    token = token_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    create_resp = await async_client.post(
        "/links/shorten",
        json={"original_url": "https://example.com", "custom_alias": "statsalias"},
        headers=headers,
    )
    assert create_resp.status_code == 200
    short_code = create_resp.json()["short_url"].split("/")[-1]
    await async_client.get(f"/{short_code}", headers=headers)
    stats_resp = await async_client.get(f"/links/{short_code}/stats", headers=headers)
    assert stats_resp.status_code == 200
    stats = stats_resp.json()
    assert stats["click_count"] >= 1


# Тесты для неавторизованных пользователей или не создателей ссылки
class DummyUserDifferent:
    id = uuid.uuid4()


@pytest.mark.asyncio
async def test_update_short_link_unauthorized(async_client):
    create_response = await async_client.post(
        "/links/shorten", json={"original_url": "https://example.com"}
    )
    assert create_response.status_code == 200
    short_code = create_response.json()["short_url"].split("/")[-1]

    app.dependency_overrides[get_current_user] = lambda: DummyUserDifferent()

    response = await async_client.put(
        f"/links/{short_code}", json={"custom_alias": "newalias"}
    )
    assert response.status_code == 403
    app.dependency_overrides[get_current_user] = lambda: dummy_user


@pytest.mark.asyncio
async def test_delete_short_link_unauthorized(async_client):
    create_response = await async_client.post(
        "/links/shorten", json={"original_url": "https://example.com"}
    )
    assert create_response.status_code == 200
    short_code = create_response.json()["short_url"].split("/")[-1]

    app.dependency_overrides[get_current_user] = lambda: DummyUserDifferent()
    response = await async_client.delete(f"/links/{short_code}")
    assert response.status_code == 403
    app.dependency_overrides[get_current_user] = lambda: dummy_user


@pytest.mark.asyncio
async def test_get_link_stats_unauthorized(async_client):
    create_response = await async_client.post(
        "/links/shorten", json={"original_url": "https://example.com"}
    )
    assert create_response.status_code == 200
    short_code = create_response.json()["short_url"].split("/")[-1]

    app.dependency_overrides[get_current_user] = lambda: DummyUserDifferent()
    response = await async_client.get(f"/links/{short_code}/stats")
    assert response.status_code == 403
    app.dependency_overrides[get_current_user] = lambda: dummy_user


@pytest.mark.asyncio
async def test_search_link_by_url_unauthorized(async_client):
    await async_client.post(
        "/links/shorten", json={"original_url": "https://example.com"}
    )
    app.dependency_overrides[get_current_user] = lambda: DummyUserDifferent()
    response = await async_client.get(
        "/links/search", params={"original_url": "https://example.com"}
    )

    assert response.status_code in (403, 404)
    app.dependency_overrides[get_current_user] = lambda: dummy_user


# Тесты доп
@pytest.mark.asyncio
async def test_shorten_link_with_custom_alias(async_client: AsyncClient):
    response = await async_client.post(
        "/links/shorten",
        json={"original_url": "https://custom.com", "custom_alias": "myalias"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "short_url" in data
    assert data["short_url"].endswith("/myalias")


@pytest.mark.asyncio
async def test_redirect_link_not_found(async_client: AsyncClient):
    resp = await async_client.get("/nonexistent", follow_redirects=False)
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Short link not found"


@pytest.mark.asyncio
async def test_redirect_link_expired(async_client: AsyncClient, override_get_db):
    past = datetime.utcnow() - timedelta(days=1)
    response = await async_client.post(
        "/links/shorten",
        json={"original_url": "https://expired.com", "expires_at": past.isoformat()},
    )
    assert response.status_code == 200
    short_code = response.json()["short_url"].split("/")[-1]

    resp = await async_client.get(f"/{short_code}", follow_redirects=False)
    assert resp.status_code == 410
    assert resp.json()["detail"] == "Link has expired"


@pytest.mark.asyncio
async def test_update_short_link_not_found(async_client: AsyncClient):
    resp = await async_client.put(
        "/links/nonexistent", json={"custom_alias": "newalias"}
    )
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Short link not found"


@pytest.mark.asyncio
async def test_link_stats_not_found(async_client: AsyncClient):
    resp = await async_client.get("/links/nonexistent/stats")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Short link not found"


@pytest.mark.asyncio
async def test_search_link_by_url_not_found(async_client: AsyncClient):
    resp = await async_client.get(
        "/links/search", params={"original_url": "https://no-link.com"}
    )
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Link not found"


@pytest.mark.asyncio
async def test_get_expired_links_not_found(async_client: AsyncClient):
    resp = await async_client.get("/links/expired")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "No expired links found"


@pytest.mark.asyncio
async def test_get_expired_links_found(async_client, test_db):
    from app.models import LinkHistory
    from datetime import datetime, timedelta

    expired_link = LinkHistory(
        short_code="expired1",
        original_url="https://expired.com",
        expires_at=datetime.utcnow() - timedelta(days=1),
        click_count=10,
        created_at=datetime.utcnow(),
        user_id=dummy_user.id,
    )
    test_db.add(expired_link)
    await test_db.commit()

    resp = await async_client.get("/links/expired")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert any(link["short_code"] == "expired1" for link in data)
