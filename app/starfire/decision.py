import json
import structlog
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timezone, timedelta

from app.starfire.brain import StarfireBrain
from app.starfire.prompts import (
    PORTFOLIO_CONTEXT_TEMPLATE,
    TASK_CONTEXT_TEMPLATE,
    GOAL_CONTEXT_TEMPLATE,
    BILLS_CONTEXT_TEMPLATE,
    DATA_RESULT_TEMPLATE,
)
from app.models import User, PortfolioState, Task, Goal, Bill
from app.risk.engine import RiskEngine
from app.osiris.executor import OsirisExecutor
from app.events.publisher import EventPublisher
from app.integrations.lumiscapital import lumiscapital, formatter
from app.integrations.osiris_bridge import osiris_bridge
from app.integrations.osiris_telegram import osiris_telegram
from app.integrations.lumisnova_telegram import lumisnova_telegram

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

        # ── OSIRIS ROUTING ──────────────────────────────────────────────
        if action_type == "ROUTE_TRADE":
            return await self._route_trade(user, action)

        # ── LUMISNOVA ROUTING ───────────────────────────────────────────
        if action_type == "QUERY_LUMISNOVA":
            return await self._query_lumisnova(user, action, history, context)

        # ── MARKET DATA (direct FMP) ─────────────────────────────────────
        if action_type in LUMISCAPITAL_ACTIONS:
            return await self._fetch_and_analyze(user, action, history, context)

        # ── GOOGLE ──────────────────────────────────────────────────────
        if action_type in GOOGLE_ACTIONS:
            return await self._handle_google_action(user, action, history, context)

        # ── INTERNAL TASKS / GOALS / SPENDING / BILLS ──────────────────
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
        if action_type == "ADD_BILL":
            return await self._add_bill(user, action)
        if action_type == "MARK_BILL_PAID":
            return await self._mark_bill_paid(user, action)

        return action.get("message", "Action processed.")

    # ─────────────────────────────────────────────────────────────────────
    # OSIRIS — trade routing
    # ─────────────────────────────────────────────────────────────────────

    async def _route_trade(self, user: User, action: dict) -> str:
        symbol = action.get("symbol", "")
        side = action.get("side", "BUY")
        quantity = action.get("quantity")
        size_pct = action.get("size_pct", 5.0)

        if not symbol or not side:
            return "Missing symbol or side for trade. Please specify what to trade."

        # Risk check
        risk_result = await self.risk.validate_trade(user.id, symbol, side, float(size_pct))
        if not risk_result["allowed"]:
            return (
                f"Trade blocked by risk engine: {risk_result['reason']}\n\n"
                "Would you like to adjust the parameters?"
            )

        # Send to OSIRIS via Telegram bridge first (primary)
        tg_sent = await osiris_telegram.send_trade_order(
            user_telegram_id=user.telegram_id,
            symbol=symbol,
            side=side,
            size_pct=float(size_pct),
            extra={"quantity": quantity, "intent": action},
        )

        # Also attempt HTTP bridge if configured
        if osiris_bridge.is_available():
            execution = await osiris_bridge.execute_trade(
                user_id=user.id,
                symbol=symbol,
                side=side,
                size_pct=float(size_pct),
                intent_payload=action,
            )
        else:
            execution = await self.osiris.execute_trade(
                user_id=user.id,
                symbol=symbol,
                side=side,
                size_pct=float(size_pct),
                intent_payload=action,
            )

        if execution["status"] == "FILLED":
            await self.publisher.publish(
                "PORTFOLIO_EVENT",
                {"user_id": user.id, "event": "TRADE_FILLED", "symbol": symbol, "side": side,
                 "filled_price": execution["filled_price"]},
            )
            tg_status = " | Order also sent to Argus Tower." if tg_sent else ""
            return (
                f"OSIRIS executed.\n"
                f"{side} {symbol} @ ${execution['filled_price']:,.4f}\n"
                f"Slippage: {execution['slippage']*100:.3f}%\n"
                f"Order ID: {execution['order_id']}"
                f"{tg_status}"
            )

        if tg_sent:
            return (
                f"Trade order sent to OSIRIS via Argus Tower.\n"
                f"{side} {symbol} — OSIRIS will confirm execution.\n"
                f"_(HTTP bridge: {execution.get('error', 'not available')})_"
            )

        return f"Could not reach OSIRIS. Error: {execution.get('error', 'Unknown')}"

    # ─────────────────────────────────────────────────────────────────────
    # LUMISNOVA — financial data routing
    # ─────────────────────────────────────────────────────────────────────

    async def _query_lumisnova(
        self, user: User, action: dict, history: list, context: Optional[str]
    ) -> str:
        query = action.get("query", "portfolio_summary")

        # Notify group and send portfolio summary via @Lumiscapital_bot
        if lumisnova_telegram.is_available():
            await lumisnova_telegram.notify_command(query, action, user.telegram_id)
            if "portfolio" in query:
                result = await self.db.execute(
                    select(PortfolioState).where(PortfolioState.user_id == user.id)
                    .order_by(PortfolioState.snapshot_at.desc()).limit(1)
                )
                portfolio = result.scalar_one_or_none()
                if portfolio:
                    summary = (
                        f"Value: ${float(portfolio.total_value or 0):,.2f}\n"
                        f"Cash: ${float(portfolio.cash or 0):,.2f}\n"
                        f"Daily P&L: ${float(portfolio.daily_pnl or 0):,.2f} ({float(portfolio.daily_pnl_pct or 0):.2f}%)"
                    )
                    await lumisnova_telegram.send_portfolio_summary(user.telegram_id, summary)
                    return "Portfolio summary sent via LUMISNOVA."
            return f"Query routed to LUMISNOVA: _{query}_"

        # Fallback: serve from direct FMP / local DB
        if "portfolio" in query:
            result = await self.db.execute(
                select(PortfolioState).where(PortfolioState.user_id == user.id)
                .order_by(PortfolioState.snapshot_at.desc()).limit(1)
            )
            portfolio = result.scalar_one_or_none()
            if portfolio:
                return (
                    f"Portfolio (local snapshot):\n"
                    f"Value: ${float(portfolio.total_value or 0):,.2f}\n"
                    f"Cash: ${float(portfolio.cash or 0):,.2f}\n"
                    f"Daily P&L: ${float(portfolio.daily_pnl or 0):,.2f} ({float(portfolio.daily_pnl_pct or 0):.2f}%)\n\n"
                    f"_Connect LUMISNOVA for live portfolio data._"
                )
            return "No portfolio data yet."

        return "LUMISNOVA not connected. Set `LUMISNOVA_BOT_TOKEN` in Railway."

    # ─────────────────────────────────────────────────────────────────────
    # MARKET DATA — direct FMP (GET_* actions)
    # ─────────────────────────────────────────────────────────────────────

    async def _fetch_and_analyze(self, user: User, action: dict, history: list, context: Optional[str]) -> str:
        action_type = action.get("action")
        raw_data = await self._fetch_lumiscapital(action_type, action)

        if raw_data is None:
            return "Market data unavailable. Check your FMP API key."

        formatted = self._format_lumiscapital_data(action_type, action, raw_data)
        data_context = (context or "") + DATA_RESULT_TEMPLATE.format(
            action=action_type, data=formatted[:2000],
        )
        analysis = await self.brain.think(
            "You just fetched this data. Give a concise analysis and key takeaways.",
            history, data_context,
        )
        full_response = formatted
        if analysis["type"] == "chat" and analysis["content"].strip():
            full_response = formatted + "\n\n---\n" + analysis["content"]

        # Deliver via @Lumiscapital_bot when available — data appears to come from LUMISNOVA
        if lumisnova_telegram.is_available() and user.telegram_id:
            sent = await lumisnova_telegram.send_market_data(user.telegram_id, action_type, full_response)
            if sent:
                return f"_Data delivered via LUMISNOVA._"

        return full_response

    async def _fetch_lumiscapital(self, action_type: str, action: dict):
        try:
            if action_type == "GET_PRICE":
                symbols = [s.strip() for s in action.get("symbols", action.get("symbol", "")).split(",") if s.strip()]
                if not symbols:
                    return None
                return await lumiscapital.get_quote(symbols[0]) if len(symbols) == 1 else await lumiscapital.get_quotes(symbols)

            if action_type == "GET_MACRO":
                return {"indicators": await lumiscapital.get_economic_indicators(), "treasury": await lumiscapital.get_treasury_rates()}

            if action_type == "GET_EARNINGS":
                return await lumiscapital.get_earnings_calendar(int(action.get("days_ahead", 7)))

            if action_type == "GET_EARNINGS_DETAIL":
                s = action.get("symbol", "")
                return {"surprises": await lumiscapital.get_earnings_surprises(s), "estimates": await lumiscapital.get_analyst_estimates(s), "symbol": s}

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
                s = action.get("symbol", "")
                return {"profile": await lumiscapital.get_company_profile(s), "metrics": await lumiscapital.get_key_metrics(s)}

            if action_type == "GET_MOVERS":
                t = action.get("type", "gainers")
                if t == "losers":
                    return await lumiscapital.get_losers()
                if t in ("actives", "active"):
                    return await lumiscapital.get_most_active()
                return await lumiscapital.get_gainers()

            if action_type == "GET_INSIDER":
                return await lumiscapital.get_insider_trades(action.get("symbol", ""))

            if action_type == "GET_SENATE":
                return await lumiscapital.get_senate_trades(action.get("symbol"))

        except Exception as e:
            logger.error("lumiscapital_fetch_error", action=action_type, error=str(e))
            return None

    def _format_lumiscapital_data(self, action_type: str, action: dict, data) -> str:
        if data is None:
            return "No data."
        if action_type == "GET_PRICE":
            if isinstance(data, list):
                return "\n\n".join(formatter.format_quote(q) for q in data)
            return formatter.format_quote(data)
        if action_type == "GET_MACRO":
            return formatter.format_macro_summary(data.get("indicators", []), data.get("treasury"))
        if action_type == "GET_EARNINGS":
            return formatter.format_earnings_calendar(data)
        if action_type == "GET_EARNINGS_DETAIL":
            s = data.get("symbol", "")
            lines = [f"*{s} Earnings*\n"]
            for x in data.get("surprises", [])[:5]:
                lines.append(f"  {x.get('date','')[:7]}: Actual `{x.get('actualEarningResult','N/A')}` vs Est `{x.get('estimatedEarning','N/A')}`")
            for x in data.get("estimates", [])[:3]:
                lines.append(f"  {x.get('date','')[:7]}: EPS `{x.get('estimatedEpsAvg','N/A')}` Rev `${(x.get('estimatedRevenueAvg') or 0)/1e9:.2f}B`")
            return "\n".join(lines)
        if action_type == "GET_NEWS":
            t = action.get("topic", "general")
            title = "Market News" if t == "general" else "Political News" if t == "political" else f"{t.upper()} News"
            return formatter.format_news(data, title)
        if action_type == "GET_SECTOR":
            return formatter.format_sector_performance(data)
        if action_type == "GET_SCOUT":
            return formatter.format_scout_report(data, "Stock Scout")
        if action_type == "GET_PROFILE":
            p = data.get("profile")
            return "Profile not found." if not p else formatter.format_company_profile(p, data.get("metrics"))
        if action_type == "GET_MOVERS":
            titles = {"gainers": "Top Gainers", "losers": "Top Losers", "actives": "Most Active"}
            return formatter.format_scout_report(data, titles.get(action.get("type", "gainers"), "Movers"))
        if action_type == "GET_INSIDER":
            if not data:
                return "No insider trades found."
            lines = [f"*Insider — {action.get('symbol','').upper()}*\n"]
            for t in data[:10]:
                lines.append(f"`{t.get('transactionDate','')[:10]}` {t.get('reportingName','')} — {t.get('transactionType','')} `{t.get('securitiesTransacted','')}`")
            return "\n".join(lines)
        if action_type == "GET_SENATE":
            if not data:
                return "No Senate disclosures."
            lines = ["*Senate Trades*\n"]
            for t in data[:15]:
                lines.append(f"`{t.get('transactionDate','')[:10]}` *{t.get('senator','')}* — {t.get('asset_description','')} ({t.get('type','')})")
            return "\n".join(lines)
        return str(data)[:1500]

    # ─────────────────────────────────────────────────────────────────────
    # GOOGLE
    # ─────────────────────────────────────────────────────────────────────

    def _get_google_services(self, user: User):
        if not user.google_token_json:
            raise RuntimeError("Google not connected. Use /connect_google to link your account.")
        from app.integrations.gmail_service import GmailService, DriveService
        return GmailService(user.google_token_json), DriveService(user.google_token_json)

    async def _handle_google_action(self, user: User, action: dict, history: list, context: Optional[str]) -> str:
        action_type = action.get("action")
        try:
            gmail, drive = self._get_google_services(user)
        except RuntimeError as e:
            return str(e)

        try:
            if action_type == "GET_EMAILS":
                query = action.get("query", "unread")
                limit = int(action.get("limit", 10))
                messages = gmail.list_unread(limit) if query == "unread" else gmail.search(query, limit)
                if not messages:
                    return "No emails found."
                lines = [f"*{'Unread' if query == 'unread' else 'Search: ' + query}*\n"]
                for i, m in enumerate(messages, 1):
                    lines.append(f"{i}. *{m.get('subject','(no subject)')}*\n   From: {m.get('from','')}\n   _{m.get('snippet','')[:100]}_")
                formatted = "\n".join(lines)
                data_ctx = (context or "") + DATA_RESULT_TEMPLATE.format(action=action_type, data=formatted[:2000])
                analysis = await self.brain.think("Summarize these emails, flag urgent items.", history, data_ctx)
                return formatted + ("\n\n---\n" + analysis["content"] if analysis["type"] == "chat" and analysis["content"].strip() else "")

            if action_type == "READ_EMAIL":
                msg = gmail.read_message(action.get("message_id", ""))
                if not msg:
                    return "Could not read that email."
                text = f"*From:* {msg['from']}\n*Subject:* {msg['subject']}\n*Date:* {msg['date']}\n\n{msg['body']}"
                data_ctx = (context or "") + DATA_RESULT_TEMPLATE.format(action=action_type, data=text[:3000])
                analysis = await self.brain.think("Summarize and suggest a response if appropriate.", history, data_ctx)
                return text[:1500] + ("\n\n---\n" + analysis["content"] if analysis["type"] == "chat" and analysis["content"].strip() else "")

            if action_type == "SEND_EMAIL":
                to, subject, body = action.get("to", ""), action.get("subject", ""), action.get("body", "")
                if not to or not subject or not body:
                    return "Missing to/subject/body."
                success = gmail.send_email(to, subject, body, reply_to_thread=action.get("reply_to_thread"))
                return f"Email sent to {to}\nSubject: {subject}" if success else "Failed to send email."

            if action_type == "SEARCH_DRIVE":
                files = drive.search(action.get("query", ""))
                if not files:
                    return "No Drive files found."
                lines = [f"*Drive: {action.get('query','')}*\n"]
                for f in files:
                    lines.append(f"• [{f.get('name','')}]({f.get('webViewLink','')})\n  {f.get('modifiedTime','')[:10]}")
                return "\n".join(lines)

            if action_type == "READ_DOC":
                content = drive.read_doc(action.get("file_id", ""))
                if not content:
                    return "Could not read document."
                data_ctx = (context or "") + DATA_RESULT_TEMPLATE.format(action=action_type, data=content[:3000])
                analysis = await self.brain.think("Summarize this document.", history, data_ctx)
                return analysis["content"] if analysis["type"] == "chat" else content[:2000]

            if action_type == "CREATE_DOC":
                link = drive.create_doc(action.get("title", "STARFIRE Doc"), action.get("content", ""))
                return f"Document created: [{action.get('title','')}]({link})" if link else "Failed to create document."

        except Exception as e:
            logger.error("google_action_error", action=action_type, error=str(e))
            return f"Google error: {e}"

        return "Done."

    # ─────────────────────────────────────────────────────────────────────
    # BILLS
    # ─────────────────────────────────────────────────────────────────────

    async def _add_bill(self, user: User, action: dict) -> str:
        bill = Bill(
            user_id=user.id,
            name=action.get("name", "New Bill"),
            category=action.get("category", "other"),
            amount=float(action.get("amount", 0)),
            due_day=action.get("due_day"),
            is_recurring=action.get("is_recurring", True),
            autopay=action.get("autopay", False),
            notes=action.get("notes"),
        )
        if action.get("due_date"):
            try:
                bill.due_date = datetime.fromisoformat(action["due_date"].replace("Z", "+00:00"))
            except ValueError:
                pass
        self.db.add(bill)
        await self.db.flush()
        recur = "monthly" if bill.is_recurring else "one-time"
        due = f" (due day {bill.due_day})" if bill.due_day else ""
        return f"Bill added: *{bill.name}* — ${bill.amount:.2f}/{recur}{due}"

    async def _mark_bill_paid(self, user: User, action: dict) -> str:
        bill_id = action.get("bill_id")
        if not bill_id:
            return "Which bill? Use /bills to see IDs."
        result = await self.db.execute(select(Bill).where(Bill.id == bill_id, Bill.user_id == user.id))
        bill = result.scalar_one_or_none()
        if not bill:
            return f"Bill {bill_id} not found."
        bill.last_paid_at = datetime.now(timezone.utc)
        return f"*{bill.name}* marked as paid."

    # ─────────────────────────────────────────────────────────────────────
    # TASKS / GOALS / SPENDING / BUDGET
    # ─────────────────────────────────────────────────────────────────────

    async def _create_task(self, user: User, action: dict) -> str:
        from app.models.task import Task as TaskModel
        task = TaskModel(
            user_id=user.id,
            title=action.get("title", "New Task"),
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
        return f"Task added: *{task.title}*{due_str}"

    async def _complete_task(self, user: User, action: dict) -> str:
        task_id = action.get("task_id")
        if not task_id:
            return "Which task? Use /tasks to see IDs."
        result = await self.db.execute(select(Task).where(Task.id == task_id, Task.user_id == user.id))
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
        return f"Goal set: *{goal.title}* — Target: {goal.target_value} {goal.unit or ''}"

    async def _record_spending(self, user: User, action: dict) -> str:
        from app.models.spending import SpendingRecord
        record = SpendingRecord(
            user_id=user.id,
            category=action.get("category", "General"),
            description=action.get("description"),
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

    # ─────────────────────────────────────────────────────────────────────
    # CONTEXT BUILDER
    # ─────────────────────────────────────────────────────────────────────

    async def _build_context(self, user: User) -> Optional[str]:
        parts = []
        now = datetime.now(timezone.utc)

        # Portfolio
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

        # Tasks
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

        # Goals
        result = await self.db.execute(
            select(Goal).where(Goal.user_id == user.id, Goal.status == "ACTIVE").limit(5)
        )
        goals = result.scalars().all()
        if goals:
            goal_lines = "\n".join(f"- {g.title}: {g.current_value}/{g.target_value} {g.unit or ''}" for g in goals)
            parts.append(GOAL_CONTEXT_TEMPLATE.format(goals=goal_lines))

        # Upcoming bills (due within 7 days)
        result = await self.db.execute(
            select(Bill).where(Bill.user_id == user.id, Bill.is_active == True)
        )
        bills = result.scalars().all()
        upcoming = []
        for b in bills:
            if b.is_recurring and b.due_day:
                # Calculate next due date
                next_due = now.replace(day=min(b.due_day, 28))
                if next_due < now:
                    if now.month == 12:
                        next_due = next_due.replace(year=now.year + 1, month=1)
                    else:
                        next_due = next_due.replace(month=now.month + 1)
                if (next_due - now).days <= 7:
                    upcoming.append(f"- {b.name}: ${float(b.amount):.2f} due {next_due.strftime('%b %d')}")
            elif b.due_date and 0 <= (b.due_date - now).days <= 7:
                upcoming.append(f"- {b.name}: ${float(b.amount):.2f} due {b.due_date.strftime('%b %d')}")
        if upcoming:
            parts.append(BILLS_CONTEXT_TEMPLATE.format(bills="\n".join(upcoming)))

        # System status
        osiris_ok = osiris_telegram.is_available()
        lumisnova_ok = lumisnova_telegram.is_available()
        parts.append(
            f"## System Status\n"
            f"- OSIRIS bridge: {'connected (Argus Tower)' if osiris_ok else 'HTTP only'}\n"
            f"- LUMISNOVA bridge: {'connected' if lumisnova_ok else 'not connected (using direct FMP)'}\n"
            f"- Google: {'connected' if user.google_token_json else 'not connected'}"
        )

        return "\n".join(parts) if parts else None
