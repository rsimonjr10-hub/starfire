import json
import structlog
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timezone

from app.starfire.brain import StarfireBrain
from app.starfire.prompts import (
    PORTFOLIO_CONTEXT_TEMPLATE,
    TASK_CONTEXT_TEMPLATE,
    GOAL_CONTEXT_TEMPLATE,
    DATA_RESULT_TEMPLATE,
)
from app.models import User, PortfolioState, Task, Goal
from app.risk.engine import RiskEngine
from app.osiris.executor import OsirisExecutor
from app.events.publisher import EventPublisher
from app.integrations.lumiscapital import lumiscapital, formatter

logger = structlog.get_logger(__name__)

# Actions that fetch data from Lumiscapital before sending back to STARFIRE for analysis
LUMISCAPITAL_ACTIONS = {
    "GET_PRICE", "GET_MACRO", "GET_EARNINGS", "GET_EARNINGS_DETAIL",
    "GET_NEWS", "GET_SECTOR", "GET_SCOUT", "GET_PROFILE",
    "GET_MOVERS", "GET_INSIDER", "GET_SENATE",
}


class DecisionEngine:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.brain = StarfireBrain()
        self.risk = RiskEngine(db)
        self.osiris = OsirisExecutor(db)
        self.publisher = EventPublisher()

    async def process_message(self, user: User, message: str) -> str:
        context = await self._build_context(user)
        history = user.conversation_history or []

        result = await self.brain.think(message, history, context)

        if result["type"] == "chat":
            reply = result["content"]
        else:
            reply = await self._handle_action(user, result["content"], history, context)

        updated_history = self.brain.append_to_history(history, message, result["raw"])
        user.conversation_history = updated_history[-40:]

        return reply

    async def _handle_action(
        self, user: User, action: dict, history: list, context: Optional[str]
    ) -> str:
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

        if action_type in LUMISCAPITAL_ACTIONS:
            return await self._fetch_and_analyze(user, action, history, context)

        return action.get("message", "Action processed.")

    # ------------------------------------------------------------------ #
    # LUMISCAPITAL — fetch data then feed back to STARFIRE for analysis
    # ------------------------------------------------------------------ #

    async def _fetch_and_analyze(
        self, user: User, action: dict, history: list, context: Optional[str]
    ) -> str:
        action_type = action.get("action")
        raw_data = await self._fetch_lumiscapital(action_type, action)

        if raw_data is None:
            return "I couldn't retrieve that data right now. The market data service may be unavailable — please check your FMP API key."

        # Format data for immediate display
        formatted = self._format_lumiscapital_data(action_type, action, raw_data)

        # Also re-engage STARFIRE brain with the data for deeper analysis
        data_context = (context or "") + DATA_RESULT_TEMPLATE.format(
            action=action_type,
            data=formatted[:2000],
        )
        analysis = await self.brain.think(
            f"You just fetched this data. Provide a concise analysis and key takeaways.",
            history,
            data_context,
        )

        if analysis["type"] == "chat" and analysis["content"].strip():
            return formatted + "\n\n" + "---\n*STARFIRE Analysis*\n" + analysis["content"]
        return formatted

    async def _fetch_lumiscapital(self, action_type: str, action: dict):
        try:
            if action_type == "GET_PRICE":
                symbols = [s.strip() for s in action.get("symbols", action.get("symbol", "")).split(",") if s.strip()]
                if not symbols:
                    return None
                if len(symbols) == 1:
                    return await lumiscapital.get_quote(symbols[0])
                return await lumiscapital.get_quotes(symbols)

            if action_type == "GET_MACRO":
                indicators = await lumiscapital.get_economic_indicators()
                treasury = await lumiscapital.get_treasury_rates()
                return {"indicators": indicators, "treasury": treasury}

            if action_type == "GET_EARNINGS":
                days = int(action.get("days_ahead", 7))
                return await lumiscapital.get_earnings_calendar(days)

            if action_type == "GET_EARNINGS_DETAIL":
                symbol = action.get("symbol", "")
                surprises = await lumiscapital.get_earnings_surprises(symbol)
                estimates = await lumiscapital.get_analyst_estimates(symbol)
                return {"surprises": surprises, "estimates": estimates, "symbol": symbol}

            if action_type == "GET_NEWS":
                topic = action.get("topic", "general")
                limit = int(action.get("limit", 10))
                if topic == "general":
                    return await lumiscapital.get_general_news(limit)
                if topic == "political":
                    return await lumiscapital.get_political_news(limit)
                return await lumiscapital.get_stock_news(topic, limit)

            if action_type == "GET_SECTOR":
                return await lumiscapital.get_sector_performance()

            if action_type == "GET_SCOUT":
                criteria = action.get("criteria", {})
                if isinstance(criteria, str):
                    try:
                        criteria = json.loads(criteria)
                    except Exception:
                        criteria = {}
                return await lumiscapital.scout_stocks(**criteria)

            if action_type == "GET_PROFILE":
                symbol = action.get("symbol", "")
                profile = await lumiscapital.get_company_profile(symbol)
                metrics = await lumiscapital.get_key_metrics(symbol)
                return {"profile": profile, "metrics": metrics}

            if action_type == "GET_MOVERS":
                mover_type = action.get("type", "gainers")
                if mover_type == "gainers":
                    return await lumiscapital.get_gainers()
                if mover_type == "losers":
                    return await lumiscapital.get_losers()
                return await lumiscapital.get_most_active()

            if action_type == "GET_INSIDER":
                return await lumiscapital.get_insider_trades(action.get("symbol", ""))

            if action_type == "GET_SENATE":
                return await lumiscapital.get_senate_trades(action.get("symbol"))

        except Exception as e:
            logger.error("lumiscapital_fetch_error", action=action_type, error=str(e))
            return None

    def _format_lumiscapital_data(self, action_type: str, action: dict, data) -> str:
        if data is None:
            return "No data available."

        if action_type == "GET_PRICE":
            if isinstance(data, list):
                return "\n\n".join(formatter.format_quote(q) for q in data)
            if isinstance(data, dict):
                return formatter.format_quote(data)

        if action_type == "GET_MACRO":
            return formatter.format_macro_summary(
                data.get("indicators", []),
                data.get("treasury"),
            )

        if action_type == "GET_EARNINGS":
            return formatter.format_earnings_calendar(data)

        if action_type == "GET_EARNINGS_DETAIL":
            symbol = data.get("symbol", "")
            lines = [f"*{symbol} Earnings Detail*\n"]
            surprises = data.get("surprises", [])
            if surprises:
                lines.append("*Historical Surprises:*")
                for s in surprises[:5]:
                    actual = s.get("actualEarningResult", "N/A")
                    est = s.get("estimatedEarning", "N/A")
                    lines.append(f"  {s.get('date','')[:7]}: Actual `{actual}` vs Est `{est}`")
            estimates = data.get("estimates", [])
            if estimates:
                lines.append("\n*Analyst Estimates:*")
                for e in estimates[:3]:
                    lines.append(
                        f"  {e.get('date','')[:7]}: EPS est `{e.get('estimatedEpsAvg','N/A')}` "
                        f"| Rev est `${(e.get('estimatedRevenueAvg') or 0)/1e9:.2f}B`"
                    )
            return "\n".join(lines)

        if action_type == "GET_NEWS":
            topic = action.get("topic", "general")
            title = (
                "Market News" if topic == "general"
                else "Political / Senate News" if topic == "political"
                else f"{topic.upper()} News"
            )
            return formatter.format_news(data, title)

        if action_type == "GET_SECTOR":
            return formatter.format_sector_performance(data)

        if action_type == "GET_SCOUT":
            return formatter.format_scout_report(data, "Stock Scout Report")

        if action_type == "GET_PROFILE":
            profile = data.get("profile")
            metrics = data.get("metrics")
            if not profile:
                return "Company profile not found."
            return formatter.format_company_profile(profile, metrics)

        if action_type == "GET_MOVERS":
            mover_type = action.get("type", "gainers")
            titles = {"gainers": "Top Gainers", "losers": "Top Losers", "actives": "Most Active"}
            title = titles.get(mover_type, "Market Movers")
            return formatter.format_scout_report(data, title)

        if action_type == "GET_INSIDER":
            if not data:
                return "No insider trades found."
            lines = [f"*Insider Trades — {action.get('symbol','').upper()}*\n"]
            for t in data[:10]:
                lines.append(
                    f"`{t.get('transactionDate','')[:10]}` {t.get('reportingName','')} — "
                    f"{t.get('transactionType','')} `{t.get('securitiesTransacted','')}`"
                )
            return "\n".join(lines)

        if action_type == "GET_SENATE":
            if not data:
                return "No Senate trading disclosures found."
            lines = ["*Senate Trading Disclosures*\n"]
            for t in data[:15]:
                lines.append(
                    f"`{t.get('transactionDate','')[:10]}` *{t.get('senator','')}* — "
                    f"{t.get('asset_description','')} ({t.get('type','')})"
                )
            return "\n".join(lines)

        return str(data)[:1500]

    # ------------------------------------------------------------------ #
    # TRADE
    # ------------------------------------------------------------------ #

    async def _dispatch_trade(self, user: User, action: dict) -> str:
        symbol = action.get("symbol", "")
        side = action.get("side", "BUY")
        size_pct = float(action.get("size_pct", 0))

        if not symbol or not side or size_pct <= 0:
            return "I need a valid symbol, side (BUY/SELL), and position size to execute a trade."

        risk_result = await self.risk.validate_trade(user.id, symbol, side, size_pct)
        if not risk_result["allowed"]:
            return (
                f"Trade BLOCKED by risk engine: {risk_result['reason']}\n\n"
                "Your financial safety is my priority. Would you like to adjust the trade parameters?"
            )

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
        return f"Trade could not be executed: {execution.get('error', 'Unknown error')}"

    # ------------------------------------------------------------------ #
    # TASKS / GOALS / SPENDING
    # ------------------------------------------------------------------ #

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
            {"user_id": user.id, "category": record.category, "amount": float(record.amount)},
        )
        return f"Spending recorded: ${record.amount:.2f} in {record.category}"

    # ------------------------------------------------------------------ #
    # CONTEXT BUILDER
    # ------------------------------------------------------------------ #

    async def _build_context(self, user: User) -> Optional[str]:
        parts = []

        result = await self.db.execute(
            select(PortfolioState)
            .where(PortfolioState.user_id == user.id)
            .order_by(PortfolioState.snapshot_at.desc())
            .limit(1)
        )
        portfolio = result.scalar_one_or_none()
        if portfolio:
            parts.append(
                PORTFOLIO_CONTEXT_TEMPLATE.format(
                    total_value=float(portfolio.total_value or 0),
                    cash=float(portfolio.cash or 0),
                    daily_pnl=float(portfolio.daily_pnl or 0),
                    daily_pnl_pct=float(portfolio.daily_pnl_pct or 0),
                    positions=str(portfolio.positions or {}),
                )
            )

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
