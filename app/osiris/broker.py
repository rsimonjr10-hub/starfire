import random
import httpx
import structlog
from datetime import datetime, timezone
from app.config import settings

logger = structlog.get_logger(__name__)


class BrokerResult:
    def __init__(self, order_id: str, filled_price: float, quantity: float, slippage: float):
        self.order_id = order_id
        self.filled_price = filled_price
        self.quantity = quantity
        self.slippage = slippage
        self.status = "FILLED"
        self.executed_at = datetime.now(timezone.utc)


class MockBroker:
    """
    Mock broker for development / paper trading.
    Simulates realistic fills with minor slippage.
    OSIRIS calls this; it never makes decisions.
    """

    async def get_quote(self, symbol: str) -> float:
        mock_prices = {
            "AAPL": 185.50,
            "TSLA": 245.30,
            "MSFT": 415.20,
            "GOOGL": 175.80,
            "AMZN": 195.40,
            "NVDA": 875.00,
            "BTC/USD": 68000.00,
            "ETH/USD": 3800.00,
            "SPY": 520.00,
            "QQQ": 445.00,
        }
        base = mock_prices.get(symbol.upper(), 100.0)
        noise = base * random.uniform(-0.002, 0.002)
        return round(base + noise, 4)

    async def submit_order(
        self,
        symbol: str,
        side: str,
        quantity: float,
        order_type: str = "market",
    ) -> BrokerResult:
        quote = await self.get_quote(symbol)
        # Simulate market slippage: 0.01% – 0.05%
        slippage_factor = random.uniform(0.0001, 0.0005)
        if side == "BUY":
            filled_price = quote * (1 + slippage_factor)
        else:
            filled_price = quote * (1 - slippage_factor)

        order_id = f"MOCK-{symbol}-{int(datetime.now(timezone.utc).timestamp())}"
        logger.info(
            "mock_broker_fill",
            symbol=symbol,
            side=side,
            quantity=quantity,
            filled_price=filled_price,
            slippage=slippage_factor,
        )
        return BrokerResult(
            order_id=order_id,
            filled_price=round(filled_price, 4),
            quantity=quantity,
            slippage=round(slippage_factor, 6),
        )


class AlpacaBroker:
    """
    Real Alpaca broker integration (paper or live).
    Uses Alpaca Trade API v2.
    """

    def __init__(self):
        self.base_url = settings.broker_base_url
        self.headers = {
            "APCA-API-KEY-ID": settings.broker_api_key,
            "APCA-API-SECRET-KEY": settings.broker_api_secret,
            "Content-Type": "application/json",
        }

    async def get_quote(self, symbol: str) -> float:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self.base_url}/v2/stocks/{symbol}/quotes/latest",
                headers=self.headers,
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
            return float(data["quote"]["ap"])

    async def submit_order(
        self,
        symbol: str,
        side: str,
        quantity: float,
        order_type: str = "market",
    ) -> BrokerResult:
        payload = {
            "symbol": symbol,
            "qty": str(quantity),
            "side": side.lower(),
            "type": order_type,
            "time_in_force": "day",
        }
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.base_url}/v2/orders",
                json=payload,
                headers=self.headers,
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()

        filled_price = float(data.get("filled_avg_price") or 0)
        quote = await self.get_quote(symbol)
        slippage = abs(filled_price - quote) / quote if quote else 0

        return BrokerResult(
            order_id=data["id"],
            filled_price=filled_price,
            quantity=float(data.get("filled_qty") or quantity),
            slippage=slippage,
        )

    async def get_account(self) -> dict:
        """Account equity, buying power, and today's P&L."""
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{self.base_url}/v2/account", headers=self.headers)
            resp.raise_for_status()
            return resp.json()

    async def get_positions(self) -> list[dict]:
        """All open positions."""
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{self.base_url}/v2/positions", headers=self.headers)
            resp.raise_for_status()
            return resp.json()

    async def get_recent_orders(self, limit: int = 20) -> list[dict]:
        """Today's filled orders."""
        from datetime import date
        after = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{self.base_url}/v2/orders",
                headers=self.headers,
                params={"status": "filled", "limit": limit, "after": after, "direction": "desc"},
            )
            resp.raise_for_status()
            return resp.json()


def get_broker():
    if settings.use_mock_broker:
        return MockBroker()
    return AlpacaBroker()
