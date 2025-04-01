import pytest
import jwt
from httpx import AsyncClient
from unittest.mock import AsyncMock, MagicMock
from datetime import timedelta, datetime
from app.models import User
from auth import (
    get_password_hash,
    register_user,
    login_for_access_token,
    verify_password,
    create_access_token,
    get_user,
    authenticate_user,
    get_current_user,
    get_current_user_optional,
    SECRET_KEY,
    UserCreate
)
from fastapi import HTTPException
from fastapi.security import OAuth2PasswordRequestForm


@pytest.mark.asyncio
async def test_register_user(mocker):
    """Тест успешной регистрации пользователя"""

    mock_db = AsyncMock()

    mock_result = MagicMock()
    mock_result.scalars.return_value.first.return_value = None
    mock_db.execute.return_value = mock_result

    mock_db.commit = AsyncMock()
    mock_db.refresh = AsyncMock()

    user_data = UserCreate(email="newuser@test.com", password="password123")
    response = await register_user(user_data, mock_db)

    assert response["msg"] == "User successfully registered"
    assert response["email"] == "newuser@test.com"

    mock_result.scalars.return_value.first.return_value = User(email="newuser@test.com")

    with pytest.raises(HTTPException) as exc_info:
        await register_user(user_data, mock_db)

    assert exc_info.value.status_code == 400
    assert "Email already registered" in str(exc_info.value.detail)


@pytest.mark.asyncio
async def test_login_invalid_credentials(mocker):
    mock_db = AsyncMock()

    mocker.patch("auth.authenticate_user", return_value=None)

    form_data = OAuth2PasswordRequestForm(
        username="user@test.com", password="wrongpassword"
    )

    with pytest.raises(HTTPException) as exc_info:
        await login_for_access_token(form_data, mock_db)
    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_login_valid_credentials(mocker):
    mock_db = AsyncMock()
    mock_user = User(
        email="user@test.com", hashed_password=get_password_hash("password")
    )
    mocker.patch("auth.authenticate_user", return_value=mock_user)
    mocker.patch("auth.create_access_token", return_value="mock_access_token")

    form_data = OAuth2PasswordRequestForm(username="user@test.com", password="password")

    response = await login_for_access_token(form_data, mock_db)
    assert response["access_token"] == "mock_access_token"
    assert response["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_get_current_user_valid_token(mocker):
    mock_db = AsyncMock()
    mock_user = User(email="user@example.com", hashed_password="hashedpassword")

    mocker.patch("auth.jwt.decode", return_value={"sub": "user@example.com"})
    mocker.patch("auth.get_user", return_value=mock_user)

    user = await get_current_user("valid_token", mock_db)

    assert user is not None
    assert user.email == "user@example.com"


@pytest.mark.asyncio
async def test_get_current_user_expired_token(mocker):
    mock_db = AsyncMock()

    mocker.patch("auth.jwt.decode", side_effect=jwt.ExpiredSignatureError)

    with pytest.raises(HTTPException) as exc_info:
        await get_current_user("expired_token", mock_db)
    assert exc_info.value.status_code == 401
    assert "Token has expired" in str(exc_info.value.detail)


@pytest.mark.asyncio
async def test_get_current_user_invalid_token(mocker):
    mock_db = AsyncMock()

    mocker.patch("auth.jwt.decode", side_effect=jwt.PyJWTError)

    with pytest.raises(HTTPException) as exc_info:
        await get_current_user("invalid_token", mock_db)
    assert exc_info.value.status_code == 401
    assert "Could not validate credentials" in str(exc_info.value.detail)


@pytest.mark.asyncio
async def test_get_current_user_user_not_found(mocker):
    mock_db = AsyncMock()

    mocker.patch("auth.jwt.decode", return_value={"sub": "user@example.com"})
    mocker.patch("auth.get_user", return_value=None)

    with pytest.raises(HTTPException) as exc_info:
        await get_current_user("valid_token", mock_db)
    assert exc_info.value.status_code == 401
    assert "Could not validate credentials" in str(exc_info.value.detail)


@pytest.mark.asyncio
async def test_get_current_user_optional_no_token(mocker):
    mock_db = AsyncMock()
    user = await get_current_user_optional(None, mock_db)

    assert user is None


@pytest.mark.asyncio
async def test_get_current_user_optional_valid_token(mocker):
    mock_db = AsyncMock()
    mock_user = User(email="user@example.com", hashed_password="hashedpassword")

    mocker.patch("auth.jwt.decode", return_value={"sub": "user@example.com"})
    mocker.patch("auth.get_user", return_value=mock_user)

    user = await get_current_user_optional("valid_token", mock_db)

    assert user is not None
    assert user.email == "user@example.com"


@pytest.mark.asyncio
async def test_get_current_user_optional_invalid_token(mocker):
    mock_db = AsyncMock()

    mocker.patch("auth.jwt.decode", side_effect=jwt.PyJWTError)

    user = await get_current_user_optional("invalid_token", mock_db)

    assert user is None


@pytest.mark.asyncio
async def test_authenticate_user_invalid_password(mocker):
    mock_db = AsyncMock()
    mock_user = User(
        email="test@test.com", hashed_password=get_password_hash("correct_password")
    )
    mocker.patch("auth.get_user", return_value=mock_user)
    mocker.patch("auth.verify_password", return_value=False)
    user = await authenticate_user(mock_db, "test@test.com", "wrong_password")
    assert user is None
