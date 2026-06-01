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
from app.models import User, PortfolioState, Task, Goal, Bill, BotTicket
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

GOOGLE_ACTIONS = {
    # Gmail
    "GET_EMAILS", "READ_EMAIL", "SEND_EMAIL",
    "DRAFT_EMAIL", "SEND_DRAFT", "LIST_DRAFTS", "DELETE_DRAFT",
    "REPLY_EMAIL", "ARCHIVE_EMAIL", "DELETE_EMAIL", "MARK_READ",
    # Drive / Docs
    "SEARCH_DRIVE", "READ_DOC", "CREATE_DOC",
    # Calendar
    "GET_CALENDAR", "CREATE_EVENT", "UPDATE_EVENT",
    "DELETE_EVENT", "SEARCH_CALENDAR", "CREATE_APPOINTMENT",
    # Sheets
    "UPDATE_SHEET", "GET_SHEET_PL",
    "CREATE_SHEET", "DELETE_SHEET_ROW", "DELETE_SHEET",
    "SHEET_FORMAT", "SHEET_UPDATE_CELL", "SHEET_UPDATE_RANGE",
    "SHEET_READ", "SHEET_FIND", "SHEET_FIND_REPLACE",
    "SHEET_INSERT_ROW", "SHEET_CLEAR", "SHEET_DELETE_TAB",
    "SHEET_DELETE_COLUMNS", "SHEET_ADD_TAB", "SHEET_RENAME_TAB",
    "SHEET_FREEZE", "SHEET_AUTO_RESIZE", "SHEET_CONDITIONAL_FORMAT",
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

    async def _handle_action(self, user: User, action: dict, history: list, context: Optional[str]) -> str:
        action_type = action.get("action", "IGNORE")

        if action_type == "IGNORE":
            return action.get("message", "Noted.")
        if action_type == "NOTIFY":
            return action.get("message", "")

        # ── DIRECT BOT MESSAGING ────────────────────────────────────────
        if action_type == "MESSAGE_LUMISNOVA":
            return await self._message_lumisnova(user, action)
        if action_type == "MESSAGE_OSIRIS":
            return await self._message_osiris(user, action)

        # ── TICKETING ───────────────────────────────────────────────────
        if action_type == "ASSIGN_TICKET":
            return await self._assign_ticket(user, action)
        if action_type == "CLOSE_TICKET":
            return await self._close_ticket(user, action)
        if action_type == "CHECK_TICKETS":
            return await self._check_tickets(user, action)

        # ── OSIRIS ROUTING ──────────────────────────────────────────────
        if action_type == "ROUTE_TRADE":
            return await self._route_trade(user, action)
        if action_type == "CHECK_OSIRIS_PERFORMANCE":
            return await self._check_osiris_performance(user, action)

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
    # BOT MESSAGING — relay user instructions to LUMISNOVA / OSIRIS
    # ─────────────────────────────────────────────────────────────────────

    async def _message_lumisnova(self, user: User, action: dict) -> str:
        msg = action.get("message", "")
        if not msg:
            return "No message to relay."
        # Post to Argus Tower as OSIRIS (STARFIRE doesn't have group access,
        # and using @Lumiscapital_bot's token causes duplicate responses)
        sent = await osiris_telegram.send_command(
            "LUMISNOVA_REQUEST",
            {"message": msg, "from_user": user.telegram_id},
            user.telegram_id,
        )
        if sent:
            return f"Posted to Argus Tower for LUMISNOVA:\n_{msg}_"
        return "Couldn't reach Argus Tower. Check /health."

    async def _message_osiris(self, user: User, action: dict) -> str:
        msg = action.get("message", "")
        if not msg:
            return "No message to relay."
        sent = await osiris_telegram.send_command(
            "USER_MESSAGE",
            {"message": msg, "from_user": user.telegram_id},
            user.telegram_id,
        )
        if sent:
            return f"Relayed to OSIRIS in Argus Tower:\n_{msg}_"
        return "Couldn't reach Argus Tower. Check OSIRIS bridge in /health."

    # ─────────────────────────────────────────────────────────────────────
    # TICKETING — delegate tasks to bots and track completion
    # ─────────────────────────────────────────────────────────────────────

    async def _assign_ticket(self, user: User, action: dict) -> str:
        assigned_to = action.get("assigned_to", "OSIRIS").upper()
        title = action.get("title", "")
        if not title:
            return "Ticket needs a title."

        ticket = BotTicket(
            user_id=user.id,
            title=title,
            description=action.get("description"),
            assigned_to=assigned_to,
            priority=action.get("priority", 5),
            context=action.get("context"),
            status="QUEUED",
        )
        self.db.add(ticket)
        await self.db.flush()

        # Deliver ticket as a DM to the user appearing from the assigned bot.
        # This puts the ticket directly in the user's bot chat so the bot's
        # Claude session sees it in conversation context when the user opens it.
        # (Bots cannot receive messages from other bots via Telegram, so
        #  Argus Tower posting has no effect on the receiving bot — this is the
        #  correct delivery path.)
        delivered = False
        if user.telegram_id:
            ticket_dm = (
                f"📋 *STARFIRE → {assigned_to}*\n"
                f"Ticket #{ticket.id} assigned\n\n"
                f"*{title}*"
                + (f"\n{action.get('description', '')}" if action.get("description") else "")
                + f"\n\nPriority: {ticket.priority}/10\n"
                f"Fetch via: `GET /internal/tickets/{assigned_to.lower()}`"
            )
            if assigned_to == "OSIRIS":
                delivered = await osiris_telegram.send_as_osiris(user.telegram_id, ticket_dm)
            elif assigned_to == "LUMISNOVA":
                delivered = await lumisnova_telegram.send_data_to_user(user.telegram_id, ticket_dm)

        if delivered:
            ticket.status = "SENT"

        label = "delivered to your bot chat ✓" if delivered else "queued — bot will pick it up via API"
        return (
            f"Ticket #{ticket.id} → *{assigned_to}*\n"
            f"*{title}*"
            + (f"\n_{action.get('description')}_" if action.get("description") else "")
            + f"\nStatus: {label}"
        )

    async def _close_ticket(self, user: User, action: dict) -> str:
        ticket_id = action.get("ticket_id")
        if not ticket_id:
            return "Which ticket? Give me an ID."
        result = await self.db.execute(
            select(BotTicket).where(BotTicket.id == ticket_id, BotTicket.user_id == user.id)
        )
        ticket = result.scalar_one_or_none()
        if not ticket:
            return f"Ticket #{ticket_id} not found."
        ticket.status = "DONE"
        ticket.completed_at = datetime.now(timezone.utc)
        return f"Ticket #{ticket_id} closed: *{ticket.title}* ✓"

    async def _check_tickets(self, user: User, action: dict) -> str:
        """Ping each bot about their open tickets and return a queue summary."""
        result = await self.db.execute(
            select(BotTicket).where(
                BotTicket.user_id == user.id,
                BotTicket.status.in_(["QUEUED", "SENT"]),
            ).order_by(BotTicket.priority.desc(), BotTicket.created_at)
        )
        tickets = result.scalars().all()

        if not tickets:
            return "No open tickets. All bots are clear."

        now = datetime.now(timezone.utc)
        lines = ["*Open Bot Tickets*\n"]
        osiris_ids, lumisnova_ids = [], []

        for t in tickets:
            age = (now - t.created_at).seconds // 3600 if t.created_at else 0
            age_str = f"{age}h ago" if age else "just now"
            lines.append(
                f"[#{t.id}] *{t.assigned_to}* — {t.title}\n"
                f"  Status: `{t.status}` | Priority: {t.priority} | Created: {age_str}"
            )
            t.last_checked_at = now
            if t.assigned_to == "OSIRIS":
                osiris_ids.append(t.id)
            elif t.assigned_to == "LUMISNOVA":
                lumisnova_ids.append(t.id)

        # Ping the bots
        pinged = []
        if osiris_ids:
            ok = await osiris_telegram.send_command(
                "TICKET_STATUS_REQUEST",
                {"ticket_ids": osiris_ids, "from_user": user.telegram_id},
                user.telegram_id,
            )
            if ok:
                pinged.append(f"OSIRIS (tickets {osiris_ids})")
        if lumisnova_ids:
            ok = await osiris_telegram.send_command(
                "LUMISNOVA_TICKET_STATUS",
                {"ticket_ids": lumisnova_ids, "from_user": user.telegram_id},
                user.telegram_id,
            )
            if ok:
                pinged.append(f"LUMISNOVA (tickets {lumisnova_ids})")

        summary = "\n".join(lines)
        if pinged:
            summary += f"\n\n_Pinged: {', '.join(pinged)} — awaiting response._"
        else:
            summary += "\n\n_Bridges unavailable — couldn't ping bots._"
        return summary

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

        # Notify user in their OSIRIS private chat so OSIRIS sees the order
        osiris_msg = (
            f"STARFIRE ROUTE → {side} {symbol}\n"
            f"Size: {size_pct}%{f' | Qty: {quantity}' if quantity else ''}\n"
            f"Authorized by STARFIRE. Execute?"
        )
        await osiris_telegram.send_as_osiris(user.telegram_id, osiris_msg)

        # Also post command to Argus Tower group
        tg_sent = await osiris_telegram.send_trade_order(
            user_telegram_id=user.telegram_id,
            symbol=symbol,
            side=side,
            size_pct=float(size_pct),
            extra={"quantity": quantity, "intent": action},
        )

        # HTTP bridge if configured
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

    async def _check_osiris_performance(self, user: User, action: dict) -> str:
        """Read the latest OSIRIS performance report pushed via /internal/tickets/osiris/report."""
        report = (user.preferences or {}).get("osiris_report")

        # If HTTP bridge is up, try to pull live status too
        live_status = None
        if osiris_bridge.is_available():
            try:
                live_status = await osiris_bridge.get_status()
            except Exception:
                pass

        if not report and not live_status:
            return (
                "No OSIRIS performance data yet.\n\n"
                "OSIRIS needs to push reports to STARFIRE using:\n"
                "`POST /internal/tickets/osiris/report`\n"
                "with `X-Service-Secret` header.\n\n"
                "Or set `OSIRIS_SERVICE_URL` in Railway so I can pull status directly."
            )

        lines = ["*OSIRIS Performance*\n"]

        if report:
            reported_at = report.get("reported_at", "")[:19].replace("T", " ")
            pnl_today = report.get("pnl_today")
            pnl_total = report.get("pnl_total")
            trades = report.get("trades_today")
            wins = report.get("wins_today")
            losses = report.get("losses_today")
            win_rate = report.get("win_rate")
            summary = report.get("summary")
            positions = report.get("open_positions") or {}
            fills = report.get("fills") or []

            if pnl_today is not None:
                sign = "+" if pnl_today >= 0 else ""
                icon = "🟢" if pnl_today >= 0 else "🔴"
                lines.append(f"{icon} P/L Today: `{sign}${pnl_today:,.2f}`")
            if pnl_total is not None:
                sign = "+" if pnl_total >= 0 else ""
                lines.append(f"P/L All-Time: `{sign}${pnl_total:,.2f}`")
            if trades is not None:
                wr_str = f" | Win Rate: `{win_rate*100:.0f}%`" if win_rate is not None else ""
                wl_str = f" ({wins}W / {losses}L)" if wins is not None else ""
                lines.append(f"Trades Today: `{trades}`{wl_str}{wr_str}")
            if summary:
                lines.append(f"\n_{summary}_")
            if positions:
                lines.append("\n*Open Positions*")
                for sym, pos in list(positions.items())[:8]:
                    qty = pos.get("qty", pos.get("quantity", "?"))
                    avg = pos.get("avg", pos.get("avg_price", "?"))
                    lines.append(f"  `{sym}`: {qty} @ ${avg}")
            if fills:
                lines.append("\n*Recent Fills*")
                for f in fills[:5]:
                    pl_str = f" P/L: ${f.get('pnl'):,.2f}" if f.get("pnl") is not None else ""
                    lines.append(f"  `{f.get('symbol')}` {f.get('side')} × {f.get('quantity','?')}{pl_str}")
            lines.append(f"\n_Last report: {reported_at} UTC_")

        if live_status and live_status.get("status") != "unreachable":
            lines.append(f"\n*Live Bridge*: {live_status}")

        return "\n".join(lines)

    # ─────────────────────────────────────────────────────────────────────
    # LUMISNOVA — financial data routing
    # ─────────────────────────────────────────────────────────────────────

    async def _query_lumisnova(
        self, user: User, action: dict, history: list, context: Optional[str]
    ) -> str:
        query = action.get("query", "portfolio_summary")

        # Always answer from local DB — @Lumiscapital_bot can't respond autonomously
        result = await self.db.execute(
            select(PortfolioState).where(PortfolioState.user_id == user.id)
            .order_by(PortfolioState.snapshot_at.desc()).limit(1)
        )
        portfolio = result.scalar_one_or_none()

        # Check for a specific position in the query (e.g. position_IREN)
        symbol = None
        if query.startswith("position_"):
            symbol = query.replace("position_", "").upper()
        elif action.get("symbol"):
            symbol = action.get("symbol", "").upper()

        if symbol and portfolio and portfolio.positions:
            positions = portfolio.positions if isinstance(portfolio.positions, dict) else {}
            pos = positions.get(symbol) or positions.get(symbol.lower())
            if pos:
                qty = pos.get("qty") or pos.get("quantity") or pos.get("shares", 0)
                avg = pos.get("avg_price") or pos.get("average_price", 0)
                summary = f"You hold *{qty}* shares of *{symbol}* @ avg ${float(avg):,.2f}"
            else:
                summary = f"No position in *{symbol}* found in your tracked portfolio."
            if lumisnova_telegram.is_available() and user.telegram_id:
                await lumisnova_telegram.send_data_to_user(user.telegram_id, f"*LUMISNOVA — Position*\n\n{summary}")
                return "_Position data sent via LUMISNOVA._"
            return summary

        if portfolio:
            summary = (
                f"Value: ${float(portfolio.total_value or 0):,.2f}\n"
                f"Cash: ${float(portfolio.cash or 0):,.2f}\n"
                f"Daily P&L: ${float(portfolio.daily_pnl or 0):,.2f} ({float(portfolio.daily_pnl_pct or 0):.2f}%)"
            )
            if lumisnova_telegram.is_available() and user.telegram_id:
                await lumisnova_telegram.send_portfolio_summary(user.telegram_id, summary)
                return "_Portfolio summary sent via LUMISNOVA._"
            return f"Portfolio:\n{summary}"

        return "No portfolio data tracked yet. Trades you execute via OSIRIS will be recorded here."

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
        if analysis["type"] == "chat" and analysis["content"].strip():
            return formatted + "\n\n---\n" + analysis["content"]
        return formatted

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

    def _google_connected(self, user: User) -> bool:
        return bool(user.google_token_json)

    def _calendar(self, user: User):
        from app.integrations.gmail_service import CalendarService
        return CalendarService(user.google_token_json)

    def _sheets(self, user: User):
        from app.integrations.gmail_service import SheetsService
        return SheetsService(user.google_token_json)

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
                to = action.get("to", "")
                subject = action.get("subject", "")
                body = action.get("body", "")
                if not to or not subject or not body:
                    return "Missing to/subject/body."
                success = gmail.send_email(
                    to=to, subject=subject, body=body,
                    cc=action.get("cc"), bcc=action.get("bcc"),
                    reply_to_thread=action.get("reply_to_thread"),
                    reply_to_message_id=action.get("reply_to_message_id"),
                )
                if success:
                    cc_str = f" (CC: {action['cc']})" if action.get("cc") else ""
                    return f"Email sent to *{to}*{cc_str}\nSubject: _{subject}_"
                return "Failed to send email."

            if action_type == "DRAFT_EMAIL":
                to = action.get("to", "")
                subject = action.get("subject", "")
                body = action.get("body", "")
                if not to or not subject or not body:
                    return "Missing to/subject/body for draft."
                draft = gmail.create_draft(
                    to=to, subject=subject, body=body,
                    cc=action.get("cc"), bcc=action.get("bcc"),
                    reply_to_thread=action.get("reply_to_thread"),
                )
                if draft:
                    preview = body[:300].replace("\n", " ")
                    return (
                        f"Draft saved ✓\n"
                        f"*To:* {to}\n"
                        f"*Subject:* {subject}\n"
                        + (f"*CC:* {action['cc']}\n" if action.get("cc") else "")
                        + f"\n_{preview}..._\n\n"
                        f"Draft ID: `{draft['id']}`\n"
                        f"Say _\"send draft {draft['id']}\"_ when ready."
                    )
                return "Failed to save draft."

            if action_type == "SEND_DRAFT":
                draft_id = action.get("draft_id", "")
                if not draft_id:
                    return "Which draft? Give me the draft ID."
                ok = gmail.send_draft(draft_id)
                return "Draft sent ✓" if ok else "Failed to send draft. Check the ID."

            if action_type == "LIST_DRAFTS":
                drafts = gmail.list_drafts(limit=action.get("limit", 10))
                if not drafts:
                    return "No saved drafts."
                lines = ["*Saved Drafts*\n"]
                for d in drafts:
                    lines.append(f"`{d['id']}` → *{d['to']}* | _{d['subject']}_\n  {d['snippet'][:80]}")
                return "\n".join(lines)

            if action_type == "DELETE_DRAFT":
                draft_id = action.get("draft_id", "")
                ok = gmail.delete_draft(draft_id) if draft_id else False
                return "Draft deleted." if ok else "Couldn't delete that draft."

            if action_type == "REPLY_EMAIL":
                message_id = action.get("message_id", "")
                body = action.get("body", "")
                if not message_id or not body:
                    return "Need message_id and reply body."
                ok = gmail.reply_to(message_id, body)
                return "Reply sent ✓" if ok else "Failed to send reply."

            if action_type == "ARCHIVE_EMAIL":
                message_id = action.get("message_id", "")
                ok = gmail.archive_email(message_id) if message_id else False
                return "Archived ✓" if ok else "Couldn't archive — check the message ID."

            if action_type == "DELETE_EMAIL":
                message_id = action.get("message_id", "")
                ok = gmail.delete_email(message_id) if message_id else False
                return "Moved to trash ✓" if ok else "Couldn't delete — check the message ID."

            if action_type == "MARK_READ":
                message_id = action.get("message_id", "")
                ok = gmail.mark_read(message_id) if message_id else False
                return "Marked as read ✓" if ok else "Couldn't mark — check the message ID."

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

        # Calendar actions
        if action_type == "GET_CALENDAR":
            if not self._google_connected(user):
                return "Google not connected. Use /connect_google."
            try:
                events = self._calendar(user).list_upcoming(int(action.get("limit", 10)))
                if not events:
                    return "No upcoming calendar events."
                lines = ["*Upcoming Events*\n"]
                for e in events:
                    start = e.get("start", {})
                    dt = start.get("dateTime", start.get("date", ""))[:16].replace("T", " ")
                    lines.append(f"`{dt}` — *{e.get('summary', '(no title)')}*")
                return "\n".join(lines)
            except Exception as e:
                logger.error("calendar_get_error", error=str(e))
                return f"Calendar error: {e}"

        if action_type in ("CREATE_EVENT", "CREATE_APPOINTMENT"):
            if not self._google_connected(user):
                return "Google not connected. Use /connect_google."
            title = action.get("title", "")
            start = action.get("start", "")
            if not title or not start:
                return "Need event title and start time."
            try:
                attendees = action.get("attendees") or []
                if isinstance(attendees, str):
                    attendees = [a.strip() for a in attendees.split(",") if a.strip()]
                reminders = action.get("reminders_minutes") or action.get("reminders")
                if isinstance(reminders, int):
                    reminders = [reminders]

                event = self._calendar(user).create_event(
                    title=title,
                    start=start,
                    end=action.get("end"),
                    description=action.get("description"),
                    location=action.get("location"),
                    attendees=attendees or None,
                    reminders_minutes=reminders,
                    all_day=action.get("all_day", False),
                    recurrence=action.get("recurrence"),
                    tz=action.get("timezone", "America/New_York"),
                )
                if event:
                    link = event.get("htmlLink", "")
                    start_str = start[:16].replace("T", " ")
                    end_str = (action.get("end", "")[:16].replace("T", " ")) if action.get("end") else ""
                    inv_str = f"\nInvites sent to: {', '.join(attendees)}" if attendees else ""
                    return (
                        f"Event created ✓\n"
                        f"*{title}*\n"
                        f"Start: `{start_str}`"
                        + (f" → `{end_str}`" if end_str else "")
                        + (f"\nLocation: {action['location']}" if action.get("location") else "")
                        + inv_str
                        + (f"\n[View in Calendar]({link})" if link else "")
                    )
                return "Failed to create event."
            except Exception as e:
                logger.error("calendar_create_error", error=str(e))
                return f"Calendar error: {e}"

        if action_type == "UPDATE_EVENT":
            if not self._google_connected(user):
                return "Google not connected. Use /connect_google."
            event_id = action.get("event_id", "")
            if not event_id:
                return "Need the event ID to update. Search for it with 'find [event name]'."
            try:
                attendees = action.get("attendees")
                if isinstance(attendees, str):
                    attendees = [a.strip() for a in attendees.split(",") if a.strip()]
                event = self._calendar(user).update_event(
                    event_id=event_id,
                    title=action.get("title"),
                    start=action.get("start"),
                    end=action.get("end"),
                    description=action.get("description"),
                    location=action.get("location"),
                    attendees=attendees,
                    tz=action.get("timezone", "America/New_York"),
                )
                return f"Event updated ✓\n*{event.get('summary', '')}*" if event else "Failed to update event."
            except Exception as e:
                return f"Calendar error: {e}"

        if action_type == "DELETE_EVENT":
            if not self._google_connected(user):
                return "Google not connected. Use /connect_google."
            event_id = action.get("event_id", "")
            if not event_id:
                return "Need the event ID to delete."
            try:
                ok = self._calendar(user).delete_event(event_id)
                return "Event cancelled and attendees notified ✓" if ok else "Failed to delete event."
            except Exception as e:
                return f"Calendar error: {e}"

        if action_type == "SEARCH_CALENDAR":
            if not self._google_connected(user):
                return "Google not connected. Use /connect_google."
            query = action.get("query", "")
            if not query:
                return "What should I search for in your calendar?"
            try:
                events = self._calendar(user).search_events(query, int(action.get("limit", 10)))
                if not events:
                    return f"No calendar events found matching '{query}'."
                lines = [f"*Calendar: {query}*\n"]
                for e in events:
                    start = e.get("start", {})
                    dt = start.get("dateTime", start.get("date", ""))[:16].replace("T", " ")
                    eid = e.get("id", "")
                    lines.append(f"`{dt}` — *{e.get('summary', '(no title)')}*\nID: `{eid}`")
                return "\n".join(lines)
            except Exception as e:
                return f"Calendar error: {e}"

        # Sheets — options P/L tracking
        if action_type in ("UPDATE_SHEET", "GET_SHEET_PL"):
            if not self._google_connected(user):
                return "Google not connected. Use /connect_google."

            sheets = self._sheets(user)
            tab = action.get("tab")

            # Resolve the target spreadsheet: explicit id > name lookup > saved default
            sheet_id = action.get("sheet_id")
            sheet_name = action.get("sheet_name")
            if not sheet_id and sheet_name:
                sheet_id = sheets.find_spreadsheet_by_name(sheet_name)
                if not sheet_id:
                    return f"Couldn't find a Google Sheet named *{sheet_name}* in your Drive."
            if not sheet_id:
                sheet_id = (user.preferences or {}).get("options_sheet_id")
            if not sheet_id:
                return (
                    "No P/L sheet linked.\n"
                    "Either name it (\"log this to my Options sheet\") or use "
                    "`/setsheet [name or Sheet ID]`."
                )

            try:
                if action_type == "GET_SHEET_PL":
                    date_prefix = action.get("date", datetime.now(timezone.utc).strftime("%Y-%m-%d"))
                    records = sheets.get_pl_summary(sheet_id, date_prefix, tab=tab)
                    if not records:
                        return f"No P/L entries found for {date_prefix}."
                    total = sum(float(r.get("pl", 0) or 0) for r in records)
                    sign = "+" if total >= 0 else ""
                    lines = [f"*Options P/L — {date_prefix}*\n"]
                    for r in records:
                        pl_val = float(r.get("pl", 0) or 0)
                        s = "+" if pl_val >= 0 else ""
                        lines.append(f"*{r['symbol']}* {r['type']} — {s}${pl_val:,.2f} ({r['contracts']} contracts)")
                    lines.append(f"\nTotal: `{sign}${total:,.2f}`")
                    return "\n".join(lines)

                # UPDATE_SHEET — append a P/L row
                date = action.get("date", datetime.now(timezone.utc).strftime("%Y-%m-%d"))
                symbol = action.get("symbol", "")
                trade_type = action.get("type", "option")
                entry = float(action.get("entry", 0))
                exit_price = float(action.get("exit", 0))
                contracts = int(action.get("contracts", 1))
                pl = float(action.get("pl", round((exit_price - entry) * contracts * 100, 2)))
                notes = action.get("notes", "")

                ok = sheets.append_pl_row(
                    sheet_id, date, symbol, trade_type, entry, exit_price,
                    contracts, pl, notes, tab=tab,
                )
                if ok:
                    sign = "+" if pl >= 0 else ""
                    where = f" → tab *{tab}*" if tab else ""
                    return (
                        f"P/L logged to sheet{where}:\n"
                        f"*{symbol.upper()}* {trade_type.upper()}\n"
                        f"Entry: `${entry}` → Exit: `${exit_price}` | {contracts} contract{'s' if contracts != 1 else ''}\n"
                        f"P/L: `{sign}${pl:,.2f}`"
                    )
                return "Failed to update sheet. Check the name/tab and that STARFIRE has edit access."
            except Exception as e:
                logger.error("sheets_error", action=action_type, error=str(e))
                return f"Sheets error: {e}"

        # CREATE_SHEET — make a new spreadsheet
        if action_type == "CREATE_SHEET":
            if not self._google_connected(user):
                return "Google not connected. Use /connect_google."
            title = action.get("title") or action.get("name", "")
            if not title:
                return "What should I name the new sheet?"
            try:
                sheets = self._sheets(user)
                result = sheets.create_spreadsheet(
                    title=title,
                    tab=action.get("tab"),
                    with_headers=action.get("pl_template", True),
                )
                if not result:
                    return "Failed to create the sheet."
                # Link as the default P/L sheet if none set, or if asked
                prefs = dict(user.preferences or {})
                if action.get("set_default") or not prefs.get("options_sheet_id"):
                    prefs["options_sheet_id"] = result["id"]
                    user.preferences = prefs
                    linked = "\n_Linked as your default P/L sheet._"
                else:
                    linked = ""
                return (
                    f"Created sheet *{title}*\n"
                    f"[Open]({result['url']})"
                    f"{linked}"
                )
            except Exception as e:
                logger.error("create_sheet_error", error=str(e))
                return f"Sheets error: {e}"

        # DELETE_SHEET_ROW — remove matching P/L rows
        if action_type == "DELETE_SHEET_ROW":
            if not self._google_connected(user):
                return "Google not connected. Use /connect_google."
            sheets = self._sheets(user)
            sheet_id = action.get("sheet_id")
            if not sheet_id and action.get("sheet_name"):
                sheet_id = sheets.find_spreadsheet_by_name(action["sheet_name"])
                if not sheet_id:
                    return f"Couldn't find a sheet named *{action['sheet_name']}*."
            sheet_id = sheet_id or (user.preferences or {}).get("options_sheet_id")
            if not sheet_id:
                return "No P/L sheet linked. Use `/setsheet [name or ID]`."
            symbol = action.get("symbol")
            date = action.get("date")
            if not symbol and not date:
                return "Tell me which rows to remove — by symbol, date, or both."
            try:
                removed = sheets.delete_rows_matching(
                    sheet_id, symbol=symbol, date=date, tab=action.get("tab"),
                )
                if removed:
                    crit = ", ".join(filter(None, [symbol, date]))
                    return f"Removed {removed} row{'s' if removed != 1 else ''} ({crit}) from the sheet."
                return "No matching rows found to remove."
            except Exception as e:
                logger.error("delete_sheet_row_error", error=str(e))
                return f"Sheets error: {e}"

        # DELETE_SHEET — trash an entire spreadsheet
        if action_type == "DELETE_SHEET":
            if not self._google_connected(user):
                return "Google not connected. Use /connect_google."
            sheets = self._sheets(user)
            sheet_id = action.get("sheet_id")
            sheet_name = action.get("sheet_name")
            if not sheet_id and sheet_name:
                sheet_id = sheets.find_spreadsheet_by_name(sheet_name)
                if not sheet_id:
                    return f"Couldn't find a sheet named *{sheet_name}*."
            if not sheet_id:
                return "Which sheet should I delete? Give me a name."
            try:
                ok = sheets.trash_spreadsheet(sheet_id)
                if ok:
                    prefs = dict(user.preferences or {})
                    if prefs.get("options_sheet_id") == sheet_id:
                        prefs.pop("options_sheet_id", None)
                        user.preferences = prefs
                    label = sheet_name or sheet_id
                    return f"Moved *{label}* to Drive trash (recoverable for 30 days)."
                return "Failed to delete the sheet. Check STARFIRE has access."
            except Exception as e:
                logger.error("delete_sheet_error", error=str(e))
                return f"Sheets error: {e}"

        # ── ADVANCED SHEETS OPERATIONS ────────────────────────────────────
        if action_type in {
            "SHEET_FORMAT", "SHEET_UPDATE_CELL", "SHEET_UPDATE_RANGE",
            "SHEET_READ", "SHEET_FIND", "SHEET_FIND_REPLACE",
            "SHEET_INSERT_ROW", "SHEET_CLEAR", "SHEET_DELETE_TAB",
            "SHEET_DELETE_COLUMNS", "SHEET_ADD_TAB", "SHEET_RENAME_TAB",
            "SHEET_FREEZE", "SHEET_AUTO_RESIZE", "SHEET_CONDITIONAL_FORMAT",
        }:
            return await self._sheets_op(user, action, action_type)

        return "Done."

    async def _resolve_sheet(self, user: User, action: dict):
        """Resolve spreadsheet ID from action. Returns (sheets, sheet_id) or raises."""
        sheets = self._sheets(user)
        sheet_id = action.get("sheet_id")
        if not sheet_id and action.get("sheet_name"):
            sheet_id = sheets.find_spreadsheet_by_name(action["sheet_name"])
            if not sheet_id:
                return sheets, None
        sheet_id = sheet_id or (user.preferences or {}).get("options_sheet_id")
        return sheets, sheet_id

    async def _sheets_op(self, user: User, action: dict, action_type: str) -> str:
        if not self._google_connected(user):
            return "Google not connected. Use /connect_google."
        try:
            sheets, sheet_id = await self._resolve_sheet(user, action)
            if not sheet_id:
                name = action.get("sheet_name", "")
                return (
                    f"Couldn't find sheet *{name}*." if name
                    else "No sheet specified. Tell me the sheet name."
                )
            tab = action.get("tab")

            # ── FORMAT ────────────────────────────────────────────────────
            if action_type == "SHEET_FORMAT":
                style = action.get("style", "pl")
                if style == "pl":
                    ok = sheets.apply_full_pl_formatting(
                        sheet_id, tab=tab,
                        header_bg=action.get("header_bg", "#1a3a5c"),
                        header_fg=action.get("header_fg", "#ffffff"),
                        positive_color=action.get("positive_color", "#b7e1cd"),
                        negative_color=action.get("negative_color", "#f4cccc"),
                    )
                    return "Sheet formatted ✓ — dark header, currency columns, green/red P/L, frozen row." if ok else "Formatting failed."
                # Custom range format
                rng = action.get("range")
                if not rng:
                    return "Specify a range (e.g. 'A1:H1') for custom formatting."
                ok = sheets.format_range(
                    sheet_id, rng, tab=tab,
                    bg=action.get("bg"),
                    bold=action.get("bold", False),
                    fg=action.get("fg"),
                    font_size=action.get("font_size"),
                    h_align=action.get("h_align"),
                    number_format=action.get("number_format"),
                )
                return f"Formatted *{rng}* ✓" if ok else "Formatting failed."

            # ── CONDITIONAL FORMAT ─────────────────────────────────────────
            if action_type == "SHEET_CONDITIONAL_FORMAT":
                rng = action.get("range", "G2:G1000")
                ok = sheets.add_conditional_formatting(
                    sheet_id, rng, tab=tab,
                    positive_color=action.get("positive_color", "#b7e1cd"),
                    negative_color=action.get("negative_color", "#f4cccc"),
                )
                return f"Conditional formatting added to *{rng}* ✓" if ok else "Failed."

            # ── UPDATE CELL ───────────────────────────────────────────────
            if action_type == "SHEET_UPDATE_CELL":
                cell = action.get("cell", "")
                value = action.get("value", "")
                if not cell:
                    return "Which cell? (e.g. B3)"
                ok = sheets.update_cell(sheet_id, cell, value, tab=tab)
                return f"Cell *{cell}* updated to `{value}` ✓" if ok else "Update failed."

            # ── UPDATE RANGE ──────────────────────────────────────────────
            if action_type == "SHEET_UPDATE_RANGE":
                rng = action.get("range", "")
                values = action.get("values", [])
                if not rng or not values:
                    return "Need range and values."
                ok = sheets.update_range(sheet_id, rng, values)
                return f"Range *{rng}* updated ✓" if ok else "Update failed."

            # ── READ ──────────────────────────────────────────────────────
            if action_type == "SHEET_READ":
                rng = action.get("range", "")
                cell = action.get("cell", "")
                if cell:
                    val = sheets.read_cell(sheet_id, cell if "!" in cell else f"{tab or 'Sheet1'}!{cell}")
                    return f"*{cell}* = `{val}`" if val is not None else f"*{cell}* is empty."
                if rng:
                    rows = sheets.read_range(sheet_id, rng)
                    if not rows:
                        return "Range is empty."
                    lines = [" | ".join(str(c) for c in row) for row in rows[:20]]
                    return f"*{rng}*\n```\n" + "\n".join(lines) + "\n```"
                return "Specify a cell or range to read."

            # ── FIND ──────────────────────────────────────────────────────
            if action_type == "SHEET_FIND":
                symbol = action.get("symbol") or action.get("value", "")
                col = action.get("column", 1)  # default Symbol column
                if not symbol:
                    return "What should I search for?"
                matches = sheets.find_rows(sheet_id, col, symbol, tab=tab)
                if not matches:
                    return f"No rows found matching *{symbol}*."
                lines = [f"Row {m['_row_index']+1}: {m['date']} | {m['symbol']} | {m['type']} | P/L {m['pl']}" for m in matches[:15]]
                return f"*{len(matches)} match{'es' if len(matches) != 1 else ''}*\n" + "\n".join(lines)

            # ── FIND & REPLACE ────────────────────────────────────────────
            if action_type == "SHEET_FIND_REPLACE":
                find = action.get("find", "")
                replace = action.get("replace", "")
                if not find:
                    return "What should I replace?"
                count = sheets.find_and_replace(sheet_id, find, replace, tab=tab)
                return f"Replaced {count} occurrence{'s' if count != 1 else ''} of *{find}* → *{replace}* ✓"

            # ── INSERT ROW ────────────────────────────────────────────────
            if action_type == "SHEET_INSERT_ROW":
                row_index = action.get("row", 2)
                values = action.get("values", [])
                ok = sheets.insert_row(sheet_id, row_index, values, tab=tab)
                return f"Row inserted at position {row_index} ✓" if ok else "Insert failed."

            # ── CLEAR ─────────────────────────────────────────────────────
            if action_type == "SHEET_CLEAR":
                rng = action.get("range", "")
                if not rng:
                    return "Which range should I clear? (e.g. A2:H50)"
                ok = sheets.clear_range(sheet_id, rng)
                return f"Cleared *{rng}* ✓" if ok else "Clear failed."

            # ── DELETE TAB ────────────────────────────────────────────────
            if action_type == "SHEET_DELETE_TAB":
                tab_name = action.get("tab", "")
                if not tab_name:
                    return "Which tab should I delete?"
                ok = sheets.delete_tab(sheet_id, tab_name)
                return f"Tab *{tab_name}* deleted ✓" if ok else "Delete failed — tab not found."

            # ── DELETE COLUMNS ────────────────────────────────────────────
            if action_type == "SHEET_DELETE_COLUMNS":
                start = action.get("start_col", 0)
                end = action.get("end_col", start + 1)
                ok = sheets.delete_columns(sheet_id, start, end, tab=tab)
                return f"Column(s) {start}–{end} deleted ✓" if ok else "Delete failed."

            # ── ADD TAB ───────────────────────────────────────────────────
            if action_type == "SHEET_ADD_TAB":
                tab_name = action.get("tab", "")
                if not tab_name:
                    return "What should I name the new tab?"
                ok = sheets.add_tab(sheet_id, tab_name, with_headers=action.get("with_headers", True))
                return f"Tab *{tab_name}* added ✓" if ok else "Failed — tab may already exist."

            # ── RENAME TAB ────────────────────────────────────────────────
            if action_type == "SHEET_RENAME_TAB":
                old = action.get("old_name") or action.get("tab", "")
                new = action.get("new_name", "")
                if not old or not new:
                    return "Need old and new tab names."
                ok = sheets.rename_tab(sheet_id, old, new)
                return f"Tab renamed *{old}* → *{new}* ✓" if ok else "Rename failed."

            # ── FREEZE ────────────────────────────────────────────────────
            if action_type == "SHEET_FREEZE":
                ok = sheets.freeze(sheet_id, rows=action.get("rows", 1), cols=action.get("cols", 0), tab=tab)
                return "Rows frozen ✓" if ok else "Freeze failed."

            # ── AUTO RESIZE ───────────────────────────────────────────────
            if action_type == "SHEET_AUTO_RESIZE":
                ok = sheets.auto_resize_columns(
                    sheet_id, start_col=action.get("start_col", 0),
                    end_col=action.get("end_col", 8), tab=tab,
                )
                return "Columns auto-resized ✓" if ok else "Resize failed."

        except Exception as e:
            logger.error("sheets_op_error", action=action_type, error=str(e))
            return f"Sheets error: {e}"

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
