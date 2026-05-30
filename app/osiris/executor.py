import structlog
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.trade import Trade
from app.models.portfolio import PortfolioState
from app.models.event_log import ExecutionLog
from app.osiris.broker import get_broker

logger = structlog.get_logger(__name__)


class OsirisExecutor:
    """
    OSIRIS: Pure execution engine.

    OSIRIS does NOT:
    - Make decisions
    - Talk to the user
    - Modify trade parameters

    OSIRIS ONLY:
    - Receives validated trade intents from STARFIRE
    - Submits orders to the broker
    - Records results
    - Returns execution status
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.broker = get_broker()

    async def execute_trade(
        self,
        user_id: int,
        symbol: str,
        side: str,
        size_pct: float,
        intent_payload: dict,
    ) -> dict:
        """
        Execute a validated trade intent.
        Returns execution result dict.
        """
        trade = Trade(
            user_id=user_id,
            symbol=symbol,
            side=side,
            size_pct=size_pct,
            status="PENDING",
            intent_payload=intent_payload,
        )
        self.db.add(trade)
        await self.db.flush()

        try:
            # Determine quantity from portfolio
            quantity = await self._calculate_quantity(user_id, symbol, size_pct)

            result = await self.broker.submit_order(
                symbol=symbol,
                side=side,
                quantity=quantity,
            )

            trade.filled_price = result.filled_price
            trade.quantity = result.quantity
            trade.slippage = result.slippage
            trade.broker_order_id = result.order_id
            trade.status = "FILLED"
            trade.executed_at = result.executed_at
            trade.result_payload = {
                "filled_price": result.filled_price,
                "quantity": result.quantity,
                "slippage": result.slippage,
                "order_id": result.order_id,
            }

            await self._log_execution(
                trade_id=trade.id,
                user_id=user_id,
                action="TRADE_FILL",
                status="SUCCESS",
                details=trade.result_payload,
            )

            logger.info(
                "osiris_trade_filled",
                user_id=user_id,
                symbol=symbol,
                side=side,
                filled_price=result.filled_price,
                order_id=result.order_id,
            )

            return {
                "status": "FILLED",
                "filled_price": result.filled_price,
                "quantity": result.quantity,
                "slippage": result.slippage,
                "order_id": result.order_id,
            }

        except Exception as e:
            trade.status = "REJECTED"
            trade.block_reason = str(e)
            await self._log_execution(
                trade_id=trade.id,
                user_id=user_id,
                action="TRADE_FILL",
                status="ERROR",
                details={},
                error=str(e),
            )
            logger.error("osiris_trade_error", user_id=user_id, symbol=symbol, error=str(e))
            return {"status": "REJECTED", "error": str(e)}

    async def _calculate_quantity(
        self, user_id: int, symbol: str, size_pct: float
    ) -> float:
        result = await self.db.execute(
            select(PortfolioState)
            .where(PortfolioState.user_id == user_id)
            .order_by(PortfolioState.snapshot_at.desc())
            .limit(1)
        )
        portfolio = result.scalar_one_or_none()

        if portfolio and portfolio.total_value:
            portfolio_value = float(portfolio.total_value)
        else:
            portfolio_value = 10_000.0  # default paper portfolio

        trade_value = portfolio_value * (size_pct / 100)
        price = await self.broker.get_quote(symbol)

        if price <= 0:
            return 1.0

        quantity = trade_value / price
        return round(quantity, 8)

    async def _log_execution(
        self,
        trade_id: int,
        user_id: int,
        action: str,
        status: str,
        details: dict,
        error: str = None,
    ) -> None:
        log = ExecutionLog(
            trade_id=trade_id,
            user_id=user_id,
            action=action,
            status=status,
            details=details,
            error_message=error,
        )
        self.db.add(log)
