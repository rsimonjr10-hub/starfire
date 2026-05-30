import json
import redis.asyncio as aioredis
import structlog
from datetime import datetime, timezone
from app.config import settings

logger = structlog.get_logger(__name__)

_redis_pool = None


async def get_redis() -> aioredis.Redis:
    global _redis_pool
    if _redis_pool is None:
        _redis_pool = aioredis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
        )
    return _redis_pool


class EventPublisher:
    async def publish(self, event_type: str, payload: dict) -> None:
        message = {
            "event_type": event_type,
            "payload": payload,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        try:
            redis = await get_redis()
            await redis.publish(event_type, json.dumps(message))
            logger.info("event_published", event_type=event_type)
        except Exception as e:
            logger.error("event_publish_error", event_type=event_type, error=str(e))
