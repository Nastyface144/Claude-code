"""Хендлеры Telegram-бота."""

from __future__ import annotations

import logging
from html import escape

from aiogram import Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import Message

from .formatting import HELP_TEXT
from .service import TradingEngine

log = logging.getLogger(__name__)


async def cmd_start(message: Message, engine: TradingEngine) -> None:
    await engine.storage.add_subscriber(message.chat.id)
    settings = engine.settings
    await message.answer(
        "✅ Рассылка сигналов включена.\n"
        f"Порог подтверждений: {settings.min_confirmations} из {settings.total_indicators} "
        f"индикаторов в окне {settings.signal_window_seconds // 60} мин.\n"
        f"Риск на сделку: {settings.risk_per_trade_pct}% от баланса "
        f"{settings.account_balance:g} {settings.account_currency}.\n\n"
        "Список команд — /help"
    )


async def cmd_help(message: Message, engine: TradingEngine) -> None:
    await message.answer(HELP_TEXT)


async def cmd_stop(message: Message, engine: TradingEngine) -> None:
    await engine.storage.set_active(message.chat.id, False)
    await message.answer("⏸ Рассылка выключена. Включить обратно — /start")


async def cmd_status(message: Message, engine: TradingEngine) -> None:
    settings = engine.settings
    trades_today, risk_budget_used, realized_loss = await engine.storage.todays_risk_summary()
    max_loss_amount = settings.account_balance * settings.max_daily_loss_pct / 100

    lines = [
        "<b>Состояние</b>",
        f"Баланс счёта: {settings.account_balance:g} {escape(settings.account_currency)}",
        f"Риск на сделку: {settings.risk_per_trade_pct}%",
        f"Дневной лимит убытка: {settings.max_daily_loss_pct}% "
        f"({max_loss_amount:.2f} {escape(settings.account_currency)})",
        f"Лимит сделок в день: {settings.max_daily_trades}",
        "",
        "<b>Сегодня</b>",
        f"Сделок отправлено: {trades_today}/{settings.max_daily_trades}",
        f"Риск-бюджет использован: {risk_budget_used:.2f} из {max_loss_amount:.2f}",
        f"Зафиксированный убыток: {realized_loss:.2f}",
        "",
        f"ИИ-проверка: {'включена' if settings.ai_enabled else 'выключена'} "
        f"({escape(settings.ai_model)})",
    ]
    await message.answer("\n".join(lines))


async def cmd_trades(message: Message, command: CommandObject, engine: TradingEngine) -> None:
    limit = 5
    if command.args and command.args.strip().isdigit():
        limit = max(1, min(20, int(command.args.strip())))
    rows = await engine.storage.recent_trades(limit=limit)
    if not rows:
        await message.answer("Сделок пока нет.")
        return

    blocks = []
    for row in rows:
        result = ""
        if row["pnl_amount"] is not None:
            mark = "✅" if row["pnl_amount"] >= 0 else "❌"
            result = f"\n{mark} результат: {row['pnl_amount']:+.2f}"
        ai = ""
        if row["ai_approved"] is not None:
            ai = f"\nИИ: {'одобрено' if row['ai_approved'] else 'отклонено'} ({row['ai_confidence']}%)"
        take_profit = f"{row['take_profit']:g}" if row["take_profit"] is not None else "—"
        blocks.append(
            f"№{row['id']} · {escape(row['symbol'])} {escape(row['timeframe'])} "
            f"{'LONG' if row['direction'] == 'buy' else 'SHORT'}\n"
            f"Вход {row['entry']:g} · SL {row['stop_loss']:g} · TP {take_profit}\n"
            f"Объём {row['lots']:g} лот · риск {row['risk_amount']:.2f} ({row['risk_pct']:.2f}%)"
            f"{ai}{result}"
        )
    await message.answer("\n\n".join(blocks))


async def cmd_close(message: Message, command: CommandObject, engine: TradingEngine) -> None:
    raw = (command.args or "").strip().split()
    if len(raw) != 2 or not raw[0].isdigit():
        await message.answer(
            "Как пользоваться: <code>/close 12 -45.5</code> — номер сделки и итог в валюте счёта "
            "(отрицательное число — убыток)."
        )
        return
    trade_id = int(raw[0])
    try:
        pnl = float(raw[1])
    except ValueError:
        await message.answer("Итог сделки должен быть числом, например -45.5 или 120")
        return

    ok = await engine.storage.close_trade(trade_id, pnl)
    if not ok:
        await message.answer(f"Сделка №{trade_id} не найдена")
        return
    await message.answer(f"✅ Сделка №{trade_id} закрыта с результатом {pnl:+.2f}")


def build_router() -> Router:
    """Свежий Router с командами. Router привязывается лишь к одному Dispatcher,
    поэтому создаём его функцией, а не на уровне модуля."""
    router = Router(name="trading")
    router.message.register(cmd_start, CommandStart())
    router.message.register(cmd_help, Command("help"))
    router.message.register(cmd_stop, Command("stop"))
    router.message.register(cmd_status, Command("status"))
    router.message.register(cmd_trades, Command("trades"))
    router.message.register(cmd_close, Command("close"))
    return router
