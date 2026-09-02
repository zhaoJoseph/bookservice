from fastapi import HTTPException
from .constants import NOT_FOUND_MESSAGE, ISBN_REQUIRED_MESSAGE, ISBN_ALREADY_EXISTS_MESSAGE, FAILED_DELETE_MESSAGE
from fastapi.responses import JSONResponse
from fastapi.requests import Request
from fastapi import FastAPI

class BookNotFound(HTTPException):
    def __init__(self, detail: str = NOT_FOUND_MESSAGE):
        # Explicitly call the parent constructor with your defaults
        super().__init__(status_code=404, detail=detail)

class ISBNRequired(HTTPException):
    def __init__(self, detail: str = ISBN_REQUIRED_MESSAGE):
        # Explicitly call the parent constructor with your defaults
        super().__init__(status_code=400, detail=detail)

class ISBNAlreadyExists(HTTPException):
    def __init__(self, detail: str = ISBN_ALREADY_EXISTS_MESSAGE):
        # Explicitly call the parent constructor with your defaults
        super().__init__(status_code=409, detail=detail)

class FailedDelete(HTTPException):
    def __init__(self, detail: str = FAILED_DELETE_MESSAGE):
        # Explicitly call the parent constructor with your defaults
        super().__init__(status_code=500, detail=detail)

def register_exception_handlers(app: FastAPI):
# Register the handler
    @app.exception_handler(BookNotFound)
    async def book_not_found_handler(request: Request, exc: BookNotFound):
        return JSONResponse(
            status_code=exc.status_code, 
            content={"detail": exc.detail} 
        )

    @app.exception_handler(ISBNRequired)
    async def isbn_required_handler(request: Request, exc: ISBNRequired):
        return JSONResponse(
            status_code=exc.status_code, 
            content={"detail": exc.detail} 
        )

    @app.exception_handler(ISBNAlreadyExists)
    async def isbn_already_exists_handler(request: Request, exc: ISBNAlreadyExists):
        return JSONResponse(
            status_code=exc.status_code, 
            content={"detail": exc.detail} 
        )

    @app.exception_handler(FailedDelete)
    async def failed_delete_handler(request: Request, exc: FailedDelete):
        return JSONResponse(
            status_code=exc.status_code, 
            content={"detail": exc.detail} 
        )