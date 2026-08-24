"""Сборка и запуск приложения: постоянный режим и один цикл для расписания."""

from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramConflictError
from aiogram.types import BotCommand

from .bot import build_router
from .config import Settings
from .service import PollReport, Radar
from .sources import DEFAULT_SOURCES
from .storage import Storage

log = logging.getLogger(__name__)

COMMANDS = [
    BotCommand(command="start", description="Включить рассылку заказов"),
    BotCommand(command="check", description="Опросить биржи сейчас"),
    BotCommand(command="last", description="Последние находки"),
    BotCommand(command="search", description="Поиск по найденным заказам"),
    BotCommand(command="status", description="Состояние и настройки"),
    BotCommand(command="keywords", description="Правила фильтра"),
    BotCommand(command="add", description="Добавить своё ключевое слово"),
    BotCommand(command="ban", description="Слово-исключение"),
    BotCommand(command="score", description="Порог релевантности"),
    BotCommand(command="sources", description="Источники (RSS бирж)"),
    BotCommand(command="stop", description="Выключить рассылку"),
    BotCommand(command="help", description="Справка"),
]

UPDATE_OFFSET_KEY = "update_offset"


async def build(settings: Settings) -> tuple[Storage, Bot, Radar, Dispatcher]:
    storage = await Storage(settings.db_path).connect()
    await storage.seed_sources(DEFAULT_SOURCES)
    for chat_id in settings.target_chat_ids:
        await storage.add_subscriber(chat_id)

    bot = Bot(settings.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    radar = Radar(settings, storage, bot)

    dispatcher = Dispatcher()
    dispatcher["radar"] = radar
    dispatcher.include_router(build_router())
    return storage, bot, radar, dispatcher


async def run(settings: Settings | None = None) -> None:
    """Постоянный режим: long polling Telegram + фоновой опрос бирж."""
    settings = settings or Settings.from_env()
    storage, bot, radar, dispatcher = await build(settings)

    poller = asyncio.create_task(radar.run_forever(), name="radar-poller")
    try:
        await bot.set_my_commands(COMMANDS)
        me = await bot.get_me()
        log.info("Бот @%s запущен", me.username)
        await dispatcher.start_polling(bot, radar=radar)
    finally:
        poller.cancel()
        try:
            await poller
        except asyncio.CancelledError:
            pass
        await bot.session.close()
        await storage.close()


async def run_once(settings: Settings | None = None) -> PollReport:
    """Один цикл для cron / GitHub Actions: разобрать команды, опросить биржи, разослать."""
    settings = settings or Settings.from_env()
    storage, bot, radar, dispatcher = await build(settings)

    try:
        await bot.set_my_commands(COMMANDS)
        await handle_pending_updates(bot, dispatcher, radar, storage)
        report = await radar.poll_once()
        log.info(
            "Цикл завершён: получено=%s новых=%s подходящих=%s отправлено=%s",
            report.fetched,
            report.new,
            report.relevant,
            report.sent,
        )
        await storage.compact()
        return report
    finally:
        await bot.session.close()
        await storage.close()


async def handle_pending_updates(
    bot: Bot, dispatcher: Dispatcher, radar: Radar, storage: Storage, limit: int = 100
) -> int:
    """Забрать накопившиеся сообщения (в том числе /start) и обработать их."""
    offset = await storage.get_meta_int(UPDATE_OFFSET_KEY) or None
    try:
        updates = await bot.get_updates(offset=offset, limit=limit, timeout=0)
    except TelegramConflictError:
        # Где-то уже запущен постоянный режим — команды обработает он.
        log.warning("Telegram отдаёт конфликт: бот уже запущен в другом месте")
        return 0

    for update in updates:
        try:
            await dispatcher.feed_update(bot, update, radar=radar)
        except Exception:  # noqa: BLE001 - один кривой апдейт не должен ломать цикл
            log.exception("Не удалось обработать апдейт %s", update.update_id)

    if updates:
        await storage.set_meta(UPDATE_OFFSET_KEY, updates[-1].update_id + 1)
    return len(updates)
