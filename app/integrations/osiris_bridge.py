"""
OSIRIS Bridge — HTTP client for the external OSIRIS service on Railway.

When OSIRIS_SERVICE_URL is set, STARFIRE sends validated trade intents
to the remote OSIRIS service instead of the local executor.

Protocol:
  POST /execute
  Body: {
    "user_id": 123,
    "symbol": "AAPL",
    "side": "BUY",
    "size_pct": 10.0,
    "intent_payload": {...},
    "secret": "..."
  }
  Response: {
    "status": "FILLED" | "REJECTED",
    "filled_price": 185.50,
    "quantity": 5.4,
    "slippage": 0.0003,
    "order_id": "...",
    "error": null
  }
"""

import httpx
import structlog
from typing import Optional
from app.config import settings

logger = structlog.get_logger(__name__)


class OsirisBridge:
    """
    HTTP bridge to the external OSIRIS Railway service.
    STARFIRE sends validated trade intents; OSIRIS executes and returns fills.
    """

    def __init__(self):
        self.base_url = settings.osiris_service_url.rstrip("/") if settings.osiris_service_url else ""
        self.secret = settings.inter_service_secret
        self.timeout = 30

    @property
    def _headers(self) -> dict:
        return {
            "X-Service-Secret": self.secret,
            "Content-Type": "application/json",
        }

    def is_available(self) -> bool:
        return bool(settings.osiris_service_url)

    async def execute_trade(
        self,
        user_id: int,
        symbol: str,
        side: str,
        size_pct: float,
        intent_payload: dict,
    ) -> dict:
        """
        Send a validated trade intent to OSIRIS for execution.
        Returns execution result dict compatible with the local OsirisExecutor.
        """
        payload = {
            "user_id": user_id,
            "symbol": symbol,
            "side": side,
            "size_pct": size_pct,
            "intent_payload": intent_payload,
            "secret": self.secret,
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(
                    f"{self.base_url}/execute",
                    json=payload,
                    headers=self._headers,
                )
                resp.raise_for_status()
                result = resp.json()
                logger.info(
                    "osiris_bridge_response",
                    symbol=symbol,
                    side=side,
                    status=result.get("status"),
                )
                return result
        except Exception as e:
            logger.error("osiris_bridge_error", symbol=symbol, error=str(e))
            return {"status": "REJECTED", "error": f"OSIRIS unreachable: {str(e)}"}

    async def get_status(self) -> dict:
        """Get OSIRIS service status and current positions."""
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    f"{self.base_url}/status",
                    headers=self._headers,
                )
                resp.raise_for_status()
                return resp.json()
        except Exception as e:
            logger.error("osiris_status_error", error=str(e))
            return {"status": "unreachable", "error": str(e)}

    async def ping(self) -> bool:
        """Health check."""
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(f"{self.base_url}/health")
                return resp.status_code == 200
        except Exception:
            return False


osiris_bridge = OsirisBridge()
