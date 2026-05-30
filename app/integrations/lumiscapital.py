"""
Lumiscapital — FMP-powered intelligence layer.

STARFIRE calls this to pull:
  - Real-time & historical prices
  - Macro economic indicators
  - Earnings calendar & surprises
  - Company financials & profiles
  - Political / market news
  - Stock screener (scout reports)
  - Sector performance

STARFIRE asks → Lumiscapital fetches → STARFIRE formats → User receives.
"""

import httpx
import structlog
from datetime import datetime, date, timedelta
from typing import Optional
from app.config import settings

logger = structlog.get_logger(__name__)

FMP_BASE = "https://financialmodelingprep.com/api"


class LumiscapitalClient:
    """
    Wraps the Financial Modeling Prep API.
    All methods return clean dicts ready for STARFIRE to format.
    """

    def __init__(self):
        self.api_key = settings.fmp_api_key
        self.timeout = 15

    def _params(self, **kwargs) -> dict:
        return {"apikey": self.api_key, **kwargs}

    async def _get(self, path: str, **params) -> dict | list | None:
        url = f"{FMP_BASE}{path}"
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(url, params=self._params(**params))
                resp.raise_for_status()
                data = resp.json()
                if isinstance(data, dict) and data.get("Error Message"):
                    logger.error("fmp_api_error", message=data["Error Message"])
                    return None
                return data
        except Exception as e:
            logger.error("lumiscapital_fetch_error", path=path, error=str(e))
            return None

    # ------------------------------------------------------------------ #
    # PRICES
    # ------------------------------------------------------------------ #

    async def get_quote(self, symbol: str) -> Optional[dict]:
        """Real-time quote for a single symbol."""
        data = await self._get(f"/v3/quote/{symbol.upper()}")
        if data and isinstance(data, list):
            return data[0]
        return None

    async def get_quotes(self, symbols: list[str]) -> list[dict]:
        """Batch quotes for multiple symbols."""
        joined = ",".join(s.upper() for s in symbols)
        data = await self._get(f"/v3/quote/{joined}")
        return data or []

    async def get_historical_prices(
        self, symbol: str, days: int = 30
    ) -> list[dict]:
        """Daily historical OHLCV for a symbol."""
        from_date = (date.today() - timedelta(days=days)).isoformat()
        data = await self._get(
            f"/v3/historical-price-full/{symbol.upper()}",
            from_=from_date,
        )
        if data and "historical" in data:
            return data["historical"][:days]
        return []

    # ------------------------------------------------------------------ #
    # MACRO DATA
    # ------------------------------------------------------------------ #

    async def get_economic_indicators(self) -> list[dict]:
        """Key macro indicators: GDP, CPI, unemployment, etc."""
        indicators = []
        for name in [
            "GDP", "realGDP", "nominalPotentialGDP", "realGDPPerCapita",
            "federalFunds", "CPI", "inflationRate", "inflation",
            "retailSales", "consumerSentiment", "durableGoods",
            "unemploymentRate", "totalNonfarmPayroll",
        ]:
            data = await self._get(f"/v4/economic?name={name}&limit=1")
            if data and isinstance(data, list) and data:
                indicators.append({"indicator": name, **data[0]})
        return indicators

    async def get_treasury_rates(self) -> Optional[dict]:
        """Current US Treasury rates."""
        data = await self._get("/v4/treasury?limit=1")
        if data and isinstance(data, list):
            return data[0]
        return None

    async def get_market_risk_premium(self) -> list[dict]:
        """Market risk premium by country."""
        return await self._get("/v4/market_risk_premium") or []

    async def get_sector_performance(self) -> list[dict]:
        """Current sector P&L performance."""
        return await self._get("/v3/sectors-performance") or []

    # ------------------------------------------------------------------ #
    # EARNINGS
    # ------------------------------------------------------------------ #

    async def get_earnings_calendar(self, days_ahead: int = 7) -> list[dict]:
        """Upcoming earnings for the next N days."""
        from_date = date.today().isoformat()
        to_date = (date.today() + timedelta(days=days_ahead)).isoformat()
        data = await self._get(
            "/v3/earning_calendar",
            from_=from_date,
            to=to_date,
        )
        return data or []

    async def get_earnings_surprises(self, symbol: str) -> list[dict]:
        """Historical earnings vs. estimate for a symbol."""
        data = await self._get(f"/v3/earnings-surprises/{symbol.upper()}")
        return (data or [])[:8]

    async def get_income_statement(self, symbol: str) -> Optional[dict]:
        """Most recent annual income statement."""
        data = await self._get(
            f"/v3/income-statement/{symbol.upper()}",
            limit=1,
        )
        if data and isinstance(data, list):
            return data[0]
        return None

    # ------------------------------------------------------------------ #
    # COMPANY PROFILES
    # ------------------------------------------------------------------ #

    async def get_company_profile(self, symbol: str) -> Optional[dict]:
        """Full company profile: description, sector, market cap, CEO, etc."""
        data = await self._get(f"/v3/profile/{symbol.upper()}")
        if data and isinstance(data, list):
            return data[0]
        return None

    async def get_key_metrics(self, symbol: str) -> Optional[dict]:
        """Key financial metrics: P/E, EV/EBITDA, ROE, etc."""
        data = await self._get(
            f"/v3/key-metrics/{symbol.upper()}",
            limit=1,
        )
        if data and isinstance(data, list):
            return data[0]
        return None

    async def get_analyst_estimates(self, symbol: str) -> list[dict]:
        """Analyst EPS and revenue estimates."""
        data = await self._get(
            f"/v3/analyst-estimates/{symbol.upper()}",
            limit=4,
        )
        return data or []

    async def get_price_target(self, symbol: str) -> list[dict]:
        """Analyst price targets."""
        data = await self._get(
            f"/v4/price-target?symbol={symbol.upper()}&limit=5"
        )
        return data or []

    async def get_upgrades_downgrades(self, symbol: str) -> list[dict]:
        """Recent analyst upgrades and downgrades."""
        data = await self._get(
            f"/v4/upgrades-downgrades?symbol={symbol.upper()}&limit=10"
        )
        return data or []

    # ------------------------------------------------------------------ #
    # NEWS & POLITICAL
    # ------------------------------------------------------------------ #

    async def get_general_news(self, limit: int = 10) -> list[dict]:
        """Latest general financial/market news."""
        data = await self._get("/v4/general_news", page=0)
        return (data or [])[:limit]

    async def get_stock_news(self, symbol: str, limit: int = 10) -> list[dict]:
        """News specifically about a stock."""
        data = await self._get(
            "/v3/stock_news",
            tickers=symbol.upper(),
            limit=limit,
        )
        return data or []

    async def get_political_news(self, limit: int = 10) -> list[dict]:
        """Senate/House trading disclosures and political news."""
        data = await self._get("/v4/senate-trading", page=0)
        return (data or [])[:limit]

    async def get_senate_trades(self, symbol: Optional[str] = None) -> list[dict]:
        """Senate stock trading disclosures."""
        path = "/v4/senate-trading"
        if symbol:
            path += f"?symbol={symbol.upper()}"
        else:
            path += "?page=0"
        data = await self._get(path)
        return (data or [])[:20]

    # ------------------------------------------------------------------ #
    # STOCK SCREENER (SCOUT)
    # ------------------------------------------------------------------ #

    async def scout_stocks(
        self,
        market_cap_min: Optional[float] = None,
        market_cap_max: Optional[float] = None,
        price_min: Optional[float] = None,
        price_max: Optional[float] = None,
        beta_max: Optional[float] = None,
        volume_min: Optional[float] = None,
        sector: Optional[str] = None,
        exchange: str = "NASDAQ,NYSE",
        limit: int = 20,
    ) -> list[dict]:
        """Screen stocks by fundamental and technical criteria."""
        params: dict = {"exchange": exchange, "limit": limit}
        if market_cap_min:
            params["marketCapMoreThan"] = int(market_cap_min)
        if market_cap_max:
            params["marketCapLowerThan"] = int(market_cap_max)
        if price_min:
            params["priceMoreThan"] = price_min
        if price_max:
            params["priceLowerThan"] = price_max
        if beta_max:
            params["betaLowerThan"] = beta_max
        if volume_min:
            params["volumeMoreThan"] = int(volume_min)
        if sector:
            params["sector"] = sector

        data = await self._get("/v3/stock-screener", **params)
        return data or []

    async def get_gainers(self) -> list[dict]:
        """Top gaining stocks today."""
        return await self._get("/v3/stock_market/gainers") or []

    async def get_losers(self) -> list[dict]:
        """Top losing stocks today."""
        return await self._get("/v3/stock_market/losers") or []

    async def get_most_active(self) -> list[dict]:
        """Most actively traded stocks today."""
        return await self._get("/v3/stock_market/actives") or []

    # ------------------------------------------------------------------ #
    # INSIDER TRADING
    # ------------------------------------------------------------------ #

    async def get_insider_trades(self, symbol: str) -> list[dict]:
        """Recent insider buy/sell transactions."""
        data = await self._get(
            f"/v4/insider-trading?symbol={symbol.upper()}&limit=10"
        )
        return data or []

    # ------------------------------------------------------------------ #
    # CRYPTO
    # ------------------------------------------------------------------ #

    async def get_crypto_quote(self, symbol: str) -> Optional[dict]:
        """Real-time crypto price (e.g. BTCUSD)."""
        sym = symbol.upper().replace("/", "").replace("-", "")
        if not sym.endswith("USD"):
            sym = sym + "USD"
        data = await self._get(f"/v3/quote/{sym}")
        if data and isinstance(data, list):
            return data[0]
        return None


class ReportFormatter:
    """
    Converts raw Lumiscapital data into readable Telegram messages.
    STARFIRE uses these to present data to the user.
    """

    @staticmethod
    def format_quote(q: dict) -> str:
        change = q.get("change", 0) or 0
        pct = q.get("changesPercentage", 0) or 0
        sign = "+" if change >= 0 else ""
        return (
            f"*{q.get('symbol')}* — {q.get('name', '')}\n"
            f"Price: `${q.get('price', 0):,.2f}`\n"
            f"Change: `{sign}{change:.2f} ({sign}{pct:.2f}%)`\n"
            f"Open: `${q.get('open', 0):,.2f}` | High: `${q.get('dayHigh', 0):,.2f}` | Low: `${q.get('dayLow', 0):,.2f}`\n"
            f"52W High: `${q.get('yearHigh', 0):,.2f}` | 52W Low: `${q.get('yearLow', 0):,.2f}`\n"
            f"Volume: `{q.get('volume', 0):,}` | Mkt Cap: `${q.get('marketCap', 0)/1e9:.2f}B`\n"
            f"P/E: `{q.get('pe', 'N/A')}` | EPS: `{q.get('eps', 'N/A')}`"
        )

    @staticmethod
    def format_macro_summary(indicators: list[dict], treasury: Optional[dict]) -> str:
        lines = ["*Macro Economic Dashboard*\n"]
        display_map = {
            "federalFunds": "Fed Funds Rate",
            "CPI": "CPI",
            "inflationRate": "Inflation Rate",
            "unemploymentRate": "Unemployment",
            "realGDP": "Real GDP",
            "retailSales": "Retail Sales",
            "consumerSentiment": "Consumer Sentiment",
        }
        for ind in indicators:
            name = ind.get("indicator", "")
            if name in display_map:
                val = ind.get("value", "N/A")
                dt = ind.get("date", "")[:7]
                lines.append(f"{display_map[name]}: `{val}` ({dt})")

        if treasury:
            lines.append("\n*US Treasury Yields*")
            for tenor in ["month1", "month3", "month6", "year1", "year2", "year5", "year10", "year30"]:
                v = treasury.get(tenor)
                if v:
                    label = tenor.replace("month", "").replace("year", "") + ("M" if "month" in tenor else "Y")
                    lines.append(f"  {label}: `{v:.2f}%`")

        return "\n".join(lines)

    @staticmethod
    def format_earnings_calendar(events: list[dict]) -> str:
        if not events:
            return "No earnings events in the next 7 days."
        lines = ["*Upcoming Earnings*\n"]
        for e in events[:15]:
            est = e.get("epsEstimated", "N/A")
            lines.append(
                f"`{e.get('date', '')}` *{e.get('symbol', '')}* — Est. EPS: {est}"
                + (" (BMO)" if e.get("time") == "bmo" else " (AMC)" if e.get("time") == "amc" else "")
            )
        return "\n".join(lines)

    @staticmethod
    def format_sector_performance(sectors: list[dict]) -> str:
        lines = ["*Sector Performance*\n"]
        for s in sectors:
            chg = float(s.get("changesPercentage", "0").replace("%", "") or 0)
            sign = "+" if chg >= 0 else ""
            bar = "🟢" if chg >= 0 else "🔴"
            lines.append(f"{bar} {s.get('sector', '')}: `{sign}{chg:.2f}%`")
        return "\n".join(lines)

    @staticmethod
    def format_scout_report(stocks: list[dict], title: str = "Scout Report") -> str:
        if not stocks:
            return "No stocks matched the criteria."
        lines = [f"*{title}*\n"]
        for s in stocks[:15]:
            chg = s.get("changesPercentage", 0) or 0
            sign = "+" if chg >= 0 else ""
            lines.append(
                f"*{s.get('symbol')}* ({s.get('sector', 'N/A')}) — "
                f"`${s.get('price', 0):,.2f}` {sign}{chg:.1f}% | "
                f"MCap: `${(s.get('marketCap') or 0)/1e9:.1f}B`"
            )
        return "\n".join(lines)

    @staticmethod
    def format_news(articles: list[dict], title: str = "Market News") -> str:
        if not articles:
            return "No news available."
        lines = [f"*{title}*\n"]
        for a in articles[:8]:
            pub = a.get("publishedDate", "")[:10]
            lines.append(f"[{pub}] [{a.get('title', '')}]({a.get('url', '')})")
        return "\n".join(lines)

    @staticmethod
    def format_company_profile(profile: dict, metrics: Optional[dict] = None) -> str:
        lines = [
            f"*{profile.get('companyName', '')} ({profile.get('symbol', '')})*\n",
            f"Sector: `{profile.get('sector', 'N/A')}` | Industry: `{profile.get('industry', 'N/A')}`",
            f"CEO: {profile.get('ceo', 'N/A')}",
            f"Exchange: `{profile.get('exchangeShortName', 'N/A')}`",
            f"Market Cap: `${(profile.get('mktCap') or 0)/1e9:.2f}B`",
            f"Employees: `{profile.get('fullTimeEmployees', 'N/A'):,}`" if profile.get("fullTimeEmployees") else "",
            f"\n{profile.get('description', '')[:300]}..." if profile.get("description") else "",
        ]
        if metrics:
            lines += [
                "\n*Key Metrics*",
                f"P/E: `{metrics.get('peRatio', 'N/A')}` | P/B: `{metrics.get('priceToBookRatio', 'N/A')}`",
                f"EV/EBITDA: `{metrics.get('enterpriseValueOverEBITDA', 'N/A')}`",
                f"ROE: `{metrics.get('roe', 'N/A')}` | ROA: `{metrics.get('returnOnAssets', 'N/A')}`",
                f"Debt/Equity: `{metrics.get('debtToEquity', 'N/A')}`",
            ]
        return "\n".join(l for l in lines if l)


lumiscapital = LumiscapitalClient()
formatter = ReportFormatter()
