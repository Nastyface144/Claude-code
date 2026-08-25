import pytest
from aiohttp.test_utils import TestClient, TestServer

from trading_signal_bot.config import Settings
from trading_signal_bot.service import TradingEngine
from trading_signal_bot.storage import Storage
from trading_signal_bot.webhook import build_app, signal_from_payload


def test_signal_from_payload_accepts_tradingview_style_fields():
    payload = {
        "indicator": "RSI_Divergence",
        "ticker": "EURUSD",
        "interval": "60",
        "action": "buy",
        "close": 1.10123,
        "sl": 1.0950,
        "tp": 1.1100,
        "comment": "bullish divergence",
    }
    signal = signal_from_payload(payload)
    assert signal.symbol == "EURUSD"
    assert signal.timeframe == "60"
    assert signal.direction == "buy"
    assert signal.price == 1.10123
    assert signal.stop_loss == 1.0950


def test_signal_from_payload_rejects_missing_fields():
    with pytest.raises(ValueError):
        signal_from_payload({"symbol": "EURUSD"})


@pytest.mark.asyncio
async def test_webhook_rejects_wrong_secret():
    settings = Settings(bot_token="x", db_path=":memory:", webhook_secret="right-secret", ai_enabled=False)
    storage = await Storage(":memory:").connect()
    engine = TradingEngine(settings, storage, bot=None)
    app = build_app(engine, settings.webhook_secret)

    async with TestClient(TestServer(app)) as client:
        resp = await client.post("/webhook/wrong-secret", json={})
        assert resp.status == 403
    await storage.close()


@pytest.mark.asyncio
async def test_webhook_accepts_valid_signal():
    settings = Settings(
        bot_token="x",
        db_path=":memory:",
        webhook_secret="right-secret",
        ai_enabled=False,
        total_indicators=3,
        min_confirmations=2,
    )
    storage = await Storage(":memory:").connect()
    engine = TradingEngine(settings, storage, bot=None)
    app = build_app(engine, settings.webhook_secret)

    payload = {
        "indicator": "rsi",
        "symbol": "EURUSD",
        "timeframe": "1h",
        "direction": "buy",
        "price": 1.1,
        "stop_loss": 1.095,
    }
    async with TestClient(TestServer(app)) as client:
        resp = await client.post("/webhook/right-secret", json=payload)
        assert resp.status == 200
        body = await resp.json()
        assert body["status"] == "waiting"
    await storage.close()
