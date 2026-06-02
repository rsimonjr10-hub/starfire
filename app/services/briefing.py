"""
AI Briefing Service — generates daily, weekly, monthly, and quarterly
intelligence reports using Claude.

Pulls live data from all modules and synthesizes into an executive brief.
"""
import json
from datetime import datetime, timezone, timedelta, date
from typing import Literal

import structlog
from anthropic import AsyncAnthropic
from sqlalchemy import select, func as sqlfunc
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.user import User
from app.models.goal import Goal
from app.models.task import Task
from app.models.spending import SpendingRecord
from app.models.bill import Bill
from app.models.habit import Habit, HabitLog
from app.models.journal_entry import JournalEntry
from app.models.health_metric import HealthMetric
from app.models.business import Business, Customer, Invoice
from app.models.net_worth_snapshot import NetWorthSnapshot
from app.models.agent_run import AgentRun

logger = structlog.get_logger(__name__)

BriefingType = Literal["daily", "weekly", "monthly", "quarterly"]


async def generate_briefing(
    db: AsyncSession,
    user: User,
    briefing_type: BriefingType = "daily",
) -> str:
    """Generate an AI briefing for the user. Returns formatted markdown text."""
    ctx = await _collect_context(db, user, briefing_type)
    prompt = _build_prompt(ctx, briefing_type, user)

    client = AsyncAnthropic(api_key=settings.anthropic_api_key)
    try:
        msg = await client.messages.create(
            model="claude-opus-4-8",
            max_tokens=2048,
            system=(
                "You are STARFIRE — an elite AI Chief of Staff producing executive intelligence briefs. "
                "Be direct, data-driven, and action-oriented. Use markdown. No fluff."
            ),
            messages=[{"role": "user", "content": prompt}],
        )
        return msg.content[0].text
    except Exception as e:
        logger.error("briefing_generation_failed", error=str(e))
        return f"Briefing generation failed: {e}"


async def _collect_context(db: AsyncSession, user: User, btype: BriefingType) -> dict:
    now = datetime.now(timezone.utc)
    today = now.date()

    if btype == "daily":
        since = now - timedelta(days=1)
    elif btype == "weekly":
        since = now - timedelta(days=7)
    elif btype == "monthly":
        since = now - timedelta(days=30)
    else:
        since = now - timedelta(days=90)

    ctx: dict = {"period": btype, "as_of": today.isoformat()}

    # Goals
    goals = (await db.execute(
        select(Goal).where(Goal.user_id == user.id, Goal.status == "ACTIVE")
    )).scalars().all()
    ctx["goals"] = [
        {
            "title": g.title,
            "pct": round(float(g.current_value or 0) / float(g.target_value or 1) * 100, 1),
            "current": float(g.current_value or 0),
            "target": float(g.target_value or 0),
            "unit": g.unit,
        }
        for g in goals
    ]

    # Tasks
    pending_tasks = (await db.execute(
        select(Task).where(Task.user_id == user.id, Task.status == "PENDING")
        .order_by(Task.priority.desc()).limit(10)
    )).scalars().all()
    ctx["pending_tasks"] = [{"title": t.title, "priority": t.priority} for t in pending_tasks]

    # Spending
    spend_rows = (await db.execute(
        select(SpendingRecord.category, sqlfunc.sum(SpendingRecord.amount).label("total"))
        .where(SpendingRecord.user_id == user.id, SpendingRecord.recorded_at >= since)
        .group_by(SpendingRecord.category)
        .order_by(sqlfunc.sum(SpendingRecord.amount).desc())
    )).all()
    ctx["spending"] = [{"category": r.category, "total": float(r.total or 0)} for r in spend_rows]
    ctx["total_spending"] = sum(s["total"] for s in ctx["spending"])

    # Habits
    habits = (await db.execute(
        select(Habit).where(Habit.user_id == user.id, Habit.is_active == True)
    )).scalars().all()
    ctx["habits"] = [
        {"name": h.name, "streak": h.current_streak, "completed_today": h.last_completed_date == today}
        for h in habits
    ]

    # Business
    businesses = (await db.execute(
        select(Business).where(Business.user_id == user.id, Business.status == "active")
    )).scalars().all()
    ctx["businesses"] = [
        {"name": b.name, "mrr": float(b.mrr or 0), "arr": float(b.arr or 0)}
        for b in businesses
    ]

    # Invoices outstanding
    outstanding = (await db.execute(
        select(sqlfunc.sum(Invoice.amount)).where(
            Invoice.user_id == user.id,
            Invoice.status.in_(["sent", "overdue"]),
        )
    )).scalar()
    ctx["outstanding_invoices"] = float(outstanding or 0)

    # Net worth latest
    latest_nw = (await db.execute(
        select(NetWorthSnapshot)
        .where(NetWorthSnapshot.user_id == user.id)
        .order_by(NetWorthSnapshot.snapshot_date.desc())
        .limit(1)
    )).scalar_one_or_none()
    if latest_nw:
        ctx["net_worth"] = float(latest_nw.net_worth or 0)
        ctx["total_assets"] = float(latest_nw.total_assets or 0)

    # Health
    recent_health = (await db.execute(
        select(HealthMetric)
        .where(HealthMetric.user_id == user.id, HealthMetric.recorded_at >= since)
        .order_by(HealthMetric.recorded_at.desc())
        .limit(20)
    )).scalars().all()
    ctx["health_metrics"] = [
        {"type": m.metric_type, "value": float(m.value), "unit": m.unit}
        for m in recent_health
    ]

    return ctx


def _build_prompt(ctx: dict, btype: str, user: User) -> str:
    name = user.first_name or "Operator"
    data = json.dumps(ctx, indent=2, default=str)
    return f"""Generate a {btype.upper()} EXECUTIVE BRIEFING for {name}.

DATA:
{data}

Format the briefing as:
# {btype.title()} Executive Briefing — {ctx['as_of']}

## 🎯 Key Priorities
## 💰 Financial Snapshot
## 📊 Business Performance
## 🏃 Life Metrics (habits, health)
## ⚡ Action Items (top 3, numbered)
## 🔮 Forward Look

Be specific with numbers. Flag anything off-track in red (use ⚠️). Celebrate wins with ✅."""
