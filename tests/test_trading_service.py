import pytest

from trading_signal_bot.config import Settings
from trading_signal_bot.models import Signal
from trading_signal_bot.service import TradingEngine
from trading_signal_bot.storage import Storage


def _settings(**overrides) -> Settings:
    base = dict(
        bot_token="x",
        db_path=":memory:",
        webhook_secret="secret",
        total_indicators=3,
        min_confirmations=2,
        signal_window_seconds=900,
        dispatch_cooldown_seconds=1800,
        ai_enabled=False,
        account_balance=100_000,
        risk_per_trade_pct=1.0,
        max_daily_trades=5,
        max_daily_loss_pct=4.0,
    )
    base.update(overrides)
    return Settings(**base)


async def _engine(settings: Settings) -> TradingEngine:
    storage = await Storage(":memory:").connect()
    return TradingEngine(settings, storage, bot=None)


def _signal(**overrides) -> Signal:
    defaults = dict(
        indicator="rsi",
        symbol="EURUSD",
        timeframe="1h",
        direction="buy",
        price=1.1000,
        stop_loss=1.0950,
        take_profit=1.1100,
    )
    defaults.update(overrides)
    return Signal(**defaults)


@pytest.mark.asyncio
async def test_waits_for_min_confirmations():
    engine = await _engine(_settings())
    result = await engine.handle_signal(_signal(indicator="rsi"))
    assert result.status == "waiting"
    assert "1/2" in result.detail
    await engine.storage.close()


@pytest.mark.asyncio
async def test_sends_once_confirmations_reached():
    engine = await _engine(_settings())
    await engine.handle_signal(_signal(indicator="rsi"))
    result = await engine.handle_signal(_signal(indicator="macd"))
    assert result.status == "sent"
    assert result.trade_id is not None

    trades = await engine.storage.recent_trades()
    assert len(trades) == 1
    assert trades[0]["symbol"] == "EURUSD"
    await engine.storage.close()


@pytest.mark.asyncio
async def test_duplicate_indicator_does_not_double_count():
    engine = await _engine(_settings())
    await engine.handle_signal(_signal(indicator="rsi"))
    result = await engine.handle_signal(_signal(indicator="rsi", price=1.1005))
    assert result.status == "waiting"
    assert "1/2" in result.detail
    await engine.storage.close()


@pytest.mark.asyncio
async def test_cooldown_prevents_resend():
    engine = await _engine(_settings())
    await engine.handle_signal(_signal(indicator="rsi"))
    await engine.handle_signal(_signal(indicator="macd"))
    result = await engine.handle_signal(_signal(indicator="ema"))
    assert result.status == "cooldown"
    await engine.storage.close()


@pytest.mark.asyncio
async def test_opposite_direction_is_a_separate_group():
    engine = await _engine(_settings())
    await engine.handle_signal(_signal(indicator="rsi", direction="buy"))
    result = await engine.handle_signal(_signal(indicator="macd", direction="sell"))
    assert result.status == "waiting"
    await engine.storage.close()


@pytest.mark.asyncio
async def test_daily_trade_limit_blocks_new_setup():
    engine = await _engine(_settings(max_daily_trades=1))
    await engine.handle_signal(_signal(indicator="rsi", symbol="EURUSD"))
    first = await engine.handle_signal(_signal(indicator="macd", symbol="EURUSD"))
    assert first.status == "sent"

    await engine.handle_signal(_signal(indicator="rsi", symbol="GBPUSD"))
    second = await engine.handle_signal(_signal(indicator="macd", symbol="GBPUSD"))
    assert second.status == "guard_blocked"
    assert "лимит сделок" in second.detail
    await engine.storage.close()
