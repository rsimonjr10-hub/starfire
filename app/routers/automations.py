"""
Automation Engine API — CRUD for trigger-based automation rules.
Auth: HMAC dashboard token.
"""
import hashlib
import hmac
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import AsyncSessionLocal
from app.models.user import User
from app.models.automation import Automation, AutomationRun

router = APIRouter(prefix="/api/automations", tags=["automations"])


def _make_token(tid: int) -> str:
    return hmac.new(settings.app_secret_key.encode(), str(tid).encode(),
                    hashlib.sha256).hexdigest()[:32]

async def _get_user(token: str = Query(...)) -> User:
    async with AsyncSessionLocal() as session:
        for u in (await session.execute(select(User).where(User.is_active == True))).scalars().all():
            if hmac.compare_digest(_make_token(u.telegram_id), token):
                return u
    raise HTTPException(status_code=403, detail="Invalid token")


class AutomationCreate(BaseModel):
    name: str
    description: Optional[str] = None
    trigger_type: str
    trigger_config: dict = {}
    action_type: str
    action_config: dict = {}

class AutomationUpdate(BaseModel):
    name: Optional[str] = None
    is_active: Optional[bool] = None
    trigger_config: Optional[dict] = None
    action_config: Optional[dict] = None


PRESET_AUTOMATIONS = [
    {
        "name": "Overspending Alert",
        "description": "Alert when monthly food spending exceeds $500",
        "trigger_type": "spending_threshold",
        "trigger_config": {"category": "food", "threshold": 500, "period": "monthly"},
        "action_type": "notify",
        "action_config": {"message": "⚠️ Your food spending has exceeded $500 this month!"},
    },
    {
        "name": "Weekly Briefing",
        "description": "Generate an AI briefing every Monday",
        "trigger_type": "schedule",
        "trigger_config": {"frequency": "weekly"},
        "action_type": "generate_report",
        "action_config": {"briefing_type": "weekly"},
    },
    {
        "name": "Overdue Task Alert",
        "description": "Notify when tasks are overdue by 3+ days",
        "trigger_type": "task_overdue",
        "trigger_config": {"days": 3},
        "action_type": "notify",
        "action_config": {"message": "📋 You have overdue tasks — check your task list!"},
    },
    {
        "name": "Journal Reminder",
        "description": "Remind to journal if missing for 2+ days",
        "trigger_type": "journal_missing",
        "trigger_config": {"days": 2},
        "action_type": "notify",
        "action_config": {"message": "📖 You haven't journaled in a few days. Take 5 minutes to reflect."},
    },
]


@router.get("")
async def list_automations(user: User = Depends(_get_user)):
    async with AsyncSessionLocal() as session:
        items = (await session.execute(
            select(Automation).where(Automation.user_id == user.id)
            .order_by(Automation.created_at.desc())
        )).scalars().all()
    return [_serialize(a) for a in items]

@router.post("")
async def create_automation(body: AutomationCreate, user: User = Depends(_get_user)):
    async with AsyncSessionLocal() as session:
        a = Automation(user_id=user.id, **body.model_dump())
        session.add(a)
        await session.commit()
        await session.refresh(a)
    return _serialize(a)

@router.post("/presets/{preset_index}")
async def install_preset(preset_index: int, user: User = Depends(_get_user)):
    if preset_index < 0 or preset_index >= len(PRESET_AUTOMATIONS):
        raise HTTPException(status_code=400, detail="Invalid preset index")
    preset = PRESET_AUTOMATIONS[preset_index]
    async with AsyncSessionLocal() as session:
        a = Automation(user_id=user.id, **preset)
        session.add(a)
        await session.commit()
        await session.refresh(a)
    return _serialize(a)

@router.get("/presets")
async def list_presets():
    return [{"index": i, **p} for i, p in enumerate(PRESET_AUTOMATIONS)]

@router.put("/{auto_id}")
async def update_automation(auto_id: int, body: AutomationUpdate, user: User = Depends(_get_user)):
    async with AsyncSessionLocal() as session:
        a = await _get_auto(session, auto_id, user.id)
        for k, v in body.model_dump(exclude_none=True).items():
            setattr(a, k, v)
        await session.commit()
    return {"ok": True}

@router.delete("/{auto_id}")
async def delete_automation(auto_id: int, user: User = Depends(_get_user)):
    async with AsyncSessionLocal() as session:
        a = await _get_auto(session, auto_id, user.id)
        await session.delete(a)
        await session.commit()
    return {"ok": True}

@router.post("/{auto_id}/run")
async def run_automation_now(auto_id: int, user: User = Depends(_get_user)):
    """Manually trigger an automation rule."""
    async with AsyncSessionLocal() as session:
        a = await _get_auto(session, auto_id, user.id)
        result = await _fire_action_now(session, user, a)
    return {"ok": True, "result": result}

@router.get("/{auto_id}/history")
async def automation_history(auto_id: int, user: User = Depends(_get_user)):
    async with AsyncSessionLocal() as session:
        runs = (await session.execute(
            select(AutomationRun).where(AutomationRun.automation_id == auto_id)
            .order_by(AutomationRun.ran_at.desc()).limit(20)
        )).scalars().all()
    return [
        {"id": r.id, "status": r.status, "triggered_by": r.triggered_by,
         "result": r.result, "error": r.error,
         "ran_at": r.ran_at.isoformat() if r.ran_at else None}
        for r in runs
    ]


async def _get_auto(session, auto_id: int, user_id: int) -> Automation:
    a = (await session.execute(
        select(Automation).where(Automation.id == auto_id, Automation.user_id == user_id)
    )).scalar_one_or_none()
    if not a:
        raise HTTPException(status_code=404)
    return a

async def _fire_action_now(session, user, auto: Automation) -> dict:
    from app.services.automation_runner import _fire_action
    return await _fire_action(session, user, auto, "manual")

def _serialize(a: Automation) -> dict:
    return {
        "id": a.id, "name": a.name, "description": a.description,
        "is_active": a.is_active, "trigger_type": a.trigger_type,
        "trigger_config": a.trigger_config, "action_type": a.action_type,
        "action_config": a.action_config, "run_count": a.run_count,
        "last_triggered_at": a.last_triggered_at.isoformat() if a.last_triggered_at else None,
    }
