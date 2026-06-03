import asyncio
import structlog
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import init_db
from app.routers import webhook, portfolio, trades, goals, admin
from app.routers import google_auth
from app.routers import tickets as tickets_router
from app.routers import dashboard as dashboard_router
from app.routers import voice as voice_router
from app.routers import knowledge as knowledge_router
from app.routers import business_os as business_router
from app.routers import life_os as life_router
from app.routers import automations as automations_router
from app.routers import briefing as briefing_router
from app.routers import realtime as realtime_router
from app.workers.market_worker import MarketWorker
from app.workers.event_worker import EventWorker
from app.workers.report_worker import ReportWorker
from app.workers.automation_worker import AutomationWorker
from app.monitoring.sentinel import sentinel
from app.monitoring.health_worker import HealthWorker

logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))
structlog.configure(
    processors=[
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.dev.ConsoleRenderer(),
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    logger_factory=structlog.stdlib.LoggerFactory(),
)

logger = structlog.get_logger(__name__)

market_worker = MarketWorker(interval_seconds=300)
event_worker = EventWorker()
report_worker = ReportWorker()
automation_worker = AutomationWorker(interval_seconds=900)
health_worker = HealthWorker()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("starfire_starting", env=settings.app_env)

    # Initialize sentinel (Sentry + Telegram alerting)
    admin_id = int(settings.admin_telegram_id) if settings.admin_telegram_id else None
    sentinel.init(sentry_dsn=settings.sentry_dsn, admin_telegram_id=admin_id)

    # Initialize database tables
    await init_db()
    logger.info("database_initialized")

    # Register Telegram webhook if configured
    if settings.telegram_bot_token and settings.telegram_webhook_url:
        await _register_telegram_webhook()

    # Start background workers
    market_task = asyncio.create_task(market_worker.start())
    event_task = asyncio.create_task(event_worker.start())
    report_task = asyncio.create_task(report_worker.start())
    automation_task = asyncio.create_task(automation_worker.start())
    health_task = asyncio.create_task(health_worker.start())
    logger.info("background_workers_started")

    yield

    # Shutdown
    await market_worker.stop()
    await event_worker.stop()
    await report_worker.stop()
    await automation_worker.stop()
    await health_worker.stop()
    market_task.cancel()
    event_task.cancel()
    report_task.cancel()
    automation_task.cancel()
    health_task.cancel()
    # Shut down telegram application cleanly
    try:
        from app.telegram.bot import get_application
        tg_app = await get_application()
        await tg_app.shutdown()
    except Exception:
        pass
    logger.info("starfire_shutdown")


async def _register_telegram_webhook():
    import httpx

    url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/setWebhook"
    webhook_url = f"{settings.telegram_webhook_url.rstrip('/')}/webhook/telegram"
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, json={"url": webhook_url})
            data = resp.json()
            if data.get("ok"):
                logger.info("telegram_webhook_registered", url=webhook_url)
            else:
                logger.warning("telegram_webhook_failed", response=data)
    except Exception as e:
        logger.error("telegram_webhook_error", error=str(e))


app = FastAPI(
    title="STARFIRE AI OS",
    description="Conversational AI Operating System powered by Claude",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(webhook.router)
app.include_router(portfolio.router)
app.include_router(trades.router)
app.include_router(goals.router)
app.include_router(admin.router)
app.include_router(google_auth.router)
app.include_router(tickets_router.router)
app.include_router(dashboard_router.router)
app.include_router(voice_router.router)
app.include_router(knowledge_router.router)
app.include_router(business_router.router)
app.include_router(life_router.router)
app.include_router(automations_router.router)
app.include_router(briefing_router.router)
app.include_router(realtime_router.router)


@app.get("/")
async def root():
    return {
        "system": "STARFIRE AI OS",
        "status": "online",
        "version": "1.0.0",
        "components": {
            "brain": "STARFIRE (Claude)",
            "executor": "OSIRIS",
            "risk_engine": "active",
            "event_bus": "Redis",
            "database": "PostgreSQL",
            "interface": "Telegram",
        },
    }


@app.get("/health")
async def health():
    return {"status": "healthy"}
