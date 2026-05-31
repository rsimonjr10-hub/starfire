"""
Internal ticket API — used by OSIRIS and LUMISNOVA to query their queues
and report completion back to STARFIRE.

Auth: X-Service-Secret header (same inter-service secret as admin routes).
"""

from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timezone
from sqlalchemy import select
from app.config import settings
from app.database import AsyncSessionLocal
from app.models.ticket import BotTicket

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
