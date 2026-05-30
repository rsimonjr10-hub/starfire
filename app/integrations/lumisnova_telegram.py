"""
LumisnovaTelegramBridge — STARFIRE routes financial data queries to @lumisnovacapital_bot.

Setup:
  - Add @starfire5_bot and @lumisnovacapital_bot to the same Telegram group
    (can reuse Argus Tower or a dedicated data channel)
  - Set LUMISNOVA_TELEGRAM_CHAT_ID to that group's chat_id in Railway

When LUMISNOVA_TELEGRAM_CHAT_ID is set, STARFIRE sends structured query
commands to that channel. @lumisnovacapital_bot reads and responds there.
Falls back to direct FMP calls when not configured.
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
    def _token(self) -> str:
        return settings.telegram_bot_token

    @property
    def _chat_id(self) -> Optional[str]:
        return settings.lumisnova_telegram_chat_id or None

    def is_available(self) -> bool:
        return bool(self._token and self._chat_id)

    async def query(
        self,
        query_type: str,
        params: dict,
        user_telegram_id: Optional[int] = None,
    ) -> bool:
        """Route a financial data query to @lumisnovacapital_bot."""
        if not self.is_available():
            return False

        body = json.dumps(params, indent=2)
        text = (
            f"STARFIRE → LUMISNOVA\n"
            f"Query: {query_type}\n"
            f"```\n{body}\n```"
        )
        if user_telegram_id:
            text += f"\nRoute reply to user: {user_telegram_id}"

        return await self._send(text)

    async def request_portfolio(self, user_telegram_id: int) -> bool:
        return await self.query("PORTFOLIO_SUMMARY", {"route_reply_to": user_telegram_id}, user_telegram_id)

    async def request_pnl(self, user_telegram_id: int, period: str = "today") -> bool:
        return await self.query("PNL_REPORT", {"period": period, "route_reply_to": user_telegram_id}, user_telegram_id)

    async def request_risk_metrics(self, user_telegram_id: int) -> bool:
        return await self.query("RISK_METRICS", {"route_reply_to": user_telegram_id}, user_telegram_id)

    async def _send(self, text: str) -> bool:
        url = f"{_TG_API}/bot{self._token}/sendMessage"
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(url, json={
                    "chat_id": self._chat_id,
                    "text": text,
                    "parse_mode": "Markdown",
                })
                data = resp.json()
                if not data.get("ok"):
                    logger.warning("lumisnova_tg_send_failed", response=data)
                    return False
                return True
        except Exception as e:
            logger.error("lumisnova_tg_send_error", error=str(e))
            return False


lumisnova_telegram = LumisnovaTelegramBridge()
