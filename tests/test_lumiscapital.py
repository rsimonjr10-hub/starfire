import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from app.integrations.lumiscapital import LumiscapitalClient, ReportFormatter


@pytest.fixture
def client():
    return LumiscapitalClient()


@pytest.fixture
def fmt():
    return ReportFormatter()


# ------------------------------------------------------------------ #
# Formatter tests (no network)
# ------------------------------------------------------------------ #

def test_format_quote_positive(fmt):
    q = {
        "symbol": "AAPL",
        "name": "Apple Inc.",
        "price": 185.50,
        "change": 2.30,
        "changesPercentage": 1.25,
        "open": 183.0,
        "dayHigh": 186.0,
        "dayLow": 182.5,
        "yearHigh": 198.0,
        "yearLow": 164.0,
        "volume": 55_000_000,
        "marketCap": 2_900_000_000_000,
        "pe": 28.5,
        "eps": 6.51,
    }
    result = fmt.format_quote(q)
    assert "AAPL" in result
    assert "185.50" in result
    assert "+2.30" in result


def test_format_quote_negative(fmt):
    q = {
        "symbol": "TSLA",
        "name": "Tesla",
        "price": 240.0,
        "change": -5.0,
        "changesPercentage": -2.04,
        "open": 245.0,
        "dayHigh": 246.0,
        "dayLow": 238.0,
        "yearHigh": 300.0,
        "yearLow": 138.0,
        "volume": 80_000_000,
        "marketCap": 760_000_000_000,
        "pe": 60.0,
        "eps": 4.0,
    }
    result = fmt.format_quote(q)
    assert "-5.00" in result


def test_format_earnings_calendar_empty(fmt):
    result = fmt.format_earnings_calendar([])
    assert "No earnings" in result


def test_format_earnings_calendar(fmt):
    events = [
        {"date": "2024-07-25", "symbol": "AAPL", "epsEstimated": 1.35, "time": "amc"},
        {"date": "2024-07-26", "symbol": "MSFT", "epsEstimated": 2.90, "time": "bmo"},
    ]
    result = fmt.format_earnings_calendar(events)
    assert "AAPL" in result
    assert "MSFT" in result
    assert "AMC" in result or "amc" in result or "(AMC)" in result


def test_format_sector_performance(fmt):
    sectors = [
        {"sector": "Technology", "changesPercentage": "1.25%"},
        {"sector": "Energy", "changesPercentage": "-0.80%"},
    ]
    result = fmt.format_sector_performance(sectors)
    assert "Technology" in result
    assert "Energy" in result


def test_format_scout_report_empty(fmt):
    result = fmt.format_scout_report([], "Test")
    assert "No stocks" in result


def test_format_scout_report(fmt):
    stocks = [
        {"symbol": "NVDA", "sector": "Technology", "price": 875.0,
         "changesPercentage": 3.5, "marketCap": 2_150_000_000_000},
    ]
    result = fmt.format_scout_report(stocks, "Scout")
    assert "NVDA" in result
    assert "875" in result


def test_format_news_empty(fmt):
    result = fmt.format_news([], "News")
    assert "No news" in result


def test_format_news(fmt):
    articles = [
        {"title": "Fed raises rates", "publishedDate": "2024-07-15T10:00:00", "url": "https://example.com/1"},
        {"title": "NVDA beats earnings", "publishedDate": "2024-07-15T09:00:00", "url": "https://example.com/2"},
    ]
    result = fmt.format_news(articles)
    assert "Fed raises rates" in result


def test_format_macro_summary(fmt):
    indicators = [
        {"indicator": "federalFunds", "value": 5.25, "date": "2024-07-01"},
        {"indicator": "inflationRate", "value": 3.2, "date": "2024-07-01"},
        {"indicator": "unemploymentRate", "value": 4.1, "date": "2024-07-01"},
    ]
    treasury = {
        "year2": 4.85,
        "year10": 4.25,
        "year30": 4.40,
    }
    result = fmt.format_macro_summary(indicators, treasury)
    assert "Fed Funds Rate" in result
    assert "5.25" in result
    assert "Treasury" in result


# ------------------------------------------------------------------ #
# Client tests (mocked HTTP)
# ------------------------------------------------------------------ #

@pytest.mark.asyncio
async def test_get_quote_success(client):
    mock_data = [{"symbol": "AAPL", "price": 185.5, "change": 1.2, "changesPercentage": 0.65}]
    with patch.object(client, "_get", new=AsyncMock(return_value=mock_data)):
        result = await client.get_quote("AAPL")
    assert result["symbol"] == "AAPL"
    assert result["price"] == 185.5


@pytest.mark.asyncio
async def test_get_quote_api_error(client):
    with patch.object(client, "_get", new=AsyncMock(return_value=None)):
        result = await client.get_quote("INVALID")
    assert result is None


@pytest.mark.asyncio
async def test_get_sector_performance(client):
    mock_data = [
        {"sector": "Technology", "changesPercentage": "2.1%"},
        {"sector": "Energy", "changesPercentage": "-0.5%"},
    ]
    with patch.object(client, "_get", new=AsyncMock(return_value=mock_data)):
        result = await client.get_sector_performance()
    assert len(result) == 2


@pytest.mark.asyncio
async def test_get_gainers(client):
    mock_data = [{"symbol": "XYZ", "price": 50.0, "changesPercentage": 15.0}]
    with patch.object(client, "_get", new=AsyncMock(return_value=mock_data)):
        result = await client.get_gainers()
    assert result[0]["symbol"] == "XYZ"


@pytest.mark.asyncio
async def test_scout_stocks(client):
    mock_data = [{"symbol": "NVDA", "sector": "Technology", "price": 875.0}]
    with patch.object(client, "_get", new=AsyncMock(return_value=mock_data)):
        result = await client.scout_stocks(market_cap_min=1e9, limit=10)
    assert len(result) == 1


@pytest.mark.asyncio
async def test_get_earnings_calendar(client):
    mock_data = [
        {"date": "2024-07-25", "symbol": "AAPL", "epsEstimated": 1.35},
    ]
    with patch.object(client, "_get", new=AsyncMock(return_value=mock_data)):
        result = await client.get_earnings_calendar(7)
    assert result[0]["symbol"] == "AAPL"
