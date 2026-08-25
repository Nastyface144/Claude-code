"""Расчёт объёма позиции и защитные лимиты риска проп-счёта."""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from .config import Settings
from .instruments import InstrumentSpec, get_instrument, load_instruments, needs_manual_pip_value
from .models import Setup


@dataclass(slots=True)
class RiskResult:
    entry: float
    stop_loss: float
    take_profit: float
    lots: float
    risk_amount: float
    risk_pct: float
    reward_ratio: float
    warnings: list[str] = field(default_factory=list)


def _fallback_stop_loss(entry: float, direction: str, default_sl_pct: float) -> float:
    offset = entry * default_sl_pct / 100
    return entry - offset if direction == "buy" else entry + offset


def _fallback_take_profit(entry: float, stop_loss: float, direction: str, rr: float) -> float:
    sl_distance = abs(entry - stop_loss)
    return entry + sl_distance * rr if direction == "buy" else entry - sl_distance * rr


def calculate_position(setup: Setup, settings: Settings) -> RiskResult:
    """Считает объём позиции так, чтобы убыток по стопу не превышал risk_per_trade_pct от баланса."""
    warnings: list[str] = []
    entry = setup.entry_price

    stop_loss = setup.stop_loss
    if stop_loss is None:
        stop_loss = _fallback_stop_loss(entry, setup.direction, settings.default_sl_pct)
        warnings.append(
            f"Стоп не пришёл ни от одного индикатора — использован запасной {settings.default_sl_pct}% от цены."
        )

    take_profit = setup.take_profit
    if take_profit is None:
        take_profit = _fallback_take_profit(entry, stop_loss, setup.direction, settings.default_risk_reward)
        warnings.append(
            f"Тейк не пришёл — рассчитан по запасному R:R {settings.default_risk_reward}."
        )

    sl_distance = abs(entry - stop_loss)
    if sl_distance <= 0:
        raise ValueError("Стоп-лосс совпадает с ценой входа — объём позиции посчитать нельзя.")

    instruments = load_instruments(settings.instruments_file)
    spec: InstrumentSpec = get_instrument(setup.symbol, instruments)
    value_per_lot_per_price_unit = spec.pip_value_override or spec.contract_size

    if needs_manual_pip_value(setup.symbol) and spec.pip_value_override is None:
        warnings.append(
            f"{setup.symbol} котируется не в {settings.account_currency}: без pip_value_override "
            "в INSTRUMENTS_FILE объём позиции может быть неточным."
        )

    risk_amount_target = settings.account_balance * settings.risk_per_trade_pct / 100
    lots_raw = risk_amount_target / (sl_distance * value_per_lot_per_price_unit)

    # Небольшой эпсилон компенсирует погрешность float (например, 1.1 - 1.095 != 0.005 ровно),
    # чтобы объём не занижался на один шаг лота там, где математически он должен округлиться ровно.
    lots = math.floor(lots_raw / settings.lot_step + 1e-9) * settings.lot_step
    lots = round(lots, 8)
    if lots < settings.min_lot:
        warnings.append(
            f"Расчётный объём {lots_raw:.4f} лота меньше минимального {settings.min_lot} — "
            "риск на сделке будет выше целевого."
        )
        lots = settings.min_lot

    actual_risk_amount = lots * sl_distance * value_per_lot_per_price_unit
    actual_risk_pct = (actual_risk_amount / settings.account_balance) * 100 if settings.account_balance else 0.0
    reward_ratio = abs(take_profit - entry) / sl_distance

    return RiskResult(
        entry=entry,
        stop_loss=stop_loss,
        take_profit=take_profit,
        lots=lots,
        risk_amount=actual_risk_amount,
        risk_pct=actual_risk_pct,
        reward_ratio=reward_ratio,
        warnings=warnings,
    )


@dataclass(slots=True)
class GuardDecision:
    allowed: bool
    reason: str = ""


def check_daily_guard(
    settings: Settings,
    *,
    trades_today: int,
    risk_budget_used_today: float,
    realized_loss_today: float,
    new_trade_risk: float,
) -> GuardDecision:
    """Проверка дневных лимитов проп-компании перед отправкой нового ордера."""
    if trades_today >= settings.max_daily_trades:
        return GuardDecision(False, f"дневной лимит сделок исчерпан ({settings.max_daily_trades})")

    max_loss_amount = settings.account_balance * settings.max_daily_loss_pct / 100

    if realized_loss_today >= max_loss_amount:
        return GuardDecision(
            False,
            f"дневной лимит убытка исчерпан по факту закрытых сделок "
            f"(-{realized_loss_today:.2f} из {max_loss_amount:.2f})",
        )

    if risk_budget_used_today + new_trade_risk > max_loss_amount:
        return GuardDecision(
            False,
            f"дневной риск-бюджет исчерпан: уже поставлено под риск {risk_budget_used_today:.2f}, "
            f"новая сделка добавит {new_trade_risk:.2f}, лимит {max_loss_amount:.2f}",
        )

    return GuardDecision(True)
