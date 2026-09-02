from .constants import EMAIL_EXISTS_MESSAGE, INCORECT_LOGIN_MESSAGE,  \
            USER_SUSPENDED_MESSAGE, INVALID_TOKEN_MESSAGE, USER_NOT_FOUND_MESSAGE
from fastapi.responses import JSONResponse
from fastapi.exceptions import HTTPException
from fastapi import FastAPI

class EmailExists(HTTPException):
    def __init__(self, detail: str = EMAIL_EXISTS_MESSAGE):
        super().__init__(status_code=409, detail=detail)

class IncorrectLogin(HTTPException):
    def __init__(self, detail: str = INCORECT_LOGIN_MESSAGE):
        super().__init__(status_code=400, detail=detail)

class UserSuspended(HTTPException):
    def __init__(self, detail: str = USER_SUSPENDED_MESSAGE):
        super().__init__(status_code=401, detail=detail)

class InvalidToken(HTTPException):
    def __init__(self, detail: str = INVALID_TOKEN_MESSAGE):
        super().__init__(status_code=401, detail=detail)

class UserNotFound(HTTPException):
    def __init__(self, detail: str = USER_NOT_FOUND_MESSAGE):
        super().__init__(status_code=404, detail=detail)

def register_exception_handlers(app: FastAPI):
    # Register the handler
    @app.exception_handler(EmailExists)
    async def email_exists_handler(request, exc: EmailExists):
        return JSONResponse(
            status_code=exc.status_code, 
            content={"detail": exc.detail} 
        )

    @app.exception_handler(IncorrectLogin)
    async def incorrect_login_handler(request, exc: IncorrectLogin):
        return JSONResponse(
            status_code=exc.status_code, 
            content={"detail": exc.detail} 
        )

    @app.exception_handler(UserSuspended)
    async def user_suspended_handler(request, exc: UserSuspended):
        return JSONResponse(
            status_code=exc.status_code, 
            content={"detail": exc.detail} 
        )
    
    @app.exception_handler(InvalidToken)
    async def invalid_token_handler(request, exc: InvalidToken):
        return JSONResponse(
            status_code=exc.status_code, 
            content={"detail": exc.detail} 
        )

    @app.exception_handler(UserNotFound)
    async def user_not_found_handler(request, exc: UserNotFound):
        return JSONResponse(
            status_code=exc.status_code, 
            content={"detail": exc.detail} 
        )