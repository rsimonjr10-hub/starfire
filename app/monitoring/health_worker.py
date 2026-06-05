"""Periodic health check worker — runs every 15 minutes."""

import asyncio
import structlog
from app.monitoring.sentinel import sentinel
from app.monitoring import heartbeat

logger = structlog.get_logger(__name__)

INTERVAL_SECONDS = 900  # 15 minutes


class HealthWorker:
    def __init__(self):
        self._running = False
        self._task: asyncio.Task = None

    async def start(self):
        self._running = True
        logger.info("health_worker_started", interval=INTERVAL_SECONDS)
        # First check 60s after startup (let the app fully boot)
        await asyncio.sleep(60)
        while self._running:
            try:
                await sentinel.health_check()
                await self._check_heartbeats()
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

    async def stop(self):
        self._running = False
