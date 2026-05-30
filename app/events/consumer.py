import json
import asyncio
import structlog
import redis.asyncio as aioredis
from typing import Callable, Awaitable
from app.config import settings
from app.events.types import EventType

logger = structlog.get_logger(__name__)


class EventConsumer:
    """
    Redis pub/sub consumer.
    Subscribes to event channels and dispatches to registered handlers.
    """

    def __init__(self):
        self._handlers: dict[str, list[Callable]] = {}
        self._running = False

    def register(self, event_type: str, handler: Callable[..., Awaitable[None]]) -> None:
        if event_type not in self._handlers:
            self._handlers[event_type] = []
        self._handlers[event_type].append(handler)

    async def start(self) -> None:
        self._running = True
        channels = list(self._handlers.keys())
        if not channels:
            logger.warning("event_consumer_no_channels")
            return

        redis = aioredis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
        )
        pubsub = redis.pubsub()
        await pubsub.subscribe(*channels)
        logger.info("event_consumer_started", channels=channels)

        try:
            while self._running:
                message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if message and message["type"] == "message":
                    await self._dispatch(message)
                await asyncio.sleep(0.01)
        finally:
            await pubsub.unsubscribe(*channels)
            await redis.aclose()

    async def stop(self) -> None:
        self._running = False

    async def _dispatch(self, message: dict) -> None:
        channel = message["channel"]
        try:
            data = json.loads(message["data"])
        except (json.JSONDecodeError, KeyError):
            return

        handlers = self._handlers.get(channel, [])
        for handler in handlers:
            try:
                await handler(data)
            except Exception as e:
                logger.error("event_handler_error", channel=channel, error=str(e))
