# src/books/router.py
import math
import os
import uuid
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Request, UploadFile, status
from fastapi.templating import Jinja2Templates

from ..auth.dependencies import current_active_user
from ..models import User
from .dependencies import get_book_service, require_admin
from .schemas import BookCreate, BookListQuery, BookListQueryAdmin, BookPublic, BookUpdate
from .services import BookService

try:
    from google.cloud import storage as gcs
except ModuleNotFoundError:
    gcs = None

router = APIRouter()

templates = Jinja2Templates(directory="templates")

@router.get("/admin", status_code=status.HTTP_200_OK)
async def get_books_list_admin(
    request: Request,
    service: Annotated[BookService, Depends(get_book_service)],
    query: Annotated[BookListQueryAdmin, Depends()],
    user: Annotated[User, Depends(require_admin)],
    hx_request: Annotated[str | None, Header(alias="HX-Request")] = None
):
    books, total = await service.list_books(query, True)
    limit = query.limit or 10
    total_pages = max(1, math.ceil(total / limit))

    current_page = max(1, query.page or 1)
    WINDOW = 2
    start_page = max(1, current_page - WINDOW)
    end_page = min(total_pages, current_page + WINDOW)

    desired_count = WINDOW * 2 + 1
    visible_count = end_page - start_page + 1
    if visible_count < desired_count:
        if start_page == 1:
            end_page = min(total_pages, start_page + desired_count - 1)
        elif end_page == total_pages:
            start_page = max(1, end_page - desired_count + 1)

    page_range = list(range(start_page, end_page + 1))

    context = {
        "request": request,
        "books": books,
        "total": total,
        "page": current_page,
        "total_pages": total_pages,
        "page_range": page_range,
        "limit": limit,
        "query": query,
    }

    if hx_request == "true":
        return templates.TemplateResponse(request, "partials/book_list_admin.html", context)

    return {
        "data": [BookPublic.model_validate(book) for book in books],
        "total": total,
        "page": current_page,
        "limit": limit,
    }

@router.get("/{id}", response_model=BookPublic)
async def get_book(
    id: int, 
    service: Annotated[BookService, Depends(get_book_service)],
    user: Annotated[User, Depends(current_active_user)] 
):
    return await service.get_by_id(id)

@router.get("", status_code=status.HTTP_200_OK)
async def get_books_list(
    request: Request,
    service: Annotated[BookService, Depends(get_book_service)],
    query: Annotated[BookListQuery, Depends()],
    user: Annotated[User, Depends(current_active_user)],
    hx_request: Annotated[str | None, Header(alias="HX-Request")] = None
):
    books, total = await service.list_books(query, False, user)

    if query.limit:
        total_pages = math.ceil(total / query.limit)
    else:
        total_pages = math.ceil(total / 20)


    start_page = max(1, query.page or 1)
    end_page = min(total_pages, start_page + 10)
    page_range = list(range(start_page, end_page + 1))

    if hx_request == "true":
        return templates.TemplateResponse(
            request,
            "partials/book_list.html", 
            {
                "request": request, 
                "books": books, 
                "total": total,
                "page": query.page,
                "total_pages": total_pages,
                "page_range": page_range,
                "limit": query.limit or 20,
            },
        )

    return {
        "data": [BookPublic.model_validate(book) for book in books],
        "total": total,
        "page": query.page,
        "limit": query.limit or 20,
    }

@router.post("", response_model=BookPublic, status_code=status.HTTP_201_CREATED)
async def create_book(
    book_in: BookCreate,
    service: Annotated[BookService, Depends(get_book_service)],
    user: Annotated[User, Depends(require_admin)]
):
    return await service.create_book(book_in)

def _resolve_book_bucket(file_name: str) -> str:
    extension = Path(file_name).suffix.lower()
    if extension == ".pdf":
        bucket_name = os.getenv("GOOGLE_PDF_BUCKET") or os.getenv("PDF_BUCKET") or os.getenv("BOOK_PDF_BUCKET")
        if not bucket_name:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="PDF bucket is not configured. Set GOOGLE_PDF_BUCKET or PDF_BUCKET.",
            )
        return bucket_name
    if extension == ".epub":
        bucket_name = os.getenv("GOOGLE_EPUB_BUCKET") or os.getenv("EPUB_BUCKET") or os.getenv("BOOK_EPUB_BUCKET")
        if not bucket_name:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="EPUB bucket is not configured. Set GOOGLE_EPUB_BUCKET or EPUB_BUCKET.",
            )
        return bucket_name
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Only PDF and EPUB files are supported.",
    )

async def _upload_book_to_gcs(book_id: int, file: UploadFile) -> dict:
    if gcs is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Google Cloud Storage is not configured for this environment.",
        )
    if not file or not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Please select a PDF or EPUB file to upload.",
        )

    extension = Path(file.filename).suffix.lower()
    if extension not in {".pdf", ".epub"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only PDF and EPUB files are supported.",
        )

    bucket_name = _resolve_book_bucket(file.filename)
    client = gcs.Client()
    object_name = f"books/{book_id}{extension}"
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(object_name)
    file.file.seek(0)
    blob.upload_from_file(file.file, rewind=True, content_type=file.content_type or ("application/pdf" if extension == ".pdf" else "application/epub+zip"))
    blob.metadata = {
        "book_id": str(book_id),
        "external_book_id": str(book_id),
        "file_type": extension.lstrip("."),
    }
    blob.patch()

    return {
        "book_id": book_id,
        "file_type": extension.lstrip("."),
        "bucket": bucket_name,
        "object_name": object_name,
        "url": f"https://storage.googleapis.com/{bucket_name}/{object_name}",
    }

@router.put("/{id}", response_model=BookPublic)
async def update_book(
    id: int,
    book_in: BookUpdate,
    service: Annotated[BookService, Depends(get_book_service)],
    user: Annotated[User, Depends(require_admin)]
):
    return await service.update_book(id, book_in)

@router.put("/admin/{id}", response_model=BookPublic)
async def update_book_admin(
    id: int,
    book_in: BookUpdate,
    request: Request,
    service: Annotated[BookService, Depends(get_book_service)],
    user: Annotated[User, Depends(require_admin)],
    hx_request: Annotated[str | None, Header(alias="HX-Request")] = None
):
    updated = await service.update_book(id, book_in)
    if hx_request == "true":
        query = BookListQueryAdmin(page=1, limit=10)
        books, total = await service.list_books(query, True)
        return templates.TemplateResponse(
            request,
            "partials/book_list_admin.html",
            {
                "request": request,
                "books": books,
                "total": total,
                "page": 1,
                "total_pages": max(1, math.ceil(total / 10)),
                "page_range": list(range(1, max(1, math.ceil(total / 10)) + 1)),
                "limit": 10,
                "query": query,
            },
        )
    return updated

@router.get("/admin/{id}/edit", status_code=status.HTTP_200_OK)
async def get_book_edit_form(
    id: int,
    request: Request,
    service: Annotated[BookService, Depends(get_book_service)],
    user: Annotated[User, Depends(require_admin)],
):
    book = await service.get_by_id(id)
    return templates.TemplateResponse(
        request,
        "partials/book_edit_modal.html",
        {"request": request, "book": book},
    )

@router.get("/admin/{id}/upload", status_code=status.HTTP_200_OK)
async def get_book_upload_form(
    id: int,
    request: Request,
    service: Annotated[BookService, Depends(get_book_service)],
    user: Annotated[User, Depends(require_admin)],
):
    book = await service.get_by_id(id)
    return templates.TemplateResponse(
        request,
        "partials/book_upload_modal.html",
        {"request": request, "book": book},
    )

@router.post("/admin/{id}/upload", status_code=status.HTTP_200_OK)
async def upload_book_file(
    id: int,
    request: Request,
    service: Annotated[BookService, Depends(get_book_service)],
    user: Annotated[User, Depends(require_admin)],
    file: UploadFile = File(...),
    book_id: Annotated[str | None, Form()] = None,
):
    if book_id is not None:
        try:
            submitted_book_id = int(book_id)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid book id.") from exc
        if submitted_book_id != id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Book id does not match the upload request.")

    await service.get_by_id(id)
    return await _upload_book_to_gcs(id, file)

@router.get("/admin/add", response_model=BookPublic, status_code=status.HTTP_201_CREATED)
async def add_book_admin(
    request: Request,
    user: Annotated[User, Depends(require_admin)]
):
    return templates.TemplateResponse(
        request,
        "partials/book_add_modal.html",
        {"request": request},
    )

@router.get("/admin/{id}/delete", status_code=status.HTTP_200_OK)
async def get_book_delete_form(
    id: int,
    request: Request,
    service: Annotated[BookService, Depends(get_book_service)],
    user: Annotated[User, Depends(require_admin)],
):
    book = await service.get_by_id(id)
    return templates.TemplateResponse(
        request,
        "partials/book_delete_modal.html",
        {"request": request, "book": book},
    )

@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_book(
    id: int,
    service: Annotated[BookService, Depends(get_book_service)],
    user: Annotated[User, Depends(require_admin)]
):
    await service.delete_book(id)

@router.delete("/admin/{id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_book_admin(
    id: int,
    request: Request,
    service: Annotated[BookService, Depends(get_book_service)],
    user: Annotated[User, Depends(require_admin)],
    hx_request: Annotated[str | None, Header(alias="HX-Request")] = None,
):
    await service.delete_book(id)
    if hx_request == "true":
        query = BookListQueryAdmin(page=1, limit=10)
        books, total = await service.list_books(query, True)
        return templates.TemplateResponse(
            request,
            "partials/book_list_admin.html",
            {
                "request": request,
                "books": books,
                "total": total,
                "page": 1,
                "total_pages": max(1, math.ceil(total / 10)),
                "page_range": list(range(1, max(1, math.ceil(total / 10)) + 1)),
                "limit": 10,
                "query": query,
            },
        )
