from trading_signal_bot.config import Settings
from trading_signal_bot.models import Setup, Signal
from trading_signal_bot.risk import calculate_position, check_daily_guard


def _settings(**overrides) -> Settings:
    base = dict(
        bot_token="x",
        db_path="unused",
        webhook_secret="secret",
        account_balance=100_000,
        risk_per_trade_pct=1.0,
        default_sl_pct=0.5,
        default_risk_reward=2.0,
        lot_step=0.01,
        min_lot=0.01,
    )
    base.update(overrides)
    return Settings(**base)


def _setup(**signal_kwargs) -> Setup:
    defaults = dict(
        indicator="rsi",
        symbol="EURUSD",
        timeframe="1h",
        direction="buy",
        price=1.1000,
    )
    defaults.update(signal_kwargs)
    signal = Signal(**defaults)
    return Setup(symbol=signal.symbol, timeframe=signal.timeframe, direction=signal.direction, signals=[signal])


def test_position_size_uses_explicit_stop_loss():
    settings = _settings()
    setup = _setup(stop_loss=1.0950, take_profit=1.1100)

    result = calculate_position(setup, settings)

    # risk_amount target = 100000 * 1% = 1000; sl_distance = 0.0050; contract_size=100000
    # lots_raw = 1000 / (0.0050 * 100000) = 2.0
    assert result.lots == 2.0
    assert result.stop_loss == 1.0950
    assert result.take_profit == 1.1100
    assert round(result.risk_amount, 2) == 1000.0
    assert not result.warnings


def test_position_size_falls_back_when_stop_missing():
    settings = _settings()
    setup = _setup()  # без stop_loss/take_profit

    result = calculate_position(setup, settings)

    assert result.stop_loss < setup.entry_price  # buy -> стоп ниже входа
    assert result.take_profit > setup.entry_price
    assert result.lots > 0
    assert any("Стоп не пришёл" in w for w in result.warnings)
    assert any("Тейк не пришёл" in w for w in result.warnings)


def test_position_size_respects_min_lot():
    settings = _settings(risk_per_trade_pct=0.001, min_lot=0.01)
    setup = _setup(stop_loss=1.0950, take_profit=1.1100)

    result = calculate_position(setup, settings)

    assert result.lots == settings.min_lot
    assert any("меньше минимального" in w for w in result.warnings)


def test_zero_stop_distance_raises():
    settings = _settings()
    setup = _setup(stop_loss=1.1000)  # равен цене входа

    try:
        calculate_position(setup, settings)
        assert False, "должно было выброситься исключение"
    except ValueError:
        pass


def test_daily_guard_blocks_on_trade_count():
    settings = _settings(max_daily_trades=2)
    decision = check_daily_guard(
        settings,
        trades_today=2,
        risk_budget_used_today=0,
        realized_loss_today=0,
        new_trade_risk=100,
    )
    assert not decision.allowed
    assert "лимит сделок" in decision.reason


def test_daily_guard_blocks_on_realized_loss():
    settings = _settings(max_daily_loss_pct=2.0, account_balance=100_000)
    decision = check_daily_guard(
        settings,
        trades_today=1,
        risk_budget_used_today=500,
        realized_loss_today=2000,  # >= 2% of 100000
        new_trade_risk=100,
    )
    assert not decision.allowed
    assert "убытка исчерпан" in decision.reason


def test_daily_guard_blocks_on_risk_budget():
    settings = _settings(max_daily_loss_pct=1.0, account_balance=100_000)
    decision = check_daily_guard(
        settings,
        trades_today=1,
        risk_budget_used_today=900,
        realized_loss_today=0,
        new_trade_risk=200,  # 900 + 200 > 1000
    )
    assert not decision.allowed
    assert "риск-бюджет" in decision.reason


def test_daily_guard_allows_within_limits():
    settings = _settings(max_daily_loss_pct=4.0, account_balance=100_000, max_daily_trades=5)
    decision = check_daily_guard(
        settings,
        trades_today=1,
        risk_budget_used_today=500,
        realized_loss_today=0,
        new_trade_risk=200,
    )
    assert decision.allowed
