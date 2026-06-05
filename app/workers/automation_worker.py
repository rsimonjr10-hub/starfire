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

                        # Email watches: check Gmail for pending watches
                        await self._check_email_watches(session, user_fresh, now)
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

    async def _check_email_watches(self, session, user, now: datetime) -> None:
        """Poll Gmail for each active email watch; notify and deactivate on match."""
        if not user.google_token_json:
            return

        from sqlalchemy import select as sa_select
        from app.models.email_watch import EmailWatch

        result = await session.execute(
            sa_select(EmailWatch).where(
                EmailWatch.user_id == user.id,
                EmailWatch.is_active == True,
            )
        )
        watches = result.scalars().all()
        if not watches:
            return

        try:
            from app.integrations.gmail_service import GmailService
            gmail = GmailService(user.google_token_json)
        except Exception as e:
            logger.error("email_watch_gmail_init_error", user_id=user.id, error=str(e))
            return

        for watch in watches:
            try:
                watch.last_checked_at = now
                # Search only emails received after the watch was created.
                # Gmail's after: accepts a unix timestamp (epoch seconds).
                created = watch.created_at
                if created.tzinfo is None:
                    created = created.replace(tzinfo=timezone.utc)
                after_ts = int(created.timestamp())
                query = f"{watch.query} after:{after_ts}"

                # search() returns summary dicts with id/from/subject already
                messages = gmail.search(query, max_results=1)
                if not messages:
                    continue

                msg = messages[0]
                subject = msg.get("subject") or "(no subject)"
                sender = msg.get("from") or "unknown sender"

                watch.is_active = False
                watch.found_at = now
                watch.matched_subject = subject[:512]
                watch.matched_from = sender[:256]
                await session.commit()

                await send_notification(
                    user.telegram_id,
                    f"Email alert — *{watch.description}*\n\n"
                    f"From: {sender}\n"
                    f"Subject: {subject}",
                )
                logger.info("email_watch_triggered", user_id=user.id, watch_id=watch.id)
            except Exception as e:
                logger.error("email_watch_check_error", user_id=user.id, watch_id=watch.id, error=str(e))
