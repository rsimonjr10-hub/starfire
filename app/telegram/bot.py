import structlog
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters
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
        h = TelegramHandlers()

        # Core personal OS
        _application.add_handler(CommandHandler("start", h.cmd_start))
        _application.add_handler(CommandHandler("help", h.cmd_help))
        _application.add_handler(CommandHandler("week", h.cmd_week))
        _application.add_handler(CommandHandler("tasks", h.cmd_tasks))
        _application.add_handler(CommandHandler("done", h.cmd_done))
        _application.add_handler(CommandHandler("goals", h.cmd_goals))
        _application.add_handler(CommandHandler("spending", h.cmd_spending))
        _application.add_handler(CommandHandler("log", h.cmd_log))
        _application.add_handler(CommandHandler("budget", h.cmd_budget))
        _application.add_handler(CommandHandler("bills", h.cmd_bills))
        _application.add_handler(CommandHandler("paid", h.cmd_paid))
        _application.add_handler(CommandHandler("health", h.cmd_health))
        _application.add_handler(CommandHandler("osiris", h.cmd_osiris))

        # Bot ticketing system
        _application.add_handler(CommandHandler("tickets", h.cmd_tickets))
        _application.add_handler(CommandHandler("checkup", h.cmd_checkup))
        _application.add_handler(CommandHandler("done_ticket", h.cmd_done_ticket))

        # Quick entry commands
        _application.add_handler(CommandHandler("newtask", h.cmd_newtask))
        _application.add_handler(CommandHandler("setreminder", h.cmd_setreminder))
        _application.add_handler(CommandHandler("cal", h.cmd_cal))
        _application.add_handler(CommandHandler("setsheet", h.cmd_setsheet))

        # Dashboard
        _application.add_handler(CommandHandler("mylink", h.cmd_mylink))
        _application.add_handler(CommandHandler("memory", h.cmd_memory))

        # Starfire One — Life OS, Knowledge OS, Business OS, AI Briefing
        _application.add_handler(CommandHandler("focus", h.cmd_focus))
        _application.add_handler(CommandHandler("decide", h.cmd_decide))
        _application.add_handler(CommandHandler("score", h.cmd_score))
        _application.add_handler(CommandHandler("brief", h.cmd_brief))
        _application.add_handler(CommandHandler("habits", h.cmd_habits))
        _application.add_handler(CommandHandler("journal", h.cmd_journal))
        _application.add_handler(CommandHandler("biz", h.cmd_biz))
        _application.add_handler(CommandHandler("know", h.cmd_know))
        _application.add_handler(CommandHandler("cfo", h.cmd_cfo))

        # Work Agent — autonomous background research + math
        _application.add_handler(CommandHandler("work", h.cmd_work))
        _application.add_handler(CommandHandler("workstatus", h.cmd_workstatus))

        # Undo — reverse the last reversible action
        _application.add_handler(CommandHandler("undo", h.cmd_undo))
        _application.add_handler(CommandHandler("life", h.cmd_life))
        _application.add_handler(CommandHandler("showp", h.cmd_showp))

        # Google (Gmail + Drive + Calendar + Sheets)
        _application.add_handler(CommandHandler("reset_chat", h.cmd_reset_chat))
        _application.add_handler(CommandHandler("connect_google", h.cmd_connect_google))
        _application.add_handler(CommandHandler("inbox", h.cmd_inbox))
        _application.add_handler(CommandHandler("clean_inbox", h.cmd_clean_inbox))
        _application.add_handler(CommandHandler("search_email", h.cmd_search_email))
        _application.add_handler(CommandHandler("drive", h.cmd_drive))

        # Voice notes and audio files → transcribe → STARFIRE brain
        _application.add_handler(
            MessageHandler(filters.VOICE | filters.AUDIO, h.handle_voice)
        )

        # Photos and documents → queue as email attachments
        _application.add_handler(MessageHandler(filters.PHOTO, h.handle_photo))
        _application.add_handler(MessageHandler(filters.Document.ALL, h.handle_document))

        # Catch-all natural language → STARFIRE brain
        _application.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, h.handle_message)
        )

        await _application.initialize()
    return _application


async def send_notification(telegram_id: int, message: str) -> None:
    try:
        app = await get_application()
        await app.bot.send_message(
            chat_id=telegram_id,
            text=message,
            parse_mode=ParseMode.HTML,
        )
    except Exception as e:
        logger.error("telegram_notify_error", telegram_id=telegram_id, error=str(e))


class StarfireBot:
    async def process_update(self, update_data: dict) -> None:
        app = await get_application()
        update = Update.de_json(update_data, app.bot)
        await app.process_update(update)
