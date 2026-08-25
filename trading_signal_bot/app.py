"""Сборка и запуск приложения: HTTP-приём алертов + Telegram-бот."""

from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand

from .bot import build_router
from .config import Settings
from .service import TradingEngine
from .storage import Storage
from .webhook import build_app

log = logging.getLogger(__name__)

COMMANDS = [
    BotCommand(command="start", description="Включить рассылку сигналов"),
    BotCommand(command="status", description="Состояние и дневной риск"),
    BotCommand(command="trades", description="Последние сделки"),
    BotCommand(command="close", description="Зафиксировать результат сделки"),
    BotCommand(command="stop", description="Выключить рассылку"),
    BotCommand(command="help", description="Справка"),
]


async def _purge_loop(storage: Storage) -> None:
    while True:
        await asyncio.sleep(3600)
        try:
            await storage.purge_old_signals(hours=12)
        except Exception:  # noqa: BLE001
            log.exception("Не удалось очистить старые сигналы")


async def build(settings: Settings) -> tuple[Storage, Bot, TradingEngine, Dispatcher]:
    storage = await Storage(settings.db_path).connect()
    for chat_id in settings.target_chat_ids:
        await storage.add_subscriber(chat_id)

    bot = Bot(settings.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    engine = TradingEngine(settings, storage, bot)

    dispatcher = Dispatcher()
    dispatcher["engine"] = engine
    dispatcher.include_router(build_router())
    return storage, bot, engine, dispatcher


async def run(settings: Settings | None = None) -> None:
    settings = settings or Settings.from_env()
    if not settings.webhook_secret:
        raise RuntimeError(
            "Не задан WEBHOOK_SECRET — без него принимать алерты TradingView небезопасно."
        )

    storage, bot, engine, dispatcher = await build(settings)

    from aiohttp import web

    web_app = build_app(engine, settings.webhook_secret)
    runner = web.AppRunner(web_app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", settings.port)
    await site.start()
    log.info("Приём алертов TradingView: POST /webhook/<секрет> на порту %s", settings.port)

    purge_task = asyncio.create_task(_purge_loop(storage), name="signals-purge")
    try:
        await bot.set_my_commands(COMMANDS)
        me = await bot.get_me()
        log.info("Бот @%s запущен", me.username)
        await dispatcher.start_polling(bot, engine=engine)
    finally:
        purge_task.cancel()
        try:
            await purge_task
        except asyncio.CancelledError:
            pass
        await runner.cleanup()
        await bot.session.close()
        await storage.close()
