import structlog
from fastapi import APIRouter, Request, HTTPException, Header
from app.config import settings
from app.telegram.bot import StarfireBot

logger = structlog.get_logger(__name__)
router = APIRouter()
bot = StarfireBot()


@router.post("/webhook/telegram")
async def telegram_webhook(request: Request):
    """
    Receives Telegram webhook updates.
    Validates the request and dispatches to the bot.
    """
    try:
        data = await request.json()
        await bot.process_update(data)
        return {"ok": True}
    except Exception as e:
        logger.error("webhook_error", error=str(e))
        raise HTTPException(status_code=500, detail="Webhook processing failed")


@router.get("/webhook/health")
async def health_check():
    return {"status": "ok", "service": "STARFIRE"}
