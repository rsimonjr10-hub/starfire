"""
Scheduled report worker.
Sends proactive daily/weekly reports to all active users via STARFIRE.
"""
import asyncio
import structlog
from datetime import datetime, timezone
from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models import User
from app.integrations.lumiscapital import lumiscapital, formatter
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
            # Daily pre-market report at 09:00 UTC (5am ET)
            if now.hour == 9 and now.minute == 0:
                await self._send_daily_reports()
                await asyncio.sleep(60)
            # Weekly macro digest on Monday morning
            elif now.weekday() == 0 and now.hour == 8 and now.minute == 0:
                await self._send_weekly_macro()
                await asyncio.sleep(60)
            else:
                await asyncio.sleep(30)

    async def stop(self) -> None:
        self._running = False

    async def _send_daily_reports(self) -> None:
        logger.info("sending_daily_reports")
        sections = await self._build_daily_report()
        if not sections:
            return

        async with AsyncSessionLocal() as session:
            result = await session.execute(select(User).where(User.is_active == True))
            users = result.scalars().all()

        for user in users:
            try:
                await send_notification(
                    user.telegram_id,
                    "STARFIRE Daily Pre-Market Report\n" + "=" * 30,
                )
                for section in sections:
                    await send_notification(user.telegram_id, section)
                    await asyncio.sleep(0.5)
            except Exception as e:
                logger.error("daily_report_send_error", user_id=user.id, error=str(e))

    async def _send_weekly_macro(self) -> None:
        logger.info("sending_weekly_macro")
        indicators = await lumiscapital.get_economic_indicators()
        treasury = await lumiscapital.get_treasury_rates()
        if not indicators:
            return

        macro_text = "STARFIRE Weekly Macro Digest\n" + "=" * 30 + "\n"
        macro_text += formatter.format_macro_summary(indicators, treasury)

        async with AsyncSessionLocal() as session:
            result = await session.execute(select(User).where(User.is_active == True))
            users = result.scalars().all()

        for user in users:
            try:
                await send_notification(user.telegram_id, macro_text)
            except Exception as e:
                logger.error("weekly_macro_error", user_id=user.id, error=str(e))

    async def _build_daily_report(self) -> list[str]:
        sections = []
        try:
            gainers = await lumiscapital.get_gainers()
            if gainers:
                sections.append(formatter.format_scout_report(gainers[:5], "Top Gainers"))

            losers = await lumiscapital.get_losers()
            if losers:
                sections.append(formatter.format_scout_report(losers[:5], "Top Losers"))

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
            logger.error("build_daily_report_error", error=str(e))

        return sections
