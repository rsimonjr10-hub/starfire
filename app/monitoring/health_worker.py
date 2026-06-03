"""Periodic health check worker — runs every 15 minutes."""

import asyncio
import structlog
from app.monitoring.sentinel import sentinel

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
            except Exception as e:
                logger.error("health_worker_error", error=str(e))
            await asyncio.sleep(INTERVAL_SECONDS)

    async def stop(self):
        self._running = False
