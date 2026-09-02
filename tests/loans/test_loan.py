import pytest
from fastapi.testclient import TestClient
from src.main import app
from src.models import User
from src.books.models import Book
from fastapi_users.password import PasswordHelper
from sqlalchemy import insert, select
from conftest import make_loan
from datetime import datetime, timedelta

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

    book_data = [
        {"id": 1, "title": "The Great Gatsby", "author": "F. Scott Fitzgerald", "description": "A novel about the American dream and the disillusionment of the Roaring Twenties.", "genre": "fiction", "cover_image_path": "https://upload.wikimedia.org/wikipedia/commons/7/7a/The_Great_Gatsby_Cover_1925_Retouched.jpg", "total_copies": 10, "available_copies": 10, "isbn": "9780547249909"},
        {"id": 2, "title": "The Catcher in the Rye", "author": "J.D. Salinger", "description": "A coming-of-age novel about the struggle of an 18-year-old teenager with identity and alienation.", "genre": "fiction", "cover_image_path": "https://upload.wikimedia.org/wikipedia/commons/8/89/The_Catcher_in_the_Rye_%281951%2C_first_edition_cover%29.jpg", "total_copies": 10, "available_copies": 10, "isbn": "9780557249900"},
        {"id": 3, "title": "Animal Farm", "author": "George Orwell", "description": "A dystopian novel about a group of farm animals who rebel against their human owner and establish a society based on animal rights.", "genre": "fiction", "cover_image_path": "https://upload.wikimedia.org/wikipedia/commons/f/fb/Animal_Farm_-_1st_edition.jpg", "total_copies": 10, "available_copies": 10, "isbn": "9780547229900"},
        {"id": 4, "title": "The Lord of the Rings", "author": "J.R.R. Tolkien", "description": "A epic fantasy novel about a hobbit named Frodo Baggins and his quest to destroy the One Ring and save Middle-earth from the Dark Lord Sauron.", "genre": "fiction", "cover_image_path": "https://upload.wikimedia.org/wikipedia/en/e/e9/First_Single_Volume_Edition_of_The_Lord_of_the_Rings.gif", "total_copies": 10, "available_copies": 10, "isbn": "9780547249910"},
        {"id": 5, "title": "The Hobbit", "author": "J.R.R. Tolkien", "description": "A children\'s fantasy novel about a hobbit named Frodo Baggins and his quest to destroy the One Ring and save Middle-earth from the Dark Lord Sauron.", "genre": "fiction", "cover_image_path": "https://upload.wikimedia.org/wikipedia/en/4/4a/TheHobbit_FirstEdition.jpg", "total_copies": 10, "available_copies": 10, "isbn": "9780547242900"},
        {"id": 6, "title": "A Game of Thrones", "author": "George R. R. Martin", "description": "A fantasy epic series about a fictionalized version of the reign of King Robert Baratheon of the Seven Kingdoms of Westeros, and the struggles of his children to become the rightful king.", "genre": "fiction", "cover_image_path": "https://upload.wikimedia.org/wikipedia/en/9/93/AGameOfThrones.jpg", "total_copies": 10, "available_copies": 10, "isbn": "9782547249900"},
        {"id": 7, "title": "Harry Potter and the Philosopher's Stone", "author": "J.K. Rowling", "description": "A fantasy novel about a boy named Harry Potter and his journey to become a wizard.", "genre": "fiction", "cover_image_path": "https://upload.wikimedia.org/wikipedia/en/6/6b/Harry_Potter_and_the_Philosopher%27s_Stone_Book_Cover.jpg", "total_copies": 10, "available_copies": 10, "isbn": "9781347249900"},
        {"id": 8, "title": "War and Peace", "author": "Leo Tolstoy", "description": "A classic novel about the Russian Revolution and the rise of the Romanov dynasty.", "genre": "fiction", "cover_image_path": "https://upload.wikimedia.org/wikipedia/commons/a/af/Tolstoy_-_War_and_Peace_-_first_edition%2C_1869.jpg", "total_copies": 10, "available_copies": 10, "isbn": "9780547231900"},
        {"id": 9, "title": "Pride and Prejudice", "author": "Jane Austen", "description": "A classic novel about the society of 19th-century England and its characters, particularly Elizabeth Bennet and her sisters.", "genre": "fiction", "cover_image_path": "https://upload.wikimedia.org/wikipedia/commons/1/17/PrideAndPrejudiceTitlePage.jpg", "total_copies": 10, "available_copies": 10 , "isbn": "9740247249900"},
        {"id": 10, "title": "Little Women", "author": "Louisa May Alcott", "description": "A classic novel about four sisters and their experiences in the 19th century.", "genre": "fiction", "cover_image_path": "https://upload.wikimedia.org/wikipedia/commons/f/f9/Houghton_AC85.A%E2%84%93194L.1869_pt.2aa_-_Little_Women%2C_title.jpg", "total_copies": 10, "available_copies": 10, "isbn": "9720545249900"},
        {"id": 11, "title": "The Adventures of Huckleberry Finn", "author": "Mark Twain", "description": "A classic novel about a boy named Huckleberry Finn and his adventures in the American South during the 19th century.", "genre": "fiction", "cover_image_path": "https://upload.wikimedia.org/wikipedia/commons/6/61/Huckleberry_Finn_book.JPG", "total_copies": 10, "available_copies": 10, "isbn": "9780547009900"},
        {"id": 12, "title": "The Adventures of Tom Sawyer", "author": "Mark Twain", "description": "A classic novel about a boy named Tom Sawyer and his adventures in the American South during the 19th century.", "genre": "fiction", "cover_image_path": "https://upload.wikimedia.org/wikipedia/commons/1/1d/Tom_Sawyer_1876_frontispiece.jpg", "total_copies": 10, "available_copies": 10, "isbn": "9780547159900"},
        {"id": 13, "title": "Crime and Punishment", "author": "Fyodor Dostoevsky", "description": "A classic novel about a man named Raskolnikov and his struggles with the law in the 19th century.", "genre": "fiction", "cover_image_path": "https://upload.wikimedia.org/wikipedia/en/4/4b/Crimeandpunishmentcover.png", "total_copies": 10, "available_copies": 10, "isbn": "9780496159900"},
        {"id": 14, "title": "Moby Dick", "author": "Herman Melville", "description": "A classic novel about a whaling captain named Captain Ahab and his crew during the 18th century.", "genre": "fiction", "cover_image_path": "https://upload.wikimedia.org/wikipedia/commons/3/36/Moby-Dick_FE_title_page.jpg", "total_copies": 10, "available_copies": 10, "isbn": "9762547159900"},
        {"id": 15, "title": "The Adventures of Sherlock Holmes", "author": "Arthur Conan Doyle", "description": "A classic novel about a detective named Sherlock Holmes and his adventures in the 19th century.", "genre": "fiction", "cover_image_path": "https://upload.wikimedia.org/wikipedia/commons/b/b9/Adventures_of_sherlock_holmes.jpg", "total_copies": 10, "available_copies": 10, "isbn": "9780547169300"},
        {"id": 16, "title": "Kafka on the Shore", "author": "Haruki Murakami", "description": "A novel about a man named Kafka and his experiences in the 19th century.", "genre": "fiction", "cover_image_path": "https://upload.wikimedia.org/wikipedia/en/1/12/Kafkaontheshore.jpg", "total_copies": 10, "available_copies": 10, "isbn": "3780547169300"},
        {"id": 17, "title": "Ulysses", "author": "James Joyce", "description": "A classic novel about a man named Leopold Bloom and his struggles with the Biblical story of the same name.", "genre": "fiction", "cover_image_path": "https://upload.wikimedia.org/wikipedia/commons/a/ab/JoyceUlysses2.jpg", "total_copies": 10, "available_copies": 10, "isbn": "9780541569300"},
        {"id": 18, "title": "Madame Bovary", "author": "Gustave Flaubert", "description": "A classic novel about a woman named Madame Bovary and her struggles with the French Revolution.", "genre": "fiction", "cover_image_path": "https://upload.wikimedia.org/wikipedia/commons/9/9f/Madame_Bovary_1857_%28hi-res%29.jpg", "total_copies": 10, "available_copies": 10, "isbn": "9759547469300"},
        {"id": 19, "title": "The Scarlet Letter", "author": "Nathaniel Hawthorne", "description": "A classic novel about a man named Hester Prynne and her struggles with the adulterous relationship with her father.", "genre": "fiction", "cover_image_path": "https://upload.wikimedia.org/wikipedia/commons/8/85/The_Scarlet_Letter_title_page.jpg", "total_copies": 10, "available_copies": 10, "isbn": "9731547258200"},
        {"id": 20, "title": "Jane Eyre", "author": "Charlotte Bronte", "description": "A classic novel about a woman named Jane Eyre and her struggles with the societal expectations of the 19th century.", "genre": "fiction", "cover_image_path": "https://upload.wikimedia.org/wikipedia/commons/9/9b/Jane_Eyre_title_page.jpg", "total_copies": 10, "available_copies": 10, "isbn": "9295547248200"},
        {"id": 21, "title": "In Search of Lost Time", "author": "Marcel Proust", "description": "A classic novel about a man named Marcel Proust and his struggles with the meaning of life.", "genre": "fiction", "cover_image_path": "https://upload.wikimedia.org/wikipedia/commons/a/ab/Proust_1917.jpg", "total_copies": 10, "available_copies": 10, "isbn": "9780543942700"},
    ]

    for book in book_data:
        await db_session.execute(insert(Book).values(**book))

    await db_session.commit()

@pytest.mark.asyncio
async def test_loan_request_route(user_client):
    response = user_client.post(
        "/api/v1/loans/request/1",
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "pending"
    assert data["requested_at"] is not None
    assert data["due_date"] is None
    assert data["returned_at"] is None
    assert data["approved_at"] is None
    assert data["rejection_reason"] is None

@pytest.mark.asyncio
async def test_loan_request_route_invalid_book_id(user_client):
    response = user_client.post(
        "/api/v1/loans/request/0",
    )
    assert response.status_code == 404

@pytest.mark.asyncio
async def test_loan_request_route_already_requested(user_client):
    response = user_client.post(
        "/api/v1/loans/request/1", 
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "pending"
    assert data["requested_at"] is not None
    assert data["due_date"] is None
    assert data["returned_at"] is None
    assert data["approved_at"] is None
    assert data["rejection_reason"] is None

    response = user_client.post(
        "/api/v1/loans/request/1", 
    )
    assert response.status_code == 409

@pytest.mark.asyncio
async def test_loan_request_route_already_active(user_client, make_loan):
    active_loan = await make_loan(status="active")

    response = user_client.post(
        "/api/v1/loans/request/1", 
    )
    assert response.status_code == 409

@pytest.mark.asyncio
async def test_loan_return_route(client, user_client, make_loan):
    
    active_loan = await make_loan(status="active")

    response = user_client.put(
        f"/api/v1/loans/{active_loan.id}/return", 
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "returned"
    assert data["returned_at"] is not None

@pytest.mark.asyncio
async def test_loan_return_route_invalid_loan_id(user_client):
    response = user_client.put(
        f"/api/v1/loans/0/return", 
    )
    assert response.status_code == 404

@pytest.mark.asyncio
async def test_loan_return_route_not_active(user_client, make_loan):

    pending_loan = await make_loan(status="pending")

    response = user_client.put(
        f"/api/v1/loans/{pending_loan.id}/return",
    )
    assert response.status_code == 400

@pytest.mark.asyncio
async def test_loan_return_route_already_returned(user_client, make_loan):

    returned_loan = await make_loan(status="returned")

    response = user_client.put(
        f"/api/v1/loans/{returned_loan.id}/return",
    )
    assert response.status_code == 400

@pytest.mark.asyncio
async def test_loan_return_route_wrong_user(user_client, make_loan):
    other_users_loan = await make_loan(email="admin@example.com", status="active")

    response = user_client.put(
        f"/api/v1/loans/{other_users_loan.id}/return",
    )
    assert response.status_code == 403

@pytest.mark.asyncio
async def test_loan_list_admin_route_multiple(admin_client, make_loan):
    await make_loan(email="user@example.com", status="pending")
    await make_loan(email="user@example.com", status="active", book_id=2)

    response = admin_client.get(
        "/api/v1/loans/admin",
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data["data"]) == 2
    assert data["total"] == 2
    assert data["page"] == 1
    assert data["limit"] == 10

@pytest.mark.asyncio
async def test_loan_list_admin_route_pagination(admin_client, make_loan):
    # Seed 21 loans across all 21 books to force a second page at limit=20
    for book_id in range(1, 22):
        await make_loan(email="user@example.com", status="pending", book_id=book_id)

    # Page 1 — should return 20 items
    response = admin_client.get(
        "/api/v1/loans/admin?page=1&limit=20",
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data["data"]) == 20
    assert data["total"] == 21
    assert data["page"] == 1
    assert data["limit"] == 20

    # Page 2 — should return the remaining 1 item
    response = admin_client.get(
        "/api/v1/loans/admin?page=2&limit=20",
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data["data"]) == 1
    assert data["total"] == 21
    assert data["page"] == 2

    # Page 3 — should return empty
    response = admin_client.get(
        "/api/v1/loans/admin?page=3&limit=20",
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data["data"]) == 0
    assert data["total"] == 21

@pytest.mark.asyncio
async def test_loan_list_admin_not_admin(user_client, make_loan):
    response = user_client.get(
        "/api/v1/loans/admin",
    )
    assert response.status_code == 401

@pytest.mark.asyncio
async def test_loan_list_admin_route_pagination_limit( admin_client, make_loan):
    for book_id in range(1, 7): 
        await make_loan(email="user@example.com", status="pending", book_id=book_id)

    response = admin_client.get(
        "/api/v1/loans/admin?page=1&limit=5",
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data["data"]) == 5
    assert data["total"] == 6

    response = admin_client.get(
        "/api/v1/loans/admin?page=2&limit=5",
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data["data"]) == 1
    assert data["total"] == 6

@pytest.mark.asyncio
async def test_loan_list_admin_filter_by_status(admin_client, make_loan):
    await make_loan(status="pending", book_id=1)
    await make_loan(status="active", book_id=2)

    response = admin_client.get("/api/v1/loans/admin?status=pending", 
                         )
    data = response.json()
    assert data["total"] == 1
    assert data["data"][0]["status"] == "pending"


@pytest.mark.asyncio
async def test_loan_list_admin_filter_by_title(admin_client, make_loan):
    await make_loan(book_id=1)  # The Great Gatsby
    await make_loan(book_id=2)  # The Catcher in the Rye

    response = admin_client.get("/api/v1/loans/admin?title=gatsby", 
                          )
    data = response.json()
    assert data["total"] == 1
    assert data["data"][0]["book"]["title"] == "The Great Gatsby"


@pytest.mark.asyncio
async def test_loan_list_admin_filter_by_author(admin_client, make_loan):
    await make_loan(book_id=1)  # The Great Gatsby
    await make_loan(book_id=2)  # The Catcher in the Rye

    response = admin_client.get("/api/v1/loans/admin?author=Fitzgerald", 
                          )
    data = response.json()
    assert data["total"] == 1
    assert data["data"][0]["book"]["author"] == "F. Scott Fitzgerald"

@pytest.mark.asyncio
async def test_loan_list_admin_filter_by_isbn(admin_client, make_loan, db_session):
    await make_loan(book_id=1)
    await make_loan(book_id=2)

    response = admin_client.get("/api/v1/loans/admin?isbn=9780547249909", 
                          )
    data = response.json()
    assert data["total"] == 1
    assert data["data"][0]["book"]["isbn"] == "9780547249909"

    response = admin_client.get("/api/v1/loans/admin?isbn=9780557249900", 
                          )
    data = response.json()
    assert data["total"] == 1
    assert data["data"][0]["book"]["isbn"] == "9780557249900"

@pytest.mark.asyncio
async def test_loan_list_admin_filter_by_genre(admin_client, make_loan):
    await make_loan(book_id=1)  # The Great Gatsby
    await make_loan(book_id=2)  # The Catcher in the Rye

    response = admin_client.get("/api/v1/loans/admin?genre=fiction", 
                          )
    data = response.json()
    assert data["total"] == 2
    assert set(loan["book"]["title"] for loan in data["data"]) == {"The Great Gatsby", "The Catcher in the Rye"}

@pytest.mark.asyncio
async def test_loan_list_admin_filter_by_email(admin_client, make_loan):
    await make_loan(email="user@example.com", book_id=1)
    await make_loan(email="admin@example.com", book_id=2)

    response = admin_client.get("/api/v1/loans/admin?email=user", 
                          )
    data = response.json()
    assert data["total"] == 1
    assert data["data"][0]["borrower"]["email"] == "user@example.com"

@pytest.mark.asyncio
async def test_loan_list_admin_filter_combined( admin_client, make_loan):
    await make_loan(email="user@example.com", status="active", book_id=1)
    await make_loan(email="user@example.com", status="pending", book_id=2)
    await make_loan(email="admin@example.com", status="active", book_id=3)

    # Only user@example.com's active loan should match
    response = admin_client.get(
        "/api/v1/loans/admin?status=active&email=user",
    )
    data = response.json()
    assert data["total"] == 1

@pytest.mark.asyncio
async def test_loan_list_admin_filter_multi_status( admin_client, make_loan):
    await make_loan(status="active", book_id=1)
    await make_loan(status="pending", book_id=2)
    await make_loan(status="returned", book_id=3)

    response = admin_client.get(
        "/api/v1/loans/admin?status=active,pending",
    )
    data = response.json()
    assert data["total"] == 2

@pytest.mark.asyncio
async def test_loan_list_admin_filter_no_results(admin_client, make_loan):
    await make_loan(book_id=1)

    response = admin_client.get(
        "/api/v1/loans/admin?title=doesnotexist",
    )
    data = response.json()
    assert data["total"] == 0
    assert data["data"] == []

@pytest.mark.asyncio
async def test_loan_list_admin_filter_by_id_invalid( admin_client, make_loan):
    await make_loan(book_id=1)

    response = admin_client.get(
        "/api/v1/loans/admin?id=0",
    )
    data = response.json()
    assert data["total"] == 0
    assert data["data"] == []

@pytest.mark.asyncio
async def test_loan_list_user(user_client, make_loan):
    await make_loan(email="user@example.com", status="pending")
    await make_loan(email="user@example.com", status="active", book_id=2)

    response = user_client.get(
        "/api/v1/loans",
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data["data"]) == 2
    assert data["total"] == 2
    assert data["page"] == 1
    assert data["limit"] == 20

@pytest.mark.asyncio
async def test_loan_list_user_pagination(user_client, make_loan):
    # Seed 21 loans across all 21 books to force a second page at limit=20
    for book_id in range(1, 22):
        await make_loan(email="user@example.com", status="pending", book_id=book_id)

    # Page 1 — should return 20 items
    response = user_client.get(
        "/api/v1/loans?page=1&limit=20",
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data["data"]) == 20
    assert data["total"] == 21
    assert data["page"] == 1
    assert data["limit"] == 20

    # Page 2 — should return the remaining 1 item
    response = user_client.get(
        "/api/v1/loans?page=2&limit=20",
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data["data"]) == 1
    assert data["total"] == 21
    assert data["page"] == 2

    # Page 3 — should return empty
    response = user_client.get(
        "/api/v1/loans?page=3&limit=20",
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data["data"]) == 0
    assert data["total"] == 21

@pytest.mark.asyncio
async def test_loan_list_user_no_token(client):
    response = client.get(
        "/api/v1/loans",
    )
    assert response.status_code == 401

@pytest.mark.asyncio
async def test_loan_list_user_limit(user_client, make_loan):
    for book_id in range(1, 7): 
        await make_loan(email="user@example.com", status="pending", book_id=book_id)

    response = user_client.get(
        "/api/v1/loans?page=1&limit=5",
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data["data"]) == 5
    assert data["total"] == 6

    response = user_client.get(
        "/api/v1/loans?page=2&limit=5",
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data["data"]) == 1
    assert data["total"] == 6

@pytest.mark.asyncio
async def test_loan_list_user_filter_by_status(user_client, make_loan):
    await make_loan(status="pending", book_id=1)
    await make_loan(status="active", book_id=2)

    response = user_client.get("/api/v1/loans?status=pending", 
                          )
    data = response.json()
    assert data["total"] == 1
    assert data["data"][0]["status"] == "pending"


@pytest.mark.asyncio
async def test_loan_list_user_filter_by_title(user_client, make_loan):
    await make_loan(book_id=1)  # The Great Gatsby
    await make_loan(book_id=2)  # The Catcher in the Rye

    response = user_client.get("/api/v1/loans?title=gatsby", 
                          )
                          
    data = response.json()
    assert data["total"] == 1
    assert data["data"][0]["book"]["title"] == "The Great Gatsby"

@pytest.mark.asyncio
async def test_loan_list_user_filter_by_author(user_client, make_loan):
    await make_loan(book_id=1)  # The Great Gatsby
    await make_loan(book_id=2)  # The Catcher in the Rye

    response = user_client.get("/api/v1/loans?author=Fitzgerald", 
                          )
    data = response.json()
    assert data["total"] == 1
    assert data["data"][0]["book"]["author"] == "F. Scott Fitzgerald"

@pytest.mark.asyncio
async def test_loan_list_user_filter_by_isbn(user_client, make_loan, db_session):
    await make_loan(book_id=1)
    await make_loan(book_id=2)

    response = user_client.get(
        "/api/v1/loans?isbn=9780547249909",
    )
    data = response.json()
    print(f"Response: {data}")
    assert data["total"] == 1
    assert set(loan["book"]["isbn"] for loan in data["data"]) == {"9780547249909"}

@pytest.mark.asyncio
async def test_loan_list_user_filter_by_genre(user_client, make_loan):
    await make_loan(book_id=1)  # The Great Gatsby
    await make_loan(book_id=2)  # The Catcher in the Rye

    response = user_client.get("/api/v1/loans?genre=fiction", 
                          )
    data = response.json()
    assert data["total"] == 2
    assert set(loan["book"]["title"] for loan in data["data"]) == {"The Great Gatsby", "The Catcher in the Rye"}

@pytest.mark.asyncio
async def test_loan_list_user_empty(user_client, make_loan):
    response = user_client.get(
        "/api/v1/loans",
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data["data"]) == 0
    assert data["total"] == 0
    assert data["page"] == 1
    assert data["limit"] == 20

@pytest.mark.asyncio
async def test_loan_list_filter_combined(user_client, make_loan):
    await make_loan(email="user@example.com", status="active", book_id=1)
    await make_loan(email="user@example.com", status="pending", book_id=2)

    response = user_client.get(
        "/api/v1/loans?status=active&title=gatsby",
    )
    data = response.json()
    assert data["total"] == 1
    assert data["data"][0]["status"] == "active"

@pytest.mark.asyncio
async def test_loan_list_user_only_sees_own_loans(user_client, make_loan, db_session):
    from sqlalchemy import select as sa_select

    result = await db_session.execute(
        sa_select(User).where(User.email == "user@example.com")  # type: ignore[arg-type]
    )
    user = result.scalars().first()

    await make_loan(email="user@example.com", book_id=1)
    await make_loan(email="admin@example.com", book_id=2)

    response = user_client.get(
        "/api/v1/loans",
    )
    data = response.json()
    assert data["total"] == 1
    assert len(data["data"]) == 1
    assert data["data"][0]["borrower"]["email"] == "user@example.com"

@pytest.mark.asyncio
async def test_loan_update_route(admin_client, make_loan):
    loan = await make_loan(status="pending")

    response = admin_client.put(
        f"/api/v1/loans/{loan.id}",
        json={"status": "active", "approved_at": datetime.now().isoformat(), 
              "due_date": (datetime.now() + timedelta(days=14)).isoformat()}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "active"
    assert data["returned_at"] is None
    assert data["approved_at"] is not None
    assert data["rejection_reason"] is None

@pytest.mark.asyncio
async def test_loan_update_route_invalid_loan_id(admin_client):
    response = admin_client.put(
        f"/api/v1/loans/0",
        json={"status": "active", "approved_at": datetime.now().isoformat(), 
              "due_date": (datetime.now() + timedelta(days=14)).isoformat()}
    )
    assert response.status_code == 404

@pytest.mark.asyncio
async def test_loan_update_route_not_admin(user_client, make_loan):
    loan = await make_loan(status="pending")

    response = user_client.put(
        f"/api/v1/loans/{loan.id}",
        json={"status": "active"}
    )
    assert response.status_code == 401

@pytest.mark.asyncio
async def test_loan_update_no_token(client):
    response = client.put(
        f"/api/v1/loans/1",
        json={"status": "active"}
    )
    assert response.status_code == 401

@pytest.mark.asyncio
async def test_loan_update_rejected_loan(admin_client, make_loan):
    loan = await make_loan(status="pending")

    response = admin_client.put(
        f"/api/v1/loans/{loan.id}",
        json={"status": "rejected", "rejected_at": datetime.now().isoformat(), "rejection_reason": "test"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "rejected"
    assert data["returned_at"] is None
    assert data["approved_at"] is None
    assert data["rejected_at"] is not None
    assert data["rejection_reason"] is not None

@pytest.mark.asyncio
async def test_loan_approve_no_copies_available(admin_client, make_loan, db_session):
    from sqlalchemy import select as sa_select
    from src.books.models import Book

    # Seed a pending loan on book 1
    loan = await make_loan(email="user@example.com", status="pending", book_id=1)

    # Set book 1's available copies to 0
    result = await db_session.execute(sa_select(Book).where(Book.id == 1))
    book = result.scalars().first()
    book.total_copies = 0
    book.available_copies = 0
    await db_session.commit()

    # Try to approve — should fail with no copies available
    response = admin_client.put(
        f"/api/v1/loans/{loan.id}",
        json={
            "status": "active",
            "due_date": (datetime.now() + timedelta(days=14)).isoformat(),
            "approved_at": datetime.now().isoformat(),
        },
    )
    assert response.status_code == 422  

@pytest.mark.asyncio
async def test_loan_approve_due_date_before_requested_at(admin_client, make_loan):
    loan = await make_loan(email="user@example.com", status="pending", book_id=1)

    # due_date in the past, before requested_at
    due_date = (datetime.now() - timedelta(days=10)).isoformat()
    response = admin_client.put(
        f"/api/v1/loans/{loan.id}",
        json={"status": "active", "due_date": due_date, "approved_at": datetime.now().isoformat()},
    )
    assert response.status_code == 422

@pytest.mark.asyncio
async def test_loan_approve_decrements_available_copies(admin_client, make_loan, db_session):
    from sqlalchemy import select as sa_select
    from src.books.models import Book

    loan = await make_loan(email="user@example.com", status="pending", book_id=1)

    # Confirm starting copy count
    result = await db_session.execute(sa_select(Book).where(Book.id == 1))
    book = result.scalars().first()
    copies_before = book.available_copies

    due_date = (datetime.now() + timedelta(days=14)).isoformat()
    response = admin_client.put(
        f"/api/v1/loans/{loan.id}",
        json={"status": "active", "due_date": due_date, "approved_at": datetime.now().isoformat()},
    )
    assert response.status_code == 200

    # Refresh book from DB and confirm copy count decreased
    await db_session.refresh(book)
    assert book.available_copies == copies_before - 1

@pytest.mark.asyncio
async def test_loan_returned_before_requested_at(admin_client, make_loan):
    loan = await make_loan(email="user@example.com", status="pending", book_id=1)

    # returned_at in the past, before requested_at
    returned_at = (datetime.now() - timedelta(days=10)).isoformat()
    response = admin_client.put(
        f"/api/v1/loans/{loan.id}",
        json={"status": "returned", "returned_at": returned_at},
    )
    assert response.status_code == 422

@pytest.mark.asyncio
async def test_loan_no_update(admin_client, make_loan):
    loan = await make_loan(email="user@example.com", status="pending", book_id=1)

    response = admin_client.put(
        f"/api/v1/loans/{loan.id}",
        json={"status": "active"},
    )
    assert response.status_code == 422

@pytest.mark.asyncio
async def test_loan_update_approved_before_requested_at(admin_client, make_loan):
    loan = await make_loan(email="user@example.com", status="pending", book_id=1)

    # approved_at in the past, before requested_at
    approved_at = (datetime.now() - timedelta(days=10)).isoformat()
    response = admin_client.put(
        f"/api/v1/loans/{loan.id}",
        json={"status": "active", "approved_at": approved_at},
    )
    assert response.status_code == 422

@pytest.mark.asyncio
async def test_loan_update_already_returned(admin_client, make_loan):
    loan = await make_loan(email="user@example.com", status="returned", book_id=1)

    response = admin_client.put(
        f"/api/v1/loans/{loan.id}",
        json={"status": "active", "approved_at": datetime.now().isoformat(), 
              "due_date": (datetime.now() + timedelta(days=14)).isoformat()},
    )
    assert response.status_code == 422

@pytest.mark.asyncio
async def test_loan_update_missing_due_date_and_approved_at(admin_client, make_loan):
    loan = await make_loan(email="user@example.com", status="pending", book_id=1)

    response = admin_client.put(
        f"/api/v1/loans/{loan.id}",
        json={"status": "active"},
    )   

    assert response.status_code == 422

@pytest.mark.asyncio
async def test_loan_update_already_rejected(admin_client, make_loan):
    loan = await make_loan(email="user@example.com", status="rejected", book_id=1)

    response = admin_client.put(
        f"/api/v1/loans/{loan.id}",
        json={"status": "active"},
    )
    assert response.status_code == 422

@pytest.mark.asyncio
async def test_loan_detail(admin_client, make_loan):
    loan = await make_loan(email="user@example.com", status="pending", book_id=1)

    response = admin_client.get(
        f"/api/v1/loans/{loan.id}/detail",
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "pending"
    assert data["requested_at"] is not None
    assert data["due_date"] is None
    assert data["returned_at"] is None
    assert data["approved_at"] is None
    assert data["rejection_reason"] is None

@pytest.mark.asyncio
async def test_loan_detail_not_found(admin_client):
    response = admin_client.get(
        f"/api/v1/loans/0/detail",
    )
    assert response.status_code == 404

@pytest.mark.asyncio
async def test_loan_detail_wrong_user( user_client, make_loan):

    # Make a loan for admin@example.com
    loan = await make_loan(email="admin@example.com", status="pending", book_id=1)

    # Try to access it as user@example.com
    response = user_client.get(
        f"/api/v1/loans/{loan.id}/detail",
    )

    # Should return 403
    assert response.status_code == 403

@pytest.mark.asyncio
async def test_loan_detail_admin(admin_client, make_loan):

    # Make a loan for user@example.com
    loan = await make_loan(email="user@example.com", status="pending", book_id=1)

    # Try to access it as admin@example.com
    response = admin_client.get(
        f"/api/v1/loans/{loan.id}/detail",
    )

    # Should return 200
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "pending"
    assert data["requested_at"] is not None
    assert data["due_date"] is None
    assert data["returned_at"] is None
    assert data["approved_at"] is None
    assert data["rejection_reason"] is None

@pytest.mark.asyncio
async def test_loan_detail_no_token(client):
    response = client.get(
        f"/api/v1/loans/1/detail",
    )
    assert response.status_code == 401