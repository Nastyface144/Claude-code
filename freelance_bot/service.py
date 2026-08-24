"""Опрос бирж, фильтрация и рассылка подходящих заказов."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field

import aiohttp
from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter

from .config import Settings
from .formatting import order_message
from .matcher import Matcher, MatchResult
from .models import Order
from .sources import build_sources
from .storage import Storage

log = logging.getLogger(__name__)


@dataclass(slots=True)
class PollReport:
    fetched: int = 0
    new: int = 0
    relevant: int = 0
    sent: int = 0
    errors: list[tuple[str, str]] = field(default_factory=list)

    def as_text(self) -> str:
        lines = [
            f"Получено объявлений: {self.fetched}",
            f"Из них новых: {self.new}",
            f"Подходящих: {self.relevant}",
            f"Отправлено: {self.sent}",
        ]
        if self.errors:
            lines.append("Ошибки источников:")
            lines += [f"• {name}: {err}" for name, err in self.errors]
        return "\n".join(lines)


class Radar:
    """Ядро: сходить на биржи, отфильтровать, разослать."""

    def __init__(self, settings: Settings, storage: Storage, bot: Bot) -> None:
        self.settings = settings
        self.storage = storage
        self.bot = bot
        self.base_matcher = Matcher()
        self._lock = asyncio.Lock()
        self.last_report: PollReport | None = None

    # --- сбор -----------------------------------------------------------
    async def collect(self) -> tuple[list[Order], list[tuple[str, str]], dict[str, str]]:
        configs = await self.storage.source_configs()
        sources = build_sources(configs)
        titles = {config.name: config.label for config in configs}
        if not sources:
            return [], [], titles

        timeout = aiohttp.ClientTimeout(total=self.settings.request_timeout)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            results = await asyncio.gather(*(source.safe_fetch(session) for source in sources))

        orders: list[Order] = []
        errors: list[tuple[str, str]] = []
        for result in results:
            await self.storage.record_source_run(result.source, len(result.orders), result.error)
            if result.ok:
                orders.extend(result.orders)
            else:
                errors.append((result.source, result.error or "неизвестная ошибка"))
                log.warning("Источник %s не ответил: %s", result.source, result.error)
        return orders, errors, titles

    # --- полный цикл ------------------------------------------------------
    async def poll_once(self) -> PollReport:
        """Один цикл: опрос источников -> фильтр -> рассылка. Не запускается параллельно сам с собой."""
        async with self._lock:
            report = PollReport()
            orders, errors, titles = await self.collect()
            report.fetched = len(orders)
            report.errors = errors

            fresh: list[tuple[Order, MatchResult]] = []
            for order in orders:
                match = self.base_matcher.match(order)
                is_new = await self.storage.save_order(order, match.score, match.tags)
                if is_new:
                    report.new += 1
                    fresh.append((order, match))

            fresh.sort(key=lambda pair: (pair[1].score, pair[0].published_ts()), reverse=True)
            report.relevant = sum(
                1 for _, match in fresh if match.is_relevant(self.settings.min_score)
            )

            for subscriber in await self.storage.active_subscribers():
                chat_id = subscriber["chat_id"]
                min_score = subscriber["min_score"] or self.settings.min_score
                matcher = await self.matcher_for(chat_id)
                sent = 0
                for order, base_match in fresh:
                    if sent >= self.settings.max_per_cycle:
                        break
                    match = base_match if matcher is self.base_matcher else matcher.match(order)
                    if not match.is_relevant(min_score):
                        continue
                    if await self.storage.was_delivered(chat_id, order.uid):
                        continue
                    if await self.send_order(chat_id, order, match, titles.get(order.source, "")):
                        await self.storage.mark_delivered(chat_id, order.uid)
                        sent += 1
                report.sent += sent

            await self.storage.purge_old(days=30)
            self.last_report = report
            return report

    async def matcher_for(self, chat_id: int) -> Matcher:
        include, exclude = await self.storage.list_rules(chat_id)
        if not include and not exclude:
            return self.base_matcher
        return self.base_matcher.with_user_rules(include=include, exclude=exclude)

    # --- отправка ---------------------------------------------------------
    async def send_order(
        self, chat_id: int, order: Order, match: MatchResult, source_title: str = ""
    ) -> bool:
        text = order_message(order, match, source_title)
        try:
            await self.bot.send_message(chat_id, text, disable_web_page_preview=True)
        except TelegramRetryAfter as exc:
            await asyncio.sleep(exc.retry_after + 1)
            return await self.send_order(chat_id, order, match, source_title)
        except TelegramForbiddenError:
            # Пользователь заблокировал бота — снимаем с рассылки.
            await self.storage.set_active(chat_id, False)
            log.info("Чат %s заблокировал бота, рассылка отключена", chat_id)
            return False
        except Exception as exc:  # noqa: BLE001
            log.warning("Не удалось отправить заказ в чат %s: %s", chat_id, exc)
            return False
        await asyncio.sleep(0.05)  # мягкий троттлинг под лимиты Telegram
        return True

    # --- фоновая задача ----------------------------------------------------
    async def run_forever(self) -> None:
        log.info("Фоновый опрос запущен, интервал %s с", self.settings.poll_interval)
        while True:
            try:
                report = await self.poll_once()
                log.info(
                    "Цикл завершён: получено=%s новых=%s подходящих=%s отправлено=%s",
                    report.fetched,
                    report.new,
                    report.relevant,
                    report.sent,
                )
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001
                log.exception("Ошибка в цикле опроса")
            await asyncio.sleep(self.settings.poll_interval)
