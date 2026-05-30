#!/usr/bin/env python3
"""
Register the Telegram webhook URL with the Bot API.
Run once after deployment:
    python scripts/setup_telegram_webhook.py
"""
import asyncio
import httpx
import os
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
WEBHOOK_URL = os.environ["TELEGRAM_WEBHOOK_URL"].rstrip("/") + "/webhook/telegram"


async def main():
    url = f"https://api.telegram.org/bot{TOKEN}/setWebhook"
    async with httpx.AsyncClient() as client:
        resp = await client.post(url, json={"url": WEBHOOK_URL})
        data = resp.json()
        if data.get("ok"):
            print(f"Webhook registered: {WEBHOOK_URL}")
        else:
            print(f"Failed: {data}")


asyncio.run(main())
