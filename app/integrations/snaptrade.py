"""
SnapTrade API client — brokerage aggregation (Chase, etc.)

Auth: HMAC-SHA256 on request body signed with consumer key.
Users are registered once; their user_id + user_secret stored in DB.
"""
import base64
import hashlib
import hmac
import json
import time
from typing import Optional

import httpx
import structlog

from app.config import settings

logger = structlog.get_logger(__name__)

SNAPTRADE_BASE = "https://api.snaptrade.com/api/v1"


def _sign(body: str = "") -> dict:
    """Return headers + base query params for a SnapTrade request."""
    timestamp = str(int(time.time()))
    sig = hmac.new(
        settings.snaptrade_consumer_key.encode(),
        body.encode(),
        hashlib.sha256,
    )
    signature = base64.b64encode(sig.digest()).decode()
    return {
        "headers": {
            "Signature": signature,
            "timestamp": timestamp,
            "Content-Type": "application/json",
        },
        "base_params": {"clientId": settings.snaptrade_client_id},
    }


class SnapTradeClient:
    """Thin async wrapper around the SnapTrade REST API."""

    async def register_user(self, user_id: str) -> Optional[str]:
        """Register a new SnapTrade user. Returns userSecret or None on failure."""
        body = json.dumps({"userId": user_id})
        auth = _sign(body)
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(
                    f"{SNAPTRADE_BASE}/snapTrade/registerUser",
                    params=auth["base_params"],
                    headers=auth["headers"],
                    content=body,
                )
                if resp.status_code in (200, 201):
                    data = resp.json()
                    return data.get("userSecret")
                if resp.status_code == 400:
                    # User might already exist — try to re-authenticate
                    logger.warning("snaptrade_register_400", body=resp.text)
                    return None
                logger.error("snaptrade_register_error", status=resp.status_code, body=resp.text)
        except Exception as e:
            logger.error("snaptrade_register_exception", error=str(e))
        return None

    async def get_login_url(
        self,
        user_id: str,
        user_secret: str,
        broker: Optional[str] = None,
        reconnect: Optional[str] = None,
    ) -> Optional[str]:
        """Return the SnapTrade connection portal URL for the user to open in a browser."""
        payload: dict = {}
        if broker:
            payload["broker"] = broker
        if reconnect:
            payload["reconnect"] = reconnect
        body = json.dumps(payload) if payload else ""
        auth = _sign(body)
        params = {**auth["base_params"], "userId": user_id, "userSecret": user_secret}
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(
                    f"{SNAPTRADE_BASE}/snapTrade/login",
                    params=params,
                    headers=auth["headers"],
                    content=body,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    return data.get("redirectURI")
                logger.error("snaptrade_login_error", status=resp.status_code, body=resp.text)
        except Exception as e:
            logger.error("snaptrade_login_exception", error=str(e))
        return None

    async def get_accounts(self, user_id: str, user_secret: str) -> list[dict]:
        """Return all brokerage accounts for a user."""
        auth = _sign()
        params = {**auth["base_params"], "userId": user_id, "userSecret": user_secret}
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(
                    f"{SNAPTRADE_BASE}/accounts",
                    params=params,
                    headers=auth["headers"],
                )
                if resp.status_code == 200:
                    return resp.json() or []
                logger.error("snaptrade_accounts_error", status=resp.status_code)
        except Exception as e:
            logger.error("snaptrade_accounts_exception", error=str(e))
        return []

    async def get_account_balances(
        self, user_id: str, user_secret: str, account_id: str
    ) -> list[dict]:
        """Return balances for a specific account."""
        auth = _sign()
        params = {**auth["base_params"], "userId": user_id, "userSecret": user_secret}
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(
                    f"{SNAPTRADE_BASE}/accounts/{account_id}/balances",
                    params=params,
                    headers=auth["headers"],
                )
                if resp.status_code == 200:
                    return resp.json() or []
                logger.error("snaptrade_balances_error", status=resp.status_code, account=account_id)
        except Exception as e:
            logger.error("snaptrade_balances_exception", error=str(e))
        return []

    async def get_positions(self, user_id: str, user_secret: str, account_id: str) -> list[dict]:
        """Return investment positions for a specific account."""
        auth = _sign()
        params = {**auth["base_params"], "userId": user_id, "userSecret": user_secret}
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(
                    f"{SNAPTRADE_BASE}/accounts/{account_id}/positions",
                    params=params,
                    headers=auth["headers"],
                )
                if resp.status_code == 200:
                    return resp.json() or []
                logger.error("snaptrade_positions_error", status=resp.status_code, account=account_id)
        except Exception as e:
            logger.error("snaptrade_positions_exception", error=str(e))
        return []

    async def get_activities(
        self, user_id: str, user_secret: str, account_id: Optional[str] = None, limit: int = 20
    ) -> list[dict]:
        """Return recent transactions. Optionally filtered to one account."""
        auth = _sign()
        params = {**auth["base_params"], "userId": user_id, "userSecret": user_secret}
        if account_id:
            params["accounts"] = account_id
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(
                    f"{SNAPTRADE_BASE}/activities",
                    params=params,
                    headers=auth["headers"],
                )
                if resp.status_code == 200:
                    data = resp.json() or []
                    return data[:limit]
                logger.error("snaptrade_activities_error", status=resp.status_code)
        except Exception as e:
            logger.error("snaptrade_activities_exception", error=str(e))
        return []

    async def get_holdings(self, user_id: str, user_secret: str) -> dict:
        """Return all holdings across all accounts (accounts + positions + balances)."""
        auth = _sign()
        params = {**auth["base_params"], "userId": user_id, "userSecret": user_secret}
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(
                    f"{SNAPTRADE_BASE}/holdings",
                    params=params,
                    headers=auth["headers"],
                )
                if resp.status_code == 200:
                    return resp.json() or {}
        except Exception as e:
            logger.error("snaptrade_holdings_exception", error=str(e))
        return {}

    async def delete_user(self, user_id: str, user_secret: str) -> bool:
        """Remove a SnapTrade user registration."""
        auth = _sign()
        params = {**auth["base_params"], "userId": user_id, "userSecret": user_secret}
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.delete(
                    f"{SNAPTRADE_BASE}/snapTrade/deleteUser",
                    params=params,
                    headers=auth["headers"],
                )
                return resp.status_code in (200, 204)
        except Exception as e:
            logger.error("snaptrade_delete_exception", error=str(e))
        return False


snaptrade = SnapTradeClient()
