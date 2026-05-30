#!/usr/bin/env python3
"""
Seed a test portfolio for a user.
Usage: TELEGRAM_ID=12345 python scripts/seed_portfolio.py
"""
import asyncio
import os
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_ID = int(os.environ.get("TELEGRAM_ID", "0"))


async def main():
    import sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    from app.database import AsyncSessionLocal, init_db
    from app.models import User, PortfolioState

    await init_db()

    async with AsyncSessionLocal() as session:
        from sqlalchemy import select

        result = await session.execute(
            select(User).where(User.telegram_id == TELEGRAM_ID)
        )
        user = result.scalar_one_or_none()

        if not user:
            user = User(
                telegram_id=TELEGRAM_ID,
                username="test_user",
                first_name="Test",
                conversation_history=[],
                preferences={},
            )
            session.add(user)
            await session.flush()

        portfolio = PortfolioState(
            user_id=user.id,
            total_value=50_000.00,
            cash=15_000.00,
            positions={
                "AAPL": {"qty": 50, "avg_price": 175.00, "current_price": 185.50},
                "MSFT": {"qty": 20, "avg_price": 400.00, "current_price": 415.20},
                "NVDA": {"qty": 10, "avg_price": 800.00, "current_price": 875.00},
            },
            daily_pnl=1250.00,
            daily_pnl_pct=2.56,
        )
        session.add(portfolio)
        await session.commit()
        print(f"Portfolio seeded for user {TELEGRAM_ID}")


asyncio.run(main())
