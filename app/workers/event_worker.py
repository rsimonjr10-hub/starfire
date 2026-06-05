import structlog
from app.events.consumer import EventConsumer
from app.events.types import EventType
from app.monitoring.sentinel import sentinel

logger = structlog.get_logger(__name__)


class EventWorker:
    """
    Listens to all Redis event channels and routes them to handlers.
    STARFIRE consumes events to decide if a proactive notification is needed.
    """

    def __init__(self):
        self.consumer = EventConsumer()
        self._register_handlers()

    def _register_handlers(self) -> None:
        self.consumer.register(EventType.MARKET_EVENT, self._on_market_event)
        self.consumer.register(EventType.PORTFOLIO_EVENT, self._on_portfolio_event)
        self.consumer.register(EventType.SPENDING_EVENT, self._on_spending_event)
        self.consumer.register(EventType.TASK_EVENT, self._on_task_event)
        self.consumer.register(EventType.TRADE_EVENT, self._on_trade_event)

    async def start(self) -> None:
        await self.consumer.start()

    async def stop(self) -> None:
        await self.consumer.stop()

    async def _on_market_event(self, event: dict) -> None:
        logger.debug("market_event", payload=event.get("payload"))

    async def _on_portfolio_event(self, event: dict) -> None:
        payload = event.get("payload", {})
        logger.info("portfolio_event", event_name=payload.get("event"))

        if payload.get("event") == "TRADE_FILLED":
            await self._notify_user(
                user_id=payload.get("user_id"),
                message=(
                    f"Trade filled: {payload.get('side')} {payload.get('symbol')} "
                    f"at ${payload.get('filled_price', 0):,.4f}"
                ),
            )

    async def _on_spending_event(self, event: dict) -> None:
        payload = event.get("payload", {})
        logger.info("spending_event", category=payload.get("category"), amount=payload.get("amount"))

    async def _on_task_event(self, event: dict) -> None:
        logger.info("task_event", payload=event.get("payload"))

    async def _on_trade_event(self, event: dict) -> None:
        logger.info("trade_event", payload=event.get("payload"))

    async def _notify_user(self, user_id: int, message: str) -> None:
        if not user_id:
            return
        try:
            from sqlalchemy import select
            from app.database import AsyncSessionLocal
            from app.models import User
            from app.telegram.bot import send_notification

            async with AsyncSessionLocal() as session:
                result = await session.execute(select(User).where(User.id == user_id))
                user = result.scalar_one_or_none()
                if user:
                    await send_notification(user.telegram_id, message)
        except Exception as e:
            await sentinel.capture(e, category="event_worker", context={"user_id": user_id})
