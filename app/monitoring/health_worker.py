"""Periodic health check worker — runs every 15 minutes."""

import asyncio
import structlog
from app.monitoring.sentinel import sentinel
from app.monitoring import heartbeat

logger = structlog.get_logger(__name__)

INTERVAL_SECONDS = 900      # 15 minutes
SELFTEST_INTERVAL = 21600   # 6 hours — re-run selftest to catch post-deploy drift


class HealthWorker:
    def __init__(self):
        self._running = False
        self._cycles = 0

    async def start(self):
        self._running = True
        logger.info("health_worker_started", interval=INTERVAL_SECONDS)
        # First check 60s after startup (let the app fully boot)
        await asyncio.sleep(60)
        while self._running:
            try:
                await sentinel.health_check()
                await self._check_heartbeats()
                await self._check_google_tokens()
                self._cycles += 1
                # Re-run selftest every 6 hours to catch post-deploy schema/logic drift
                if self._cycles % (SELFTEST_INTERVAL // INTERVAL_SECONDS) == 0:
                    await self._run_selftest()
            except Exception as e:
                logger.error("health_worker_error", error=str(e))
            await asyncio.sleep(INTERVAL_SECONDS)

    async def _check_heartbeats(self):
        """Alert if any background worker loop has gone silent (crashed/hung)."""
        beats = heartbeat.check()
        stale = {k: v for k, v in beats.items() if v != "ok"}
        if stale:
            msg = (
                "🟠 <b>STARFIRE — Worker Stalled</b>\n\n"
                + "\n".join(f"• <b>{k}</b>: <code>{v}</code>" for k, v in stale.items())
                + "\n\nA background loop stopped beating — likely crashed or hung."
            )
            await sentinel._alert(msg)
            logger.error("worker_heartbeat_stale", stale=list(stale.keys()))
        else:
            logger.info("worker_heartbeats_ok", workers=list(beats.keys()))

    async def _check_google_tokens(self):
        """
        Proactively validate every connected user's Google OAuth token.
        Alerts the admin if any token is expired or revoked so the user can
        be notified to /connect_google BEFORE their next command fails silently.
        """
        try:
            from app.database import AsyncSessionLocal
            from app.models import User
            from sqlalchemy import select
            async with AsyncSessionLocal() as session:
                result = await session.execute(
                    select(User.id, User.telegram_id, User.first_name)
                    .where(User.google_token_json.isnot(None))
                )
                users = result.all()

            expired = []
            for user_id, telegram_id, first_name in users:
                try:
                    # Re-load in fresh session to avoid stale state
                    async with AsyncSessionLocal() as session:
                        u = await session.get(User, user_id)
                        if not u or not u.google_token_json:
                            continue
                    from app.integrations.gmail_service import GmailService
                    # GmailService.__init__ calls _maybe_refresh() which raises on expired token
                    GmailService(u.google_token_json)
                except Exception as e:
                    err = str(e).lower()
                    if any(k in err for k in ("invalid_grant", "token has been expired",
                                               "token has been revoked", "refresherror")):
                        expired.append((telegram_id, first_name or f"user#{user_id}"))
                        logger.warning("google_token_expired_proactive",
                                       user_id=user_id, telegram_id=telegram_id)

            if expired:
                names = ", ".join(n for _, n in expired)
                await sentinel._alert(
                    f"🔑 <b>Google Token Expired</b>\n\n"
                    f"The following user(s) have expired Google tokens and "
                    f"will get silent failures on Gmail/Calendar/Drive commands:\n"
                    f"<b>{names}</b>\n\n"
                    f"They need to /connect_google to re-link."
                )
        except Exception as e:
            logger.error("google_token_check_error", error=str(e))

    async def _run_selftest(self):
        """Re-run the self-test suite to catch post-deploy schema/logic drift."""
        try:
            from app.monitoring.selftest import selftest
            logger.info("periodic_selftest_starting")
            results = await selftest.run(alert=True)
            failures = [k for k, v in results.items() if v != "ok"]
            if failures:
                logger.error("periodic_selftest_failed", failures=failures)
            else:
                logger.info("periodic_selftest_passed", checks=len(results))
        except Exception as e:
            logger.error("periodic_selftest_error", error=str(e))

    async def stop(self):
        self._running = False
