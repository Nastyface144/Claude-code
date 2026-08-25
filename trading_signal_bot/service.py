"""Оркестрация: приём сигнала -> агрегация -> ИИ-проверка -> риск -> рассылка."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter

from .ai_review import AIOutcome, review_setup
from .config import Settings
from .formatting import ai_rejected_message, guard_blocked_message, order_message
from .models import Setup, Signal
from .risk import RiskResult, calculate_position, check_daily_guard
from .storage import Storage

log = logging.getLogger(__name__)


@dataclass(slots=True)
class ProcessResult:
    status: str  # "waiting" | "cooldown" | "guard_blocked" | "ai_rejected" | "sent" | "error"
    detail: str = ""
    trade_id: int | None = None


class TradingEngine:
    def __init__(self, settings: Settings, storage: Storage, bot: Bot | None) -> None:
        self.settings = settings
        self.storage = storage
        self.bot = bot
        self._lock = asyncio.Lock()

    async def handle_signal(self, signal: Signal) -> ProcessResult:
        async with self._lock:
            await self.storage.save_signal(signal)
            symbol, timeframe, direction = signal.group_key

            recent = await self.storage.recent_signals(
                symbol, timeframe, direction, self.settings.signal_window_seconds
            )
            setup = Setup(symbol=symbol, timeframe=timeframe, direction=direction, signals=recent)

            if len(setup.indicators) < self.settings.min_confirmations:
                return ProcessResult(
                    "waiting",
                    f"{len(setup.indicators)}/{self.settings.min_confirmations} подтверждений",
                )

            if await self.storage.recently_dispatched(
                symbol, timeframe, direction, self.settings.dispatch_cooldown_seconds
            ):
                return ProcessResult("cooldown", "сетап уже отправлялся недавно")

            return await self._process_setup(setup)

    async def _process_setup(self, setup: Setup) -> ProcessResult:
        try:
            risk = calculate_position(setup, self.settings)
        except ValueError as exc:
            log.warning("Не удалось посчитать риск по %s: %s", setup.symbol, exc)
            return ProcessResult("error", str(exc))

        trades_today, risk_budget_used, realized_loss = await self.storage.todays_risk_summary()
        guard = check_daily_guard(
            self.settings,
            trades_today=trades_today,
            risk_budget_used_today=risk_budget_used,
            realized_loss_today=realized_loss,
            new_trade_risk=risk.risk_amount,
        )
        await self.storage.mark_dispatched(setup.symbol, setup.timeframe, setup.direction)

        if not guard.allowed:
            await self._broadcast(guard_blocked_message(setup, guard.reason))
            return ProcessResult("guard_blocked", guard.reason)

        ai = await review_setup(setup, risk, self.settings)

        if ai.ran and ai.verdict is not None and not ai.verdict.approve and self.settings.ai_block_on_reject:
            if self.settings.ai_notify_rejected:
                await self._broadcast(ai_rejected_message(setup, ai))
            return ProcessResult("ai_rejected", ai.verdict.reasoning)

        trade_id = await self.storage.log_trade(
            symbol=setup.symbol,
            timeframe=setup.timeframe,
            direction=setup.direction,
            entry=risk.entry,
            stop_loss=risk.stop_loss,
            take_profit=risk.take_profit,
            lots=risk.lots,
            risk_amount=risk.risk_amount,
            risk_pct=risk.risk_pct,
            confirmations=setup.indicators,
            ai_approved=ai.verdict.approve if ai.verdict else None,
            ai_confidence=ai.verdict.confidence if ai.verdict else None,
            ai_reasoning=ai.verdict.reasoning if ai.verdict else ai.error,
        )

        await self._broadcast(order_message(setup, risk, ai, self.settings, trade_id))
        return ProcessResult("sent", "", trade_id)

    async def _broadcast(self, text: str) -> None:
        if self.bot is None:
            log.info("(нет Telegram-бота, вывод в лог)\n%s", text)
            return
        for subscriber in await self.storage.active_subscribers():
            await self._send(subscriber["chat_id"], text)

    async def _send(self, chat_id: int, text: str) -> bool:
        assert self.bot is not None
        try:
            await self.bot.send_message(chat_id, text)
        except TelegramRetryAfter as exc:
            await asyncio.sleep(exc.retry_after + 1)
            return await self._send(chat_id, text)
        except TelegramForbiddenError:
            await self.storage.set_active(chat_id, False)
            log.info("Чат %s заблокировал бота, рассылка отключена", chat_id)
            return False
        except Exception as exc:  # noqa: BLE001
            log.warning("Не удалось отправить сообщение в чат %s: %s", chat_id, exc)
            return False
        return True
