import structlog
from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from sqlalchemy import select
from datetime import datetime, timezone, timedelta

from app.database import AsyncSessionLocal
from app.models import User, PortfolioState, Task, Goal, SpendingRecord
from app.starfire.decision import DecisionEngine
from app.integrations.lumiscapital import lumiscapital, formatter

logger = structlog.get_logger(__name__)


class TelegramHandlers:

    async def _get_or_create_user(self, telegram_update: Update) -> User:
        tg_user = telegram_update.effective_user
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(User).where(User.telegram_id == tg_user.id)
            )
            user = result.scalar_one_or_none()
            if not user:
                user = User(
                    telegram_id=tg_user.id,
                    username=tg_user.username,
                    first_name=tg_user.first_name,
                    conversation_history=[],
                    preferences={},
                )
                session.add(user)
                await session.commit()
                await session.refresh(user)
            return user

    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user = await self._get_or_create_user(update)
        await update.message.reply_text(
            f"*STARFIRE Online* \n\n"
            f"Hello {update.effective_user.first_name}. I'm your AI operating system.\n\n"
            f"I can help you with:\n"
            f"• Portfolio management & trading decisions\n"
            f"• Task & goal tracking\n"
            f"• Spending analysis\n"
            f"• Market insights\n\n"
            f"Just talk to me naturally, or use:\n"
            f"/portfolio — View your portfolio\n"
            f"/tasks — View pending tasks\n"
            f"/spending — View spending summary\n"
            f"/goals — View your goals\n"
            f"/risk — View risk limits\n"
            f"/help — Show this message\n\n"
            f"What would you like to do?",
            parse_mode=ParseMode.MARKDOWN,
        )

    async def cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await update.message.reply_text(
            "*STARFIRE Commands*\n\n"
            "*Portfolio & System*\n"
            "/start — Initialize session\n"
            "/portfolio — Portfolio snapshot\n"
            "/tasks — Pending tasks\n"
            "/spending — 30-day spending\n"
            "/goals — Active goals\n"
            "/risk — Risk limits\n\n"
            "*Lumiscapital Intelligence*\n"
            "/price AAPL TSLA — Real-time quotes\n"
            "/macro — Macro dashboard (GDP, CPI, rates)\n"
            "/earnings [SYMBOL] — Calendar or detail\n"
            "/sectors — Sector performance\n"
            "/news [SYMBOL|political] — Market news\n"
            "/movers [gainers|losers|actives] — Movers\n"
            "/scout [sector] — Stock screener\n"
            "/profile AAPL — Full company profile\n"
            "/senate [SYMBOL] — Senate disclosures\n"
            "/report — Full daily market report\n\n"
            "Or just talk to me naturally.",
            parse_mode=ParseMode.MARKDOWN,
        )

    async def cmd_portfolio(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user = await self._get_or_create_user(update)
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(PortfolioState)
                .where(PortfolioState.user_id == user.id)
                .order_by(PortfolioState.snapshot_at.desc())
                .limit(1)
            )
            portfolio = result.scalar_one_or_none()

        if not portfolio:
            await update.message.reply_text(
                "No portfolio data yet. Tell me about your holdings and I'll start tracking them.",
                parse_mode=ParseMode.MARKDOWN,
            )
            return

        pnl_sign = "+" if float(portfolio.daily_pnl or 0) >= 0 else ""
        positions = portfolio.positions or {}
        pos_lines = "\n".join(
            f"  • {sym}: {data}" for sym, data in positions.items()
        ) or "  None"

        await update.message.reply_text(
            f"*Portfolio Snapshot*\n\n"
            f"Total Value: `${float(portfolio.total_value or 0):,.2f}`\n"
            f"Cash: `${float(portfolio.cash or 0):,.2f}`\n"
            f"Daily P&L: `{pnl_sign}${float(portfolio.daily_pnl or 0):,.2f}` "
            f"({pnl_sign}{float(portfolio.daily_pnl_pct or 0):.2f}%)\n\n"
            f"*Positions:*\n{pos_lines}",
            parse_mode=ParseMode.MARKDOWN,
        )

    async def cmd_tasks(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user = await self._get_or_create_user(update)
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(Task)
                .where(Task.user_id == user.id, Task.status == "PENDING")
                .order_by(Task.priority.desc(), Task.created_at)
                .limit(10)
            )
            tasks = result.scalars().all()

        if not tasks:
            await update.message.reply_text("No pending tasks. Tell me what you need to do.")
            return

        lines = []
        for t in tasks:
            due = f" — due {t.due_at.strftime('%b %d')}" if t.due_at else ""
            lines.append(f"[{t.priority}] {t.title}{due}")

        await update.message.reply_text(
            "*Pending Tasks*\n\n" + "\n".join(lines),
            parse_mode=ParseMode.MARKDOWN,
        )

    async def cmd_spending(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user = await self._get_or_create_user(update)
        thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)

        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(SpendingRecord)
                .where(
                    SpendingRecord.user_id == user.id,
                    SpendingRecord.recorded_at >= thirty_days_ago,
                )
                .order_by(SpendingRecord.recorded_at.desc())
                .limit(20)
            )
            records = result.scalars().all()

        if not records:
            await update.message.reply_text(
                "No spending records in the last 30 days. Tell me about expenses to track them."
            )
            return

        by_category: dict[str, float] = {}
        for r in records:
            by_category[r.category] = by_category.get(r.category, 0) + float(r.amount)

        total = sum(by_category.values())
        lines = [f"  {cat}: ${amt:,.2f}" for cat, amt in sorted(by_category.items())]

        await update.message.reply_text(
            f"*Spending (Last 30 Days)*\n\n"
            + "\n".join(lines)
            + f"\n\n*Total: ${total:,.2f}*",
            parse_mode=ParseMode.MARKDOWN,
        )

    async def cmd_goals(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user = await self._get_or_create_user(update)
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(Goal)
                .where(Goal.user_id == user.id, Goal.status == "ACTIVE")
                .order_by(Goal.created_at.desc())
            )
            goals = result.scalars().all()

        if not goals:
            await update.message.reply_text(
                "No active goals. Tell me what you're working toward and I'll track it."
            )
            return

        lines = []
        for g in goals:
            if g.target_value:
                pct = min(100, float(g.current_value or 0) / float(g.target_value) * 100)
                bar = "█" * int(pct / 10) + "░" * (10 - int(pct / 10))
                lines.append(
                    f"*{g.title}*\n"
                    f"  {bar} {pct:.0f}%\n"
                    f"  {float(g.current_value or 0):.2f} / {float(g.target_value):.2f} {g.unit or ''}"
                )
            else:
                lines.append(f"*{g.title}* ({g.goal_type})")

        await update.message.reply_text(
            "*Active Goals*\n\n" + "\n\n".join(lines),
            parse_mode=ParseMode.MARKDOWN,
        )

    async def cmd_price(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Usage: /price AAPL TSLA MSFT"""
        args = context.args or []
        if not args:
            await update.message.reply_text("Usage: `/price AAPL TSLA MSFT`", parse_mode=ParseMode.MARKDOWN)
            return
        await update.message.chat.send_action("typing")
        quotes = await lumiscapital.get_quotes(args) if len(args) > 1 else [await lumiscapital.get_quote(args[0])]
        quotes = [q for q in quotes if q]
        if not quotes:
            await update.message.reply_text("Could not fetch price data. Check the symbol(s) and FMP API key.")
            return
        for q in quotes:
            await self._safe_reply(update, formatter.format_quote(q))

    async def cmd_macro(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await update.message.chat.send_action("typing")
        indicators = await lumiscapital.get_economic_indicators()
        treasury = await lumiscapital.get_treasury_rates()
        text = formatter.format_macro_summary(indicators, treasury)
        await self._safe_reply(update, text)

    async def cmd_earnings(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Usage: /earnings [AAPL] — if symbol given, shows detail. Otherwise shows calendar."""
        args = context.args or []
        await update.message.chat.send_action("typing")
        if args:
            symbol = args[0].upper()
            surprises = await lumiscapital.get_earnings_surprises(symbol)
            estimates = await lumiscapital.get_analyst_estimates(symbol)
            lines = [f"*{symbol} Earnings*\n"]
            if surprises:
                lines.append("*Historical EPS Surprises:*")
                for s in surprises[:6]:
                    actual = s.get("actualEarningResult", "N/A")
                    est = s.get("estimatedEarning", "N/A")
                    lines.append(f"  {s.get('date','')[:7]}: Actual `{actual}` vs Est `{est}`")
            if estimates:
                lines.append("\n*Forward Estimates:*")
                for e in estimates[:3]:
                    lines.append(
                        f"  {e.get('date','')[:7]}: EPS `{e.get('estimatedEpsAvg','N/A')}` "
                        f"Rev `${(e.get('estimatedRevenueAvg') or 0)/1e9:.2f}B`"
                    )
            await self._safe_reply(update, "\n".join(lines))
        else:
            calendar = await lumiscapital.get_earnings_calendar(7)
            await self._safe_reply(update, formatter.format_earnings_calendar(calendar))

    async def cmd_sectors(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await update.message.chat.send_action("typing")
        sectors = await lumiscapital.get_sector_performance()
        await self._safe_reply(update, formatter.format_sector_performance(sectors))

    async def cmd_news(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Usage: /news [AAPL | political]"""
        args = context.args or []
        await update.message.chat.send_action("typing")
        if args:
            topic = args[0].lower()
            if topic == "political":
                news = await lumiscapital.get_political_news(10)
                title = "Political / Senate News"
            else:
                news = await lumiscapital.get_stock_news(args[0].upper(), 10)
                title = f"{args[0].upper()} News"
        else:
            news = await lumiscapital.get_general_news(10)
            title = "Market News"
        await self._safe_reply(update, formatter.format_news(news, title))

    async def cmd_movers(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Usage: /movers [gainers|losers|actives]"""
        args = context.args or ["gainers"]
        mover_type = args[0].lower()
        await update.message.chat.send_action("typing")
        if mover_type == "losers":
            data = await lumiscapital.get_losers()
            title = "Top Losers"
        elif mover_type in ("actives", "active"):
            data = await lumiscapital.get_most_active()
            title = "Most Active"
        else:
            data = await lumiscapital.get_gainers()
            title = "Top Gainers"
        await self._safe_reply(update, formatter.format_scout_report(data[:10], title))

    async def cmd_scout(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Usage: /scout [sector] — screens for quality stocks"""
        args = context.args or []
        await update.message.chat.send_action("typing")
        sector = " ".join(args) if args else None
        stocks = await lumiscapital.scout_stocks(
            market_cap_min=1_000_000_000,
            price_min=10,
            volume_min=500_000,
            sector=sector,
            limit=15,
        )
        title = f"Scout Report — {sector}" if sector else "Scout Report"
        await self._safe_reply(update, formatter.format_scout_report(stocks, title))

    async def cmd_profile(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Usage: /profile AAPL"""
        args = context.args or []
        if not args:
            await update.message.reply_text("Usage: `/profile AAPL`", parse_mode=ParseMode.MARKDOWN)
            return
        await update.message.chat.send_action("typing")
        symbol = args[0].upper()
        profile = await lumiscapital.get_company_profile(symbol)
        metrics = await lumiscapital.get_key_metrics(symbol)
        if not profile:
            await update.message.reply_text(f"No profile found for {symbol}.")
            return
        await self._safe_reply(update, formatter.format_company_profile(profile, metrics))

    async def cmd_senate(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Usage: /senate [AAPL]"""
        args = context.args or []
        await update.message.chat.send_action("typing")
        symbol = args[0].upper() if args else None
        trades = await lumiscapital.get_senate_trades(symbol)
        if not trades:
            await update.message.reply_text("No Senate trading disclosures found.")
            return
        lines = ["*Senate Trading Disclosures*\n"]
        for t in trades[:15]:
            lines.append(
                f"`{t.get('transactionDate','')[:10]}` *{t.get('senator','')}* — "
                f"{t.get('asset_description','')} ({t.get('type','')})"
            )
        await self._safe_reply(update, "\n".join(lines))

    async def cmd_report(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Full daily market report — prices, macro, earnings, movers, news."""
        await update.message.chat.send_action("typing")
        await update.message.reply_text("Generating your daily market report... this takes a moment.")

        sections = []

        # Market movers
        gainers = await lumiscapital.get_gainers()
        if gainers:
            sections.append(formatter.format_scout_report(gainers[:5], "Top Gainers Today"))

        losers = await lumiscapital.get_losers()
        if losers:
            sections.append(formatter.format_scout_report(losers[:5], "Top Losers Today"))

        # Sector performance
        sectors = await lumiscapital.get_sector_performance()
        if sectors:
            sections.append(formatter.format_sector_performance(sectors))

        # Upcoming earnings
        calendar = await lumiscapital.get_earnings_calendar(3)
        if calendar:
            sections.append(formatter.format_earnings_calendar(calendar))

        # Market news
        news = await lumiscapital.get_general_news(5)
        if news:
            sections.append(formatter.format_news(news, "Top Market News"))

        if not sections:
            await update.message.reply_text("Could not generate report. Check your FMP API key.")
            return

        for section in sections:
            await self._safe_reply(update, section)

    async def _safe_reply(self, update: Update, text: str) -> None:
        if not text:
            return
        chunks = [text[i:i+4096] for i in range(0, len(text), 4096)]
        for chunk in chunks:
            try:
                await update.message.reply_text(chunk, parse_mode=ParseMode.MARKDOWN)
            except Exception:
                await update.message.reply_text(chunk)

    async def cmd_risk(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        from app.config import settings

        await update.message.reply_text(
            "*Risk Engine Limits*\n\n"
            f"Max Daily Loss: `{settings.risk_max_daily_loss_pct}%`\n"
            f"Max Position Size: `{settings.risk_max_position_size_pct}%`\n"
            f"Max Trades Per Day: `{settings.risk_max_trades_per_day}`\n\n"
            "_These limits are enforced automatically. No exceptions._",
            parse_mode=ParseMode.MARKDOWN,
        )

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user_text = update.message.text
        if not user_text:
            return

        await update.message.chat.send_action("typing")

        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(User).where(User.telegram_id == update.effective_user.id)
            )
            user = result.scalar_one_or_none()

            if not user:
                user = User(
                    telegram_id=update.effective_user.id,
                    username=update.effective_user.username,
                    first_name=update.effective_user.first_name,
                    conversation_history=[],
                    preferences={},
                )
                session.add(user)
                await session.flush()

            engine = DecisionEngine(session)
            try:
                reply = await engine.process_message(user, user_text)
                await session.commit()
            except Exception as e:
                logger.error("message_handler_error", error=str(e))
                await session.rollback()
                reply = "I encountered an error processing that. Please try again."

        await self._safe_reply(update, reply)
