from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional

from app.database import get_db
from app.models import User
from app.models.trade import Trade

router = APIRouter(prefix="/api/trades", tags=["trades"])


@router.get("/{telegram_id}")
async def get_trades(
    telegram_id: int,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.telegram_id == telegram_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    result = await db.execute(
        select(Trade)
        .where(Trade.user_id == user.id)
        .order_by(Trade.created_at.desc())
        .limit(limit)
    )
    trades = result.scalars().all()

    return [
        {
            "id": t.id,
            "symbol": t.symbol,
            "side": t.side,
            "size_pct": float(t.size_pct),
            "quantity": float(t.quantity) if t.quantity else None,
            "filled_price": float(t.filled_price) if t.filled_price else None,
            "slippage": float(t.slippage) if t.slippage else None,
            "status": t.status,
            "block_reason": t.block_reason,
            "created_at": t.created_at.isoformat() if t.created_at else None,
            "executed_at": t.executed_at.isoformat() if t.executed_at else None,
        }
        for t in trades
    ]
