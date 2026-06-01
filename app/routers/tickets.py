"""
Internal ticket API — used by OSIRIS and LUMISNOVA to query their queues,
report completion back to STARFIRE, and push performance data.

Auth: X-Service-Secret header (same inter-service secret as admin routes).
"""

from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timezone
from sqlalchemy import select
from app.config import settings
from app.database import AsyncSessionLocal
from app.models.ticket import BotTicket
from app.models.user import User

router = APIRouter(prefix="/internal/tickets", tags=["tickets"])


def _verify(x_service_secret: Optional[str] = Header(None)):
    if x_service_secret != settings.inter_service_secret:
        raise HTTPException(status_code=403, detail="Unauthorized")


# ── GET queue for a bot ────────────────────────────────────────────────────

@router.get("/{bot_name}")
async def get_tickets(bot_name: str, _=Depends(_verify)):
    """
    OSIRIS/LUMISNOVA call this to see their open ticket queue.

    Example:
      GET /internal/tickets/osiris
      X-Service-Secret: <secret>
    """
    bot = bot_name.upper()
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(BotTicket)
            .where(BotTicket.assigned_to == bot, BotTicket.status.in_(["QUEUED", "SENT"]))
            .order_by(BotTicket.priority.desc(), BotTicket.created_at)
        )
        tickets = result.scalars().all()

    return {
        "bot": bot,
        "count": len(tickets),
        "tickets": [
            {
                "id": t.id,
                "title": t.title,
                "description": t.description,
                "priority": t.priority,
                "status": t.status,
                "context": t.context,
                "created_at": t.created_at.isoformat() if t.created_at else None,
            }
            for t in tickets
        ],
    }


# ── UPDATE ticket status ───────────────────────────────────────────────────

class TicketUpdate(BaseModel):
    status: str          # DONE | FAILED | IN_PROGRESS
    result: Optional[str] = None   # optional summary to store in context


@router.post("/{ticket_id}/update")
async def update_ticket(ticket_id: int, body: TicketUpdate, _=Depends(_verify)):
    """
    OSIRIS/LUMISNOVA call this when they complete or fail a ticket.

    Example:
      POST /internal/tickets/5/update
      X-Service-Secret: <secret>
      {"status": "DONE", "result": "Portfolio scan complete — all positions healthy."}
    """
    if body.status not in ("DONE", "FAILED", "IN_PROGRESS"):
        raise HTTPException(status_code=400, detail="status must be DONE, FAILED, or IN_PROGRESS")

    async with AsyncSessionLocal() as session:
        result = await session.execute(select(BotTicket).where(BotTicket.id == ticket_id))
        ticket = result.scalar_one_or_none()
        if not ticket:
            raise HTTPException(status_code=404, detail=f"Ticket {ticket_id} not found")

        ticket.status = body.status
        if body.status == "DONE":
            ticket.completed_at = datetime.now(timezone.utc)
        if body.result:
            ctx = dict(ticket.context or {})
            ctx["result"] = body.result
            ticket.context = ctx

        await session.commit()

        # Notify the user via STARFIRE's Telegram bot
        if ticket.user_id and body.status in ("DONE", "FAILED"):
            try:
                from app.telegram.bot import send_notification
                from app.models.user import User
                u_result = await session.execute(select(User).where(User.id == ticket.user_id))
                user = u_result.scalar_one_or_none()
                if user and user.telegram_id:
                    icon = "✅" if body.status == "DONE" else "❌"
                    msg = (
                        f"{icon} *Ticket #{ticket_id} {body.status}*\n"
                        f"*{ticket.title}*"
                        + (f"\n_{body.result}_" if body.result else "")
                        + f"\n— {ticket.assigned_to}"
                    )
                    await send_notification(user.telegram_id, msg)
            except Exception:
                pass  # notification failure shouldn't break the update

    return {"ticket_id": ticket_id, "status": body.status}


# ── Acknowledge a ticket ───────────────────────────────────────────────────

@router.post("/{ticket_id}/ack")
async def ack_ticket(ticket_id: int, _=Depends(_verify)):
    """Mark a ticket as IN_PROGRESS (bot has picked it up)."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(BotTicket).where(BotTicket.id == ticket_id))
        ticket = result.scalar_one_or_none()
        if not ticket:
            raise HTTPException(status_code=404, detail=f"Ticket {ticket_id} not found")
        if ticket.status == "QUEUED":
            ticket.status = "IN_PROGRESS"
            await session.commit()
    return {"ticket_id": ticket_id, "status": "IN_PROGRESS"}


# ── OSIRIS performance push ────────────────────────────────────────────────

class TradeFill(BaseModel):
    symbol: str
    side: str                       # BUY | SELL
    quantity: Optional[float] = None
    price: Optional[float] = None
    pnl: Optional[float] = None
    timestamp: Optional[str] = None
    notes: Optional[str] = None


class OsirisPerformanceReport(BaseModel):
    user_id: int                    # which user this report is for
    pnl_today: Optional[float] = None
    pnl_total: Optional[float] = None
    trades_today: Optional[int] = None
    wins_today: Optional[int] = None
    losses_today: Optional[int] = None
    win_rate: Optional[float] = None   # 0.0 – 1.0
    open_positions: Optional[dict] = None
    fills: Optional[List[TradeFill]] = None
    summary: Optional[str] = None   # free-text from OSIRIS


@router.post("/osiris/report")
async def osiris_performance_report(body: OsirisPerformanceReport, _=Depends(_verify)):
    """
    OSIRIS calls this to push trade performance back to STARFIRE.
    STARFIRE stores it under user.preferences["osiris_report"] and
    sends a Telegram notification to the user.

    Example:
      POST /internal/tickets/osiris/report
      X-Service-Secret: <secret>
      {
        "user_id": 123,
        "pnl_today": 1250.00,
        "pnl_total": 8420.00,
        "trades_today": 4,
        "wins_today": 3,
        "losses_today": 1,
        "win_rate": 0.75,
        "open_positions": {"AAPL": {"qty": 10, "avg": 185.50}},
        "summary": "Strong day — NVDA calls +$900, SPY puts +$350, TSLA -$150."
      }
    """
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User).where(User.id == body.user_id))
        user = result.scalar_one_or_none()
        if not user:
            raise HTTPException(status_code=404, detail=f"User {body.user_id} not found")

        # Store report in user preferences
        prefs = dict(user.preferences or {})
        report_data = {
            "reported_at": datetime.now(timezone.utc).isoformat(),
            "pnl_today": body.pnl_today,
            "pnl_total": body.pnl_total,
            "trades_today": body.trades_today,
            "wins_today": body.wins_today,
            "losses_today": body.losses_today,
            "win_rate": body.win_rate,
            "open_positions": body.open_positions,
            "fills": [f.model_dump() for f in (body.fills or [])],
            "summary": body.summary,
        }
        prefs["osiris_report"] = report_data
        user.preferences = prefs
        await session.commit()

        # Notify user via Telegram
        if user.telegram_id:
            try:
                from app.telegram.bot import send_notification
                pnl = body.pnl_today
                sign = "+" if pnl and pnl >= 0 else ""
                pnl_str = f"{sign}${pnl:,.2f}" if pnl is not None else "N/A"
                wr_str = f"{body.win_rate*100:.0f}%" if body.win_rate is not None else "N/A"
                notif = (
                    f"📊 *OSIRIS Performance Report*\n"
                    f"P/L Today: `{pnl_str}`"
                    + (f" | Total: `{'+' if (body.pnl_total or 0) >= 0 else ''}${body.pnl_total:,.2f}`" if body.pnl_total is not None else "")
                    + (f"\nTrades: {body.trades_today} | Win Rate: {wr_str}" if body.trades_today else "")
                    + (f"\n\n_{body.summary}_" if body.summary else "")
                )
                await send_notification(user.telegram_id, notif)
            except Exception:
                pass

    return {"stored": True, "user_id": body.user_id}


@router.get("/osiris/report/{user_id}")
async def get_osiris_report(user_id: int, _=Depends(_verify)):
    """Retrieve the latest OSIRIS performance report for a user."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if not user:
            raise HTTPException(status_code=404, detail=f"User {user_id} not found")
        report = (user.preferences or {}).get("osiris_report")
        if not report:
            return {"user_id": user_id, "report": None, "message": "No performance report received yet."}
        return {"user_id": user_id, "report": report}
