from io import BytesIO
import fitz
from ..aws.client import s3_client
import asyncio
from ..auth.dependencies import get_jwt_strategy, get_user_manager
from ..database import get_db
from fastapi_users.db import SQLAlchemyUserDatabase
from ..models import User, UserManager
from fastapi.websockets import WebSocket

_book_cache: dict[str, fitz.Document] = {}

async def get_document(key: str) -> fitz.Document:
    if key not in _book_cache:
        file_bytes = await asyncio.to_thread(s3_client.get_file, key)
        stream = BytesIO(file_bytes)
        _book_cache[key] = fitz.open(stream=stream, filetype="pdf")
    return _book_cache[key]

async def render_page(key: str, page_num: int) -> bytes:
    doc = await get_document(key)
    page = doc.load_page(page_num)
    pix = page.get_pixmap(dpi=150)
    return pix.tobytes("jpg")

async def get_user_from_websocket(websocket: WebSocket):
    token = websocket.cookies.get("access_token")
    if not token:
        return None

    strategy = get_jwt_strategy()

    async for session in get_db():
        user_db = SQLAlchemyUserDatabase(session, User)
        user_manager = UserManager(user_db)
        user = await strategy.read_token(token, user_manager)
        return user

    return None