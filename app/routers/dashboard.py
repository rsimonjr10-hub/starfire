"""
STARFIRE Dashboard API
Serves the web frontend and provides JSON endpoints for memory management,
live system data, and SnapTrade brokerage connections (Chase, etc.).

Auth: HMAC token derived from user telegram_id + APP_SECRET_KEY.
Users get their personal URL from STARFIRE via /mylink.
"""

import hashlib
import hmac
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sqlalchemy import select, func as sqlfunc
from sqlalchemy.sql.expression import extract

from app.config import settings
from app.database import AsyncSessionLocal
from app.models.user import User
from app.models.memory import UserMemory
from app.models.task import Task
from app.models.goal import Goal
from app.models.ticket import BotTicket
from app.models.spending import SpendingRecord
from app.integrations.snaptrade import snaptrade

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

_FALLBACK_URL = "https://starfire-production-3ad8.up.railway.app"

_NO_TOKEN_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>STARFIRE OS</title>
<style>
  body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
       background:#000;color:#f1f5f9;display:flex;align-items:center;
       justify-content:center;min-height:100vh;margin:0;}
  .card{background:#0f0f0f;border:1px solid rgba(255,255,255,.1);border-radius:16px;
        padding:44px 40px;max-width:440px;text-align:center;}
  .logo{font-size:28px;font-weight:800;letter-spacing:.5px;
        background:linear-gradient(90deg,#f1f5f9,#e63946);
        -webkit-background-clip:text;-webkit-text-fill-color:transparent;}
  .sub{font-size:11px;color:#64748b;letter-spacing:1.5px;text-transform:uppercase;margin-top:4px;}
  h2{font-size:18px;font-weight:600;margin:28px 0 10px;}
  p{color:#64748b;font-size:14px;line-height:1.6;margin:0 0 8px;}
  .cmd{background:#161616;border:1px solid rgba(255,255,255,.1);border-radius:8px;
       padding:10px 16px;font-family:monospace;font-size:14px;
       color:#e63946;display:inline-block;margin-top:14px;}
</style>
</head>
<body>
<div class="card">
  <div class="logo">⚡ STARFIRE</div>
  <div class="sub">AI OS</div>
  <h2>Get Your Dashboard Link</h2>
  <p>Your dashboard requires a personal access token.</p>
  <p>Open Telegram and send this command to STARFIRE:</p>
  <div class="cmd">/mylink</div>
  <p style="margin-top:20px;font-size:12px;color:#475569;">
    STARFIRE will reply with your unique, private dashboard URL.
  </p>
</div>
</body>
</html>"""


# ── Auth ───────────────────────────────────────────────────────────────────

def _make_token(telegram_id: int) -> str:
    return hmac.new(
        settings.app_secret_key.encode(),
        str(telegram_id).encode(),
        hashlib.sha256,
    ).hexdigest()[:32]


async def _get_user(token: str = Query(...)) -> User:
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User).where(User.is_active == True))
        users = result.scalars().all()
        for u in users:
            if hmac.compare_digest(_make_token(u.telegram_id), token):
                return u
    raise HTTPException(status_code=403, detail="Invalid token")


def get_dashboard_url(telegram_id: int) -> str:
    base = (settings.telegram_webhook_url or _FALLBACK_URL).rstrip("/")
    token = _make_token(telegram_id)
    return f"{base}/dashboard?token={token}"


# ── Frontend ───────────────────────────────────────────────────────────────

@router.get("", response_class=HTMLResponse)
async def dashboard_page(token: Optional[str] = Query(default=None)):
    """Serve the dashboard HTML — auth validated via HMAC token."""
    if not token:
        return HTMLResponse(_NO_TOKEN_HTML)

    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User).where(User.is_active == True))
        users = result.scalars().all()
        valid = any(hmac.compare_digest(_make_token(u.telegram_id), token) for u in users)
    if not valid:
        return HTMLResponse(_NO_TOKEN_HTML.replace("Get Your Dashboard Link", "Invalid Token")
                            .replace("Your dashboard requires a personal access token.",
                                     "This link is invalid or has expired."),
                            status_code=403)

    from app.static.dashboard_html import DASHBOARD_HTML
    return HTMLResponse(DASHBOARD_HTML.replace("__TOKEN__", token))


# ── Memory API ─────────────────────────────────────────────────────────────

class MemoryCreate(BaseModel):
    content: str
    category: str = "fact"
    importance: int = 5


class MemoryUpdate(BaseModel):
    content: Optional[str] = None
    category: Optional[str] = None
    importance: Optional[int] = None


@router.get("/api/memories")
async def list_memories(user: User = Depends(_get_user)):
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(UserMemory)
            .where(UserMemory.user_id == user.id, UserMemory.is_active == True)
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


# ── SnapTrade API ──────────────────────────────────────────────────────────

async def _ensure_snaptrade_user(user: User) -> tuple[str, str]:
    """Register user with SnapTrade if not already done. Returns (user_id, user_secret)."""
    if user.snaptrade_user_id and user.snaptrade_user_secret:
        return user.snaptrade_user_id, user.snaptrade_user_secret

    uid = f"starfire_{user.telegram_id}"
    secret = await snaptrade.register_user(uid)
    if not secret:
        raise HTTPException(status_code=502, detail="Failed to register with SnapTrade")

    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User).where(User.id == user.id))
        db_user = result.scalar_one()
        db_user.snaptrade_user_id = uid
        db_user.snaptrade_user_secret = secret
        await session.commit()

    return uid, secret


@router.get("/api/snaptrade/connect")
async def snaptrade_connect(
    broker: Optional[str] = Query(None),
    reconnect: Optional[str] = Query(None),
    user: User = Depends(_get_user),
):
    """Return a one-time SnapTrade portal URL for the user to connect/reconnect a brokerage."""
    if not settings.snaptrade_client_id:
        raise HTTPException(status_code=503, detail="SnapTrade not configured")

    uid, secret = await _ensure_snaptrade_user(user)
    url = await snaptrade.get_login_url(uid, secret, broker=broker, reconnect=reconnect)
    if not url:
        raise HTTPException(status_code=502, detail="SnapTrade portal URL unavailable")
    return {"redirect_url": url}


@router.get("/api/snaptrade/accounts")
async def snaptrade_accounts(user: User = Depends(_get_user)):
    """Return all connected brokerage accounts with balances and positions."""
    if not settings.snaptrade_client_id:
        return {"accounts": []}

    if not user.snaptrade_user_id or not user.snaptrade_user_secret:
        return {"accounts": []}

    uid, secret = user.snaptrade_user_id, user.snaptrade_user_secret

    accounts = await snaptrade.get_accounts(uid, secret)
    result = []
    for acc in accounts:
        acc_id = acc.get("id") or acc.get("brokerage_authorization", {}).get("id", "")
        balances = await snaptrade.get_account_balances(uid, secret, acc_id) if acc_id else []
        positions = await snaptrade.get_positions(uid, secret, acc_id) if acc_id else []

        cash = next(
            (b.get("cash", 0) for b in balances if isinstance(b, dict) and b.get("currency", {}).get("code") == "USD"),
            0,
        )
        result.append({
            "id": acc_id,
            "name": acc.get("name") or acc.get("number") or "Account",
            "brokerage": (acc.get("institution_name") or
                          acc.get("brokerage", {}).get("name", "Unknown")),
            "type": acc.get("meta", {}).get("type", ""),
            "cash": float(cash or 0),
            "balances": [
                {
                    "currency": b.get("currency", {}).get("code", ""),
                    "cash": float(b.get("cash", 0)),
                    "market_value": float(b.get("market_value", 0)),
                    "total_value": float(b.get("total_value", 0)),
                }
                for b in balances if isinstance(b, dict)
            ],
            "positions": [
                {
                    "symbol": (p.get("symbol", {}).get("symbol") or
                               p.get("symbol", {}).get("description", "")),
                    "open_pnl": float(p.get("open_pnl", 0) or 0),
                    "fractional_units": float(p.get("fractional_units", 0) or 0),
                    "average_purchase_price": float(p.get("average_purchase_price", 0) or 0),
                }
                for p in positions if isinstance(p, dict)
            ],
        })
    return {"accounts": result}


@router.get("/api/snaptrade/activities")
async def snaptrade_activities(user: User = Depends(_get_user)):
    """Return recent transactions across all connected accounts."""
    if not settings.snaptrade_client_id:
        return {"activities": []}

    if not user.snaptrade_user_id or not user.snaptrade_user_secret:
        return {"activities": []}

    activities = await snaptrade.get_activities(
        user.snaptrade_user_id, user.snaptrade_user_secret, limit=25
    )
    return {
        "activities": [
            {
                "date": a.get("trade_date") or a.get("settlement_date") or "",
                "type": a.get("type", ""),
                "symbol": (a.get("symbol", {}).get("symbol") if isinstance(a.get("symbol"), dict) else a.get("symbol", "")),
                "description": a.get("description", ""),
                "amount": float(a.get("amount", 0) or 0),
                "currency": a.get("currency", "USD"),
                "account": a.get("account", {}).get("name", "") if isinstance(a.get("account"), dict) else "",
            }
            for a in activities
        ]
    }


# ── Dashboard data ─────────────────────────────────────────────────────────

@router.get("/api/data")
async def dashboard_data(user: User = Depends(_get_user)):
    """Core dashboard data: tasks, goals, tickets, spending summary."""
    now = datetime.now(timezone.utc)
    async with AsyncSessionLocal() as session:
        task_result = await session.execute(
            select(Task)
            .where(Task.user_id == user.id, Task.status == "PENDING")
            .order_by(Task.priority.desc())
            .limit(20)
        )
        tasks = task_result.scalars().all()

        goal_result = await session.execute(
            select(Goal).where(Goal.user_id == user.id, Goal.status == "ACTIVE").limit(20)
        )
        goals = goal_result.scalars().all()

        ticket_result = await session.execute(
            select(BotTicket).where(
                BotTicket.user_id == user.id,
                BotTicket.status.in_(["QUEUED", "SENT", "IN_PROGRESS"]),
            ).order_by(BotTicket.priority.desc())
        )
        tickets = ticket_result.scalars().all()

        # Spending this calendar month
        spend_result = await session.execute(
            select(SpendingRecord.category, sqlfunc.sum(SpendingRecord.amount).label("total"))
            .where(
                SpendingRecord.user_id == user.id,
                extract("year", SpendingRecord.recorded_at) == now.year,
                extract("month", SpendingRecord.recorded_at) == now.month,
            )
            .group_by(SpendingRecord.category)
            .order_by(sqlfunc.sum(SpendingRecord.amount).desc())
        )
        spend_rows = spend_result.all()

    spending_by_category = [
        {"category": row.category, "total": float(row.total or 0)} for row in spend_rows
    ]
    spending_this_month = sum(r["total"] for r in spending_by_category)

    return {
        "user": {"name": user.first_name or user.username or "User"},
        "snaptrade_connected": bool(user.snaptrade_user_id and user.snaptrade_user_secret),
        "spending_this_month": round(spending_this_month, 2),
        "spending_by_category": spending_by_category,
        "tasks": [
            {
                "id": t.id,
                "title": t.title,
                "priority": t.priority,
                "due": t.due_at.isoformat() if t.due_at else None,
            }
            for t in tasks
        ],
        "goals": [
            {
                "id": g.id,
                "title": g.title,
                "current": float(g.current_value or 0),
                "target": float(g.target_value or 0),
                "unit": g.unit,
            }
            for g in goals
        ],
        "tickets": [
            {
                "id": t.id,
                "title": t.title,
                "assigned_to": t.assigned_to,
                "status": t.status,
                "priority": t.priority,
            }
            for t in tickets
        ],
    }
