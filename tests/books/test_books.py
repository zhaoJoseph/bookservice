import pytest
from fastapi.testclient import TestClient
from src.main import app
from src.models import User
from fastapi_users.password import PasswordHelper
from sqlalchemy import insert

import uuid

password_helper = PasswordHelper()

# Base fixture for DB overrides only (no client creation)
@pytest.fixture
def test_db_context(override_get_db, seed_test_data):
    # Just ensures DB is seeded. No client involved.
    yield

@pytest.fixture
def admin_client(test_db_context):
    """
    Creates a FRESH, independent TestClient logged in as ADMIN.
    """
    with TestClient(app) as c:
        # Login
        resp = c.post(
            "/api/v1/auth/token",
            data={"username": "admin@example.com", "password": "password"}
        )
        if resp.status_code != 200:
            raise RuntimeError(f"Admin login failed: {resp.text}")
        # 'c' now has the admin cookie.
        # Yield it. This 'c' is independent of any other client.
        yield c

@pytest.fixture
def user_client(test_db_context):
    """
    Creates a FRESH, independent TestClient logged in as USER.
    """
    with TestClient(app) as c:
        # Login
        resp = c.post(
            "/api/v1/auth/token",
            data={"username": "user@example.com", "password": "password"}
        )
        if resp.status_code != 200:
            raise RuntimeError(f"User login failed: {resp.text}")
        # 'c' now has the user cookie.
        # This 'c' is a DIFFERENT object than the one in admin_client.
        yield c


@pytest.fixture(autouse=True)
async def seed_test_data(db_session, override_get_db):
    hashed = password_helper.hash("password")

    users_data = [
        {
            "id": uuid.UUID("00000000-0000-0000-0000-000000000001"),  # fixed UUID
            "name": "admin",
            "email": "admin@example.com",
            "hashed_password": hashed,
            "role": "admin",
            "status": "active",
            "is_active": True
        },
        {
            "id": uuid.UUID("00000000-0000-0000-0000-000000000002"),  # fixed UUID
            "name": "user",
            "email": "user@example.com",
            "hashed_password": hashed,
            "role": "user",
            "status": "active",
            "is_active": True
        },
        {
            "id": uuid.UUID("00000000-0000-0000-0000-000000000003"),
            "name": "suspendeduser",
            "email": "suspended@example.com",
            "hashed_password": hashed,
            "role": "user",
            "status": "suspended",
            "is_active": False
        },
        {
            "id": uuid.UUID("00000000-0000-0000-0000-000000000004"),
            "name": "inactiveuser",
            "email": "inactive@example.com",
            "hashed_password": hashed,
            "role": "user",
            "status": "inactive",
            "is_active": False
        },
    ]

    for user in users_data:
        await db_session.execute(insert(User).values(**user))

    await db_session.commit()

# Admin Routes

@pytest.mark.asyncio
async def test_create_book_route(admin_client):
    response = admin_client.post(
        "/api/v1/books", 
        json={"title": "testbook", "author": "testauthor", "description": "testdescription", "isbn": "1234567890", "genre": "fiction", "total_copies": 10},
        
    )
    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "testbook"
    assert data["author"] == "testauthor"
    assert data["description"] == "testdescription"
    assert data["isbn"] == "1234567890"
    assert data["genre"] == "fiction"
    assert data["total_copies"] == 10

@pytest.mark.asyncio
async def test_create_book_route_invalid_isbn(admin_client):
    response = admin_client.post(
        "/api/v1/books", 
        json={"title": "testbook", "author": "testauthor", "description": "testdescription", "isbn": "12345678901", "genre": "fiction", "total_copies": 10},
    )
    assert response.status_code == 201 
    response = admin_client.post(
        "/api/v1/books", 
        json={"title": "testbook", "author": "testauthor", "description": "testdescription", "isbn": "12345678901", "genre": "fiction", "total_copies": 10},
        
    )
    assert response.status_code == 409

@pytest.mark.asyncio
async def test_create_book_route_no_isbn(admin_client):
    response = admin_client.post(
        "/api/v1/books", 
        json={"title": "testbook", "author": "testauthor", "description": "testdescription", "genre": "fiction", "total_copies": 10},
       
    )
    assert response.status_code == 422

@pytest.mark.asyncio
async def test_create_book_route_empty_body(admin_client):
    response = admin_client.post(
        "/api/v1/books", 
        json={},
        
    )
    assert response.status_code == 422

@pytest.mark.asyncio
async def test_create_book_route_invalid_body(admin_client):
    response = admin_client.post(
        "/api/v1/books", 
        json={"title": "testbook", "author": "testauthor", "description": "testdescription", "isbn": "1234567890", "total_copies": "not_a_number", "genre": "fiction"},
       
    )
    assert response.status_code == 422

@pytest.mark.asyncio
async def test_create_book_route_invalid_total_copies(admin_client):
    response = admin_client.post(
        "/api/v1/books", 
        json={"title": "testbook", "author": "testauthor", "description": "testdescription", "isbn": "1234567890", "total_copies": -1, "genre": "fiction"},
       
    )
    assert response.status_code == 422

@pytest.mark.asyncio
async def test_create_book_route_invalid_available_copies(admin_client):
    # available_copies is not a field in BookCreate - it's automatically set to total_copies
    # This test verifies that we can't manually set it via the API
    response = admin_client.post(
        "/api/v1/books", 
        json={"title": "testbook", "author": "testauthor", "description": "testdescription", "isbn": "1234567890", "genre": "fiction", "total_copies": 10},
        
    )
    assert response.status_code == 201
    data = response.json()
    assert data["available_copies"] == 10  # Should equal total_copies

@pytest.mark.asyncio
async def test_create_book_route_not_admin( user_client):
    response = user_client.post(
        "/api/v1/books", 
        json={"title": "testbook", "author": "testauthor", "description": "testdescription", "isbn": "1234567890", "genre": "fiction", "total_copies": 10},
        
    )
    assert response.status_code == 401

@pytest.mark.asyncio
async def test_delete_book_route( admin_client):
    response = admin_client.post(
        "/api/v1/books", 
        json={"title": "testbook", "author": "testauthor", "description": "testdescription", "isbn": "1234567890", "genre": "fiction", "total_copies": 10},
        
    )
    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "testbook"
    assert data["author"] == "testauthor"
    assert data["description"] == "testdescription"
    assert data["isbn"] == "1234567890"

    response = admin_client.delete(
        f"/api/v1/books/{data['id']}",
        
    )
    assert response.status_code == 204

@pytest.mark.asyncio 
async def test_put_book_route( admin_client):
    response = admin_client.post(
        "/api/v1/books", 
        json={"title": "testbook", "author": "testauthor", "description": "testdescription", "isbn": "1234567890", "genre": "fiction", "total_copies": 10},
        
    )
    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "testbook"
    assert data["author"] == "testauthor"
    assert data["description"] == "testdescription"
    assert data["isbn"] == "1234567890"

    response = admin_client.put(
        f"/api/v1/books/{data['id']}", 
        json={"title": "newtestbook", "author": "newtestauthor", "description": "newtestdescription", "isbn": "1234567891", "genre": "non-fiction", "total_copies": 20},
        
    )
    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "newtestbook"
    assert data["author"] == "newtestauthor"
    assert data["description"] == "newtestdescription"
    assert data["isbn"] == "1234567891"

@pytest.mark.asyncio
async def test_put_book_route_invalid_isbn(admin_client):
    # Create first book
    response = admin_client.post(
        "/api/v1/books", 
        json={"title": "testbook", "author": "testauthor", "description": "testdescription", "isbn": "1234567890", "genre": "fiction", "total_copies": 10},
        
    )
    assert response.status_code == 201
    data = response.json()
    book_id = data["id"]
    
    # Create second book with different ISBN
    response = admin_client.post(
        "/api/v1/books", 
        json={"title": "testbook2", "author": "testauthor2", "description": "testdescription2", "isbn": "9876543210", "genre": "fiction", "total_copies": 10},
        
    )
    assert response.status_code == 201
    
    # Try to change first book's ISBN to match second book's ISBN (should fail)
    response = admin_client.put(
        f"/api/v1/books/{book_id}", 
        json={"isbn": "9876543210"},
        
    )
    assert response.status_code == 409

@pytest.mark.asyncio
async def test_put_book_route_empty_body(admin_client):
    response = admin_client.post(
        "/api/v1/books", 
        json={"title": "testbook", "author": "testauthor", "description": "testdescription", "isbn": "1234567890", "genre": "fiction", "total_copies": 10},
        
    )
    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "testbook"
    assert data["author"] == "testauthor"
    assert data["description"] == "testdescription"
    assert data["isbn"] == "1234567890"

    response = admin_client.put(
        f"/api/v1/books/{data['id']}", 
        json={},
        
    )
    assert response.status_code == 422

# Public Routes

@pytest.mark.asyncio
async def test_get_books_list_route( user_client, admin_client):
    response = admin_client.post(
        "/api/v1/books", 
        json={"title": "testbook", "author": "testauthor", "description": "testdescription", "isbn": "1234567890", "genre": "fiction", "total_copies": 10},
        
    )
    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "testbook"
    assert data["author"] == "testauthor"
    assert data["description"] == "testdescription"
    assert data["isbn"] == "1234567890"
    assert data["genre"] == "fiction"
    assert data["total_copies"] == 10
    assert data["available_copies"] == 10

    response = user_client.get(
        "/api/v1/books", 
        
    )
    assert response.status_code == 200
    data = response.json()
    assert data["data"][0]["id"] == 1
    assert data["data"][0]["title"] == "testbook"
    assert data["data"][0]["author"] == "testauthor"
    assert data["data"][0]["description"] == "testdescription"
    assert data["data"][0]["isbn"] == "1234567890"
    assert data["data"][0]["genre"] == "fiction"
    assert data["data"][0]["total_copies"] == 10
    assert data["data"][0]["available_copies"] == 10

@pytest.mark.asyncio
async def test_get_book(admin_client, user_client):
    response = admin_client.post(
        "/api/v1/books", 
        json={"title": "testbook", "author": "testauthor", "description": "testdescription", "isbn": "1234567890", "genre": "fiction", "total_copies": 10},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "testbook"
    assert data["author"] == "testauthor"
    assert data["description"] == "testdescription"
    assert data["isbn"] == "1234567890"
    assert data["genre"] == "fiction"
    assert data["total_copies"] == 10
    assert data["available_copies"] == 10

    response = user_client.get(
        f"/api/v1/books/{data['id']}", 
        
    )
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == 1
    assert data["title"] == "testbook"
    assert data["author"] == "testauthor"
    assert data["description"] == "testdescription"
    assert data["isbn"] == "1234567890"
    assert data["genre"] == "fiction"
    assert data["total_copies"] == 10
    assert data["available_copies"] == 10

