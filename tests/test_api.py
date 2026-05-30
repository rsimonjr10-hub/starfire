import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import patch, AsyncMock


@pytest.mark.asyncio
async def test_root_endpoint():
    with patch("app.main.init_db", new_callable=AsyncMock), \
         patch("app.main._register_telegram_webhook", new_callable=AsyncMock), \
         patch("app.main.market_worker.start", new_callable=AsyncMock), \
         patch("app.main.event_worker.start", new_callable=AsyncMock):
        from app.main import app
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/")
            assert resp.status_code == 200
            data = resp.json()
            assert data["system"] == "STARFIRE AI OS"
            assert data["status"] == "online"


@pytest.mark.asyncio
async def test_health_endpoint():
    with patch("app.main.init_db", new_callable=AsyncMock), \
         patch("app.main._register_telegram_webhook", new_callable=AsyncMock), \
         patch("app.main.market_worker.start", new_callable=AsyncMock), \
         patch("app.main.event_worker.start", new_callable=AsyncMock):
        from app.main import app
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/health")
            assert resp.status_code == 200
            assert resp.json()["status"] == "healthy"
