from fastapi import HTTPException
from .constants import LOAN_NOT_FOUND, VALIDATION_ERROR, LOAN_ALREADY_EXISTS, WRONG_USER, LOAN_NOT_ACTIVE
from fastapi.responses import JSONResponse
from fastapi.requests import Request
from fastapi import FastAPI

class LoanNotFound(HTTPException):
    def __init__(self, detail: str = LOAN_NOT_FOUND):
        # Explicitly call the parent constructor with your defaults
        super().__init__(status_code=404, detail=detail)

class ValidationError(HTTPException):
    def __init__(self, detail: str = VALIDATION_ERROR):
        # Explicitly call the parent constructor with your defaults
        super().__init__(status_code=422, detail=detail)

class LoanAlreadyExists(HTTPException):
    def __init__(self, detail: str = LOAN_ALREADY_EXISTS):
        # Explicitly call the parent constructor with your defaults
        super().__init__(status_code=409, detail=detail)

class WrongUser(HTTPException):
    def __init__(self, detail: str = WRONG_USER):
        # Explicitly call the parent constructor with your defaults
        super().__init__(status_code=403, detail=detail)

class LoanNotActive(HTTPException):
    def __init__(self, detail: str = LOAN_NOT_ACTIVE):
        # Explicitly call the parent constructor with your defaults
        super().__init__(status_code=400, detail=detail)

def register_exception_handlers(app: FastAPI):
# Register the handler
    @app.exception_handler(LoanNotFound)
    async def loan_not_found_handler(request: Request, exc: LoanNotFound):
        return JSONResponse(
            status_code=exc.status_code, 
            content={"detail": exc.detail} 
        )
    
    @app.exception_handler(ValidationError)
    async def validation_error_handler(request: Request, exc: ValidationError):
        return JSONResponse(
            status_code=exc.status_code, 
            content={"detail": exc.detail} 
        )
    
    @app.exception_handler(LoanAlreadyExists)
    async def loan_already_exists_handler(request: Request, exc: LoanAlreadyExists):
        return JSONResponse(
            status_code=exc.status_code, 
            content={"detail": exc.detail} 
        )
    
    @app.exception_handler(WrongUser)
    async def wrong_user_handler(request: Request, exc: WrongUser):
        return JSONResponse(
            status_code=exc.status_code, 
            content={"detail": exc.detail} 
        )
    
    @app.exception_handler(LoanNotActive)
    async def loan_not_active_handler(request: Request, exc: LoanNotActive):
        return JSONResponse(
            status_code=exc.status_code, 
            content={"detail": exc.detail} 
        )