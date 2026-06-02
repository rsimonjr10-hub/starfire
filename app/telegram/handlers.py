import structlog
from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from sqlalchemy import select
from datetime import datetime, timezone, timedelta

from app.database import AsyncSessionLocal
from app.models import User, PortfolioState, Task, Goal, SpendingRecord, Bill, BotTicket
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
            f"/week — This week's tasks\n"
            f"/bills — Bills & subscriptions\n"
            f"/inbox — Check emails (needs /connect\\_google)\n"
            f"/health — System status (OSIRIS, LUMISNOVA, Google)\n"
            f"/help — Full command list\n\n"
            f"Or just talk to me naturally.",
            parse_mode=ParseMode.MARKDOWN,
        )

    async def cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await update.message.reply_text(
            "*STARFIRE Commands*\n\n"
            "*Tasks & Goals*\n"
            "/week — This week's tasks\n"
            "/tasks — All pending tasks\n"
            "/done [id] — Mark task complete\n"
            "/goals — Active goals\n\n"
            "*Money*\n"
            "/bills — Bills & subscriptions\n"
            "/paid [id] — Mark bill as paid\n"
            "/spending — 30-day spending summary\n"
            "/log [amount] [category] [desc] — Log expense\n"
            "/budget — Budget vs actual\n\n"
            "*Gmail & Drive*\n"
            "/inbox — Unread emails\n"
            "/search\\_email [query] — Search emails\n"
            "/drive [query] — Search Google Drive\n"
            "/connect\\_google — Link your Google account\n\n"
            "*System*\n"
            "/health — System status\n"
            "/osiris — OSIRIS bridge status\n\n"
            "_For market data, prices & news — ask @Lumiscapital\\_bot_\n\n"
            "Or just talk to me naturally.",
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
                "GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET in Railway.",
            )
            return
        auth_url = f"{_OAUTH_BASE}/auth/google?telegram_id={user.telegram_id}"
        await update.message.reply_text(
            f"<b>Connect Google Account</b>\n\n"
            f"Tap the link below to authorize STARFIRE to access your Gmail and Drive:\n\n"
            f'<a href="{auth_url}">Authorize STARFIRE → Google</a>\n\n'
            f"<i>This gives STARFIRE read/send access to Gmail and read/write access to Drive. "
            f"Your credentials are stored securely in the database.</i>",
            parse_mode=ParseMode.HTML,
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

    async def cmd_bills(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Show all active bills and subscriptions."""
        user = await self._get_or_create_user(update)
        now = datetime.now(timezone.utc)

        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(Bill)
                .where(Bill.user_id == user.id, Bill.is_active == True)
                .order_by(Bill.category, Bill.name)
            )
            bills = result.scalars().all()

        if not bills:
            await update.message.reply_text(
                "No bills tracked. Tell me about your bills:\n"
                "_\"Add Netflix $15.99 monthly due on the 15th\"_",
                parse_mode=ParseMode.MARKDOWN,
            )
            return

        total_monthly = 0.0
        by_cat: dict[str, list] = {}
        for b in bills:
            by_cat.setdefault(b.category, []).append(b)
            if b.is_recurring:
                total_monthly += float(b.amount)

        lines = ["*Bills & Subscriptions*\n"]
        for cat, cat_bills in sorted(by_cat.items()):
            lines.append(f"*{cat.title()}*")
            for b in cat_bills:
                due = f" — day {b.due_day}" if b.due_day else ""
                autopay = " ⚡" if b.autopay else ""
                recur = "/mo" if b.is_recurring else " (one-time)"
                paid = f" _(last paid {b.last_paid_at.strftime('%b %d')})_" if b.last_paid_at else ""
                lines.append(f"  [{b.id}] {b.name}: ${float(b.amount):.2f}{recur}{due}{autopay}{paid}")

        lines.append(f"\n*Total recurring: ${total_monthly:.2f}/mo*")
        lines.append("\nUse `/paid [id]` to mark a bill as paid.")
        await self._safe_reply(update, "\n".join(lines))

    async def cmd_paid(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Usage: /paid 3"""
        args = context.args or []
        if not args or not args[0].isdigit():
            await update.message.reply_text("Usage: `/paid [bill_id]` — get IDs from /bills", parse_mode=ParseMode.MARKDOWN)
            return
        bill_id = int(args[0])
        user = await self._get_or_create_user(update)
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(Bill).where(Bill.id == bill_id, Bill.user_id == user.id))
            bill = result.scalar_one_or_none()
            if not bill:
                await update.message.reply_text(f"Bill {bill_id} not found.")
                return
            bill.last_paid_at = datetime.now(timezone.utc)
            await session.commit()
        await update.message.reply_text(f"*{bill.name}* marked as paid.", parse_mode=ParseMode.MARKDOWN)

    async def cmd_tickets(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Show all open bot tickets grouped by assignee."""
        user = await self._get_or_create_user(update)
        args = context.args or []
        # Optional filter: /tickets osiris | /tickets lumisnova | /tickets all | /tickets done
        filter_arg = args[0].upper() if args else "OPEN"

        async with AsyncSessionLocal() as session:
            if filter_arg == "DONE":
                stmt = select(BotTicket).where(
                    BotTicket.user_id == user.id,
                    BotTicket.status == "DONE",
                ).order_by(BotTicket.completed_at.desc()).limit(20)
            elif filter_arg in ("OSIRIS", "LUMISNOVA"):
                stmt = select(BotTicket).where(
                    BotTicket.user_id == user.id,
                    BotTicket.assigned_to == filter_arg,
                    BotTicket.status.in_(["QUEUED", "SENT"]),
                ).order_by(BotTicket.priority.desc(), BotTicket.created_at)
            else:
                stmt = select(BotTicket).where(
                    BotTicket.user_id == user.id,
                    BotTicket.status.in_(["QUEUED", "SENT"]),
                ).order_by(BotTicket.priority.desc(), BotTicket.created_at)

            result = await session.execute(stmt)
            tickets = result.scalars().all()

        if not tickets:
            await update.message.reply_text(
                "No open tickets." if filter_arg != "DONE" else "No completed tickets yet."
            )
            return

        # Group by assignee
        groups: dict[str, list] = {}
        for t in tickets:
            groups.setdefault(t.assigned_to, []).append(t)

        lines = [f"*Bot Ticket Queue*\n{'━' * 22}\n"]
        status_icons = {"QUEUED": "🕐", "SENT": "📤", "DONE": "✅", "FAILED": "❌"}
        for bot, bot_tickets in groups.items():
            lines.append(f"*{bot}* ({len(bot_tickets)} ticket{'s' if len(bot_tickets) != 1 else ''})")
            for t in bot_tickets:
                icon = status_icons.get(t.status, "•")
                due = f" | done {t.completed_at.strftime('%b %d')}" if t.completed_at else ""
                lines.append(f"  {icon} #{t.id} p{t.priority} — {t.title}{due}")
            lines.append("")

        lines.append("_/checkup to ping bots for status | /done\\_ticket [id] to close_")
        await self._safe_reply(update, "\n".join(lines))

    async def cmd_checkup(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Ping all bots about their open tickets and show the queue."""
        user = await self._get_or_create_user(update)
        await update.message.chat.send_action("typing")

        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(BotTicket).where(
                    BotTicket.user_id == user.id,
                    BotTicket.status.in_(["QUEUED", "SENT"]),
                ).order_by(BotTicket.priority.desc(), BotTicket.created_at)
            )
            tickets = result.scalars().all()

            if not tickets:
                await update.message.reply_text("All bots are clear — no open tickets.")
                return

            from app.integrations.osiris_telegram import osiris_telegram
            from datetime import datetime, timezone

            now = datetime.now(timezone.utc)
            osiris_ids, lumisnova_ids = [], []
            lines = ["*Checkup — Open Tickets*\n"]

            for t in tickets:
                age_h = int((now - t.created_at).total_seconds() // 3600) if t.created_at else 0
                age_str = f"{age_h}h" if age_h else "just now"
                lines.append(f"#{t.id} *{t.assigned_to}* p{t.priority} — {t.title} ({age_str})")
                t.last_checked_at = now
                if t.assigned_to == "OSIRIS":
                    osiris_ids.append(t.id)
                elif t.assigned_to == "LUMISNOVA":
                    lumisnova_ids.append(t.id)

            pinged = []
            if osiris_ids:
                ok = await osiris_telegram.send_command(
                    "TICKET_STATUS_REQUEST",
                    {"ticket_ids": osiris_ids, "from_user": user.telegram_id},
                    user.telegram_id,
                )
                if ok:
                    pinged.append(f"OSIRIS ({len(osiris_ids)} tickets)")
            if lumisnova_ids:
                ok = await osiris_telegram.send_command(
                    "LUMISNOVA_TICKET_STATUS",
                    {"ticket_ids": lumisnova_ids, "from_user": user.telegram_id},
                    user.telegram_id,
                )
                if ok:
                    pinged.append(f"LUMISNOVA ({len(lumisnova_ids)} tickets)")

            await session.commit()

        suffix = f"\n\n_Pinged: {', '.join(pinged)}_" if pinged else "\n\n_Couldn't reach bots — check /health_"
        await self._safe_reply(update, "\n".join(lines) + suffix)

    async def cmd_done_ticket(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Close a bot ticket: /done_ticket [id]"""
        args = context.args or []
        if not args or not args[0].isdigit():
            await update.message.reply_text("Usage: `/done_ticket [ticket_id]`", parse_mode=ParseMode.MARKDOWN)
            return

        ticket_id = int(args[0])
        user = await self._get_or_create_user(update)

        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(BotTicket).where(BotTicket.id == ticket_id, BotTicket.user_id == user.id)
            )
            ticket = result.scalar_one_or_none()
            if not ticket:
                await update.message.reply_text(f"Ticket #{ticket_id} not found.")
                return
            ticket.status = "DONE"
            ticket.completed_at = datetime.now(timezone.utc)
            await session.commit()

        await update.message.reply_text(
            f"Ticket #{ticket_id} closed ✓\n*{ticket.title}*",
            parse_mode=ParseMode.MARKDOWN,
        )

    async def cmd_health(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Full system health check."""
        from app.integrations.osiris_telegram import osiris_telegram
        from app.integrations.osiris_bridge import osiris_bridge
        from app.integrations.lumisnova_telegram import lumisnova_telegram

        user = await self._get_or_create_user(update)
        await update.message.chat.send_action("typing")

        lines = ["*STARFIRE System Health*\n" + "━" * 26 + "\n"]

        # OSIRIS
        lines.append("*OSIRIS (Execution)*")
        if osiris_bridge.is_available():
            ok = await osiris_bridge.ping()
            lines.append(f"  HTTP: {'🟢 online' if ok else '🔴 UNREACHABLE'}")
        else:
            lines.append("  HTTP: not configured\n  _Set OSIRIS\\_SERVICE\\_URL in Railway_")

        diag = await osiris_telegram.diagnose()
        if diag.get("status") == "not_configured":
            lines.append("  Telegram: not configured\n  _Set OSIRIS\\_TELEGRAM\\_CHAT\\_ID_")
        elif diag.get("status") == "ok":
            chat = diag.get("chat_title", diag.get("chat_id", ""))
            lines.append(f"  Telegram: 🟢 connected ({chat})")
        else:
            err = diag.get("error", "unknown")
            fix = diag.get("fix", "")
            lines.append(f"  Telegram: 🔴 FAILED — {err}")
            if fix:
                lines.append(f"  _Fix: {fix}_")

        # OSIRIS last performance report
        report = (user.preferences or {}).get("osiris_report")
        if report:
            pnl = report.get("pnl_today")
            sign = "+" if pnl and pnl >= 0 else ""
            pnl_str = f"{sign}${pnl:,.2f}" if pnl is not None else "N/A"
            reported_at = report.get("reported_at", "")[:10]
            lines.append(f"  Last P/L: `{pnl_str}` ({reported_at})")

        # LUMISNOVA
        lines.append("\n*LUMISNOVA (Data)*")
        if lumisnova_telegram.is_available():
            lines.append("  Telegram: connected")
        else:
            lines.append("  Telegram: not configured (using direct FMP)")

        # Google
        lines.append("\n*Google Workspace*")
        lines.append(f"  Gmail + Drive: {'connected' if user.google_token_json else 'not connected — /connect_google'}")

        # STARFIRE itself
        lines.append(f"\n*STARFIRE*")
        lines.append(f"  Status: online")
        lines.append(f"  Brain: Claude (Anthropic)")

        await self._safe_reply(update, "\n".join(lines))

    async def cmd_osiris(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Send a status ping to osiris_prime_bot via Argus Tower."""
        from app.integrations.osiris_telegram import osiris_telegram
        from app.integrations.osiris_bridge import osiris_bridge

        user = await self._get_or_create_user(update)
        lines = ["*OSIRIS Bridge*\n"]

        if osiris_bridge.is_available():
            ok = await osiris_bridge.ping()
            lines.append(f"HTTP: {'online' if ok else 'unreachable'}")
        else:
            lines.append("HTTP: not configured")

        if osiris_telegram.is_available():
            sent = await osiris_telegram.request_status(user.telegram_id)
            lines.append(f"Telegram: {'status request sent to Argus Tower' if sent else 'SEND FAILED'}")
        else:
            lines.append("Telegram: not configured\n_Set OSIRIS\\_TELEGRAM\\_CHAT\\_ID in Railway_")

        await self._safe_reply(update, "\n".join(lines))

    # ------------------------------------------------------------------ #
    # QUICK COMMANDS — /newtask  /setreminder  /cal  /setsheet
    # ------------------------------------------------------------------ #

    async def cmd_newtask(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Usage: /newtask Task title [p1-10]"""
        import re
        args = context.args or []
        if not args:
            await update.message.reply_text(
                "Usage: `/newtask Task title [p1-10]`\nExample: `/newtask Call accountant p8`",
                parse_mode=ParseMode.MARKDOWN,
            )
            return

        priority = 5
        parts = list(args)
        if parts and re.match(r"^p\d+$", parts[-1], re.IGNORECASE):
            priority = max(1, min(10, int(parts.pop()[1:])))

        title = " ".join(parts)
        user = await self._get_or_create_user(update)

        async with AsyncSessionLocal() as session:
            task = Task(user_id=user.id, title=title, priority=priority)
            session.add(task)
            await session.commit()
            await session.refresh(task)

        await update.message.reply_text(
            f"Task added: *{task.title}* (p{task.priority}) — ID `{task.id}`",
            parse_mode=ParseMode.MARKDOWN,
        )

    async def cmd_setreminder(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Usage: /setreminder tomorrow 9am Call mom"""
        args = context.args or []
        if not args:
            await update.message.reply_text(
                "Usage: `/setreminder [when] [what]`\nExample: `/setreminder tomorrow 9am Call accountant`",
                parse_mode=ParseMode.MARKDOWN,
            )
            return
        await self._run_brain(update, "Set a reminder: " + " ".join(args))

    async def cmd_cal(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Usage: /cal Board meeting tomorrow 2pm"""
        args = context.args or []
        if not args:
            await update.message.reply_text(
                "Usage: `/cal Event title [date/time]`\nExample: `/cal Board meeting June 5 at 2pm`",
                parse_mode=ParseMode.MARKDOWN,
            )
            return
        await self._run_brain(update, "Add to calendar: " + " ".join(args))

    async def cmd_setsheet(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Link a Google Sheet for options P/L tracking — by ID or by name."""
        args = context.args or []
        if not args:
            await update.message.reply_text(
                "Usage: `/setsheet [name or Google Sheet ID]`\n"
                "Examples:\n"
                "`/setsheet Options P/L`  — finds it by name in your Drive\n"
                "`/setsheet 1BxiMVs0XRA...`  — the ID from the sheet URL",
                parse_mode=ParseMode.MARKDOWN,
            )
            return

        user = await self._get_or_create_user(update)
        raw = " ".join(args).strip()

        # A single token with no spaces and 30+ chars is almost certainly an ID.
        looks_like_id = len(args) == 1 and " " not in raw and len(raw) >= 30
        sheet_id = raw
        display = raw

        if not looks_like_id:
            if not user.google_token_json:
                await update.message.reply_text(
                    "To look up a sheet by name I need Google access. Use /connect_google first, "
                    "or pass the Sheet ID directly.",
                )
                return
            await update.message.chat.send_action("typing")
            from app.integrations.gmail_service import SheetsService
            resolved = SheetsService(user.google_token_json).find_spreadsheet_by_name(raw)
            if not resolved:
                await update.message.reply_text(
                    f"Couldn't find a Google Sheet named \"{raw}\" in your Drive. "
                    f"Check the name or paste the Sheet ID instead.",
                )
                return
            sheet_id = resolved
            display = f"{raw} (`{resolved}`)"

        async with AsyncSessionLocal() as session:
            result = await session.execute(select(User).where(User.id == user.id))
            db_user = result.scalar_one_or_none()
            prefs = dict(db_user.preferences or {})
            prefs["options_sheet_id"] = sheet_id
            db_user.preferences = prefs
            await session.commit()

        await update.message.reply_text(
            f"Options P/L sheet linked: {display}\n\n"
            f"Tell me: _\"Update my P/L: sold 10 AAPL calls, entry $2.50, exit $3.75\"_ and I'll log it.",
            parse_mode=ParseMode.MARKDOWN,
        )

    async def cmd_mylink(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Send the user their personal dashboard URL."""
        from app.routers.dashboard import get_dashboard_url
        user = await self._get_or_create_user(update)
        url = get_dashboard_url(user.telegram_id)
        await update.message.reply_text(
            f"🔗 <b>Your STARFIRE Dashboard</b>\n\n"
            f"<a href=\"{url}\">{url}</a>\n\n"
            f"<i>This link is personal — don't share it. It gives full access to your memory, tasks, and OSIRIS data.</i>",
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
        )

    async def cmd_memory(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """List stored memories via the brain."""
        await self._run_brain(update, "list my memories")

    async def _run_brain(self, update: Update, text: str) -> None:
        """Route arbitrary text through STARFIRE brain and reply."""
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
                reply = await engine.process_message(user, text)
                await session.commit()
            except Exception as e:
                logger.error("brain_error", error=str(e))
                await session.rollback()
                reply = "Something went wrong. Try again."

        await self._safe_reply(update, reply)

    # ------------------------------------------------------------------ #
    # NATURAL LANGUAGE (main STARFIRE brain)
    # ------------------------------------------------------------------ #

    _WAKE_WORDS = ("star ", "starfire", "@starfire5_bot")

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user_text = update.message.text
        if not user_text:
            return

        # In group/supergroup chats only respond when directly addressed
        chat_type = update.effective_chat.type if update.effective_chat else "private"
        if chat_type in ("group", "supergroup"):
            lower = user_text.lower()
            if not any(lower.startswith(w) or w in lower for w in self._WAKE_WORDS):
                return
            # Strip the wake word so the brain sees a clean message
            for wake in self._WAKE_WORDS:
                if lower.startswith(wake):
                    user_text = user_text[len(wake):].strip()
                    break
                idx = lower.find(wake)
                if idx != -1:
                    user_text = (user_text[:idx] + user_text[idx + len(wake):]).strip()
                    break
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
