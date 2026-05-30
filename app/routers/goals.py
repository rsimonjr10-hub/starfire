from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.models import User, Goal

router = APIRouter(prefix="/api/goals", tags=["goals"])


@router.get("/{telegram_id}")
async def get_goals(telegram_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.telegram_id == telegram_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    result = await db.execute(
        select(Goal)
        .where(Goal.user_id == user.id, Goal.status == "ACTIVE")
        .order_by(Goal.created_at.desc())
    )
    goals = result.scalars().all()

    return [
        {
            "id": g.id,
            "title": g.title,
            "goal_type": g.goal_type,
            "target_value": float(g.target_value) if g.target_value else None,
            "current_value": float(g.current_value) if g.current_value else 0,
            "unit": g.unit,
            "status": g.status,
            "target_date": g.target_date.isoformat() if g.target_date else None,
            "progress_pct": (
                min(100, float(g.current_value or 0) / float(g.target_value) * 100)
                if g.target_value and float(g.target_value) > 0
                else 0
            ),
        }
        for g in goals
    ]


@router.patch("/{goal_id}/progress")
async def update_goal_progress(
    goal_id: int,
    current_value: float,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Goal).where(Goal.id == goal_id))
    goal = result.scalar_one_or_none()
    if not goal:
        raise HTTPException(status_code=404, detail="Goal not found")

    goal.current_value = current_value
    if goal.target_value and current_value >= float(goal.target_value):
        goal.status = "ACHIEVED"

    return {"status": "updated", "achieved": goal.status == "ACHIEVED"}
