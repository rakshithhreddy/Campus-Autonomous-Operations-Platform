"""
REAL-TIME STREAMING API
=======================
Server-Sent Events (SSE) + WebSocket for true real-time streaming.
Tokens appear instantly - just like ChatGPT!

FIX: All endpoints now require JWT authentication (Depends(get_current_principal)).
     WebSocket connections use a token query param for auth since browsers cannot
     send Authorization headers in WebSocket upgrades.
"""
from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect, Request, Depends, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional
import json

from ..core.auth import get_current_principal, Principal
from ..core.auth import _decode_principal_from_token, _dev_principal_from_headers, _is_dev_like_env
from ..core.realtime_ai import (
    stream_ai_response,
    chat_sync,
    execute_task,
    execute_task_sync,
    get_session,
    create_session,
    clear_session,
    get_history
)

router = APIRouter(prefix="/api/stream", tags=["realtime-ai"])


class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None


class ConfirmRequest(BaseModel):
    session_id: str
    confirmed: bool


# ============================================================================
# SSE STREAMING ENDPOINT
# ============================================================================

@router.post("/chat")
async def stream_chat(
    request: ChatRequest,
    principal: Principal = Depends(get_current_principal),
):
    """
    Stream AI response in real-time using Server-Sent Events.
    Requires a valid JWT in Authorization header.
    """
    session_id = request.session_id or create_session()

    async def generate():
        full_response = ""
        async for chunk in stream_ai_response(session_id, request.message):
            full_response += chunk
            yield f"data: {json.dumps({'type': 'token', 'content': chunk})}\n\n"

        session = get_session(session_id)
        has_action = session.pending_task is not None
        action_type = session.pending_task.get("action") if has_action else None
        yield f"data: {json.dumps({'type': 'done', 'session_id': session_id, 'has_action': has_action, 'action_type': action_type})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


@router.post("/chat/sync")
async def chat_endpoint(
    request: ChatRequest,
    principal: Principal = Depends(get_current_principal),
):
    """Non-streaming chat — returns full response at once. Requires auth."""
    session_id = request.session_id or create_session()
    result = await chat_sync(session_id, request.message)
    return result


# ============================================================================
# TASK EXECUTION WITH STREAMING
# ============================================================================

@router.post("/execute")
async def stream_execute(
    request: ConfirmRequest,
    principal: Principal = Depends(get_current_principal),
):
    """Execute pending task with streaming status updates. Requires auth."""
    async def generate():
        async for chunk in execute_task(request.session_id, request.confirmed):
            yield f"data: {json.dumps({'type': 'status', 'content': chunk})}\n\n"
        yield f"data: {json.dumps({'type': 'done', 'success': True})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


@router.post("/execute/sync")
async def execute_endpoint(
    request: ConfirmRequest,
    principal: Principal = Depends(get_current_principal),
):
    """Non-streaming execute. Requires auth."""
    result = await execute_task_sync(request.session_id, request.confirmed)
    return result


# ============================================================================
# WEBSOCKET — BIDIRECTIONAL REAL-TIME
# Auth via ?token= query param (browsers can't send Authorization in WS upgrade)
# ============================================================================

@router.websocket("/ws/{session_id}")
async def websocket_chat(
    websocket: WebSocket,
    session_id: str,
    token: Optional[str] = Query(default=None),
):
    """
    Full bidirectional WebSocket for real-time chat.
    Authentication: pass JWT as ?token=<bearer_token> query param.

    Send: {"message": "Hello"}
    Receive: {"type": "token", "content": "Hi"} ... {"type": "done"}
    """
    # Authenticate before accepting
    principal = None
    if token:
        try:
            principal = _decode_principal_from_token(token)
        except Exception:
            pass

    if principal is None and _is_dev_like_env():
        # In dev, allow connection but with a synthetic principal
        from starlette.requests import Request as StarletteRequest
        principal = _dev_principal_from_headers(websocket)

    if principal is None:
        await websocket.close(code=4001)  # 4001 = Unauthorized
        return

    await websocket.accept()

    try:
        while True:
            data = await websocket.receive_json()

            if "message" in data:
                async for chunk in stream_ai_response(session_id, data["message"]):
                    await websocket.send_json({"type": "token", "content": chunk})

                session = get_session(session_id)
                has_action = session.pending_task is not None
                await websocket.send_json({
                    "type": "done",
                    "has_action": has_action,
                    "action_type": session.pending_task.get("action") if has_action else None
                })

            elif data.get("action") == "confirm":
                async for chunk in execute_task(session_id, data.get("confirmed", True)):
                    await websocket.send_json({"type": "status", "content": chunk})
                await websocket.send_json({"type": "done", "success": True})

            elif data.get("action") == "cancel":
                async for chunk in execute_task(session_id, False):
                    await websocket.send_json({"type": "status", "content": chunk})
                await websocket.send_json({"type": "done", "cancelled": True})

    except WebSocketDisconnect:
        pass
    except Exception as e:
        await websocket.send_json({"type": "error", "message": str(e)})


# ============================================================================
# SESSION MANAGEMENT
# ============================================================================

@router.post("/session")
async def create_new_session(
    principal: Principal = Depends(get_current_principal),
):
    """Create a new chat session. Requires auth."""
    session_id = create_session()
    return {"session_id": session_id}


@router.delete("/session/{session_id}")
async def delete_session(
    session_id: str,
    principal: Principal = Depends(get_current_principal),
):
    """Delete a session. Requires auth."""
    clear_session(session_id)
    return {"status": "deleted"}


@router.get("/history/{session_id}")
async def get_chat_history(
    session_id: str,
    principal: Principal = Depends(get_current_principal),
):
    """Get conversation history. Requires auth."""
    history = get_history(session_id)
    return {"session_id": session_id, "messages": history}
