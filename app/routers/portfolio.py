from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional
from decimal import Decimal

from app.database import get_db
from app.models import User, PortfolioState

router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])


class PortfolioUpdateRequest(BaseModel):
    telegram_id: int
    total_value: float
    cash: float
    positions: dict
    daily_pnl: Optional[float] = 0.0
    daily_pnl_pct: Optional[float] = 0.0


@router.get("/{telegram_id}")
async def get_portfolio(telegram_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.telegram_id == telegram_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    result = await db.execute(
        select(PortfolioState)
        .where(PortfolioState.user_id == user.id)
        .order_by(PortfolioState.snapshot_at.desc())
        .limit(1)
    )
    portfolio = result.scalar_one_or_none()
    if not portfolio:
        raise HTTPException(status_code=404, detail="No portfolio data")

    return {
        "user_id": user.id,
        "total_value": float(portfolio.total_value or 0),
        "cash": float(portfolio.cash or 0),
        "positions": portfolio.positions,
        "daily_pnl": float(portfolio.daily_pnl or 0),
        "daily_pnl_pct": float(portfolio.daily_pnl_pct or 0),
        "snapshot_at": portfolio.snapshot_at.isoformat() if portfolio.snapshot_at else None,
    }


@router.post("/update")
async def update_portfolio(req: PortfolioUpdateRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.telegram_id == req.telegram_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    snapshot = PortfolioState(
        user_id=user.id,
        total_value=req.total_value,
        cash=req.cash,
        positions=req.positions,
        daily_pnl=req.daily_pnl,
        daily_pnl_pct=req.daily_pnl_pct,
    )
    db.add(snapshot)
    return {"status": "updated"}
