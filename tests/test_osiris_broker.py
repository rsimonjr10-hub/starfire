import pytest
from app.osiris.broker import MockBroker


@pytest.mark.asyncio
async def test_mock_broker_get_quote_known_symbol():
    broker = MockBroker()
    price = await broker.get_quote("AAPL")
    assert price > 0
    assert 180 < price < 200


@pytest.mark.asyncio
async def test_mock_broker_get_quote_unknown_symbol():
    broker = MockBroker()
    price = await broker.get_quote("UNKNOWN_XYZ")
    assert price > 0  # returns default


@pytest.mark.asyncio
async def test_mock_broker_buy_order():
    broker = MockBroker()
    result = await broker.submit_order("AAPL", "BUY", 10.0)
    assert result.status == "FILLED"
    assert result.filled_price > 0
    assert result.slippage >= 0
    assert result.order_id.startswith("MOCK-AAPL-")


@pytest.mark.asyncio
async def test_mock_broker_sell_order():
    broker = MockBroker()
    result = await broker.submit_order("TSLA", "SELL", 5.0)
    assert result.status == "FILLED"
    assert result.filled_price > 0


@pytest.mark.asyncio
async def test_mock_broker_buy_has_positive_slippage():
    broker = MockBroker()
    order = await broker.submit_order("AAPL", "BUY", 10.0)
    # Slippage is positive for a buy
    assert order.slippage > 0
    # Filled price is in a realistic range for AAPL
    assert 180 < order.filled_price < 200


@pytest.mark.asyncio
async def test_mock_broker_sell_has_negative_slippage():
    broker = MockBroker()
    order = await broker.submit_order("AAPL", "SELL", 10.0)
    # Slippage is positive (representing cost of execution)
    assert order.slippage > 0
    assert 180 < order.filled_price < 200
