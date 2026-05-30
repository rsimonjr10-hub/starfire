import structlog
from datetime import datetime, timezone, date
from decimal import Decimal
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.config import settings
from app.models.trade import Trade
from app.models.portfolio import PortfolioState

logger = structlog.get_logger(__name__)


class RiskEngine:
    """
    Hard boundary enforcement layer.
    All rules are checked BEFORE a trade reaches OSIRIS.
    Violations result in a complete block — no exceptions.
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.max_daily_loss_pct = settings.risk_max_daily_loss_pct
        self.max_position_size_pct = settings.risk_max_position_size_pct
        self.max_trades_per_day = settings.risk_max_trades_per_day

    async def validate_trade(
        self,
        user_id: int,
        symbol: str,
        side: str,
        size_pct: float,
    ) -> dict:
        """
        Returns: {"allowed": bool, "reason": str}
        Checks all risk rules in sequence. First violation blocks the trade.
        """
        # Sequential short-circuit: stop at first violation
        size_check = self._check_position_size(size_pct)
        if not size_check["passed"]:
            logger.warning("risk_block", user_id=user_id, symbol=symbol, rule=size_check["rule"], reason=size_check["reason"])
            return {"allowed": False, "reason": size_check["reason"]}

        trade_check = await self._check_daily_trade_count(user_id)
        if not trade_check["passed"]:
            logger.warning("risk_block", user_id=user_id, symbol=symbol, rule=trade_check["rule"], reason=trade_check["reason"])
            return {"allowed": False, "reason": trade_check["reason"]}

        loss_check = await self._check_daily_loss(user_id)
        if not loss_check["passed"]:
            logger.warning("risk_block", user_id=user_id, symbol=symbol, rule=loss_check["rule"], reason=loss_check["reason"])
            return {"allowed": False, "reason": loss_check["reason"]}

        logger.info("risk_passed", user_id=user_id, symbol=symbol, side=side, size_pct=size_pct)
        return {"allowed": True, "reason": ""}

    def _check_position_size(self, size_pct: float) -> dict:
        if size_pct > self.max_position_size_pct:
            return {
                "passed": False,
                "rule": "MAX_POSITION_SIZE",
                "reason": (
                    f"Position size {size_pct:.1f}% exceeds the maximum allowed "
                    f"{self.max_position_size_pct:.1f}% per trade."
                ),
            }
        if size_pct <= 0:
            return {
                "passed": False,
                "rule": "MIN_POSITION_SIZE",
                "reason": "Position size must be greater than 0%.",
            }
        return {"passed": True, "rule": "MAX_POSITION_SIZE", "reason": ""}

    async def _check_daily_trade_count(self, user_id: int) -> dict:
        today_start = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        result = await self.db.execute(
            select(func.count(Trade.id)).where(
                Trade.user_id == user_id,
                Trade.created_at >= today_start,
                Trade.status.in_(["FILLED", "PENDING"]),
            )
        )
        count = result.scalar() or 0

        if count >= self.max_trades_per_day:
            return {
                "passed": False,
                "rule": "MAX_TRADES_PER_DAY",
                "reason": (
                    f"Daily trade limit reached ({count}/{self.max_trades_per_day}). "
                    "No more trades allowed today."
                ),
            }
        return {"passed": True, "rule": "MAX_TRADES_PER_DAY", "reason": ""}

    async def _check_daily_loss(self, user_id: int) -> dict:
        result = await self.db.execute(
            select(PortfolioState)
            .where(PortfolioState.user_id == user_id)
            .order_by(PortfolioState.snapshot_at.desc())
            .limit(1)
        )
        portfolio = result.scalar_one_or_none()

        if portfolio and portfolio.daily_pnl_pct is not None:
            loss_pct = float(portfolio.daily_pnl_pct)
            if loss_pct < 0 and abs(loss_pct) >= self.max_daily_loss_pct:
                return {
                    "passed": False,
                    "rule": "MAX_DAILY_LOSS",
                    "reason": (
                        f"Daily loss of {abs(loss_pct):.2f}% has reached the maximum allowed "
                        f"{self.max_daily_loss_pct:.2f}%. Trading suspended for today."
                    ),
                }

        return {"passed": True, "rule": "MAX_DAILY_LOSS", "reason": ""}

    def get_limits_summary(self) -> dict:
        return {
            "max_daily_loss_pct": self.max_daily_loss_pct,
            "max_position_size_pct": self.max_position_size_pct,
            "max_trades_per_day": self.max_trades_per_day,
        }
