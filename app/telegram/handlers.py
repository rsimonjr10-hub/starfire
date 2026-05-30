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
from app.config import settings

logger = structlog.get_logger(__name__)

_OAUTH_BASE = "https://starfire-production-3ad8.up.railway.app"


class TelegramHandlers:

    async def _get_or_create_user(self, update: Update) -> User:
        tg_user = update.effective_user
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(User).where(User.telegram_id == tg_user.id))
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
        await self._get_or_create_user(update)
        name = update.effective_user.first_name or "there"
        await update.message.reply_text(
            f"*STARFIRE Online*\n\n"
            f"Hey {name} — I'm your personal AI operating system.\n\n"
            f"I manage your tasks, inbox, spending, goals, and more. "
            f"Just talk to me like you'd talk to a chief of staff.\n\n"
            f"*Get started:*\n"
            f"/connect\\_google — Link Gmail & Drive\n"
            f"/week — This week's tasks\n"
            f"/inbox — Check your emails\n"
            f"/spending — Spending summary\n"
            f"/goals — Active goals\n"
            f"/help — Full command list\n\n"
            f"Or just tell me what you need done.",
            parse_mode=ParseMode.MARKDOWN,
        )

    async def cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await update.message.reply_text(
            "*STARFIRE Commands*\n\n"
            "*Personal OS*\n"
            "/week — Weekly task overview\n"
            "/tasks — All pending tasks\n"
            "/done [id] — Mark task complete\n"
            "/goals — Active goals\n"
            "/spending — 30-day spending\n"
            "/log [amount] [category] [desc] — Log expense\n"
            "/budget — Monthly budget overview\n\n"
            "*Gmail & Drive*\n"
            "/inbox — Unread emails\n"
            "/search\\_email [query] — Search emails\n"
            "/drive [query] — Search Google Drive\n"
            "/connect\\_google — Link your Google account\n\n"
            "*Market Intelligence*\n"
            "/price AAPL TSLA — Live quotes\n"
            "/macro — Economic dashboard\n"
            "/earnings [SYMBOL] — Earnings calendar\n"
            "/sectors — Sector performance\n"
            "/news [SYMBOL|political] — News\n"
            "/movers [gainers|losers|actives]\n"
            "/scout [sector] — Stock screener\n"
            "/profile AAPL — Company profile\n"
            "/senate [SYMBOL] — Senate disclosures\n\n"
            "Or just talk to me.",
            parse_mode=ParseMode.MARKDOWN,
        )

    # ------------------------------------------------------------------ #
    # TASKS
    # ------------------------------------------------------------------ #

    async def cmd_week(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Show this week's tasks, organized by due date."""
        user = await self._get_or_create_user(update)
        now = datetime.now(timezone.utc)
        week_end = now + timedelta(days=7)

        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(Task)
                .where(Task.user_id == user.id, Task.status == "PENDING")
                .order_by(Task.due_at.asc().nullslast(), Task.priority.desc())
                .limit(20)
            )
            tasks = result.scalars().all()

        if not tasks:
            await update.message.reply_text(
                "No pending tasks. Tell me what you need to get done this week.",
                parse_mode=ParseMode.MARKDOWN,
            )
            return

        overdue, this_week, later, no_due = [], [], [], []
        for t in tasks:
            if not t.due_at:
                no_due.append(t)
            elif t.due_at < now:
                overdue.append(t)
            elif t.due_at <= week_end:
                this_week.append(t)
            else:
                later.append(t)

        lines = ["*This Week*\n"]
        if overdue:
            lines.append("*Overdue*")
            for t in overdue:
                lines.append(f"  [{t.id}] {t.title} — {t.due_at.strftime('%b %d')}")
        if this_week:
            lines.append("\n*Due This Week*")
            for t in this_week:
                lines.append(f"  [{t.id}] {t.title} — {t.due_at.strftime('%b %d')}")
        if no_due:
            lines.append("\n*No Due Date*")
            for t in no_due[:5]:
                lines.append(f"  [{t.id}] {t.title}")
        if later:
            lines.append(f"\n_+{len(later)} more due later_")

        await self._safe_reply(update, "\n".join(lines))

    async def cmd_tasks(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user = await self._get_or_create_user(update)
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(Task)
                .where(Task.user_id == user.id, Task.status == "PENDING")
                .order_by(Task.priority.desc(), Task.created_at)
                .limit(15)
            )
            tasks = result.scalars().all()

        if not tasks:
            await update.message.reply_text("No pending tasks.")
            return

        lines = ["*Pending Tasks*\n"]
        for t in tasks:
            due = f" — {t.due_at.strftime('%b %d')}" if t.due_at else ""
            lines.append(f"[{t.id}] *{t.title}*{due} (p{t.priority})")

        await self._safe_reply(update, "\n".join(lines))

    async def cmd_done(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Usage: /done 42"""
        args = context.args or []
        if not args or not args[0].isdigit():
            await update.message.reply_text("Usage: `/done [task_id]`\nGet task IDs from /tasks", parse_mode=ParseMode.MARKDOWN)
            return

        task_id = int(args[0])
        user = await self._get_or_create_user(update)
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(Task).where(Task.id == task_id, Task.user_id == user.id))
            task = result.scalar_one_or_none()
            if not task:
                await update.message.reply_text(f"Task {task_id} not found.")
                return
            task.status = "DONE"
            task.completed_at = datetime.now(timezone.utc)
            await session.commit()

        await update.message.reply_text(f"Done! *{task.title}*", parse_mode=ParseMode.MARKDOWN)

    # ------------------------------------------------------------------ #
    # SPENDING & BUDGET
    # ------------------------------------------------------------------ #

    async def cmd_spending(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user = await self._get_or_create_user(update)
        thirty_ago = datetime.now(timezone.utc) - timedelta(days=30)

        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(SpendingRecord)
                .where(SpendingRecord.user_id == user.id, SpendingRecord.recorded_at >= thirty_ago)
                .order_by(SpendingRecord.recorded_at.desc())
                .limit(50)
            )
            records = result.scalars().all()

        if not records:
            await update.message.reply_text("No spending in the last 30 days. Tell me about an expense to track it.")
            return

        by_cat: dict[str, float] = {}
        for r in records:
            by_cat[r.category] = by_cat.get(r.category, 0) + float(r.amount)
        total = sum(by_cat.values())

        lines = ["*Spending — Last 30 Days*\n"]
        for cat, amt in sorted(by_cat.items(), key=lambda x: -x[1]):
            lines.append(f"  {cat}: ${amt:,.2f}")
        lines.append(f"\n*Total: ${total:,.2f}*")

        await self._safe_reply(update, "\n".join(lines))

    async def cmd_log(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Usage: /log 45 Food lunch with team"""
        args = context.args or []
        if len(args) < 2:
            await update.message.reply_text(
                "Usage: `/log [amount] [category] [description]`\nExample: `/log 45 Food lunch with team`",
                parse_mode=ParseMode.MARKDOWN,
            )
            return
        try:
            amount = float(args[0])
        except ValueError:
            await update.message.reply_text("First argument must be a number. Example: `/log 45 Food lunch`", parse_mode=ParseMode.MARKDOWN)
            return

        category = args[1].capitalize()
        description = " ".join(args[2:]) if len(args) > 2 else None
        user = await self._get_or_create_user(update)

        async with AsyncSessionLocal() as session:
            from app.models.spending import SpendingRecord
            record = SpendingRecord(
                user_id=user.id,
                category=category,
                description=description,
                amount=amount,
            )
            session.add(record)
            await session.commit()

        await update.message.reply_text(
            f"Logged: *${amount:.2f}* in *{category}*" + (f" — {description}" if description else ""),
            parse_mode=ParseMode.MARKDOWN,
        )

    async def cmd_budget(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user = await self._get_or_create_user(update)
        budget = user.budget_json or {}

        if not budget:
            await update.message.reply_text(
                "No budget set. Tell me your monthly limits:\n"
                "_\"Set my budget to $500 for food, $200 for entertainment, $100 for transport\"_",
                parse_mode=ParseMode.MARKDOWN,
            )
            return

        thirty_ago = datetime.now(timezone.utc) - timedelta(days=30)
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(SpendingRecord)
                .where(SpendingRecord.user_id == user.id, SpendingRecord.recorded_at >= thirty_ago)
            )
            records = result.scalars().all()

        spent: dict[str, float] = {}
        for r in records:
            spent[r.category] = spent.get(r.category, 0) + float(r.amount)

        lines = ["*Monthly Budget*\n"]
        for cat, limit in sorted(budget.items()):
            actual = spent.get(cat, 0)
            pct = min(100, actual / limit * 100) if limit > 0 else 0
            bar = "█" * int(pct / 10) + "░" * (10 - int(pct / 10))
            status = " OVER" if actual > limit else ""
            lines.append(f"*{cat}*{status}\n  {bar} {pct:.0f}%\n  ${actual:.0f} / ${limit:.0f}")

        await self._safe_reply(update, "\n".join(lines))

    # ------------------------------------------------------------------ #
    # GOALS
    # ------------------------------------------------------------------ #

    async def cmd_goals(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user = await self._get_or_create_user(update)
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(Goal).where(Goal.user_id == user.id, Goal.status == "ACTIVE")
                .order_by(Goal.created_at.desc())
            )
            goals = result.scalars().all()

        if not goals:
            await update.message.reply_text("No active goals. Tell me what you're working toward.")
            return

        lines = []
        for g in goals:
            if g.target_value:
                pct = min(100, float(g.current_value or 0) / float(g.target_value) * 100)
                bar = "█" * int(pct / 10) + "░" * (10 - int(pct / 10))
                lines.append(f"*{g.title}*\n  {bar} {pct:.0f}% — {float(g.current_value or 0):.2f}/{float(g.target_value):.2f} {g.unit or ''}")
            else:
                lines.append(f"*{g.title}* ({g.goal_type})")

        await self._safe_reply(update, "*Active Goals*\n\n" + "\n\n".join(lines))

    # ------------------------------------------------------------------ #
    # GOOGLE — Gmail & Drive
    # ------------------------------------------------------------------ #

    async def cmd_connect_google(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user = await self._get_or_create_user(update)
        if not settings.google_client_id:
            await update.message.reply_text(
                "Google OAuth is not configured yet. The bot admin needs to set "
                "GOOGLE\\_CLIENT\\_ID and GOOGLE\\_CLIENT\\_SECRET in Railway.",
                parse_mode=ParseMode.MARKDOWN,
            )
            return
        auth_url = f"{_OAUTH_BASE}/auth/google?telegram_id={user.telegram_id}"
        await update.message.reply_text(
            f"*Connect Google Account*\n\n"
            f"Tap the link below to authorize STARFIRE to access your Gmail and Drive:\n\n"
            f"{auth_url}\n\n"
            f"_This gives STARFIRE read/send access to your Gmail and read/write access to Drive. "
            f"Your credentials are stored securely in the database._",
            parse_mode=ParseMode.MARKDOWN,
        )

    async def cmd_inbox(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Show unread emails."""
        user = await self._get_or_create_user(update)
        if not user.google_token_json:
            await update.message.reply_text(
                "Gmail not connected. Use /connect\\_google to link your account.",
                parse_mode=ParseMode.MARKDOWN,
            )
            return

        await update.message.chat.send_action("typing")
        try:
            from app.integrations.gmail_service import GmailService
            gmail = GmailService(user.google_token_json)
            messages = gmail.list_unread(10)
        except Exception as e:
            await update.message.reply_text(f"Error reading inbox: {e}")
            return

        if not messages:
            await update.message.reply_text("Inbox is clear — no unread messages.")
            return

        lines = [f"*Unread Emails ({len(messages)})*\n"]
        for i, m in enumerate(messages, 1):
            lines.append(
                f"{i}. *{m.get('subject','(no subject)')}*\n"
                f"   From: {m.get('from','')}\n"
                f"   _{m.get('snippet','')[:100]}_"
            )
        await self._safe_reply(update, "\n".join(lines))

    async def cmd_search_email(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Usage: /search_email invoices from:amazon"""
        args = context.args or []
        if not args:
            await update.message.reply_text("Usage: `/search_email [query]`", parse_mode=ParseMode.MARKDOWN)
            return

        user = await self._get_or_create_user(update)
        if not user.google_token_json:
            await update.message.reply_text("Gmail not connected. Use /connect\\_google.", parse_mode=ParseMode.MARKDOWN)
            return

        query = " ".join(args)
        await update.message.chat.send_action("typing")
        try:
            from app.integrations.gmail_service import GmailService
            gmail = GmailService(user.google_token_json)
            messages = gmail.search(query, 10)
        except Exception as e:
            await update.message.reply_text(f"Search error: {e}")
            return

        if not messages:
            await update.message.reply_text(f"No emails found for: {query}")
            return

        lines = [f"*Email Search: {query}*\n"]
        for i, m in enumerate(messages, 1):
            lines.append(
                f"{i}. *{m.get('subject','(no subject)')}*\n"
                f"   From: {m.get('from','')}\n"
                f"   _{m.get('snippet','')[:100]}_"
            )
        await self._safe_reply(update, "\n".join(lines))

    async def cmd_drive(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Usage: /drive budget 2025"""
        user = await self._get_or_create_user(update)
        if not user.google_token_json:
            await update.message.reply_text("Drive not connected. Use /connect\\_google.", parse_mode=ParseMode.MARKDOWN)
            return

        args = context.args or []
        await update.message.chat.send_action("typing")
        try:
            from app.integrations.gmail_service import DriveService
            drive = DriveService(user.google_token_json)
            if args:
                query = " ".join(args)
                files = drive.search(query)
                title = f"Drive: {query}"
            else:
                files = drive.list_recent()
                title = "Recent Drive Files"
        except Exception as e:
            await update.message.reply_text(f"Drive error: {e}")
            return

        if not files:
            await update.message.reply_text("No files found.")
            return

        lines = [f"*{title}*\n"]
        for f in files:
            link = f.get("webViewLink", "")
            name = f.get("name", "Untitled")
            modified = f.get("modifiedTime", "")[:10]
            lines.append(f"• [{name}]({link}) — {modified}")

        await self._safe_reply(update, "\n".join(lines))

    # ------------------------------------------------------------------ #
    # MARKET (kept for direct use)
    # ------------------------------------------------------------------ #

    async def cmd_price(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        args = context.args or []
        if not args:
            await update.message.reply_text("Usage: `/price AAPL TSLA`", parse_mode=ParseMode.MARKDOWN)
            return
        await update.message.chat.send_action("typing")
        quotes = await lumiscapital.get_quotes(args) if len(args) > 1 else [await lumiscapital.get_quote(args[0])]
        quotes = [q for q in quotes if q]
        if not quotes:
            await update.message.reply_text("Could not fetch price data.")
            return
        for q in quotes:
            await self._safe_reply(update, formatter.format_quote(q))

    async def cmd_macro(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await update.message.chat.send_action("typing")
        indicators = await lumiscapital.get_economic_indicators()
        treasury = await lumiscapital.get_treasury_rates()
        await self._safe_reply(update, formatter.format_macro_summary(indicators, treasury))

    async def cmd_earnings(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        args = context.args or []
        await update.message.chat.send_action("typing")
        if args:
            symbol = args[0].upper()
            surprises = await lumiscapital.get_earnings_surprises(symbol)
            estimates = await lumiscapital.get_analyst_estimates(symbol)
            lines = [f"*{symbol} Earnings*\n"]
            for s in surprises[:6]:
                lines.append(f"  {s.get('date','')[:7]}: Actual `{s.get('actualEarningResult','N/A')}` vs Est `{s.get('estimatedEarning','N/A')}`")
            for e in estimates[:3]:
                lines.append(f"  {e.get('date','')[:7]}: EPS `{e.get('estimatedEpsAvg','N/A')}` Rev `${(e.get('estimatedRevenueAvg') or 0)/1e9:.2f}B`")
            await self._safe_reply(update, "\n".join(lines))
        else:
            calendar = await lumiscapital.get_earnings_calendar(7)
            await self._safe_reply(update, formatter.format_earnings_calendar(calendar))

    async def cmd_sectors(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await update.message.chat.send_action("typing")
        sectors = await lumiscapital.get_sector_performance()
        await self._safe_reply(update, formatter.format_sector_performance(sectors))

    async def cmd_news(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        args = context.args or []
        await update.message.chat.send_action("typing")
        if args:
            topic = args[0].lower()
            if topic == "political":
                news = await lumiscapital.get_political_news(10)
                title = "Political News"
            else:
                news = await lumiscapital.get_stock_news(args[0].upper(), 10)
                title = f"{args[0].upper()} News"
        else:
            news = await lumiscapital.get_general_news(10)
            title = "Market News"
        await self._safe_reply(update, formatter.format_news(news, title))

    async def cmd_movers(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        args = context.args or ["gainers"]
        t = args[0].lower()
        await update.message.chat.send_action("typing")
        if t == "losers":
            data = await lumiscapital.get_losers()
        elif t in ("actives", "active"):
            data = await lumiscapital.get_most_active()
        else:
            data = await lumiscapital.get_gainers()
        await self._safe_reply(update, formatter.format_scout_report(data[:10], t.capitalize()))

    async def cmd_scout(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        args = context.args or []
        await update.message.chat.send_action("typing")
        sector = " ".join(args) if args else None
        stocks = await lumiscapital.scout_stocks(market_cap_min=1_000_000_000, price_min=10, volume_min=500_000, sector=sector, limit=15)
        title = f"Scout — {sector}" if sector else "Stock Scout"
        await self._safe_reply(update, formatter.format_scout_report(stocks, title))

    async def cmd_profile(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
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
        args = context.args or []
        await update.message.chat.send_action("typing")
        symbol = args[0].upper() if args else None
        trades = await lumiscapital.get_senate_trades(symbol)
        if not trades:
            await update.message.reply_text("No Senate disclosures found.")
            return
        lines = ["*Senate Trading Disclosures*\n"]
        for t in trades[:15]:
            lines.append(f"`{t.get('transactionDate','')[:10]}` *{t.get('senator','')}* — {t.get('asset_description','')} ({t.get('type','')})")
        await self._safe_reply(update, "\n".join(lines))

    async def cmd_portfolio(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user = await self._get_or_create_user(update)
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(PortfolioState).where(PortfolioState.user_id == user.id)
                .order_by(PortfolioState.snapshot_at.desc()).limit(1)
            )
            portfolio = result.scalar_one_or_none()

        if not portfolio:
            await update.message.reply_text("No portfolio data yet. Tell me about your holdings.")
            return

        sign = "+" if float(portfolio.daily_pnl or 0) >= 0 else ""
        positions = portfolio.positions or {}
        pos_lines = "\n".join(f"  • {s}: {d}" for s, d in positions.items()) or "  None"
        await update.message.reply_text(
            f"*Portfolio*\n\nValue: `${float(portfolio.total_value or 0):,.2f}`\n"
            f"Cash: `${float(portfolio.cash or 0):,.2f}`\n"
            f"Daily P&L: `{sign}${float(portfolio.daily_pnl or 0):,.2f}` ({sign}{float(portfolio.daily_pnl_pct or 0):.2f}%)\n\n"
            f"*Positions:*\n{pos_lines}",
            parse_mode=ParseMode.MARKDOWN,
        )

    async def cmd_risk(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await update.message.reply_text(
            f"*Risk Limits*\n\nMax Daily Loss: `{settings.risk_max_daily_loss_pct}%`\n"
            f"Max Position: `{settings.risk_max_position_size_pct}%`\n"
            f"Max Trades/Day: `{settings.risk_max_trades_per_day}`",
            parse_mode=ParseMode.MARKDOWN,
        )

    async def cmd_osiris(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Ping osiris_prime_bot via Telegram and show connection status."""
        from app.integrations.osiris_telegram import osiris_telegram
        from app.integrations.osiris_bridge import osiris_bridge

        user = await self._get_or_create_user(update)
        lines = ["*OSIRIS Status*\n"]

        # HTTP bridge
        if osiris_bridge.is_available():
            ping_ok = await osiris_bridge.ping()
            lines.append(f"HTTP bridge: {'connected' if ping_ok else 'unreachable'}")
        else:
            lines.append("HTTP bridge: not configured")

        # Telegram bridge
        if osiris_telegram.is_available():
            sent = await osiris_telegram.request_status(user.telegram_id)
            lines.append(f"Telegram bridge: {'command sent to osiris_prime_bot' if sent else 'send failed'}")
            if sent:
                lines.append(f"_osiris_prime_bot will reply in your shared group_")
        else:
            lines.append(
                "Telegram bridge: not configured\n"
                "_Set OSIRIS\\_TELEGRAM\\_CHAT\\_ID in Railway to enable_"
            )

        await self._safe_reply(update, "\n".join(lines))

    # ------------------------------------------------------------------ #
    # NATURAL LANGUAGE (main STARFIRE brain)
    # ------------------------------------------------------------------ #

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user_text = update.message.text
        if not user_text:
            return

        await update.message.chat.send_action("typing")

        async with AsyncSessionLocal() as session:
            result = await session.execute(select(User).where(User.telegram_id == update.effective_user.id))
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
                logger.error("message_error", error=str(e))
                await session.rollback()
                reply = "Something went wrong on my end. Try again in a moment."

        await self._safe_reply(update, reply)

    async def _safe_reply(self, update: Update, text: str) -> None:
        if not text:
            return
        chunks = [text[i:i+4096] for i in range(0, len(text), 4096)]
        for chunk in chunks:
            try:
                await update.message.reply_text(chunk, parse_mode=ParseMode.MARKDOWN)
            except Exception:
                await update.message.reply_text(chunk)
