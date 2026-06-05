"""
Automation Worker — evaluates all active automation rules on a schedule.
Runs every 15 minutes by default.
"""
import asyncio
import structlog
from datetime import datetime, timezone, timedelta
from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.user import User
from app.services.automation_runner import evaluate_all
from app.telegram.bot import send_notification

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

        now = datetime.now(timezone.utc)
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

                        # Proactive idle nudge: if silent for 8+ hours during business hours
                        await self._maybe_nudge(session, user_fresh, now)
            except Exception as e:
                logger.error("automation_user_error", user_id=user.id, error=str(e))

    async def _maybe_nudge(self, session, user, now: datetime) -> None:
        """Send a proactive check-in if the user has been silent for 8+ business hours."""
        if not user.updated_at:
            return
        last_active = user.updated_at.replace(tzinfo=timezone.utc) if user.updated_at.tzinfo is None else user.updated_at
        hours_idle = (now - last_active).total_seconds() / 3600
        if hours_idle < 8:
            return

        # Only nudge during business hours (9am–6pm ET = 13–22 UTC)
        if not (13 <= now.hour <= 22):
            return

        # Max one nudge per calendar day (stored in user preferences)
        today_str = now.strftime("%Y-%m-%d")
        prefs = user.preferences or {}
        if prefs.get("last_idle_nudge") == today_str:
            return

        try:
            await send_notification(
                user.telegram_id,
                "I've been quiet for a while. What's on your plate? "
                "I can check your tasks, inbox, pull data, or draft something — just say the word.",
            )
            prefs["last_idle_nudge"] = today_str
            user.preferences = prefs
            await session.commit()
            logger.info("idle_nudge_sent", user_id=user.id)
        except Exception as e:
            logger.error("idle_nudge_error", user_id=user.id, error=str(e))
