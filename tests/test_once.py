"""Режим одного цикла (cron / GitHub Actions)."""

from datetime import datetime, timedelta, timezone

import pytest
from aiogram import Bot
from aiogram.client.session.base import BaseSession
from aiogram.methods import GetUpdates, SendMessage, SetMyCommands
from aiogram.types import Chat, Message, Update, User

import freelance_bot.app as app_module
from freelance_bot.app import UPDATE_OFFSET_KEY, run_once
from freelance_bot.config import Settings
from freelance_bot.models import Order
from freelance_bot.service import Radar
from freelance_bot.storage import Storage

CHAT_ID = 777


def user_update(update_id: int, text: str) -> Update:
    return Update(
        update_id=update_id,
        message=Message(
            message_id=update_id,
            date=datetime.now(timezone.utc),
            chat=Chat(id=CHAT_ID, type="private"),
            from_user=User(id=CHAT_ID, is_bot=False, first_name="Тест"),
            text=text,
        ),
    )


class MockSession(BaseSession):
    def __init__(self, updates: list[Update]) -> None:
        super().__init__()
        self.updates = updates
        self.sent: list[str] = []
        self.get_updates_offsets: list[int | None] = []

    async def close(self) -> None:  # pragma: no cover
        pass

    async def stream_content(self, *args, **kwargs):  # pragma: no cover
        yield b""

    async def make_request(self, bot, method, timeout=None):
        if isinstance(method, GetUpdates):
            self.get_updates_offsets.append(method.offset)
            pending, self.updates = self.updates, []
            return pending
        if isinstance(method, SetMyCommands):
            return True
        if isinstance(method, SendMessage):
            self.sent.append(method.text)
            return Message(
                message_id=len(self.sent),
                date=datetime.now(timezone.utc),
                chat=Chat(id=CHAT_ID, type="private"),
                text=method.text,
            ).as_(bot)
        return True


@pytest.fixture()
def cron_env(tmp_path, monkeypatch):
    """Готовит окружение: подменяем сессию Telegram и поход на биржи."""
    sessions: list[MockSession] = []
    orders = [
        Order(
            source="test",
            external_id="1",
            title="Нужен телеграм-бот для записи клиентов",
            url="https://example.com/1",
            description="Бот на aiogram, бюджет 40 000 руб",
        )
    ]

    def make_session(updates: list[Update]) -> None:
        session = MockSession(updates)
        sessions.append(session)
        real_bot = Bot

        def bot_factory(token, **kwargs):
            return real_bot(token, session=session, **kwargs)

        monkeypatch.setattr(app_module, "Bot", bot_factory)

    async def fake_collect(self):
        return list(orders), [], {"test": "Тестовая биржа"}

    monkeypatch.setattr(Radar, "collect", fake_collect)

    settings = Settings(bot_token="42:TEST", db_path=tmp_path / "db.sqlite", min_score=5)
    return settings, make_session, sessions, orders


async def test_start_from_updates_then_delivery(cron_env):
    settings, make_session, sessions, _ = cron_env
    make_session([user_update(10, "/start")])

    report = await run_once(settings)

    assert report.sent == 1
    texts = sessions[-1].sent
    assert any("Рассылка включена" in text for text in texts)
    assert any("телеграм-бот для записи" in text for text in texts)


async def test_second_run_skips_processed_updates_and_orders(cron_env):
    settings, make_session, sessions, _ = cron_env
    make_session([user_update(10, "/start")])
    await run_once(settings)

    make_session([])
    report = await run_once(settings)

    assert sessions[-1].get_updates_offsets == [11]  # оффсет сохранился между запусками
    assert report.new == 0 and report.sent == 0
    assert sessions[-1].sent == []


async def test_target_chat_is_subscribed_without_start(cron_env, tmp_path):
    settings, make_session, sessions, _ = cron_env
    settings = Settings(
        bot_token="42:TEST",
        db_path=tmp_path / "db.sqlite",
        min_score=5,
        target_chat_ids=(CHAT_ID,),
    )
    make_session([])

    report = await run_once(settings)

    assert report.sent == 1
    assert "телеграм-бот для записи" in sessions[-1].sent[0]


async def test_offset_is_stored(cron_env):
    settings, make_session, _, _ = cron_env
    make_session([user_update(10, "/start"), user_update(11, "/status")])
    await run_once(settings)

    storage = await Storage(settings.db_path).connect()
    assert await storage.get_meta_int(UPDATE_OFFSET_KEY) == 12
    await storage.close()


async def test_compact_keeps_dedup_but_drops_old_rows(tmp_path):
    storage = await Storage(tmp_path / "db.sqlite").connect()
    order = Order(source="test", external_id="1", title="Телеграм бот", url="https://x/1", description="A" * 500)
    await storage.save_order(order, 10, ["бот"])

    old = (datetime.now(timezone.utc) - timedelta(days=5)).isoformat(timespec="seconds")
    await storage.db.execute("UPDATE orders SET found_at = ?", (old,))
    await storage.db.commit()

    await storage.compact(keep_details_days=2, keep_days=14)

    rows = await storage.recent_orders(limit=5)
    assert rows[0]["description"] == ""  # текст выброшен
    assert await storage.save_order(order, 10, ["бот"]) is False  # но повтор всё ещё ловится

    await storage.compact(keep_details_days=2, keep_days=1)
    assert await storage.recent_orders(limit=5) == []
    await storage.close()
