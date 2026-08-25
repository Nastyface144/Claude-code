"""Форматирование сообщений для Telegram."""

from __future__ import annotations

from html import escape

from .ai_review import AIOutcome
from .config import Settings
from .models import Setup
from .risk import RiskResult

HELP_TEXT = (
    "<b>Бот торговых сигналов</b>\n\n"
    "Собирает сигналы от твоих индикаторов TradingView, при достижении порога "
    "подтверждений проверяет сетап через ИИ, считает объём позиции под риск "
    "проп-счёта и присылает готовый приказ на вход.\n\n"
    "Команды:\n"
    "/start — включить рассылку\n"
    "/stop — выключить рассылку\n"
    "/status — состояние, дневной риск, лимиты\n"
    "/trades [N] — последние сделки\n"
    "/close &lt;id&gt; &lt;pnl&gt; — зафиксировать результат сделки (для дневного лимита убытка)\n"
    "/help — эта справка"
)


def _direction_label(direction: str) -> str:
    return "🟢 LONG (buy)" if direction == "buy" else "🔴 SHORT (sell)"


def order_message(setup: Setup, risk: RiskResult, ai: AIOutcome, settings: Settings, trade_id: int) -> str:
    lines = [
        f"📡 <b>{escape(setup.symbol)}</b> · {escape(setup.timeframe)} · {_direction_label(setup.direction)}",
        f"Подтвердили {len(setup.indicators)}/{settings.total_indicators}: "
        f"{escape(', '.join(setup.indicators))}",
        "",
        f"Вход: <b>{risk.entry:g}</b>",
        f"Стоп-лосс: <b>{risk.stop_loss:g}</b>",
        f"Тейк-профит: <b>{risk.take_profit:g}</b>",
        f"R:R ≈ {risk.reward_ratio:.2f}",
        "",
        f"Объём: <b>{risk.lots:g} лот</b>",
        f"Риск на сделке: <b>{risk.risk_amount:.2f} {escape(settings.account_currency)} "
        f"({risk.risk_pct:.2f}% от баланса)</b>",
    ]

    if ai.ran and ai.verdict is not None:
        mark = "✅" if ai.verdict.approve else "⛔️"
        lines += [
            "",
            f"{mark} <b>ИИ-проверка</b>: уверенность {ai.verdict.confidence}%",
            escape(ai.verdict.reasoning),
        ]
        if ai.verdict.warnings:
            lines.append("⚠️ " + escape("; ".join(ai.verdict.warnings)))
    elif not ai.ran:
        lines += ["", f"⚠️ ИИ-проверка недоступна: {escape(ai.error)}"]

    if risk.warnings:
        lines += ["", "⚠️ " + escape(" / ".join(risk.warnings))]

    lines += ["", f"Сделка №{trade_id} · закрыть результат: <code>/close {trade_id} &lt;pnl&gt;</code>"]
    return "\n".join(lines)


def guard_blocked_message(setup: Setup, reason: str) -> str:
    return (
        f"⛔️ Сигнал по <b>{escape(setup.symbol)}</b> {escape(setup.timeframe)} "
        f"({_direction_label(setup.direction)}) подтверждён индикаторами, но НЕ отправлен: "
        f"{escape(reason)}."
    )


def ai_rejected_message(setup: Setup, ai: AIOutcome) -> str:
    verdict = ai.verdict
    reasoning = escape(verdict.reasoning) if verdict else ""
    confidence = verdict.confidence if verdict else 0
    return (
        f"⛔️ Сетап <b>{escape(setup.symbol)}</b> {escape(setup.timeframe)} "
        f"({_direction_label(setup.direction)}) отклонён ИИ-проверкой "
        f"(уверенность {confidence}%): {reasoning}"
    )
