"""Сборка и запуск приложения."""

from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand

from .bot import router
from .config import Settings
from .service import Radar
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


async def run(settings: Settings | None = None) -> None:
    settings = settings or Settings.from_env()

    storage = await Storage(settings.db_path).connect()
    await storage.seed_sources(DEFAULT_SOURCES)

    bot = Bot(settings.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    radar = Radar(settings, storage, bot)

    dispatcher = Dispatcher()
    dispatcher["radar"] = radar
    dispatcher.include_router(router)

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
