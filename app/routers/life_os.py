"""
Life OS API — habits, journal entries, and health metrics.
Auth: HMAC dashboard token.
"""
import hashlib
import hmac
from datetime import date, datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, func as sqlfunc
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import AsyncSessionLocal
from app.models.user import User
from app.models.habit import Habit, HabitLog
from app.models.journal_entry import JournalEntry
from app.models.health_metric import HealthMetric

router = APIRouter(prefix="/api/life", tags=["life_os"])


def _make_token(tid: int) -> str:
    return hmac.new(settings.app_secret_key.encode(), str(tid).encode(),
                    hashlib.sha256).hexdigest()[:32]

async def _get_user(token: str = Query(...)) -> User:
    async with AsyncSessionLocal() as session:
        for u in (await session.execute(select(User).where(User.is_active == True))).scalars().all():
            if hmac.compare_digest(_make_token(u.telegram_id), token):
                return u
    raise HTTPException(status_code=403, detail="Invalid token")


# ════ HABITS ══════════════════════════════════════════════════════════════

class HabitCreate(BaseModel):
    name: str
    description: Optional[str] = None
    frequency: str = "daily"
    target_count: int = 1
    color: str = "#38bdf8"
    icon: str = "⚡"

@router.get("/habits")
async def list_habits(user: User = Depends(_get_user)):
    today = datetime.now(timezone.utc).date()
    async with AsyncSessionLocal() as session:
        habits = (await session.execute(
            select(Habit).where(Habit.user_id == user.id, Habit.is_active == True)
        )).scalars().all()
        # Completions today
        logs_today = (await session.execute(
            select(HabitLog.habit_id).where(
                HabitLog.user_id == user.id, HabitLog.completed_date == today
            )
        )).scalars().all()
    completed_ids = set(logs_today)
    return [
        {
            "id": h.id, "name": h.name, "description": h.description,
            "frequency": h.frequency, "target_count": h.target_count,
            "current_streak": h.current_streak, "longest_streak": h.longest_streak,
            "total_completions": h.total_completions,
            "completed_today": h.id in completed_ids,
            "color": h.color, "icon": h.icon,
        }
        for h in habits
    ]

@router.post("/habits")
async def create_habit(body: HabitCreate, user: User = Depends(_get_user)):
    async with AsyncSessionLocal() as session:
        h = Habit(user_id=user.id, **body.model_dump())
        session.add(h)
        await session.commit()
        await session.refresh(h)
    return {"id": h.id, "name": h.name}

@router.post("/habits/{habit_id}/complete")
async def complete_habit(habit_id: int, notes: Optional[str] = None,
                         user: User = Depends(_get_user)):
    today = datetime.now(timezone.utc).date()
    async with AsyncSessionLocal() as session:
        h = await _get_habit(session, habit_id, user.id)
        # Check already logged
        existing = (await session.execute(
            select(HabitLog).where(
                HabitLog.habit_id == habit_id,
                HabitLog.completed_date == today,
            )
        )).scalar_one_or_none()
        if existing:
            return {"ok": True, "already_done": True}

        log = HabitLog(habit_id=habit_id, user_id=user.id,
                       completed_date=today, notes=notes)
        session.add(log)

        # Update streak
        yesterday = today.replace(day=today.day - 1) if today.day > 1 else today
        if h.last_completed_date and (today - h.last_completed_date).days == 1:
            h.current_streak = (h.current_streak or 0) + 1
        elif not h.last_completed_date or (today - h.last_completed_date).days > 1:
            h.current_streak = 1
        h.longest_streak = max(h.longest_streak or 0, h.current_streak)
        h.total_completions = (h.total_completions or 0) + 1
        h.last_completed_date = today
        await session.commit()
    return {"ok": True, "streak": h.current_streak}

@router.delete("/habits/{habit_id}")
async def delete_habit(habit_id: int, user: User = Depends(_get_user)):
    async with AsyncSessionLocal() as session:
        h = await _get_habit(session, habit_id, user.id)
        h.is_active = False
        await session.commit()
    return {"ok": True}


# ════ JOURNAL ════════════════════════════════════════════════════════════

class JournalCreate(BaseModel):
    entry_date: Optional[str] = None    # ISO date string, defaults to today
    content: str
    mood: Optional[int] = None
    energy: Optional[int] = None
    gratitude: Optional[str] = None
    intentions: Optional[str] = None
    wins: Optional[str] = None
    challenges: Optional[str] = None
    tags: list[str] = []

@router.get("/journal")
async def list_journal(
    limit: int = Query(30, le=100),
    user: User = Depends(_get_user)
):
    async with AsyncSessionLocal() as session:
        entries = (await session.execute(
            select(JournalEntry).where(JournalEntry.user_id == user.id)
            .order_by(JournalEntry.entry_date.desc()).limit(limit)
        )).scalars().all()
    return [_jentry(e) for e in entries]

@router.post("/journal")
async def create_journal(body: JournalCreate, user: User = Depends(_get_user)):
    entry_date = date.fromisoformat(body.entry_date) if body.entry_date else date.today()
    async with AsyncSessionLocal() as session:
        # Check if entry already exists for this date
        existing = (await session.execute(
            select(JournalEntry).where(
                JournalEntry.user_id == user.id,
                JournalEntry.entry_date == entry_date,
            )
        )).scalar_one_or_none()
        if existing:
            # Update existing
            existing.content = body.content
            if body.mood is not None: existing.mood = body.mood
            if body.energy is not None: existing.energy = body.energy
            existing.gratitude = body.gratitude
            existing.wins = body.wins
            existing.challenges = body.challenges
            existing.tags = body.tags
            await session.commit()
            return _jentry(existing)
        e = JournalEntry(
            user_id=user.id,
            entry_date=entry_date,
            content=body.content,
            mood=body.mood,
            energy=body.energy,
            gratitude=body.gratitude,
            intentions=body.intentions,
            wins=body.wins,
            challenges=body.challenges,
            tags=body.tags,
        )
        session.add(e)
        await session.commit()
        await session.refresh(e)
    return _jentry(e)

@router.get("/journal/{entry_id}")
async def get_journal(entry_id: int, user: User = Depends(_get_user)):
    async with AsyncSessionLocal() as session:
        e = (await session.execute(
            select(JournalEntry).where(JournalEntry.id == entry_id,
                                       JournalEntry.user_id == user.id)
        )).scalar_one_or_none()
        if not e:
            raise HTTPException(status_code=404)
    return _jentry(e)


# ════ HEALTH METRICS ══════════════════════════════════════════════════════

class HealthCreate(BaseModel):
    metric_type: str
    value: float
    unit: Optional[str] = None
    notes: Optional[str] = None
    recorded_at: Optional[str] = None

@router.get("/health")
async def list_health(
    metric_type: Optional[str] = Query(None),
    days: int = Query(30, le=365),
    user: User = Depends(_get_user)
):
    from datetime import timedelta
    since = datetime.now(timezone.utc) - timedelta(days=days)
    async with AsyncSessionLocal() as session:
        q = select(HealthMetric).where(
            HealthMetric.user_id == user.id,
            HealthMetric.recorded_at >= since,
        ).order_by(HealthMetric.recorded_at.desc())
        if metric_type:
            q = q.where(HealthMetric.metric_type == metric_type)
        items = (await session.execute(q)).scalars().all()
    return [_health(m) for m in items]

@router.post("/health")
async def log_health(body: HealthCreate, user: User = Depends(_get_user)):
    async with AsyncSessionLocal() as session:
        recorded = (datetime.fromisoformat(body.recorded_at)
                    if body.recorded_at else datetime.now(timezone.utc))
        m = HealthMetric(
            user_id=user.id,
            metric_type=body.metric_type,
            value=body.value,
            unit=body.unit,
            notes=body.notes,
            recorded_at=recorded,
        )
        session.add(m)
        await session.commit()
        await session.refresh(m)
    return _health(m)

@router.get("/summary")
async def life_summary(user: User = Depends(_get_user)):
    """Quick summary for the dashboard: habit completion, mood avg, health stats."""
    today = datetime.now(timezone.utc).date()
    from datetime import timedelta
    week_ago = datetime.now(timezone.utc) - timedelta(days=7)
    async with AsyncSessionLocal() as session:
        total_habits = (await session.execute(
            select(sqlfunc.count()).where(Habit.user_id == user.id, Habit.is_active == True)
        )).scalar()
        completed_today = (await session.execute(
            select(sqlfunc.count()).where(
                HabitLog.user_id == user.id, HabitLog.completed_date == today
            )
        )).scalar()
        avg_mood = (await session.execute(
            select(sqlfunc.avg(JournalEntry.mood)).where(
                JournalEntry.user_id == user.id,
                JournalEntry.entry_date >= week_ago.date(),
                JournalEntry.mood != None,
            )
        )).scalar()
        latest_weight = (await session.execute(
            select(HealthMetric).where(
                HealthMetric.user_id == user.id,
                HealthMetric.metric_type == "weight",
            ).order_by(HealthMetric.recorded_at.desc()).limit(1)
        )).scalar_one_or_none()
    return {
        "habits_total": total_habits or 0,
        "habits_completed_today": completed_today or 0,
        "avg_mood_7d": round(float(avg_mood), 1) if avg_mood else None,
        "latest_weight": {"value": float(latest_weight.value), "unit": latest_weight.unit}
                          if latest_weight else None,
    }


# ── Helpers ────────────────────────────────────────────────────────────────
async def _get_habit(session, habit_id: int, user_id: int) -> Habit:
    h = (await session.execute(
        select(Habit).where(Habit.id == habit_id, Habit.user_id == user_id)
    )).scalar_one_or_none()
    if not h:
        raise HTTPException(status_code=404)
    return h

def _jentry(e) -> dict:
    return {
        "id": e.id, "entry_date": str(e.entry_date), "content": e.content,
        "mood": e.mood, "energy": e.energy, "gratitude": e.gratitude,
        "wins": e.wins, "challenges": e.challenges, "tags": e.tags or [],
        "ai_summary": e.ai_summary,
    }

def _health(m) -> dict:
    return {
        "id": m.id, "metric_type": m.metric_type, "value": float(m.value),
        "unit": m.unit, "notes": m.notes,
        "recorded_at": m.recorded_at.isoformat() if m.recorded_at else None,
    }
