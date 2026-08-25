from trading_signal_bot.ai_review import AIOutcome, AIVerdict
from trading_signal_bot.config import Settings
from trading_signal_bot.formatting import ai_rejected_message, guard_blocked_message, order_message
from trading_signal_bot.models import Setup, Signal
from trading_signal_bot.risk import calculate_position


def _setup() -> Setup:
    signals = [
        Signal(indicator="rsi", symbol="EURUSD", timeframe="1h", direction="buy", price=1.1, stop_loss=1.095, take_profit=1.11),
        Signal(indicator="macd", symbol="EURUSD", timeframe="1h", direction="buy", price=1.1005),
    ]
    return Setup(symbol="EURUSD", timeframe="1h", direction="buy", signals=signals)


def test_order_message_contains_key_fields():
    settings = Settings(bot_token="x", db_path=":memory:", webhook_secret="s", total_indicators=7)
    setup = _setup()
    risk = calculate_position(setup, settings)
    ai = AIOutcome(ran=False, verdict=None, error="ИИ выключена")

    text = order_message(setup, risk, ai, settings, trade_id=1)

    assert "EURUSD" in text
    assert "LONG" in text
    assert "rsi" in text and "macd" in text
    assert "Объём" in text
    assert "ИИ-проверка недоступна" in text


def test_order_message_shows_ai_verdict():
    settings = Settings(bot_token="x", db_path=":memory:", webhook_secret="s")
    setup = _setup()
    risk = calculate_position(setup, settings)
    verdict = AIVerdict(approve=True, confidence=82, reasoning="Согласованный сетап", warnings=[])
    ai = AIOutcome(ran=True, verdict=verdict)

    text = order_message(setup, risk, ai, settings, trade_id=2)

    assert "82%" in text
    assert "Согласованный сетап" in text


def test_guard_blocked_message_mentions_reason():
    setup = _setup()
    text = guard_blocked_message(setup, "дневной лимит сделок исчерпан (5)")
    assert "EURUSD" in text
    assert "исчерпан" in text


def test_ai_rejected_message_mentions_confidence():
    setup = _setup()
    verdict = AIVerdict(approve=False, confidence=20, reasoning="Индикаторы противоречат друг другу", warnings=[])
    ai = AIOutcome(ran=True, verdict=verdict)
    text = ai_rejected_message(setup, ai)
    assert "20%" in text
    assert "противоречат" in text
