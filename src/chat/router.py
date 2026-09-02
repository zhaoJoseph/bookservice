from typing import Annotated
from fastapi import APIRouter, WebSocket, Request, Depends, Response, UploadFile
import requests
from fastapi.websockets import WebSocketDisconnect
from .services import ChatService
from .dependencies import get_chat_service
from ..models import User
from ..auth.dependencies import current_active_user
from ..loans.services import LoanService
from ..loans.dependencies import get_loan_service
from .exceptions import MessageEmpty, ChatNotFound, MessageExists
import uuid
from html import escape
import os

router = APIRouter()

RAG_SERVICE_URL = "http://34.123.16.5"
RAG_SERVICE_HEADERS = {"Host": "rag-query.local"}
EXTERNAL_ASK_URL = os.getenv("EXTERNAL_ASK_URL")


# Keep track of connected notification sockets and the chat_id + client_id each socket is
# viewing (if any). Store a small dict per WebSocket so the server can avoid
# echoing updates back to the originating client (prevents duplicate UI inserts).
connected_notification_sockets: dict[WebSocket, dict] = {}

@router.websocket("/ws/notifications")
async def websocket_notifications(websocket: WebSocket):
    # Clients may include ?chat_id=<uuid>&client_id=<uuid> when connecting to
    # indicate which chat they're currently viewing and the per-tab client id.
    # Store that mapping so message OOB swaps are delivered only to relevant
    # clients, and originators can be excluded from broadcasts.
    await websocket.accept()
    chat_param = websocket.query_params.get("chat_id")
    client_param = websocket.query_params.get("client_id")
    connected_notification_sockets[websocket] = {"chat_id": chat_param, "client_id": client_param}
    try:
        while True:
            data = await websocket.receive_json()

            if data.get("type") == "new_chat":
                # client-initiated new_chat request -> echo back an HTML
                # fragment for backward compatibility with existing client
                chat_id = data["chat_id"]
                safe_chat_id = escape(str(chat_id), quote=True)
                html_fragment = f'<li data-chat-id="{safe_chat_id}">Chat {safe_chat_id}</li>'
                await websocket.send_text(html_fragment)

            if data.get("type") == "update_chat":
                # Allow the client to tell us it's now viewing a different chat.
                # This updates the mapping so subsequent notify_message calls go
                # to the correct viewers.
                new_chat = data.get("chat_id")
                if websocket in connected_notification_sockets:
                    connected_notification_sockets[websocket]["chat_id"] = new_chat
    except WebSocketDisconnect:
        pass
    finally:
        # ensure socket is removed on any exit
        try:
            if websocket in connected_notification_sockets:
                del connected_notification_sockets[websocket]
        except Exception:
            pass


async def notify_new_chat(chat_id: str, name: str | None = None) -> None:
    """Broadcast a new_chat event to all connected notification sockets.

    The client expects an HTML fragment (Out-Of-Band) so HTMX can insert the
    new list item into #chat-list. Include the chat's name if provided; fall
    back to a short fallback when not.
    """
    safe_chat_id = escape(str(chat_id), quote=True)
    display_name = escape(str(name).strip(), quote=True) if name else f"Chat {safe_chat_id}"

    # Wrap the <li> in an Out-Of-Band fragment that HTMX's ws extension can
    # apply directly to the element with id 'chat-list'. Use hx-swap-oob="beforeend"
    # to append the new item.
    html_fragment = (
        f'<div id="chat-list" hx-swap-oob="beforeend">'
        f'<li data-chat-id="{safe_chat_id}">{display_name}</li>'
        f'</div>'
    )
    dead_sockets: list[WebSocket] = []
    for ws in list(connected_notification_sockets.keys()):
        try:
            # send HTML fragment as plain text so HTMX can perform the OOB swap
            await ws.send_text(html_fragment)
        except Exception:
            # mark broken sockets for cleanup
            dead_sockets.append(ws)

    for ds in dead_sockets:
        if ds in connected_notification_sockets:
            del connected_notification_sockets[ds]


async def notify_message(chat_id: str, html_fragment: str, origin_client_id: str | None = None) -> None:
    """Send an Out-Of-Band HTML fragment to sockets that are viewing the
    specified chat_id. If origin_client_id is provided, sockets whose
    client_id matches it will be skipped so the originator does not receive
    a duplicate insert (the originator already gets the HTTP response).

    The html_fragment should already be wrapped with an OOB target
    (e.g. id="chat-board-<chat_id>" hx-swap-oob="beforeend")."""
    dead_sockets: list[WebSocket] = []
    for ws, info in list(connected_notification_sockets.items()):
        try:
            viewed_chat = info.get("chat_id")
            ws_client_id = info.get("client_id")
            # Only send to sockets that are viewing this chat (exact match)
            if viewed_chat is None:
                continue
            if str(viewed_chat) == str(chat_id):
                # Skip sending back to originator when provided
                if origin_client_id is not None and ws_client_id == origin_client_id:
                    continue
                await ws.send_text(html_fragment)
        except Exception:
            dead_sockets.append(ws)

    for ds in dead_sockets:
        if ds in connected_notification_sockets:
            del connected_notification_sockets[ds]


def format_inline_answer(answer: str | None) -> str:
    if answer is None:
        return '<div class="assistant-message"><strong>Assistant:</strong> I was unable to answer your question, please try again later.</div>'

    normalized = str(answer).replace("\r\n", "\n").strip()
    escaped_md = escape(normalized, quote=True)
    return '<div class="assistant-message" data-md="' + escaped_md + '"></div>'


@router.post("/send/{chat_id}")
async def message(request: Request,
                  chat_id: str,
                  chat_service: Annotated[ChatService, Depends(get_chat_service)],
                  loan_service: Annotated[LoanService, Depends(get_loan_service)],
                  user: Annotated[User, Depends(current_active_user)]):
    try:
        data = await request.json()
    except ValueError:
        try:
            form_data = await request.form()
            data = dict(form_data)
        except Exception:
            data = {}

    message_content = data.get("message")
    if isinstance(message_content, list):
        message_content = message_content[0] if message_content else None

    if message_content is None:
        raise MessageEmpty()

    message_content = str(message_content).strip()
    if not message_content:
        raise MessageEmpty()

    selected_book_id = (
        data.get("external_id")
        or data.get("book_id")
        or data.get("selected_id")
    )
    if isinstance(selected_book_id, list):
        selected_book_id = selected_book_id[0] if selected_book_id else None
    if selected_book_id is not None:
        selected_book_id = str(selected_book_id).strip()

    # Extract optional per-tab client id (populated by the client in hx-vals)
    client_id = data.get('client_id')
    if isinstance(client_id, list):
        client_id = client_id[0] if client_id else None
    if client_id is not None:
        client_id = str(client_id)

    chatid = uuid.UUID(chat_id)

    if not await chat_service.get_by_id(chatid):
        summary_response = requests.post(
            f"{RAG_SERVICE_URL}/summarize",
            headers=RAG_SERVICE_HEADERS,
            json={"question": message_content},
        )

        # Robustly pick a title from the RAG response. Try several common
        # keys, and fall back to a short snippet of the user's message so
        # chats aren't named the generic "New Chat".
        title = None
        if summary_response.status_code == 200:
            try:
                resp_json = summary_response.json()
            except Exception:
                resp_json = None

            if isinstance(resp_json, dict):
                title = resp_json.get("title") or resp_json.get("summary") or resp_json.get("result") or resp_json.get("answer")

        if title:
            # normalize whitespace
            title = " ".join(str(title).split())
            if title.strip() == "":
                title = None

        if not title:
            # derive a short fallback title from the message content
            fallback = message_content.replace("\n", " ").strip()
            if not fallback:
                title = None
            else:
                max_len = 60
                if len(fallback) > max_len:
                    # cut at last space before max_len when possible
                    cut = fallback[:max_len]
                    last_space = cut.rfind(' ')
                    if last_space > 10:
                        cut = cut[:last_space]
                    title = cut + "..."
                else:
                    title = fallback

        chat_obj = await chat_service.add_chat(chatid, user.id, title)
        # Notify connected websocket clients that a new chat was created so the
        # chat UI can add the new chat to the list and enable the "new chat"
        # button. Include the summarized title so clients show the proper name.
        try:
            await notify_new_chat(str(chat_obj.id), chat_obj.name)
        except Exception:
            # Best-effort notify; do not fail the whole request if sockets are down.
            pass
    elif not await chat_service.get_id_user(chatid, user.id):
        raise MessageExists()

    loans = await loan_service.get_active_loans(user)
    valid_loan_ids = {str(loan.book_id) for loan in loans}

    if selected_book_id not in valid_loan_ids:
        error_fragment = '<div class="assistant-message"><strong>Assistant:</strong> You do not have a loan for that book.</div>'
        return Response(error_fragment, media_type="text/html")

    # Only use a selected book when the browser explicitly sent one, and only
    # when it is one of the user's active loans. Do not silently replace a
    # missing/stale selection with a different book from the list; that makes the
    # app behave as if the user chose a different loan than the one shown in the UI.
    if selected_book_id in (None, ""):
        external_params = None
    elif selected_book_id not in valid_loan_ids:
        error_fragment = '<div class="assistant-message"><strong>Assistant:</strong> That book is not one of your active loans.</div>'
        return Response(error_fragment, media_type="text/html")
    else:
        external_params = {"external_id": selected_book_id}

    selected_book_id = external_params["external_id"] if external_params else None

    # Store the user's message in the DB so it can be shown to other clients.
    try:
        user_msg = await chat_service.add_message(chatid, user.id, message_content)
        # Notify viewers of this chat about the new user message (OOB swap into chat-board)
        try:
            safe_text = escape(message_content, quote=True)
            user_html = (
                f'<div id="chat-board-{chatid}" hx-swap-oob="beforeend">'
                f'<div class="user-message"><strong>User:</strong> {safe_text}</div>'
                f'</div>'
            )
            # Avoid echoing this user message back to the originating tab
            await notify_message(str(chatid), user_html, origin_client_id=client_id)
        except Exception:
            pass
    except Exception:
        # If DB write fails, continue — do not block answering.
        user_msg = None

    print(f"Asking external service for {message_content} from {selected_book_id}")

    ask_payload = {"question": message_content}
    if selected_book_id not in (None, ""):
        ask_payload["external_id"] = selected_book_id

    # Match the actual query API contract used by the live service: plain
    # question + external_id, not a different RAG payload shape.
    ask_url = f"{RAG_SERVICE_URL}/query"

    try:
        external_response = requests.post(
            ask_url,
            json=ask_payload,
            headers=RAG_SERVICE_HEADERS,
            timeout=30,
        )
    except requests.RequestException:
        fragment = '<div class="assistant-message"><strong>Assistant:</strong> I was unable to answer your question, please try again later.</div>'
        return Response(fragment, media_type="text/html")

    if external_response.status_code != 200:
        fragment = '<div class="assistant-message"><strong>Assistant:</strong> I was unable to answer your question, please try again later.</div>'
        return Response(fragment, media_type="text/html")

    payload = external_response.json()
    answer = payload.get("answer") or payload.get("result") or payload.get("data") or payload.get("book")

    # Persist the assistant reply to the DB and notify viewers of this chat
    assistant_text = str(answer) if answer is not None else ""
    try:
        if user_msg is not None:
            updated = await chat_service.update_message_reply(user_msg.id, assistant_text)
        else:
            # fallback: create a message row for the assistant reply
            updated = await chat_service.add_message(chatid, user.id, "")
            updated = await chat_service.update_message_reply(updated.id, assistant_text)

        # Build assistant HTML and send as OOB swap to viewers of this chat
        try:
            assistant_fragment = format_inline_answer(assistant_text if assistant_text else None)
            html_fragment = (
                f'<div id="chat-board-{chatid}" hx-swap-oob="beforeend">'
                f'{assistant_fragment}'
                f'</div>'
            )
            # Avoid sending the assistant fragment back to the originator (they will
            # already receive the HTTP response that contains the assistant bubble).
            await notify_message(str(chatid), html_fragment, origin_client_id=client_id)
        except Exception:
            pass
    except Exception:
        pass

    return Response(format_inline_answer(str(answer) if answer is not None else None), media_type="text/html")


@router.get("/messages/{chat_id}")
async def get_messages(chat_id: str,
                       chat_service: Annotated[ChatService, Depends(get_chat_service)],
                       user: Annotated[User, Depends(current_active_user)]):
    """Return the recent messages for a chat as HTML to be injected into the
    chat board. Ensures the requesting user owns the chat."""
    try:
        chat_uuid = uuid.UUID(chat_id)
    except Exception:
        raise ChatNotFound()

    # ensure user owns chat
    if not await chat_service.get_id_user(chat_uuid, user.id):
        raise ChatNotFound()

    messages = await chat_service.get_messages_for_chat(chat_uuid, limit=200)

    # Build HTML fragment: user messages and assistant replies
    parts = []
    for m in messages:
        safe_user = escape(str(m.content), quote=True)
        parts.append(f'<div class="user-message"><strong>You:</strong> {safe_user}</div>')
        # assistant reply may be empty
        if getattr(m, 'reply', None):
            # reuse format_inline_answer to produce data-md assistant bubble
            parts.append(format_inline_answer(str(m.reply)))

    html = "".join(parts)
    return Response(html, media_type="text/html")