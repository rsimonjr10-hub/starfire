import structlog
from telegram import Update, Bot
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from telegram.constants import ParseMode
from app.config import settings
from app.telegram.handlers import TelegramHandlers

logger = structlog.get_logger(__name__)

_application: Application = None


async def get_application() -> Application:
    global _application
    if _application is None:
        _application = (
            Application.builder()
            .token(settings.telegram_bot_token)
            .build()
        )
        handlers = TelegramHandlers()
        _application.add_handler(CommandHandler("start", handlers.cmd_start))
        _application.add_handler(CommandHandler("portfolio", handlers.cmd_portfolio))
        _application.add_handler(CommandHandler("tasks", handlers.cmd_tasks))
        _application.add_handler(CommandHandler("spending", handlers.cmd_spending))
        _application.add_handler(CommandHandler("goals", handlers.cmd_goals))
        _application.add_handler(CommandHandler("risk", handlers.cmd_risk))
        _application.add_handler(CommandHandler("help", handlers.cmd_help))
        # Lumiscapital / FMP intelligence commands
        _application.add_handler(CommandHandler("price", handlers.cmd_price))
        _application.add_handler(CommandHandler("macro", handlers.cmd_macro))
        _application.add_handler(CommandHandler("earnings", handlers.cmd_earnings))
        _application.add_handler(CommandHandler("sectors", handlers.cmd_sectors))
        _application.add_handler(CommandHandler("news", handlers.cmd_news))
        _application.add_handler(CommandHandler("movers", handlers.cmd_movers))
        _application.add_handler(CommandHandler("scout", handlers.cmd_scout))
        _application.add_handler(CommandHandler("profile", handlers.cmd_profile))
        _application.add_handler(CommandHandler("senate", handlers.cmd_senate))
        _application.add_handler(CommandHandler("report", handlers.cmd_report))
        _application.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.handle_message)
        )
        await _application.initialize()
    return _application


async def send_notification(telegram_id: int, message: str) -> None:
    """Send a proactive notification from STARFIRE to a user."""
    try:
        app = await get_application()
        await app.bot.send_message(
            chat_id=telegram_id,
            text=message,
            parse_mode=ParseMode.MARKDOWN,
        )
    except Exception as e:
        logger.error("telegram_notify_error", telegram_id=telegram_id, error=str(e))


class StarfireBot:
    async def process_update(self, update_data: dict) -> None:
        app = await get_application()
        update = Update.de_json(update_data, app.bot)
        await app.process_update(update)
