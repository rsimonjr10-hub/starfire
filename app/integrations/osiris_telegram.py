"""
OsirisTelegramBridge — lets STARFIRE send commands to osiris_prime_bot via Telegram.

How it works:
  1. STARFIRE formats a structured command message.
  2. Sends it to OSIRIS_TELEGRAM_CHAT_ID using STARFIRE's own bot token.
     (This must be a group/channel where osiris_prime_bot is a member and can read.)
  3. Optionally, if OSIRIS_BOT_TOKEN is set, STARFIRE can also send
     result notifications to users appearing to come from osiris_prime_bot.

Setup:
  - Create a Telegram group → add @starfire5_bot + @osiris_prime_bot
  - Get the group's chat_id (send /start to @userinfobot in the group)
  - Set OSIRIS_TELEGRAM_CHAT_ID to that value in Railway
  - Optionally set OSIRIS_BOT_TOKEN to osiris_prime_bot's token for reply support
"""

import json
import structlog
import httpx
from typing import Optional
from app.config import settings

logger = structlog.get_logger(__name__)

_TG_API = "https://api.telegram.org"


def _normalize_chat_id(chat_id: Optional[str]) -> Optional[str]:
    """Telegram web URLs show supergroup IDs without the -100 prefix. Fix it."""
    if not chat_id:
        return None
    s = chat_id.strip()
    # Supergroup IDs are large negatives. Web hash drops the '100' after the minus.
    # e.g. web shows -5001956862 but API needs -1005001956862
    if s.startswith("-") and not s.startswith("-100") and len(s) >= 10:
        return "-100" + s[1:]
    return s


class OsirisTelegramBridge:

    @property
    def _starfire_token(self) -> str:
        return settings.telegram_bot_token

    @property
    def _osiris_token(self) -> Optional[str]:
        return settings.osiris_bot_token or None

    @property
    def _chat_id(self) -> Optional[str]:
        raw = settings.osiris_telegram_chat_id or None
        return _normalize_chat_id(raw)

    def is_available(self) -> bool:
        return bool(self._starfire_token and self._chat_id)

    @property
    def _post_token(self) -> str:
        """Use OSIRIS token to post if available (it's already in Argus Tower).
        Fall back to STARFIRE token if not set."""
        return self._osiris_token or self._starfire_token

    async def send_command(
        self,
        command: str,
        payload: dict,
        user_telegram_id: Optional[int] = None,
    ) -> bool:
        """
        Send a structured command to the Argus Tower group.
        Uses OSIRIS bot token so it can post without @starfire5_bot being in the group.
        """
        if not self.is_available():
            return False

        body = json.dumps(payload, indent=2)
        text = (
            f"STARFIRE → OSIRIS\n"
            f"Command: {command}\n"
            f"```\n{body}\n```"
        )
        if user_telegram_id:
            text += f"\nRoute reply to user: {user_telegram_id}"

        return await self._send(self._post_token, self._chat_id, text)

    async def send_trade_order(
        self,
        user_telegram_id: int,
        symbol: str,
        side: str,
        size_pct: float,
        extra: Optional[dict] = None,
    ) -> bool:
        """
        Notify osiris_prime_bot of a trade order STARFIRE has authorized.
        """
        payload = {
            "symbol": symbol,
            "side": side,
            "size_pct": size_pct,
            "authorized_by": "STARFIRE",
            "route_reply_to": user_telegram_id,
        }
        if extra:
            payload.update(extra)
        return await self.send_command("EXECUTE_TRADE", payload, user_telegram_id)

    async def request_status(self, user_telegram_id: int) -> bool:
        """Ask osiris_prime_bot for a status report."""
        return await self.send_command(
            "STATUS_REQUEST",
            {"route_reply_to": user_telegram_id},
            user_telegram_id,
        )

    async def send_as_osiris(
        self,
        user_telegram_id: int,
        text: str,
    ) -> bool:
        """
        Send a message to a user appearing to come from osiris_prime_bot.
        Requires OSIRIS_BOT_TOKEN to be set.
        """
        if not self._osiris_token:
            return False
        return await self._send(self._osiris_token, str(user_telegram_id), text)

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
                    logger.warning("osiris_tg_send_failed", chat_id=chat_id, response=data)
                    return False
                logger.info("osiris_tg_command_sent", chat_id=chat_id)
                return True
        except Exception as e:
            logger.error("osiris_tg_send_error", error=str(e))
            return False


osiris_telegram = OsirisTelegramBridge()
