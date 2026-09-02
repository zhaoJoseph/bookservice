import pytest
from fastapi.testclient import TestClient
from sqlalchemy import insert
from src.main import app
from src.models import User
from fastapi_users.password import PasswordHelper
from src.models import get_user_manager, User, UserManager, get_user_db
from src.database import get_db
from sqlalchemy import select

from typing import Optional

from fastapi import Request

password_helper = PasswordHelper()

@pytest.fixture
async def user_manager(db_session): 
    user_db_gen = get_user_db(db_session)
    user_db = await anext(user_db_gen)

    class TestUserManager(UserManager):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.captured_token: Optional[str] = None

        async def on_after_request_verify(self, user: User, token: str, request: Optional[Request] = None):
            self.captured_token = token

    manager = TestUserManager(user_db, password_helper)
    yield manager
    await user_db_gen.aclose()

@pytest.fixture
def client(db_session, user_manager):
    def override_get_db():
        yield db_session

    async def override_get_user_manager(): 
        yield user_manager

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_user_manager] = override_get_user_manager

    with TestClient(app) as c:
        yield c

    app.dependency_overrides.clear()

@pytest.fixture(autouse=True)
async def seed_test_data(db_session):
    """
    Seeds the database with required users before each test.
    Runs automatically because of autouse=True.
    """
    hashed = password_helper.hash("password")

    users_data = [
        {"name": "admin", "email": "admin@example.com", "hashed_password": hashed, "role": "admin", "status": "active", "is_active": True},
        {"name": "user", "email": "user@example.com", "hashed_password": hashed, "role": "user", "status": "active", "is_active": True},
        {"name": "suspendeduser", "email": "suspended@example.com", "hashed_password": hashed, "role": "user", "status": "suspended", "is_active": False},
        {"name": "inactiveuser", "email": "inactive@example.com", "hashed_password": hashed, "role": "user", "status": "inactive", "is_active": False},
    ]

    for user in users_data:
        await db_session.execute(insert(User).values(**user))

    await db_session.commit()


@pytest.mark.asyncio
async def test_login_route(client):
    response = client.post("/api/v1/auth/token", data={"username": "admin@example.com", "password": "password"})
    assert response.status_code == 200
    data = response.json()
    assert "accessToken" in data
    assert data["tokenType"] == "bearer"


@pytest.mark.asyncio
async def test_login_route_invalid_password(client):
    response = client.post("/api/v1/auth/token", data={"username": "admin@example.com", "password": "wrongpassword"})
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_login_route_invalid_username(client):
    response = client.post("/api/v1/auth/token", data={"username": "wrongusername@example.com", "password": "password"})
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_login_route_suspended_user(client):
    response = client.post("/api/v1/auth/token", data={"username": "suspended@example.com", "password": "password"})
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_login_route_inactive_user(client):
    response = client.post("/api/v1/auth/token", data={"username": "inactive@example.com", "password": "password"})
    assert response.status_code == 401

@pytest.mark.asyncio
async def test_register_route_invalid_password(client):
    response = client.post("/api/v1/auth/register", data={"email": "admin@example.com", "password": "wrongpassword", 
                                                       "confirm_password": "wrongpassword", "name": "admin", "genres": [1,2,3,4,5]})
    assert response.status_code == 422

@pytest.mark.asyncio
async def test_register_route(client):
    response = client.post("/api/v1/auth/register", data={"name": "testuser", "email": "test@test.com",
                                                          "password": "Qwertyuiop123@", 
                                                          "confirm_password": "Qwertyuiop123@", "genres": [1,2,3,4,5]})
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "testuser"
    assert data["email"] == "test@test.com"
    assert data["is_verified"] is False

@pytest.mark.asyncio
async def test_register_route_invalid_username(client):
    response = client.post("/api/v1/auth/register", data={"name": "**@#*(@#)", "email": "test@test.com",
                                                          "password": "Qwertyuiop123@", 
                                                          "confirm_password": "Qwertyuiop123@", "genres": [1,2,3,4,5]})
    assert response.status_code == 422

@pytest.mark.asyncio
async def test_register_route_invalid_email(client):
    response = client.post("/api/v1/auth/register", data={"name": "testuser", "email": "testtest.com",
                                                          "password": "Qwertyuiop123@", 
                                                          "confirm_password": "Qwertyuiop123@", "genres": [1,2,3,4,5]})
    assert response.status_code == 422

@pytest.mark.asyncio
async def test_register_route_empty_body(client):
    response = client.post("/api/v1/auth/register", data={})
    assert response.status_code == 422

@pytest.mark.asyncio
async def test_register_route_invalid_confirm_password(client):
    response = client.post("/api/v1/auth/register", data={"name": "testuser", "email": "test@test.com",
                                                          "password": "Qwertyuiop123@", 
                                                          "confirm_password": "Quiop123@", "genres": [1,2,3,4,5]})
    assert response.status_code == 422

@pytest.mark.asyncio
async def test_register_route_already_exists(client):
    response = client.post("/api/v1/auth/register", data={"name": "testuser", "email": "test@test.com",
                                                          "password": "Qwertyuiop123@", 
                                                          "confirm_password": "Qwertyuiop123@", "genres": [1,2,3,4,5]})
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "testuser"
    assert data["email"] == "test@test.com"
    assert data["is_verified"] is False

    response = client.post("/api/v1/auth/register", data={"name": "testuser", "email": "test@test.com",
                                                          "password": "Qwertyuiop123@", 
                                                          "confirm_password": "Qwertyuiop123@", "genres": [1,2,3,4,5]})
    assert response.status_code == 409

@pytest.mark.asyncio
async def test_verify_user_route(client, user_manager):
    response = client.post("/api/v1/auth/register", data={"name": "testuser", "email": "test@test.com",
                                                          "password": "Qwertyuiop123@", 
                                                          "confirm_password": "Qwertyuiop123@", "genres": [1,2,3,4,5]})
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "testuser"
    assert data["email"] == "test@test.com"
    assert data["is_verified"] is False

    response = client.post("/api/v1/auth/request-verify-token", data={"email": "test@test.com"})
    assert response.status_code == 202 

    assert user_manager.captured_token is not None

    response = client.get(f"/api/v1/auth/verify?token={user_manager.captured_token}")
    assert response.status_code == 200
    data = response.json()
    assert data["is_verified"] is True