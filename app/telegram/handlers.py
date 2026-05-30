import structlog
from decimal import Decimal
from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from sqlalchemy import select
from datetime import datetime, timezone, timedelta

from app.database import AsyncSessionLocal
from app.models import User, PortfolioState, Task, Goal, SpendingRecord
from app.starfire.decision import DecisionEngine

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
            "/start — Initialize session\n"
            "/portfolio — Current portfolio snapshot\n"
            "/tasks — Pending tasks\n"
            "/spending — Spending summary\n"
            "/goals — Active goals\n"
            "/risk — Risk engine limits\n\n"
            "Or just send me a message in plain English.",
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

        # Split long messages
        if len(reply) > 4096:
            for i in range(0, len(reply), 4096):
                await update.message.reply_text(
                    reply[i:i+4096],
                    parse_mode=ParseMode.MARKDOWN,
                )
        else:
            try:
                await update.message.reply_text(reply, parse_mode=ParseMode.MARKDOWN)
            except Exception:
                await update.message.reply_text(reply)
