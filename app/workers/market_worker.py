import asyncio
import structlog
from datetime import datetime, timezone
from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models import User, PortfolioState
from app.events.publisher import EventPublisher

logger = structlog.get_logger(__name__)


class MarketWorker:
    """
    Periodically updates portfolio snapshots and publishes MARKET_EVENTs.
    Runs as a background task — does not make decisions.
    """

    def __init__(self, interval_seconds: int = 300):
        self.interval = interval_seconds
        self.publisher = EventPublisher()
        self._running = False

    async def start(self) -> None:
        self._running = True
        logger.info("market_worker_started", interval=self.interval)
        while self._running:
            try:
                await self._tick()
            except Exception as e:
                logger.error("market_worker_error", error=str(e))
            await asyncio.sleep(self.interval)

    async def stop(self) -> None:
        self._running = False

    async def _tick(self) -> None:
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(User).where(User.is_active == True))
            users = result.scalars().all()

            for user in users:
                await self._refresh_portfolio(session, user)

        await self.publisher.publish(
            "MARKET_EVENT",
            {
                "event": "MARKET_TICK",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )

    async def _refresh_portfolio(self, session, user: User) -> None:
        result = await session.execute(
            select(PortfolioState)
            .where(PortfolioState.user_id == user.id)
            .order_by(PortfolioState.snapshot_at.desc())
            .limit(1)
        )
        existing = result.scalar_one_or_none()

        if not existing:
            snapshot = PortfolioState(
                user_id=user.id,
                total_value=10_000.00,
                cash=10_000.00,
                positions={},
                daily_pnl=0,
                daily_pnl_pct=0,
            )
            session.add(snapshot)
            await session.flush()

            await self.publisher.publish(
                "PORTFOLIO_EVENT",
                {
                    "user_id": user.id,
                    "event": "PORTFOLIO_INITIALIZED",
                    "total_value": 10_000.00,
                },
            )
