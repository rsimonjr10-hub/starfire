"""
STARFIRE daily briefing scheduler.

Morning briefing: 09:00 UTC — bills due, tasks for the day, market summary, system health
Evening summary:  22:00 UTC — task progress, spending, goal tracking, warnings
Weekly macro:     Monday 08:00 UTC
"""
import asyncio
import structlog
from datetime import datetime, timezone, timedelta
from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models import User, Task, Bill, SpendingRecord
from app.integrations.lumiscapital import lumiscapital, formatter
from app.integrations.osiris_telegram import osiris_telegram
from app.integrations.osiris_bridge import osiris_bridge
from app.telegram.bot import send_notification

logger = structlog.get_logger(__name__)


class ReportWorker:
    def __init__(self):
        self._running = False

    async def start(self) -> None:
        self._running = True
        logger.info("report_worker_started")
        while self._running:
            now = datetime.now(timezone.utc)
            h, m = now.hour, now.minute

            if h == 7 and m == 0:
                await self._broadcast_per_user(self._morning_focus)
                await asyncio.sleep(61)
            elif h == 9 and m == 0:
                await self._broadcast(await self._morning_briefing())
                await asyncio.sleep(61)
            elif h == 22 and m == 0:
                await self._broadcast_per_user(self._evening_summary)
                await asyncio.sleep(61)
            elif now.weekday() == 0 and h == 8 and m == 0:
                await self._broadcast(await self._weekly_macro())
                await asyncio.sleep(61)
            else:
                await asyncio.sleep(30)

    async def stop(self) -> None:
        self._running = False

    # ─────────────────────────────────────────────────────────────────────
    # MORNING BRIEFING
    # ─────────────────────────────────────────────────────────────────────

    async def _morning_focus(self, user) -> list[str]:
        """7am per-user: top 3 priorities + the one ask. No AI call — fast."""
        from app.services.focus_engine import compute_daily_focus, format_daily_focus
        try:
            async with AsyncSessionLocal() as session:
                focus = await compute_daily_focus(session, user.id)
            return [format_daily_focus(focus, user.first_name or "")]
        except Exception as e:
            logger.error("morning_focus_error", user_id=user.id, error=str(e))
            return []

    async def _morning_briefing(self) -> list[str]:
        logger.info("building_morning_briefing")
        sections = ["*STARFIRE Morning Briefing*\n" + "━" * 28]

        # System health
        health = await self._system_health()
        sections.append(health)

        # Market overview
        try:
            gainers = await lumiscapital.get_gainers()
            if gainers:
                sections.append(formatter.format_scout_report(gainers[:5], "Pre-Market Movers"))
            sectors = await lumiscapital.get_sector_performance()
            if sectors:
                sections.append(formatter.format_sector_performance(sectors))
            calendar = await lumiscapital.get_earnings_calendar(1)
            if calendar:
                sections.append(formatter.format_earnings_calendar(calendar))
            news = await lumiscapital.get_general_news(5)
            if news:
                sections.append(formatter.format_news(news, "Top Stories"))
        except Exception as e:
            logger.error("morning_market_data_error", error=str(e))

        return sections

    # ─────────────────────────────────────────────────────────────────────
    # EVENING SUMMARY (per-user, includes personal data)
    # ─────────────────────────────────────────────────────────────────────

    async def _evening_summary(self, user: User) -> list[str]:
        sections = [f"*STARFIRE Evening Summary*\n" + "━" * 28]
        now = datetime.now(timezone.utc)

        async with AsyncSessionLocal() as session:
            # Tasks due today or overdue
            result = await session.execute(
                select(Task)
                .where(Task.user_id == user.id, Task.status == "PENDING")
                .order_by(Task.due_at.asc().nullslast())
                .limit(10)
            )
            tasks = result.scalars().all()
            overdue = [t for t in tasks if t.due_at and t.due_at < now]
            due_today = [t for t in tasks if t.due_at and now <= t.due_at <= now + timedelta(hours=24)]

            task_lines = []
            if overdue:
                task_lines.append(f"*Overdue ({len(overdue)}):*")
                for t in overdue[:5]:
                    task_lines.append(f"  [{t.id}] {t.title}")
            if due_today:
                task_lines.append(f"*Due Today ({len(due_today)}):*")
                for t in due_today[:5]:
                    task_lines.append(f"  [{t.id}] {t.title}")
            if task_lines:
                sections.append("*Tasks*\n" + "\n".join(task_lines))

            # Bills due in next 5 days
            result = await session.execute(
                select(Bill).where(Bill.user_id == user.id, Bill.is_active == True)
            )
            bills = result.scalars().all()
            bill_lines = []
            for b in bills:
                if b.is_recurring and b.due_day:
                    next_due = now.replace(day=min(b.due_day, 28))
                    if next_due < now:
                        if now.month == 12:
                            next_due = next_due.replace(year=now.year + 1, month=1)
                        else:
                            next_due = next_due.replace(month=now.month + 1)
                    days_away = (next_due - now).days
                    if 0 <= days_away <= 5:
                        autopay = " (autopay)" if b.autopay else " — action needed"
                        bill_lines.append(f"  {b.name}: ${float(b.amount):.2f} in {days_away}d{autopay}")
            if bill_lines:
                sections.append("*Upcoming Bills*\n" + "\n".join(bill_lines))

            # Today's spending
            today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            result = await session.execute(
                select(SpendingRecord)
                .where(SpendingRecord.user_id == user.id, SpendingRecord.recorded_at >= today_start)
            )
            records = result.scalars().all()
            if records:
                total = sum(float(r.amount) for r in records)
                sections.append(f"*Today's Spending:* ${total:.2f} across {len(records)} transaction(s)")

        return sections

    # ─────────────────────────────────────────────────────────────────────
    # WEEKLY MACRO
    # ─────────────────────────────────────────────────────────────────────

    async def _weekly_macro(self) -> list[str]:
        logger.info("building_weekly_macro")
        sections = ["*STARFIRE Weekly Macro Digest*\n" + "━" * 28]
        try:
            indicators = await lumiscapital.get_economic_indicators()
            treasury = await lumiscapital.get_treasury_rates()
            if indicators:
                sections.append(formatter.format_macro_summary(indicators, treasury))
        except Exception as e:
            logger.error("weekly_macro_error", error=str(e))
        return sections

    # ─────────────────────────────────────────────────────────────────────
    # SYSTEM HEALTH
    # ─────────────────────────────────────────────────────────────────────

    async def _system_health(self) -> str:
        lines = ["*System Health*"]

        # OSIRIS
        if osiris_bridge.is_available():
            ok = await osiris_bridge.ping()
            lines.append(f"  OSIRIS HTTP: {'online' if ok else 'UNREACHABLE'}")
        else:
            lines.append("  OSIRIS HTTP: not configured")

        tg_ok = osiris_telegram.is_available()
        lines.append(f"  OSIRIS Telegram: {'connected (Argus Tower)' if tg_ok else 'not configured'}")

        return "\n".join(lines)

    # ─────────────────────────────────────────────────────────────────────
    # BROADCAST HELPERS
    # ─────────────────────────────────────────────────────────────────────

    async def _broadcast(self, sections: list[str]) -> None:
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(User).where(User.is_active == True))
            users = result.scalars().all()

        for user in users:
            for section in sections:
                try:
                    await send_notification(user.telegram_id, section)
                    await asyncio.sleep(0.3)
                except Exception as e:
                    logger.error("broadcast_error", user_id=user.id, error=str(e))

    async def _broadcast_per_user(self, builder) -> None:
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(User).where(User.is_active == True))
            users = result.scalars().all()

        for user in users:
            try:
                sections = await builder(user)
                for section in sections:
                    await send_notification(user.telegram_id, section)
                    await asyncio.sleep(0.3)
            except Exception as e:
                logger.error("per_user_broadcast_error", user_id=user.id, error=str(e))
