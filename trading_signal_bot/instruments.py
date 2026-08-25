"""Параметры инструментов для расчёта объёма позиции.

Формула расчёта универсальна и предполагает, что валюта котировки инструмента
совпадает с валютой счёта (это верно для XXXUSD-пар, золота, индексов и
крипты на большинстве проп-счетов в USD). Для инструментов с другой валютой
котировки (например, USDJPY на не-USD счету) задайте `pip_value_override` —
стоимость одного пункта цены за один лот в валюте счёта.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class InstrumentSpec:
    """contract_size — количество базового актива в одном лоте/контракте."""

    contract_size: float = 100_000.0
    pip_value_override: float | None = None


DEFAULT_INSTRUMENTS: dict[str, InstrumentSpec] = {
    # Форекс-мажоры и кросс-пары, котируемые в USD (1 лот = 100 000 единиц базовой валюты)
    "EURUSD": InstrumentSpec(contract_size=100_000),
    "GBPUSD": InstrumentSpec(contract_size=100_000),
    "AUDUSD": InstrumentSpec(contract_size=100_000),
    "NZDUSD": InstrumentSpec(contract_size=100_000),
    "USDCAD": InstrumentSpec(contract_size=100_000),
    "USDCHF": InstrumentSpec(contract_size=100_000),
    # Металлы
    "XAUUSD": InstrumentSpec(contract_size=100),
    "XAGUSD": InstrumentSpec(contract_size=5_000),
    # Индексы (CFD, 1 лот = 1 контракт)
    "US30": InstrumentSpec(contract_size=1),
    "US100": InstrumentSpec(contract_size=1),
    "NAS100": InstrumentSpec(contract_size=1),
    "SPX500": InstrumentSpec(contract_size=1),
    "US500": InstrumentSpec(contract_size=1),
    "GER40": InstrumentSpec(contract_size=1),
    "DE40": InstrumentSpec(contract_size=1),
    # Крипта
    "BTCUSD": InstrumentSpec(contract_size=1),
    "ETHUSD": InstrumentSpec(contract_size=1),
}

# Пары, котируемые не в USD, — без ручного override объём будет неточным.
_NON_USD_QUOTE_HINT = {"USDJPY", "EURJPY", "GBPJPY", "USDMXN", "USDZAR"}


def load_instruments(extra_file: str = "") -> dict[str, InstrumentSpec]:
    """Базовая таблица + пользовательские инструменты из JSON-файла (необязательно).

    Формат файла: {"SYMBOL": {"contract_size": 100000, "pip_value_override": null}, ...}
    """
    table = dict(DEFAULT_INSTRUMENTS)
    if not extra_file:
        return table
    path = Path(extra_file)
    if not path.exists():
        return table
    raw = json.loads(path.read_text(encoding="utf-8"))
    for symbol, spec in raw.items():
        table[symbol.strip().upper()] = InstrumentSpec(
            contract_size=float(spec.get("contract_size", 100_000)),
            pip_value_override=(
                float(spec["pip_value_override"]) if spec.get("pip_value_override") else None
            ),
        )
    return table


def get_instrument(symbol: str, table: dict[str, InstrumentSpec]) -> InstrumentSpec:
    return table.get(symbol.strip().upper(), InstrumentSpec())


def needs_manual_pip_value(symbol: str) -> bool:
    return symbol.strip().upper() in _NON_USD_QUOTE_HINT
