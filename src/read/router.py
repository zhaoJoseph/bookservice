from fastapi import APIRouter, WebSocket, Request
from fastapi.responses import HTMLResponse
from ..aws.client import s3_client
from .utils import render_page, get_user_from_websocket
from fastapi.websockets import WebSocketDisconnect
from ..loans.services import LoanService
from ..database import get_db

router = APIRouter()

@router.websocket("/ws")
async def read(websocket : WebSocket, book_id : int):
    book_id_param = websocket.query_params.get("book_id")
    if not book_id_param:
        await websocket.close(code=4001)
        return

    try:
        book_id = int(book_id_param)
    except ValueError:
        await websocket.close(code=4001)
        return

    user = await get_user_from_websocket(websocket)
    if not user or not user.is_active:
        await websocket.close(code=4401)  
        return

    async for session in get_db():
        loan_service = LoanService(session)
        has_loan = await loan_service.has_active_loan(user.id, book_id)
        if not has_loan:
            await websocket.close(code=4403)
            return

    await websocket.accept()

    if not websocket.query_params.get("book_id"):
        await websocket.close()
        return
    book_id = int(websocket.query_params["book_id"])
    
    if not book_id:
        await websocket.close()
        return
    key = f"books/{book_id}.pdf"
    try:
        while True:
            data = await websocket.receive_json()
            page_num = data['page']
            img_bytes = await render_page(key, page_num)
            await websocket.send_bytes(img_bytes)
    except WebSocketDisconnect:
        pass
    except Exception as e:
        try:
            await websocket.send_json({"error": str(e)})
        except Exception:
            pass  

@router.get("/page/{book_id}", response_class=HTMLResponse)
async def read_book(request: Request, book_id : int):
    return f"""
    <div id="book-viewer" style="text-align: center;">
        
        <canvas id="page-canvas" width="800" height="1000" style="border: 1px solid #ccc; display: block; margin: 0 auto;"></canvas>
        <div style="margin-top: 10px;">Page: <span id="page-num">Loading...</span></div>
        
        <div style="d-flex flex-row">
            <button id="btn-prev">Previous</button>
            <button id="btn-next">Next</button>
        </div>
        
        <!-- Hidden input to store book_id if needed for other logic -->
        <input type="hidden" id="current-book-id" value="{book_id}">
    </div>
    """