"""
LumisnovaTelegramBridge — STARFIRE routes financial data through @Lumiscapital_bot.

How it works:
  1. STARFIRE fetches data (from FMP or LUMISNOVA service).
  2. Sends the formatted result TO THE USER via @Lumiscapital_bot's token,
     so the data appears to come from LUMISNOVA — not from STARFIRE.
  3. Also posts commands to Argus Tower (group) so @Lumiscapital_bot can
     pick up requests and respond independently if it has its own logic.

Required env vars:
  LUMISNOVA_BOT_TOKEN       = @Lumiscapital_bot's bot token
  LUMISNOVA_TELEGRAM_CHAT_ID = group chat_id (Argus Tower or dedicated channel)
"""

import json
import structlog
import httpx
from typing import Optional
from app.config import settings

logger = structlog.get_logger(__name__)
_TG_API = "https://api.telegram.org"


class LumisnovaTelegramBridge:

    @property
    def _lumisnova_token(self) -> Optional[str]:
        return settings.lumisnova_bot_token or None

    @property
    def _starfire_token(self) -> str:
        return settings.telegram_bot_token

    @property
    def _chat_id(self) -> Optional[str]:
        return settings.lumisnova_telegram_chat_id or None

    def is_available(self) -> bool:
        return bool(self._lumisnova_token)

    def has_group(self) -> bool:
        return bool(self._chat_id)

    async def send_data_to_user(self, user_telegram_id: int, text: str) -> bool:
        """
        Send financial data TO THE USER appearing as @Lumiscapital_bot.
        Requires the user to have started a conversation with @Lumiscapital_bot.
        Falls back to group if direct message fails.
        """
        if not self._lumisnova_token:
            return False

        # Try direct message to user
        ok = await self._send(self._lumisnova_token, str(user_telegram_id), text)
        if ok:
            return True

        # Fallback: send to group if configured
        if self._chat_id:
            group_text = f"[Data for user {user_telegram_id}]\n\n{text}"
            return await self._send(self._lumisnova_token, self._chat_id, group_text)

        return False

    async def post_to_group(self, text: str) -> bool:
        """Post a message to the shared group as @Lumiscapital_bot."""
        if not self._lumisnova_token or not self._chat_id:
            return False
        return await self._send(self._lumisnova_token, self._chat_id, text)

    async def notify_command(
        self,
        query_type: str,
        params: dict,
        user_telegram_id: Optional[int] = None,
    ) -> bool:
        """
        Notify the group that STARFIRE is routing a data request to LUMISNOVA.
        @Lumiscapital_bot can pick this up and respond autonomously.
        """
        if not self._chat_id:
            return False

        body = json.dumps(params, indent=2)
        text = (
            f"STARFIRE → LUMISNOVA\n"
            f"Query: {query_type}\n"
            f"```\n{body}\n```"
        )
        if user_telegram_id:
            text += f"\nRoute reply to user: {user_telegram_id}"

        # Use @Lumiscapital_bot's own token to post (it sees its own message)
        token = self._lumisnova_token or self._starfire_token
        return await self._send(token, self._chat_id, text)

    async def send_portfolio_summary(self, user_telegram_id: int, data: str) -> bool:
        return await self.send_data_to_user(
            user_telegram_id,
            f"*LUMISNOVA Portfolio Summary*\n\n{data}"
        )

    async def send_market_data(self, user_telegram_id: int, action_type: str, data: str) -> bool:
        labels = {
            "GET_PRICE": "Market Quote",
            "GET_MACRO": "Macro Dashboard",
            "GET_EARNINGS": "Earnings Calendar",
            "GET_NEWS": "Market News",
            "GET_SECTOR": "Sector Performance",
            "GET_PROFILE": "Company Profile",
            "GET_MOVERS": "Market Movers",
            "GET_SENATE": "Senate Disclosures",
        }
        label = labels.get(action_type, "Market Data")
        return await self.send_data_to_user(
            user_telegram_id,
            f"*LUMISNOVA — {label}*\n\n{data}"
        )

    async def _send(self, token: str, chat_id: str, text: str) -> bool:
        url = f"{_TG_API}/bot{token}/sendMessage"
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(url, json={
                    "chat_id": chat_id,
                    "text": text,
                    "parse_mode": "Markdown",
                })
                data = resp.json()
                if not data.get("ok"):
                    logger.warning("lumisnova_tg_send_failed", chat_id=chat_id, error=data.get("description"))
                    return False
                return True
        except Exception as e:
            logger.error("lumisnova_tg_error", error=str(e))
            return False


lumisnova_telegram = LumisnovaTelegramBridge()
