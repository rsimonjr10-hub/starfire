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
from app.integrations.osiris_bridge import osiris_bridge
from app.integrations.osiris_telegram import osiris_telegram

logger = structlog.get_logger(__name__)

LUMISCAPITAL_ACTIONS = {
    "GET_PRICE", "GET_MACRO", "GET_EARNINGS", "GET_EARNINGS_DETAIL",
    "GET_NEWS", "GET_SECTOR", "GET_SCOUT", "GET_PROFILE",
    "GET_MOVERS", "GET_INSIDER", "GET_SENATE",
}

GOOGLE_ACTIONS = {"GET_EMAILS", "READ_EMAIL", "SEND_EMAIL", "SEARCH_DRIVE", "READ_DOC", "CREATE_DOC"}


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

    async def _handle_action(self, user: User, action: dict, history: list, context: Optional[str]) -> str:
        action_type = action.get("action", "IGNORE")

        if action_type == "IGNORE":
            return action.get("message", "Noted.")

        if action_type == "NOTIFY":
            return action.get("message", "")

        if action_type == "TRADE":
            return await self._dispatch_trade(user, action)

        if action_type == "CREATE_TASK":
            return await self._create_task(user, action)

        if action_type == "COMPLETE_TASK":
            return await self._complete_task(user, action)

        if action_type == "UPDATE_GOAL":
            return await self._update_goal(user, action)

        if action_type == "RECORD_SPENDING":
            return await self._record_spending(user, action)

        if action_type == "SET_BUDGET":
            return await self._set_budget(user, action)

        if action_type in LUMISCAPITAL_ACTIONS:
            return await self._fetch_and_analyze(user, action, history, context)

        if action_type in GOOGLE_ACTIONS:
            return await self._handle_google_action(user, action, history, context)

        return action.get("message", "Action processed.")

    # ------------------------------------------------------------------ #
    # GOOGLE — Gmail & Drive
    # ------------------------------------------------------------------ #

    def _get_google_services(self, user: User):
        """Returns (gmail_service, drive_service) or raises RuntimeError."""
        if not user.google_token_json:
            raise RuntimeError("Google not connected. Use /connect_google to link your account.")
        from app.integrations.gmail_service import GmailService, DriveService
        return GmailService(user.google_token_json), DriveService(user.google_token_json)

    async def _handle_google_action(
        self, user: User, action: dict, history: list, context: Optional[str]
    ) -> str:
        action_type = action.get("action")
        try:
            gmail, drive = self._get_google_services(user)
        except RuntimeError as e:
            return str(e)

        try:
            if action_type == "GET_EMAILS":
                query = action.get("query", "unread")
                limit = int(action.get("limit", 10))
                if query == "unread":
                    messages = gmail.list_unread(limit)
                else:
                    messages = gmail.search(query, limit)

                if not messages:
                    return "No emails found."

                lines = [f"*{'Unread Emails' if query == 'unread' else 'Email Search: ' + query}*\n"]
                for i, m in enumerate(messages, 1):
                    lines.append(
                        f"{i}. *{m.get('subject','(no subject)')}*\n"
                        f"   From: {m.get('from','')}\n"
                        f"   {m.get('snippet','')[:100]}…"
                    )

                formatted = "\n".join(lines)
                data_ctx = (context or "") + DATA_RESULT_TEMPLATE.format(
                    action=action_type, data=formatted[:2000]
                )
                analysis = await self.brain.think(
                    "Summarize these emails and flag anything important or urgent.",
                    history, data_ctx,
                )
                if analysis["type"] == "chat" and analysis["content"].strip():
                    return formatted + "\n\n---\n" + analysis["content"]
                return formatted

            if action_type == "READ_EMAIL":
                message_id = action.get("message_id", "")
                msg = gmail.read_message(message_id)
                if not msg:
                    return "Could not read that email."

                text = (
                    f"*From:* {msg['from']}\n"
                    f"*Subject:* {msg['subject']}\n"
                    f"*Date:* {msg['date']}\n\n"
                    f"{msg['body']}"
                )
                data_ctx = (context or "") + DATA_RESULT_TEMPLATE.format(action=action_type, data=text[:3000])
                analysis = await self.brain.think(
                    "Summarize this email and suggest a response if appropriate.",
                    history, data_ctx,
                )
                if analysis["type"] == "chat" and analysis["content"].strip():
                    return text[:1500] + "\n\n---\n*STARFIRE:*\n" + analysis["content"]
                return text

            if action_type == "SEND_EMAIL":
                to = action.get("to", "")
                subject = action.get("subject", "")
                body = action.get("body", "")
                thread_id = action.get("reply_to_thread")
                if not to or not subject or not body:
                    return "Missing to/subject/body for email."
                success = gmail.send_email(to, subject, body, reply_to_thread=thread_id)
                if success:
                    return f"Email sent to {to}\nSubject: {subject}"
                return "Failed to send email. Check that Google is connected and has Gmail send permissions."

            if action_type == "SEARCH_DRIVE":
                query = action.get("query", "")
                files = drive.search(query)
                if not files:
                    return f"No Drive files found for: {query}"
                lines = [f"*Drive Search: {query}*\n"]
                for f in files:
                    lines.append(
                        f"• [{f.get('name','')}]({f.get('webViewLink','')})\n"
                        f"  {f.get('mimeType','').split('.')[-1]} — {f.get('modifiedTime','')[:10]}"
                    )
                return "\n".join(lines)

            if action_type == "READ_DOC":
                file_id = action.get("file_id", "")
                content = drive.read_doc(file_id)
                if not content:
                    return "Could not read that document."
                data_ctx = (context or "") + DATA_RESULT_TEMPLATE.format(
                    action=action_type, data=content[:3000]
                )
                analysis = await self.brain.think(
                    "Summarize this document concisely.",
                    history, data_ctx,
                )
                if analysis["type"] == "chat":
                    return analysis["content"]
                return content[:2000]

            if action_type == "CREATE_DOC":
                title = action.get("title", "STARFIRE Document")
                content = action.get("content", "")
                link = drive.create_doc(title, content)
                if link:
                    return f"Document created: [{title}]({link})"
                return "Failed to create document."

        except Exception as e:
            logger.error("google_action_error", action=action_type, error=str(e))
            return f"Error with Google integration: {e}"

        return action.get("message", "Done.")

    # ------------------------------------------------------------------ #
    # LUMISCAPITAL
    # ------------------------------------------------------------------ #

    async def _fetch_and_analyze(self, user: User, action: dict, history: list, context: Optional[str]) -> str:
        action_type = action.get("action")
        raw_data = await self._fetch_lumiscapital(action_type, action)

        if raw_data is None:
            return "I couldn't retrieve that data right now. The market data service may be unavailable."

        formatted = self._format_lumiscapital_data(action_type, action, raw_data)
        data_context = (context or "") + DATA_RESULT_TEMPLATE.format(
            action=action_type, data=formatted[:2000],
        )
        analysis = await self.brain.think(
            "You just fetched this data. Provide a concise analysis and key takeaways.",
            history, data_context,
        )

        if analysis["type"] == "chat" and analysis["content"].strip():
            return formatted + "\n\n---\n*STARFIRE Analysis*\n" + analysis["content"]
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
            return formatter.format_quote(data)

        if action_type == "GET_MACRO":
            return formatter.format_macro_summary(data.get("indicators", []), data.get("treasury"))

        if action_type == "GET_EARNINGS":
            return formatter.format_earnings_calendar(data)

        if action_type == "GET_EARNINGS_DETAIL":
            symbol = data.get("symbol", "")
            lines = [f"*{symbol} Earnings*\n"]
            for s in data.get("surprises", [])[:5]:
                lines.append(f"  {s.get('date','')[:7]}: Actual `{s.get('actualEarningResult','N/A')}` vs Est `{s.get('estimatedEarning','N/A')}`")
            for e in data.get("estimates", [])[:3]:
                lines.append(f"  {e.get('date','')[:7]}: EPS `{e.get('estimatedEpsAvg','N/A')}` Rev `${(e.get('estimatedRevenueAvg') or 0)/1e9:.2f}B`")
            return "\n".join(lines)

        if action_type == "GET_NEWS":
            topic = action.get("topic", "general")
            title = "Market News" if topic == "general" else "Political News" if topic == "political" else f"{topic.upper()} News"
            return formatter.format_news(data, title)

        if action_type == "GET_SECTOR":
            return formatter.format_sector_performance(data)

        if action_type == "GET_SCOUT":
            return formatter.format_scout_report(data, "Stock Scout")

        if action_type == "GET_PROFILE":
            profile = data.get("profile")
            return "Company profile not found." if not profile else formatter.format_company_profile(profile, data.get("metrics"))

        if action_type == "GET_MOVERS":
            titles = {"gainers": "Top Gainers", "losers": "Top Losers", "actives": "Most Active"}
            return formatter.format_scout_report(data, titles.get(action.get("type", "gainers"), "Movers"))

        if action_type == "GET_INSIDER":
            if not data:
                return "No insider trades found."
            lines = [f"*Insider Trades — {action.get('symbol','').upper()}*\n"]
            for t in data[:10]:
                lines.append(f"`{t.get('transactionDate','')[:10]}` {t.get('reportingName','')} — {t.get('transactionType','')} `{t.get('securitiesTransacted','')}`")
            return "\n".join(lines)

        if action_type == "GET_SENATE":
            if not data:
                return "No Senate disclosures found."
            lines = ["*Senate Trades*\n"]
            for t in data[:15]:
                lines.append(f"`{t.get('transactionDate','')[:10]}` *{t.get('senator','')}* — {t.get('asset_description','')} ({t.get('type','')})")
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
                f"Trade blocked by risk engine: {risk_result['reason']}\n\n"
                "Would you like to adjust the parameters?"
            )

        if osiris_bridge.is_available():
            execution = await osiris_bridge.execute_trade(
                user_id=user.id, symbol=symbol, side=side,
                size_pct=size_pct, intent_payload=action,
            )
        else:
            execution = await self.osiris.execute_trade(
                user_id=user.id, symbol=symbol, side=side,
                size_pct=size_pct, intent_payload=action,
            )

        # Also forward trade order to osiris_prime_bot via Telegram if configured
        await osiris_telegram.send_trade_order(
            user_telegram_id=user.telegram_id,
            symbol=symbol,
            side=side,
            size_pct=size_pct,
            extra={"intent": action},
        )

        if execution["status"] == "FILLED":
            await self.publisher.publish(
                "PORTFOLIO_EVENT",
                {"user_id": user.id, "event": "TRADE_FILLED", "symbol": symbol, "side": side,
                 "filled_price": execution["filled_price"]},
            )
            source = "OSIRIS (external)" if osiris_bridge.is_available() else "OSIRIS"
            return (
                f"Trade executed by {source}.\n"
                f"{side} {symbol} @ ${execution['filled_price']:,.4f}\n"
                f"Slippage: {execution['slippage']*100:.3f}%\n"
                f"Order ID: {execution['order_id']}"
            )
        return f"Trade failed: {execution.get('error', 'Unknown error')}"

    # ------------------------------------------------------------------ #
    # TASKS / GOALS / SPENDING / BUDGET
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
        due_str = f" — due {task.due_at.strftime('%b %d')}" if task.due_at else ""
        return f"Task added: *{task.title}*{due_str} (priority {task.priority}/10)"

    async def _complete_task(self, user: User, action: dict) -> str:
        task_id = action.get("task_id")
        if not task_id:
            return "Which task should I mark complete? Use /tasks to see IDs."
        result = await self.db.execute(
            select(Task).where(Task.id == task_id, Task.user_id == user.id)
        )
        task = result.scalar_one_or_none()
        if not task:
            return f"Task {task_id} not found."
        task.status = "DONE"
        task.completed_at = datetime.now(timezone.utc)
        return f"Done! *{task.title}* marked complete."

    async def _update_goal(self, user: User, action: dict) -> str:
        from app.models.goal import Goal as GoalModel
        goal = GoalModel(
            user_id=user.id,
            title=action.get("title", "New Goal"),
            description=action.get("description"),
            goal_type=action.get("goal_type", "personal"),
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
        return f"Goal set: *{goal.title}*\nTarget: {goal.target_value} {goal.unit or ''}"

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
        return f"Logged: ${record.amount:.2f} in *{record.category}*"

    async def _set_budget(self, user: User, action: dict) -> str:
        budgets = action.get("budgets", {})
        if not budgets:
            return "No budget data provided."
        current = user.budget_json or {}
        current.update(budgets)
        user.budget_json = current
        lines = [f"  {cat}: ${limit:.2f}/mo" for cat, limit in sorted(current.items())]
        return "Budget updated:\n" + "\n".join(lines)

    # ------------------------------------------------------------------ #
    # CONTEXT
    # ------------------------------------------------------------------ #

    async def _build_context(self, user: User) -> Optional[str]:
        parts = []

        result = await self.db.execute(
            select(PortfolioState).where(PortfolioState.user_id == user.id)
            .order_by(PortfolioState.snapshot_at.desc()).limit(1)
        )
        portfolio = result.scalar_one_or_none()
        if portfolio:
            parts.append(PORTFOLIO_CONTEXT_TEMPLATE.format(
                total_value=float(portfolio.total_value or 0),
                cash=float(portfolio.cash or 0),
                daily_pnl=float(portfolio.daily_pnl or 0),
                daily_pnl_pct=float(portfolio.daily_pnl_pct or 0),
                positions=str(portfolio.positions or {}),
            ))

        result = await self.db.execute(
            select(Task).where(Task.user_id == user.id, Task.status == "PENDING")
            .order_by(Task.priority.desc()).limit(5)
        )
        tasks = result.scalars().all()
        if tasks:
            task_lines = "\n".join(
                f"- [id:{t.id}] [{t.priority}] {t.title}" + (f" (due {t.due_at.date()})" if t.due_at else "")
                for t in tasks
            )
            parts.append(TASK_CONTEXT_TEMPLATE.format(count=len(tasks), tasks=task_lines))

        result = await self.db.execute(
            select(Goal).where(Goal.user_id == user.id, Goal.status == "ACTIVE").limit(5)
        )
        goals = result.scalars().all()
        if goals:
            goal_lines = "\n".join(
                f"- {g.title}: {g.current_value}/{g.target_value} {g.unit or ''}" for g in goals
            )
            parts.append(GOAL_CONTEXT_TEMPLATE.format(goals=goal_lines))

        if user.google_token_json:
            parts.append("## Google Integration: Connected (Gmail + Drive available)")
        else:
            parts.append("## Google Integration: Not connected. User can type /connect_google to link Gmail and Drive.")

        return "\n".join(parts) if parts else None
