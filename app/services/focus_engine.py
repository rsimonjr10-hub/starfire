"""
STARFIRE Daily Focus Engine
Computes the top 3 priorities + the one ask from tasks, goals, and bills.
No AI call — fast, deterministic, runs at 7am for all users.
"""
from datetime import datetime, timezone, timedelta
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Task, Goal, Bill


async def compute_daily_focus(db: AsyncSession, user_id: int) -> dict:
    """
    Returns:
      top3         — list of up to 3 {label, type, urgency, tag} dicts
      ask          — the single most critical item (str | None)
      has_items    — bool
      overdue_count, due_today_count
    """
    now = datetime.now(timezone.utc)
    today_end = now.replace(hour=23, minute=59, second=59)

    overdue_res = await db.execute(
        select(Task)
        .where(Task.user_id == user_id, Task.status == "PENDING", Task.due_at < now)
        .order_by(Task.priority.desc())
        .limit(5)
    )
    overdue = overdue_res.scalars().all()

    today_res = await db.execute(
        select(Task)
        .where(
            Task.user_id == user_id,
            Task.status == "PENDING",
            Task.due_at >= now,
            Task.due_at <= today_end,
        )
        .order_by(Task.priority.desc())
        .limit(5)
    )
    due_today = today_res.scalars().all()

    # Bills: the model tracks recurring (due_day) and one-time (due_date) bills,
    # with last_paid_at instead of an is_paid flag. Filter active bills, then
    # determine which are due within ~1 day and not yet paid this cycle.
    bills_res = await db.execute(
        select(Bill).where(Bill.user_id == user_id, Bill.is_active == True)
    )
    all_bills = bills_res.scalars().all()
    bills_due = [b for b in all_bills if _bill_due_soon(b, now)][:3]

    goals_res = await db.execute(
        select(Goal)
        .where(Goal.user_id == user_id, Goal.status == "ACTIVE")
        .order_by(Goal.target_date.asc().nullslast())
        .limit(2)
    )
    goals = goals_res.scalars().all()

    items = []
    for t in overdue:
        items.append({"label": t.title, "type": "task", "urgency": 3, "tag": "OVERDUE"})
    for b in bills_due:
        amt = f" ${float(b.amount):,.0f}" if b.amount else ""
        items.append({"label": f"{b.name}{amt}", "type": "bill", "urgency": 3, "tag": "BILL DUE"})
    for t in due_today:
        items.append({"label": t.title, "type": "task", "urgency": 2, "tag": "due today"})
    for g in goals:
        dl = f" · deadline {g.target_date.strftime('%b %d')}" if g.target_date else ""
        items.append({"label": f"{g.title}{dl}", "type": "goal", "urgency": 1, "tag": "goal"})

    top3 = items[:3]
    ask = items[0]["label"] if items else None

    return {
        "top3": top3,
        "ask": ask,
        "has_items": bool(items),
        "overdue_count": len(overdue),
        "due_today_count": len(due_today),
    }


def _bill_due_soon(bill, now: datetime, window_days: int = 1) -> bool:
    """True if an active bill is due within window_days and not yet paid this cycle."""
    # One-time bill
    if not bill.is_recurring and bill.due_date:
        due = bill.due_date
        if due.tzinfo is None:
            due = due.replace(tzinfo=timezone.utc)
        if bill.last_paid_at and bill.last_paid_at >= due:
            return False
        return now <= due <= now + timedelta(days=window_days)

    # Recurring bill keyed to a day-of-month
    if bill.is_recurring and bill.due_day:
        day = min(int(bill.due_day), 28)
        # next occurrence of that day-of-month
        candidate = now.replace(day=day, hour=0, minute=0, second=0, microsecond=0)
        if candidate < now:
            if now.month == 12:
                candidate = candidate.replace(year=now.year + 1, month=1)
            else:
                candidate = candidate.replace(month=now.month + 1)
        days_away = (candidate - now).days
        if not (0 <= days_away <= window_days):
            return False
        # Already paid this cycle?
        if bill.last_paid_at:
            paid = bill.last_paid_at
            if paid.tzinfo is None:
                paid = paid.replace(tzinfo=timezone.utc)
            if paid.month == candidate.month and paid.year == candidate.year:
                return False
        return True

    return False


def format_daily_focus(focus: dict, name: str = "") -> str:
    greeting = f"Hey {name}. " if name else ""
    if not focus["has_items"]:
        return (
            f"{greeting}*Slate is clear.*\n\n"
            "No overdue tasks, nothing urgent today. What do you want to build?"
        )

    lines = [f"{greeting}*Your Focus Today*\n"]
    for i, item in enumerate(focus["top3"], 1):
        tag = f" `{item['tag']}`" if item["urgency"] >= 2 else ""
        lines.append(f"{i}. {item['label']}{tag}")

    if focus["ask"]:
        lines.append(f"\n*The one call I need from you:* {focus['ask']}")

    return "\n".join(lines)
