"""
Automation Worker — evaluates all active automation rules on a schedule.
Runs every 15 minutes by default.
"""
import asyncio
import structlog
from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.user import User
from app.services.automation_runner import evaluate_all

logger = structlog.get_logger(__name__)


class AutomationWorker:
    def __init__(self, interval_seconds: int = 900):
        self.interval = interval_seconds
        self._running = False

    async def start(self):
        self._running = True
        logger.info("automation_worker_started", interval=self.interval)
        while self._running:
            try:
                await self._tick()
            except Exception as e:
                logger.error("automation_worker_error", error=str(e))
            await asyncio.sleep(self.interval)

    async def stop(self):
        self._running = False

    async def _tick(self):
        async with AsyncSessionLocal() as session:
            users = (await session.execute(
                select(User).where(User.is_active == True)
            )).scalars().all()

        for user in users:
            try:
                async with AsyncSessionLocal() as session:
                    user_fresh = (await session.execute(
                        select(User).where(User.id == user.id)
                    )).scalar_one_or_none()
                    if user_fresh:
                        fired = await evaluate_all(session, user_fresh)
                        if fired:
                            logger.info("automations_fired",
                                        user_id=user.id,
                                        count=len(fired),
                                        names=[f["automation"] for f in fired])
            except Exception as e:
                logger.error("automation_user_error", user_id=user.id, error=str(e))
