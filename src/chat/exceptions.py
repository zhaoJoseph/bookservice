from fastapi import HTTPException
from .constants import CHAT_NOT_FOUND, MESSAGE_EMPTY, MESSAGE_EXISTS
from fastapi.responses import JSONResponse
from fastapi.requests import Request
from fastapi import FastAPI

class ChatNotFound(HTTPException):
    def __init__(self, detail: str = CHAT_NOT_FOUND):
        # Explicitly call the parent constructor with your defaults
        super().__init__(status_code=404, detail=detail)    

class MessageEmpty(HTTPException):
    def __init__(self, detail: str = MESSAGE_EMPTY):
        # Explicitly call the parent constructor with your defaults
        super().__init__(status_code=400, detail=detail)

class MessageExists(HTTPException):
    def __init__(self, detail: str = MESSAGE_EXISTS):
        # Explicitly call the parent constructor with your defaults 
        super().__init__(status_code=409, detail=detail)

def register_exception_handlers(app: FastAPI):
# Register the handler
    @app.exception_handler(ChatNotFound)
    async def chat_not_found_handler(request: Request, exc: ChatNotFound):
        return JSONResponse(
            status_code=exc.status_code, 
            content={"detail": exc.detail} 
        )

    @app.exception_handler(MessageEmpty)
    async def message_empty_handler(request: Request, exc: MessageEmpty):
        return JSONResponse(
            status_code=exc.status_code, 
            content={"detail": exc.detail} 
        )

    @app.exception_handler(MessageExists)
    async def message_exists_handler(request: Request, exc: MessageExists):
        return JSONResponse(
            status_code=exc.status_code, 
            content={"detail": exc.detail} 
        )