"""
WebSocket endpoint for real-time dashboard updates.

Clients connect with their auth token and receive server-sent events when
data changes (new tasks, portfolio updates, automation fires, etc.).

Usage:  ws://host/ws?token=<hmac_token>
"""
import asyncio
import hashlib
import hmac
import json
from datetime import datetime, timezone
from typing import Optional

import structlog
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from sqlalchemy import select

from app.config import settings
from app.database import AsyncSessionLocal
from app.models.user import User

logger = structlog.get_logger(__name__)
router = APIRouter(tags=["realtime"])

# Connected clients: {user_id: [WebSocket, ...]}
_connections: dict[int, list[WebSocket]] = {}


def _make_token(tid: int) -> str:
    return hmac.new(settings.app_secret_key.encode(), str(tid).encode(),
                    hashlib.sha256).hexdigest()[:32]


async def _auth_token(token: str) -> Optional[User]:
    async with AsyncSessionLocal() as session:
        for u in (await session.execute(select(User).where(User.is_active == True))).scalars().all():
            if hmac.compare_digest(_make_token(u.telegram_id), token):
                return u
    return None


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, token: str = Query(...)):
    user = await _auth_token(token)
    if not user:
        await websocket.close(code=4003, reason="Invalid token")
        return

    await websocket.accept()
    uid = user.id
    _connections.setdefault(uid, []).append(websocket)
    logger.info("ws_connected", user_id=uid)

    try:
        # Send initial heartbeat
        await websocket.send_text(json.dumps({
            "type": "connected",
            "user": user.first_name or user.username,
            "ts": datetime.now(timezone.utc).isoformat(),
        }))

        # Keep-alive loop
        while True:
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
                msg = json.loads(data)
                if msg.get("type") == "ping":
                    await websocket.send_text(json.dumps({"type": "pong"}))
            except asyncio.TimeoutError:
                # Send heartbeat
                await websocket.send_text(json.dumps({
                    "type": "heartbeat",
                    "ts": datetime.now(timezone.utc).isoformat(),
                }))
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error("ws_error", user_id=uid, error=str(e))
    finally:
        if uid in _connections:
            _connections[uid] = [ws for ws in _connections[uid] if ws != websocket]
        logger.info("ws_disconnected", user_id=uid)


async def broadcast(user_id: int, event_type: str, data: dict) -> None:
    """Push an event to all WebSocket clients for a given user."""
    connections = _connections.get(user_id, [])
    if not connections:
        return
    payload = json.dumps({"type": event_type, "data": data,
                          "ts": datetime.now(timezone.utc).isoformat()})
    dead = []
    for ws in connections:
        try:
            await ws.send_text(payload)
        except Exception:
            dead.append(ws)
    if dead:
        _connections[user_id] = [ws for ws in connections if ws not in dead]


async def broadcast_all(event_type: str, data: dict) -> None:
    """Broadcast to all connected users."""
    for uid in list(_connections.keys()):
        await broadcast(uid, event_type, data)
