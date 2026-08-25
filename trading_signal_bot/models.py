"""Модели сигналов и готовых сетапов."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

DIRECTIONS = ("buy", "sell")


def normalize_direction(raw: str) -> str:
    value = (raw or "").strip().lower()
    if value in ("buy", "long", "bull", "bullish", "покупка", "лонг"):
        return "buy"
    if value in ("sell", "short", "bear", "bearish", "продажа", "шорт"):
        return "sell"
    raise ValueError(f"Неизвестное направление сигнала: {raw!r}")


def normalize_symbol(raw: str) -> str:
    return (raw or "").strip().upper().replace(" ", "")


@dataclass(slots=True)
class Signal:
    """Один сигнал от одного индикатора TradingView."""

    indicator: str
    symbol: str
    timeframe: str
    direction: str
    price: float
    received_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    stop_loss: float | None = None
    take_profit: float | None = None
    note: str = ""

    def __post_init__(self) -> None:
        self.symbol = normalize_symbol(self.symbol)
        self.direction = normalize_direction(self.direction)
        self.indicator = (self.indicator or "unknown").strip()
        self.timeframe = (self.timeframe or "?").strip()

    @property
    def group_key(self) -> tuple[str, str, str]:
        return (self.symbol, self.timeframe, self.direction)


@dataclass(slots=True)
class Setup:
    """Подтверждённый несколькими индикаторами сетап, готовый к расчёту риска."""

    symbol: str
    timeframe: str
    direction: str
    signals: list[Signal]

    @property
    def indicators(self) -> list[str]:
        seen: list[str] = []
        for signal in self.signals:
            if signal.indicator not in seen:
                seen.append(signal.indicator)
        return seen

    @property
    def entry_price(self) -> float:
        return self.signals[-1].price

    @property
    def stop_loss(self) -> float | None:
        values = [s.stop_loss for s in self.signals if s.stop_loss is not None]
        return sum(values) / len(values) if values else None

    @property
    def take_profit(self) -> float | None:
        values = [s.take_profit for s in self.signals if s.take_profit is not None]
        return sum(values) / len(values) if values else None
