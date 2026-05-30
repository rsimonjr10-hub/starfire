import structlog
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from datetime import datetime, timezone

from app.starfire.brain import StarfireBrain
from app.starfire.prompts import (
    PORTFOLIO_CONTEXT_TEMPLATE,
    TASK_CONTEXT_TEMPLATE,
    GOAL_CONTEXT_TEMPLATE,
)
from app.models import User, PortfolioState, Task, Goal
from app.risk.engine import RiskEngine
from app.osiris.executor import OsirisExecutor
from app.events.publisher import EventPublisher

logger = structlog.get_logger(__name__)


class DecisionEngine:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.brain = StarfireBrain()
        self.risk = RiskEngine(db)
        self.osiris = OsirisExecutor(db)
        self.publisher = EventPublisher()

    async def process_message(self, user: User, message: str) -> str:
        """
        Main entry point: takes a user message, runs STARFIRE brain,
        handles action dispatch, returns reply text for the user.
        """
        context = await self._build_context(user)
        history = user.conversation_history or []

        result = await self.brain.think(message, history, context)

        if result["type"] == "chat":
            reply = result["content"]
        else:
            reply = await self._handle_action(user, result["content"])

        # Persist conversation
        updated_history = self.brain.append_to_history(
            history, message, result["raw"]
        )
        user.conversation_history = updated_history[-40:]

        return reply

    async def _handle_action(self, user: User, action: dict) -> str:
        action_type = action.get("action", "IGNORE")

        if action_type == "IGNORE":
            return action.get("message", "Noted.")

        if action_type == "NOTIFY":
            return action.get("message", "")

        if action_type == "TRADE":
            return await self._dispatch_trade(user, action)

        if action_type == "CREATE_TASK":
            return await self._create_task(user, action)

        if action_type == "UPDATE_GOAL":
            return await self._update_goal(user, action)

        if action_type == "RECORD_SPENDING":
            return await self._record_spending(user, action)

        return action.get("message", "Action processed.")

    async def _dispatch_trade(self, user: User, action: dict) -> str:
        symbol = action.get("symbol", "")
        side = action.get("side", "BUY")
        size_pct = float(action.get("size_pct", 0))

        if not symbol or not side or size_pct <= 0:
            return "I need a valid symbol, side (BUY/SELL), and position size to execute a trade."

        # Risk check
        risk_result = await self.risk.validate_trade(user.id, symbol, side, size_pct)
        if not risk_result["allowed"]:
            return (
                f"Trade BLOCKED by risk engine: {risk_result['reason']}\n\n"
                "Your financial safety is my priority. Would you like to adjust the trade parameters?"
            )

        # Send to OSIRIS
        execution = await self.osiris.execute_trade(
            user_id=user.id,
            symbol=symbol,
            side=side,
            size_pct=size_pct,
            intent_payload=action,
        )

        if execution["status"] == "FILLED":
            await self.publisher.publish(
                "PORTFOLIO_EVENT",
                {
                    "user_id": user.id,
                    "event": "TRADE_FILLED",
                    "symbol": symbol,
                    "side": side,
                    "filled_price": execution["filled_price"],
                },
            )
            return (
                f"Trade executed by OSIRIS.\n"
                f"Symbol: {symbol}\n"
                f"Side: {side}\n"
                f"Filled at: ${execution['filled_price']:,.4f}\n"
                f"Slippage: {execution['slippage']*100:.3f}%\n"
                f"Order ID: {execution['order_id']}"
            )
        else:
            return f"Trade could not be executed: {execution.get('error', 'Unknown error')}"

    async def _create_task(self, user: User, action: dict) -> str:
        from app.models.task import Task as TaskModel

        task = TaskModel(
            user_id=user.id,
            title=action.get("title", action.get("message", "New Task")),
            description=action.get("description"),
            priority=action.get("priority", 5),
        )
        if action.get("due"):
            try:
                task.due_at = datetime.fromisoformat(action["due"].replace("Z", "+00:00"))
            except ValueError:
                pass

        self.db.add(task)
        await self.db.flush()
        return f"Task created: **{task.title}**\nPriority: {task.priority}/10"

    async def _update_goal(self, user: User, action: dict) -> str:
        from app.models.goal import Goal as GoalModel

        goal = GoalModel(
            user_id=user.id,
            title=action.get("title", action.get("message", "New Goal")),
            description=action.get("description"),
            goal_type=action.get("goal_type", "financial"),
            target_value=action.get("target_value"),
            unit=action.get("unit"),
        )
        if action.get("due"):
            try:
                goal.target_date = datetime.fromisoformat(action["due"].replace("Z", "+00:00"))
            except ValueError:
                pass

        self.db.add(goal)
        await self.db.flush()
        return (
            f"Goal set: **{goal.title}**\n"
            f"Type: {goal.goal_type}\n"
            f"Target: {goal.target_value} {goal.unit or ''}"
        )

    async def _record_spending(self, user: User, action: dict) -> str:
        from app.models.spending import SpendingRecord

        record = SpendingRecord(
            user_id=user.id,
            category=action.get("category", "General"),
            description=action.get("description", action.get("message")),
            amount=float(action.get("amount", 0)),
        )
        self.db.add(record)
        await self.db.flush()

        await self.publisher.publish(
            "SPENDING_EVENT",
            {
                "user_id": user.id,
                "category": record.category,
                "amount": float(record.amount),
            },
        )
        return f"Spending recorded: ${record.amount:.2f} in {record.category}"

    async def _build_context(self, user: User) -> Optional[str]:
        parts = []

        # Portfolio
        result = await self.db.execute(
            select(PortfolioState)
            .where(PortfolioState.user_id == user.id)
            .order_by(PortfolioState.snapshot_at.desc())
            .limit(1)
        )
        portfolio = result.scalar_one_or_none()
        if portfolio:
            positions_str = str(portfolio.positions) if portfolio.positions else "None"
            parts.append(
                PORTFOLIO_CONTEXT_TEMPLATE.format(
                    total_value=float(portfolio.total_value or 0),
                    cash=float(portfolio.cash or 0),
                    daily_pnl=float(portfolio.daily_pnl or 0),
                    daily_pnl_pct=float(portfolio.daily_pnl_pct or 0),
                    positions=positions_str,
                )
            )

        # Pending tasks
        result = await self.db.execute(
            select(Task)
            .where(Task.user_id == user.id, Task.status == "PENDING")
            .order_by(Task.priority.desc())
            .limit(5)
        )
        tasks = result.scalars().all()
        if tasks:
            task_lines = "\n".join(
                f"- [{t.priority}] {t.title}" + (f" (due {t.due_at.date()})" if t.due_at else "")
                for t in tasks
            )
            parts.append(TASK_CONTEXT_TEMPLATE.format(count=len(tasks), tasks=task_lines))

        # Active goals
        result = await self.db.execute(
            select(Goal)
            .where(Goal.user_id == user.id, Goal.status == "ACTIVE")
            .limit(5)
        )
        goals = result.scalars().all()
        if goals:
            goal_lines = "\n".join(
                f"- {g.title}: {g.current_value}/{g.target_value} {g.unit or ''}"
                for g in goals
            )
            parts.append(GOAL_CONTEXT_TEMPLATE.format(goals=goal_lines))

        return "\n".join(parts) if parts else None
