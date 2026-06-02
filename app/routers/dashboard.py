"""
STARFIRE Dashboard API
Serves the web frontend and provides JSON endpoints for memory management
and live system data.

Auth: HMAC token derived from user telegram_id + APP_SECRET_KEY.
Users get their personal URL from STARFIRE via /mylink.
"""

import hashlib
import hmac
import json
from datetime import datetime, timezone, timedelta
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
from sqlalchemy import select

from app.config import settings
from app.database import AsyncSessionLocal
from app.models.user import User
from app.models.memory import UserMemory
from app.models.task import Task
from app.models.goal import Goal
from app.models.ticket import BotTicket

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


# ── Auth ───────────────────────────────────────────────────────────────────

def _make_token(telegram_id: int) -> str:
    return hmac.new(
        settings.app_secret_key.encode(),
        str(telegram_id).encode(),
        hashlib.sha256,
    ).hexdigest()[:32]


# Python's hmac module uses hmac.new() not hmac.HMAC() directly


async def _get_user(token: str = Query(...)) -> User:
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User).where(User.is_active == True))
        users = result.scalars().all()
        for u in users:
            if hmac.compare_digest(_make_token(u.telegram_id), token):
                return u
    raise HTTPException(status_code=403, detail="Invalid token")


def get_dashboard_url(telegram_id: int) -> str:
    base = settings.telegram_webhook_url.rstrip("/")
    token = _make_token(telegram_id)
    return f"{base}/dashboard?token={token}"


# ── Frontend ───────────────────────────────────────────────────────────────

@router.get("", response_class=HTMLResponse)
async def dashboard_page(token: str = Query(...)):
    """Serve the dashboard HTML — auth validated client-side via the token."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User).where(User.is_active == True))
        users = result.scalars().all()
        valid = any(hmac.compare_digest(_make_token(u.telegram_id), token) for u in users)
    if not valid:
        return HTMLResponse("<h1>Invalid token</h1>", status_code=403)

    from app.static.dashboard_html import DASHBOARD_HTML
    return HTMLResponse(DASHBOARD_HTML.replace("__TOKEN__", token))


# ── Memory API ─────────────────────────────────────────────────────────────

class MemoryCreate(BaseModel):
    content: str
    category: str = "fact"   # fact | preference | instruction | event
    importance: int = 5


class MemoryUpdate(BaseModel):
    content: Optional[str] = None
    category: Optional[str] = None
    importance: Optional[int] = None


@router.get("/api/memories")
async def list_memories(user: User = Depends(_get_user)):
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(UserMemory).where(UserMemory.user_id == user.id, UserMemory.is_active == True)
            .order_by(UserMemory.importance.desc(), UserMemory.created_at)
        )
        mems = result.scalars().all()
    return [
        {
            "id": m.id,
            "category": m.category,
            "content": m.content,
            "importance": m.importance,
            "created_at": m.created_at.isoformat() if m.created_at else None,
        }
        for m in mems
    ]


@router.post("/api/memories")
async def create_memory(body: MemoryCreate, user: User = Depends(_get_user)):
    async with AsyncSessionLocal() as session:
        mem = UserMemory(
            user_id=user.id,
            category=body.category,
            content=body.content,
            importance=max(1, min(10, body.importance)),
        )
        session.add(mem)
        await session.commit()
        await session.refresh(mem)
    return {"id": mem.id, "content": mem.content, "category": mem.category, "importance": mem.importance}


@router.put("/api/memories/{memory_id}")
async def update_memory(memory_id: int, body: MemoryUpdate, user: User = Depends(_get_user)):
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(UserMemory).where(UserMemory.id == memory_id, UserMemory.user_id == user.id)
        )
        mem = result.scalar_one_or_none()
        if not mem:
            raise HTTPException(status_code=404, detail="Memory not found")
        if body.content is not None:
            mem.content = body.content
        if body.category is not None:
            mem.category = body.category
        if body.importance is not None:
            mem.importance = max(1, min(10, body.importance))
        await session.commit()
    return {"ok": True}


@router.delete("/api/memories/{memory_id}")
async def delete_memory(memory_id: int, user: User = Depends(_get_user)):
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(UserMemory).where(UserMemory.id == memory_id, UserMemory.user_id == user.id)
        )
        mem = result.scalar_one_or_none()
        if not mem:
            raise HTTPException(status_code=404, detail="Memory not found")
        mem.is_active = False
        await session.commit()
    return {"ok": True}


# ── Dashboard data ─────────────────────────────────────────────────────────

@router.get("/api/data")
async def dashboard_data(user: User = Depends(_get_user)):
    """All dashboard data in a single call."""
    async with AsyncSessionLocal() as session:
        # Tasks
        task_result = await session.execute(
            select(Task).where(Task.user_id == user.id, Task.status == "PENDING")
            .order_by(Task.priority.desc()).limit(10)
        )
        tasks = task_result.scalars().all()

        # Goals
        goal_result = await session.execute(
            select(Goal).where(Goal.user_id == user.id, Goal.status == "ACTIVE").limit(10)
        )
        goals = goal_result.scalars().all()

        # Open tickets
        ticket_result = await session.execute(
            select(BotTicket).where(
                BotTicket.user_id == user.id,
                BotTicket.status.in_(["QUEUED", "SENT", "IN_PROGRESS"]),
            ).order_by(BotTicket.priority.desc())
        )
        tickets = ticket_result.scalars().all()

        # OSIRIS report from preferences
        osiris_report = (user.preferences or {}).get("osiris_report")

    # Live Alpaca data
    alpaca = None
    if not settings.use_mock_broker and settings.broker_api_key and settings.broker_api_key != "mock":
        try:
            headers = {
                "APCA-API-KEY-ID": settings.broker_api_key,
                "APCA-API-SECRET-KEY": settings.broker_api_secret,
            }
            base = settings.broker_base_url
            after = (datetime.now(timezone.utc) - timedelta(days=5)).strftime("%Y-%m-%dT%H:%M:%SZ")
            async with httpx.AsyncClient(timeout=10) as client:
                acc, pos, orders = await asyncio.gather(
                    client.get(f"{base}/v2/account", headers=headers),
                    client.get(f"{base}/v2/positions", headers=headers),
                    client.get(f"{base}/v2/orders", headers=headers,
                               params={"status": "filled", "limit": 20, "after": after, "direction": "desc"}),
                )
            acc_data = acc.json() if acc.status_code == 200 else {}
            pos_data = pos.json() if pos.status_code == 200 else []
            order_data = orders.json() if orders.status_code == 200 else []
            if isinstance(order_data, dict):
                order_data = []
            alpaca = {
                "equity": float(acc_data.get("equity", 0)),
                "cash": float(acc_data.get("cash", 0)),
                "buying_power": float(acc_data.get("buying_power", 0)),
                "pnl_today": float(acc_data.get("equity", 0)) - float(acc_data.get("last_equity", 0)),
                "positions": [
                    {
                        "symbol": p["symbol"],
                        "qty": p["qty"],
                        "avg_entry": float(p.get("avg_entry_price", 0)),
                        "unrealized_pl": float(p.get("unrealized_pl", 0)),
                        "current_price": float(p.get("current_price", 0)),
                    }
                    for p in (pos_data if isinstance(pos_data, list) else [])
                ],
                "fills": [
                    {
                        "symbol": o["symbol"],
                        "side": o["side"],
                        "qty": o.get("filled_qty"),
                        "price": float(o.get("filled_avg_price") or 0),
                        "filled_at": (o.get("filled_at") or "")[:19],
                    }
                    for o in order_data[:15]
                ],
            }
        except Exception:
            pass

    return {
        "user": {"name": user.first_name or user.username or "User"},
        "tasks": [
            {"id": t.id, "title": t.title, "priority": t.priority,
             "due": t.due_at.isoformat() if t.due_at else None}
            for t in tasks
        ],
        "goals": [
            {"id": g.id, "title": g.title, "current": float(g.current_value or 0),
             "target": float(g.target_value or 0), "unit": g.unit}
            for g in goals
        ],
        "tickets": [
            {"id": t.id, "title": t.title, "assigned_to": t.assigned_to,
             "status": t.status, "priority": t.priority}
            for t in tickets
        ],
        "osiris_report": osiris_report,
        "alpaca": alpaca,
    }


import asyncio
