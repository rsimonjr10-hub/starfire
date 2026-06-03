"""
Automation Rule Engine — evaluates trigger conditions and fires actions.
Runs on a schedule and is also called on relevant events.
"""
import json
from datetime import datetime, timezone, timedelta

import structlog
from sqlalchemy import select, func as sqlfunc
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.automation import Automation, AutomationRun
from app.models.spending import SpendingRecord
from app.models.task import Task
from app.models.habit import Habit
from app.models.user import User

logger = structlog.get_logger(__name__)


async def evaluate_all(db: AsyncSession, user: User) -> list[dict]:
    """Check all active automations for the user and fire any that trigger."""
    automations = (await db.execute(
        select(Automation).where(
            Automation.user_id == user.id,
            Automation.is_active == True,
        )
    )).scalars().all()

    fired = []
    for auto in automations:
        try:
            triggered, reason = await _check_trigger(db, user, auto)
            if triggered:
                result = await _fire_action(db, user, auto, reason)
                auto.run_count = (auto.run_count or 0) + 1
                auto.last_triggered_at = datetime.now(timezone.utc)
                auto.last_result = result
                run = AutomationRun(
                    automation_id=auto.id,
                    user_id=user.id,
                    triggered_by="scheduler",
                    status="success",
                    result=result,
                )
                db.add(run)
                fired.append({"automation": auto.name, "reason": reason, "result": result})
        except Exception as e:
            logger.error("automation_eval_error", automation_id=auto.id, error=str(e))
            run = AutomationRun(
                automation_id=auto.id,
                user_id=user.id,
                triggered_by="scheduler",
                status="failed",
                error=str(e),
            )
            db.add(run)

    if fired:
        await db.commit()
    return fired


async def _check_trigger(
    db: AsyncSession, user: User, auto: Automation
) -> tuple[bool, str]:
    cfg = auto.trigger_config or {}
    ttype = auto.trigger_type
    now = datetime.now(timezone.utc)

    if ttype == "spending_threshold":
        period = cfg.get("period", "monthly")
        category = cfg.get("category")
        threshold = float(cfg.get("threshold", 0))
        since = _period_start(period)
        q = select(sqlfunc.sum(SpendingRecord.amount)).where(
            SpendingRecord.user_id == user.id,
            SpendingRecord.recorded_at >= since,
        )
        if category:
            q = q.where(SpendingRecord.category == category)
        total = float((await db.execute(q)).scalar() or 0)
        if total > threshold:
            return True, f"Spending ${total:.0f} exceeds ${threshold:.0f} threshold"
        return False, ""

    if ttype == "task_overdue":
        cutoff = now - timedelta(days=cfg.get("days", 3))
        count = (await db.execute(
            select(sqlfunc.count()).where(
                Task.user_id == user.id,
                Task.status == "PENDING",
                Task.due_at <= cutoff,
            )
        )).scalar()
        if count and count > 0:
            return True, f"{count} overdue task(s)"
        return False, ""

    if ttype == "habit_streak_broken":
        yesterday = (now - timedelta(days=1)).date()
        broken = (await db.execute(
            select(Habit).where(
                Habit.user_id == user.id,
                Habit.is_active == True,
                Habit.current_streak > cfg.get("min_streak", 3),
                Habit.last_completed_date < yesterday,
            )
        )).scalars().all()
        if broken:
            names = ", ".join(h.name for h in broken)
            return True, f"Streak broken: {names}"
        return False, ""

    if ttype == "journal_missing":
        days = cfg.get("days", 2)
        cutoff = (now - timedelta(days=days)).date()
        from app.models.journal_entry import JournalEntry
        latest = (await db.execute(
            select(JournalEntry.entry_date)
            .where(JournalEntry.user_id == user.id)
            .order_by(JournalEntry.entry_date.desc())
            .limit(1)
        )).scalar_one_or_none()
        if not latest or latest < cutoff:
            return True, f"No journal entry in {days}+ days"
        return False, ""

    if ttype == "schedule":
        # Simple daily/weekly schedule — fire if not already run today/this week
        freq = cfg.get("frequency", "daily")
        if not auto.last_triggered_at:
            return True, "First scheduled run"
        last = auto.last_triggered_at
        if freq == "daily" and (now - last).days >= 1:
            return True, "Daily schedule triggered"
        if freq == "weekly" and (now - last).days >= 7:
            return True, "Weekly schedule triggered"
        return False, ""

    return False, ""


async def _fire_action(
    db: AsyncSession, user: User, auto: Automation, reason: str
) -> dict:
    cfg = auto.action_config or {}
    atype = auto.action_type

    if atype == "notify":
        msg = cfg.get("message", f"Automation triggered: {auto.name}\n{reason}")
        try:
            from app.telegram.bot import send_notification
            await send_notification(user.telegram_id, f"⚡ <b>{auto.name}</b>\n{msg}")
        except Exception as e:
            logger.error("automation_notify_failed", error=str(e))
        return {"action": "notify", "message": msg}

    if atype == "create_task":
        task = Task(
            user_id=user.id,
            title=cfg.get("task_title", f"Auto-task: {auto.name}"),
            description=reason,
            priority=cfg.get("priority", 7),
            status="PENDING",
        )
        db.add(task)
        return {"action": "create_task", "title": task.title}

    if atype == "generate_report":
        try:
            from app.services.briefing import generate_briefing
            report = await generate_briefing(db, user, cfg.get("briefing_type", "daily"))
            from app.telegram.bot import send_notification
            await send_notification(user.telegram_id, report[:4096])
        except Exception as e:
            logger.error("automation_report_failed", error=str(e))
        return {"action": "generate_report", "reason": reason}

    return {"action": atype, "reason": reason}


def _period_start(period: str) -> datetime:
    now = datetime.now(timezone.utc)
    if period == "daily":
        return now.replace(hour=0, minute=0, second=0, microsecond=0)
    if period == "weekly":
        return now - timedelta(days=now.weekday())
    # monthly
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
