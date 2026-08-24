"""Проверка команд бота: гоняем настоящие апдейты через настоящий Dispatcher."""

from datetime import datetime, timezone

import pytest
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.base import BaseSession
from aiogram.enums import ParseMode
from aiogram.methods import EditMessageText, SendMessage, TelegramMethod
from aiogram.types import Chat, Message, Update, User

from freelance_bot.bot import router
from freelance_bot.config import Settings
from freelance_bot.models import Order
from freelance_bot.service import Radar
from freelance_bot.storage import Storage

CHAT_ID = 555

# Router можно подключить лишь к одному Dispatcher, поэтому он общий на модуль:
DISPATCHER = Dispatcher()
DISPATCHER.include_router(router)


class MockSession(BaseSession):
    """Ловим исходящие вызовы Telegram API вместо реальных запросов."""

    def __init__(self) -> None:
        super().__init__()
        self.calls: list[TelegramMethod] = []

    @property
    def texts(self) -> list[str]:
        """Тексты всех исходящих сообщений — и новых, и отредактированных."""
        return [call.text for call in self.calls if isinstance(call, (SendMessage, EditMessageText))]

    async def close(self) -> None:  # pragma: no cover - ничего не держим
        pass

    async def stream_content(self, *args, **kwargs):  # pragma: no cover - не используется
        yield b""

    async def make_request(self, bot, method, timeout=None):
        self.calls.append(method)
        reply = Message(
            message_id=len(self.calls),
            date=datetime.now(timezone.utc),
            chat=Chat(id=CHAT_ID, type="private"),
            text=getattr(method, "text", ""),
        )
        return reply.as_(bot)  # без привязки к боту нельзя вызвать message.edit_text()


@pytest.fixture()
async def app(tmp_path):
    storage = await Storage(tmp_path / "db.sqlite").connect()
    session = MockSession()
    bot = Bot("42:TEST", session=session, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    radar = Radar(Settings(bot_token="42:TEST", db_path=tmp_path / "db.sqlite"), storage, bot)

    async def collect():
        return [
            Order(
                source="test",
                external_id="1",
                title="Нужен телеграм-бот для записи клиентов",
                url="https://example.com/1",
                description="Бот на aiogram, бюджет 40 000 руб",
            )
        ], [], {"test": "Тестовая биржа"}

    radar.collect = collect  # type: ignore[method-assign]

    async def send(text: str) -> list[str]:
        session.calls.clear()
        update = Update(
            update_id=len(session.calls) + 1,
            message=Message(
                message_id=1,
                date=datetime.now(timezone.utc),
                chat=Chat(id=CHAT_ID, type="private"),
                from_user=User(id=CHAT_ID, is_bot=False, first_name="Тест"),
                text=text,
            ),
        )
        await DISPATCHER.feed_update(bot, update, radar=radar)
        return session.texts

    yield send, storage, session
    await storage.close()


async def test_start_subscribes_chat(app):
    send, storage, _ = app
    replies = await send("/start")
    assert "Рассылка включена" in replies[0]
    assert [row["chat_id"] for row in await storage.active_subscribers()] == [CHAT_ID]


async def test_stop_unsubscribes_chat(app):
    send, storage, _ = app
    await send("/start")
    await send("/stop")
    assert await storage.active_subscribers() == []


async def test_check_polls_and_delivers(app):
    send, _, _ = app
    await send("/start")
    replies = await send("/check")
    assert any("телеграм-бот для записи" in text for text in replies)
    assert any("Отправлено: 1" in text for text in replies)


async def test_last_shows_found_orders(app):
    send, _, _ = app
    await send("/start")
    await send("/check")
    replies = await send("/last 3")
    assert "телеграм-бот для записи" in replies[0]
    assert "40 000 руб" in replies[0]


async def test_score_updates_threshold(app):
    send, storage, _ = app
    await send("/score 9")
    subscriber = await storage.get_subscriber(CHAT_ID)
    assert subscriber["min_score"] == 9
    assert "9" in (await send("/status"))[0]


async def test_add_and_del_user_keyword(app):
    send, storage, _ = app
    await send("/add уведомлени* 6")
    assert await storage.list_rules(CHAT_ID) == ([("уведомлени*", 6)], [])
    assert "уведомлени*" in (await send("/keywords"))[0]
    await send("/del уведомлени*")
    assert await storage.list_rules(CHAT_ID) == ([], [])


async def test_ban_word_filters_delivery(app):
    send, _, _ = app
    await send("/start")
    await send("/ban запис*")
    replies = await send("/check")
    assert not any("телеграм-бот для записи" in text for text in replies)


async def test_sources_add_toggle_delete(app):
    send, storage, _ = app
    await send("/addsource mysite https://example.com/rss Моя лента")
    assert "mysite" in (await send("/sources"))[0]
    await send("/togglesource mysite")
    assert "mysite" not in [c.name for c in await storage.source_configs()]
    await send("/delsource mysite")
    assert "mysite" not in [row["name"] for row in await storage.list_sources()]


async def test_bad_source_url_is_rejected(app):
    send, storage, _ = app
    replies = await send("/addsource mysite ftp://example.com")
    assert "Как пользоваться" in replies[0]
    assert "mysite" not in [row["name"] for row in await storage.list_sources()]


async def test_plain_text_runs_search(app):
    send, _, _ = app
    await send("/start")
    await send("/check")
    replies = await send("бот")
    assert "Нашёл по «бот»" in replies[0]
    assert "Не понял команду" in (await send("абракадабра"))[0]
