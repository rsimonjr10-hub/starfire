"""
Briefing API — on-demand AI executive briefings and agent runs.
Auth: HMAC dashboard token.
"""
import hashlib
import hmac
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select

from app.config import settings
from app.database import AsyncSessionLocal
from app.models.user import User
from app.services.briefing import generate_briefing

router = APIRouter(prefix="/api/briefing", tags=["briefing"])

_VALID_TYPES = ("daily", "weekly", "monthly", "quarterly")
_VALID_AGENTS = ("cfo", "research")


def _make_token(tid: int) -> str:
    return hmac.new(settings.app_secret_key.encode(), str(tid).encode(),
                    hashlib.sha256).hexdigest()[:32]


async def _get_user(token: str = Query(...)) -> User:
    async with AsyncSessionLocal() as session:
        for u in (await session.execute(select(User).where(User.is_active == True))).scalars().all():
            if hmac.compare_digest(_make_token(u.telegram_id), token):
                return u
    raise HTTPException(status_code=403, detail="Invalid token")


@router.get("/generate")
async def get_briefing(
    briefing_type: str = Query("daily"),
    user: User = Depends(_get_user),
):
    """Generate an AI executive briefing (daily | weekly | monthly | quarterly)."""
    btype = briefing_type if briefing_type in _VALID_TYPES else "daily"
    async with AsyncSessionLocal() as session:
        db_user = (await session.execute(select(User).where(User.id == user.id))).scalar_one()
        report = await generate_briefing(session, db_user, btype)
    return {
        "briefing_type": btype,
        "report": report,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


class AgentRequest(BaseModel):
    input_data: dict = {}


@router.post("/agent/{agent_name}")
async def run_agent(
    agent_name: str,
    body: AgentRequest = AgentRequest(),
    user: User = Depends(_get_user),
):
    """Run a named agent (cfo | research) and return the report."""
    if agent_name not in _VALID_AGENTS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown agent '{agent_name}'. Available: {_VALID_AGENTS}",
        )

    from app.agents.cfo_agent import CFOAgent
    from app.agents.research_agent import ResearchAgent

    agent_map = {"cfo": CFOAgent, "research": ResearchAgent}
    agent = agent_map[agent_name]()

    async with AsyncSessionLocal() as session:
        db_user = (await session.execute(select(User).where(User.id == user.id))).scalar_one()
        run = await agent.execute(session, db_user, body.input_data, trigger="api")

    return {
        "agent": agent_name,
        "status": run.status,
        "report": run.report_text,
        "duration_ms": run.duration_ms,
        "run_id": run.id,
    }
