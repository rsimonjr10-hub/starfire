import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.risk.engine import RiskEngine
from app.config import settings


@pytest.fixture
def mock_db():
    db = AsyncMock()
    return db


@pytest.fixture
def risk_engine(mock_db):
    return RiskEngine(mock_db)


def test_position_size_too_large(risk_engine):
    result = risk_engine._check_position_size(30.0)
    assert not result["passed"]
    assert "MAX_POSITION_SIZE" in result["rule"]


def test_position_size_zero(risk_engine):
    result = risk_engine._check_position_size(0.0)
    assert not result["passed"]


def test_position_size_valid(risk_engine):
    result = risk_engine._check_position_size(10.0)
    assert result["passed"]


def test_position_size_at_limit(risk_engine):
    result = risk_engine._check_position_size(25.0)
    assert result["passed"]


def test_position_size_over_limit(risk_engine):
    result = risk_engine._check_position_size(25.1)
    assert not result["passed"]


@pytest.mark.asyncio
async def test_validate_trade_blocked_by_position_size(risk_engine):
    result = await risk_engine.validate_trade(1, "AAPL", "BUY", 50.0)
    assert not result["allowed"]
    assert "25" in result["reason"]


@pytest.mark.asyncio
async def test_validate_trade_blocked_by_daily_trades(mock_db):
    from sqlalchemy import select
    from datetime import datetime, timezone

    mock_result = MagicMock()
    mock_result.scalar.return_value = 10  # at max limit
    mock_db.execute = AsyncMock(return_value=mock_result)

    engine = RiskEngine(mock_db)
    engine.max_position_size_pct = 25.0

    # Portfolio mock for daily loss check
    portfolio_result = MagicMock()
    portfolio_result.scalar_one_or_none.return_value = None
    mock_db.execute = AsyncMock(side_effect=[mock_result, portfolio_result])

    result = await engine.validate_trade(1, "AAPL", "BUY", 10.0)
    assert not result["allowed"]
    assert "limit" in result["reason"].lower()


def test_get_limits_summary(risk_engine):
    summary = risk_engine.get_limits_summary()
    assert "max_daily_loss_pct" in summary
    assert "max_position_size_pct" in summary
    assert "max_trades_per_day" in summary
