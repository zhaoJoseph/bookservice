from contextlib import asynccontextmanager
from pathlib import Path
from dotenv import load_dotenv
from fastapi import FastAPI, Request, status, Response, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.exceptions import HTTPException, RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from fastapi.templating import Jinja2Templates
from .auth.dependencies import current_active_user, current_active_user_optional
from .models import User, Role
from sqlalchemy.ext.asyncio import AsyncSession
from .loans.services import LoanService
from .chat.services import ChatService
from .chat.dependencies import get_chat_service
from .loans.dependencies import get_loan_service
import uuid
from .database import get_db

import logging
import traceback
from typing import Annotated
from sqlalchemy import text

load_dotenv()

from .database import engine, Base
from .auth.router import router as auth_router
from .books.router import router as books_router
from .loans.router import router as loans_router
from .read.router import router as read_router
from .chat.router import router as chat_router
from .auth.exceptions import register_exception_handlers as register_auth_exception_handlers
from .books.exceptions import register_exception_handlers as register_books_exception_handlers

import os

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- STARTUP --- #
    env_name = (os.getenv("APP_ENV") or os.getenv("ENVIRONMENT") or "prod").strip().lower()
    is_dev_environment = env_name in {"dev", "development", "local"} and os.getenv("TESTING") != "true"

    if is_dev_environment:
        print("🚀 Running startup database setup because environment is dev/local/test.")

        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)

                # Ensure migrations for simple schema changes: add 'content' column if missing
                try:
                    database_url = os.getenv("DATABASE_URL") or ""
                    if database_url.startswith("sqlite") or database_url == "":
                        # SQLite: inspect pragma for chats table columns
                        try:
                            res = await conn.execute(text("PRAGMA table_info(chats);") )
                            rows = res.fetchall()
                            col_names = [r[1] for r in rows] if rows is not None else []
                            if "content" not in col_names:
                                await conn.execute(text("ALTER TABLE chats ADD COLUMN content TEXT;"))
                                print("⚙️ Added 'content' column to chats table (sqlite).")
                        except Exception as e:
                            # If PRAGMA fails, ignore — table may not exist yet
                            print(f"⚠️ Could not inspect chats table for sqlite: {e}")

                        # Also ensure chat_messages.reply column exists
                        try:
                            res2 = await conn.execute(text("PRAGMA table_info(chat_messages);") )
                            rows2 = res2.fetchall()
                            col_names2 = [r[1] for r in rows2] if rows2 is not None else []
                            if "reply" not in col_names2:
                                await conn.execute(text("ALTER TABLE chat_messages ADD COLUMN reply TEXT;"))
                                print("⚙️ Added 'reply' column to chat_messages table (sqlite).")
                        except Exception as e:
                            print(f"⚠️ Could not inspect chat_messages table for sqlite: {e}")
                    else:
                        # Generic ALTER for other DBs (Postgres supports IF NOT EXISTS)
                        try:
                            await conn.execute(text("ALTER TABLE chats ADD COLUMN IF NOT EXISTS content TEXT;"))
                            print("⚙️ Ensured 'content' column exists on chats table.")
                        except Exception as e:
                            print(f"⚠️ Could not ensure content column exists: {e}")

                        try:
                            await conn.execute(text("ALTER TABLE chat_messages ADD COLUMN IF NOT EXISTS reply TEXT;"))
                            print("⚙️ Ensured 'reply' column exists on chat_messages table.")
                        except Exception as e:
                            print(f"⚠️ Could not ensure reply column exists: {e}")
                except Exception as e:
                    print(f"⚠️ Migration step failed: {e}")

                # Clear all chats on startup so the app begins with a clean chat list.
                try:
                    await conn.execute(text("DELETE FROM chats"))
                    print("🧹 Cleared all chats from the database on startup.")
                except Exception as e:
                    # Non-fatal: log and continue if the chats table doesn't exist yet
                    print(f"⚠️ Failed to clear chats on startup: {e}")

                database_url = os.getenv("DATABASE_URL")
                if database_url is None:
                    print("⚠️ DATABASE_URL not set, skipping seed.")
                else:
                    if database_url.startswith("sqlite"):
                        seed_file = Path("migrations/seed.sql")
                    else:
                        seed_file = Path("migrations/seed-pg.sql")

                    if seed_file.exists():
                        print("🌱 Executing seed.sql...")
                        try:
                            sql_script = seed_file.read_text()
                            # Split by semicolon, filter empty strings
                            statements = [s.strip() for s in sql_script.split(';') if s.strip()]
                             
                            for statement in statements:
                                # Execute each statement within the same transaction
                                await conn.execute(text(statement))
                             
                            print("✅ Database seeded successfully.")
                        except Exception as e:
                            print(f"⚠️ Seed failed (might be already seeded or syntax error): {e}")
                    else:
                        print("⚠️ seed file not found, skipping seed.")
        except Exception as e:
            print(f"❌ Database startup failed: {e}")
            # Re-raise if you want the app to crash on DB failure
            raise
    else:
        print(f"🚫 Skipping startup database setup because environment is '{env_name}'.")

    yield  # App runs here
    
    # --- SHUTDOWN --- #
    print("🛑 Shutting down...")
    await engine.dispose()

app = FastAPI(lifespan=lifespan)
templates = Jinja2Templates(directory="templates")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# fastapi-users JWT under the hood, exposed at the original /api/v1/auth/* paths

app.include_router(auth_router, prefix="/api/v1/auth", tags=["Auth"])
app.include_router(books_router, prefix="/api/v1/books", tags=["Books"])
app.include_router(loans_router, prefix="/api/v1/loans", tags=["Loans"])
app.include_router(read_router, prefix="/api/v1/read", tags=["Read"])
app.include_router(chat_router, prefix="/api/v1/chat", tags=["Chat"])

register_auth_exception_handlers(app)
register_books_exception_handlers(app)

@app.get("/health")
def health_check():
    return {"status": "ok"}

@app.get("/login", response_class=HTMLResponse)
def root(request: Request):

    access_token = request.cookies.get("access_token")
    
    if access_token:
        return RedirectResponse(url="/catalog", status_code=status.HTTP_303_SEE_OTHER)

    if request.headers.get("HX-Request") == "true":
        response = Response(status_code=status.HTTP_204_NO_CONTENT)
        response.headers["HX-Redirect"] = "/login"
        return response

    context = {"request" : request}

    return templates.TemplateResponse(request, "login.html", context)

@app.get("/register", response_class=HTMLResponse)
def register(request: Request):

    access_token = request.cookies.get("access_token")
    
    if access_token:
        return RedirectResponse(url="/catalog", status_code=status.HTTP_303_SEE_OTHER)

    if request.headers.get("HX-Request") == "true":
        response = Response(status_code=status.HTTP_204_NO_CONTENT)
        response.headers["HX-Redirect"] = "/login"
        return response

    context = {"request" : request}
    context = {"request" : request}
    return templates.TemplateResponse(request, "register.html", context)

@app.get("/catalog", response_class=HTMLResponse)
def catalog(request: Request):

    access_token = request.cookies.get("access_token")

    if not access_token:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    
    context = {"request" : request}
    return templates.TemplateResponse(request, "catalog.html", context)

@app.get("/chat", response_class=HTMLResponse)
async def chat(request: Request,
         user: Annotated[User | None, Depends(current_active_user_optional)] = None,
         chat_service: Annotated[ChatService | None, Depends(get_chat_service)] = None,
         loan_service: Annotated[LoanService | None, Depends(get_loan_service)] = None,
         chat_id: uuid.UUID | None = None):
    if not user:
        return RedirectResponse(url="/login", status_code=303)

    access_token = request.cookies.get("access_token")
    if not access_token:
        return RedirectResponse(url="/login", status_code=303)

    if chat_id is None:
        new_id = uuid.uuid4()
        return RedirectResponse(url=f"/chat?chat_id={new_id}", status_code=303)

    if chat_service is None or loan_service is None:
        return RedirectResponse(url="/login", status_code=303)

    is_new_chat = await chat_service.get_id_user(chat_id, user.id) is None
    user_loans = await loan_service.get_active_loans(user)
    
    loan_options = [
        {
           "book_id": loan.book_id,
           "title": loan.book.title if loan.book else "Unknown book",
        }
        for loan in user_loans
    ]

    # Load existing chats for the user so the chat list is populated on page load
    chats = await chat_service.get_chats_for_user(user.id)
    chat_items = [
        {"chat_id": str(c.id), "name": c.name} for c in chats
    ]

    return templates.TemplateResponse(
        request,
        "chat.html",
        {
           "chat_id": chat_id,
           "is_new_chat": is_new_chat,
           "user_loans": loan_options,
           "chats": chat_items,
        }
    )
@app.get("/loans", response_class=HTMLResponse)
def loans(request: Request):

    access_token = request.cookies.get("access_token")

    if not access_token:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    
    context = {"request" : request}
    return templates.TemplateResponse(request, "loans.html", context)

@app.get("/admin", response_class=HTMLResponse)
async def admin(request: Request, user: Annotated[User | None, Depends(current_active_user_optional)] = None):
    if not user:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

    access_token = request.cookies.get("access_token")
    if not access_token:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    
    if not user.role == Role.admin:
        return RedirectResponse(url="/catalog", status_code=status.HTTP_303_SEE_OTHER)
    
    context = {"request" : request}
    return templates.TemplateResponse(request, "admin.html", context)

@app.get("/management")
async def management(request: Request, user: Annotated[User | None, Depends(current_active_user_optional)] = None):
    if not user:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

    access_token = request.cookies.get("access_token")
    if not access_token:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    
    if not user.role == Role.admin:
        return RedirectResponse(url="/catalog", status_code=status.HTTP_303_SEE_OTHER)
    
    context = {"request" : request}
    return templates.TemplateResponse(request, "management.html", context)

@app.get("/read/{book_id}", response_class=HTMLResponse)
async def read_book(request: Request, book_id : int, 
                    user: Annotated[User, Depends(current_active_user)],
                    loan_service: Annotated[LoanService, Depends(get_loan_service)]):
    access_token = request.cookies.get("access_token")

    if not access_token:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    
    has_active_loan = await loan_service.has_active_loan(user.id, book_id)
    if not has_active_loan:
        return RedirectResponse(url="/catalog", status_code=status.HTTP_303_SEE_OTHER)

    return templates.TemplateResponse(request, "read.html", {"book_id": book_id})

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    logger.error(f"422 Validation Error on {request.url}: {exc.errors()}")
    def serialize(errors):
        result = []
        for error in errors:
            err = dict(error)
            if "ctx" in err:
                err["ctx"] = {k: str(v) for k, v in err["ctx"].items()}
            result.append(err)
        return result
    return JSONResponse(status_code=422, content={"detail":  serialize(exc.errors())})

@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    logger.error(f"HTTP Error {exc.status_code} on {request.url}: {exc.detail}")
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError):
    logger.error(f"ValueError (400) on {request.url}: {str(exc)}")
    return JSONResponse(status_code=400, content={"detail": f"Invalid value: {str(exc)}"})

@app.exception_handler(KeyError)
async def key_error_handler(request: Request, exc: KeyError):
    logger.error(f"KeyError (400) on {request.url}: {str(exc)}")
    return JSONResponse(status_code=400, content={"detail": f"Missing key: {str(exc)}"})

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"CRITICAL: Unhandled Exception on {request.url}: {traceback.format_exc()}")
    return JSONResponse(status_code=500, content={"detail": "Internal Server Error"})