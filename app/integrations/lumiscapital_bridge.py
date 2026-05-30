"""
Lumisnovacapital Bridge — HTTP client for the Lumisnovacapital_bot service.

When LUMISCAPITAL_SERVICE_URL is set (Railway internal networking), STARFIRE
sends commands directly to the Lumisnovacapital_bot service and gets responses.

Falls back to the direct FMP client when the service is not configured.

Protocol:
  POST /starfire/command
  Body: {"command": "GET_PRICE", "params": {...}, "user_telegram_id": 123}
  Response: {"status": "ok", "data": {...}, "message": "..."}

  POST /starfire/report
  Body: {"report_type": "daily|macro|earnings", "user_telegram_id": 123}
  Response: {"status": "ok", "sent": true}
"""

import httpx
import structlog
from typing import Optional
from app.config import settings

logger = structlog.get_logger(__name__)


class LumiscapitalBridge:
    """
    HTTP bridge to the Lumisnovacapital_bot Railway service.
    Used by STARFIRE to request reports and data from Lumisnovacapital.
    """

    def __init__(self):
        self.base_url = settings.lumiscapital_service_url.rstrip("/")
        self.secret = settings.inter_service_secret
        self.timeout = 20

    @property
    def _headers(self) -> dict:
        return {
            "X-Service-Secret": self.secret,
            "Content-Type": "application/json",
        }

    def is_available(self) -> bool:
        return bool(settings.lumiscapital_service_url)

    async def send_command(
        self,
        command: str,
        params: dict,
        user_telegram_id: Optional[int] = None,
    ) -> Optional[dict]:
        """
        Send a command to Lumisnovacapital and return its response.
        Returns None on error.
        """
        payload = {
            "command": command,
            "params": params,
            "user_telegram_id": user_telegram_id,
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(
                    f"{self.base_url}/starfire/command",
                    json=payload,
                    headers=self._headers,
                )
                resp.raise_for_status()
                data = resp.json()
                logger.info(
                    "lumiscapital_bridge_ok",
                    command=command,
                    status=data.get("status"),
                )
                return data
        except Exception as e:
            logger.error("lumiscapital_bridge_error", command=command, error=str(e))
            return None

    async def request_report(
        self,
        report_type: str,
        user_telegram_id: int,
        params: Optional[dict] = None,
    ) -> bool:
        """
        Tell Lumisnovacapital to generate and send a report directly to the user.
        Returns True if the request was accepted.
        """
        payload = {
            "report_type": report_type,
            "user_telegram_id": user_telegram_id,
            "params": params or {},
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(
                    f"{self.base_url}/starfire/report",
                    json=payload,
                    headers=self._headers,
                )
                resp.raise_for_status()
                data = resp.json()
                return data.get("sent", False) or data.get("status") == "ok"
        except Exception as e:
            logger.error("lumiscapital_report_error", report_type=report_type, error=str(e))
            return False

    async def ping(self) -> bool:
        """Health check — verify Lumisnovacapital is reachable."""
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(
                    f"{self.base_url}/health",
                    headers=self._headers,
                )
                return resp.status_code == 200
        except Exception:
            return False


lumiscapital_bridge = LumiscapitalBridge()
