from datetime import datetime, timedelta, timezone

import pytest

from freelance_bot.config import Settings
from freelance_bot.models import Order
from freelance_bot.service import Radar
from freelance_bot.sources.base import SourceConfig
from freelance_bot.storage import Storage


class FakeBot:
    """Минимальная замена aiogram.Bot: просто копит отправленные сообщения."""

    def __init__(self) -> None:
        self.sent: list[tuple[int, str]] = []

    async def send_message(self, chat_id: int, text: str, **kwargs) -> None:
        self.sent.append((chat_id, text))


def make_settings(tmp_path) -> Settings:
    return Settings(
        bot_token="test",
        db_path=tmp_path / "db.sqlite",
        min_score=5,
        max_per_cycle=2,
        min_source_interval=600,
    )


@pytest.fixture()
async def env(tmp_path):
    storage = await Storage(tmp_path / "db.sqlite").connect()
    bot = FakeBot()
    radar = Radar(make_settings(tmp_path), storage, bot)
    yield radar, storage, bot
    await storage.close()


def feed(radar: Radar, orders: list[Order], errors=()) -> None:
    async def collect():
        return orders, list(errors), {"test": "Тестовая биржа"}

    radar.collect = collect  # type: ignore[method-assign]


def order(external_id: str, title: str, description: str = "") -> Order:
    return Order(
        source="test",
        external_id=external_id,
        title=title,
        url=f"https://example.com/{external_id}",
        description=description,
    )


async def test_relevant_order_is_delivered(env):
    radar, storage, bot = env
    await storage.add_subscriber(100)
    feed(radar, [order("1", "Нужен телеграм-бот для записи"), order("2", "Нужен грузчик на склад")])

    report = await radar.poll_once()

    assert (report.fetched, report.new, report.relevant, report.sent) == (2, 2, 1, 1)
    assert len(bot.sent) == 1
    chat_id, text = bot.sent[0]
    assert chat_id == 100
    assert "телеграм-бот" in text and "Тестовая биржа" in text


async def test_same_order_is_not_sent_twice(env):
    radar, storage, bot = env
    await storage.add_subscriber(100)
    feed(radar, [order("1", "Разработка Telegram Mini App")])

    await radar.poll_once()
    second = await radar.poll_once()

    assert second.new == 0
    assert len(bot.sent) == 1


async def test_inactive_subscriber_gets_nothing(env):
    radar, storage, bot = env
    await storage.add_subscriber(100)
    await storage.set_active(100, False)
    feed(radar, [order("1", "Нужен лендинг под ключ")])

    await radar.poll_once()

    assert bot.sent == []


async def test_personal_min_score_and_ban_word(env):
    radar, storage, bot = env
    await storage.add_subscriber(100)
    await storage.add_subscriber(200)
    await storage.add_rule(200, "exclude", "маркетплейс")
    feed(radar, [order("1", "Телеграм-бот для маркетплейса", "бот на aiogram")])

    await radar.poll_once()

    assert [chat for chat, _ in bot.sent] == [100]


async def test_max_per_cycle_limits_flood(env):
    radar, storage, bot = env
    await storage.add_subscriber(100)
    feed(radar, [order(str(i), f"Нужен телеграм-бот №{i}") for i in range(5)])

    report = await radar.poll_once()

    assert report.relevant == 5
    assert report.sent == 2  # max_per_cycle
    assert len(bot.sent) == 2


async def test_source_errors_are_reported_not_raised(env):
    radar, storage, bot = env
    await storage.add_subscriber(100)
    feed(radar, [order("1", "Лендинг для стоматологии")], errors=[("fl", "timeout")])

    report = await radar.poll_once()

    assert report.errors == [("fl", "timeout")]
    assert report.sent == 1
    assert "timeout" in report.as_text()


async def test_orders_are_sent_best_first(env):
    radar, storage, bot = env
    await storage.add_subscriber(100)
    feed(
        radar,
        [
            order("1", "Сайт нужен", "лендинг одностраничный"),
            order("2", "Телеграм-бот + Mini App на aiogram", "лендинг тоже нужен"),
        ],
    )

    await radar.poll_once()

    assert "Mini App" in bot.sent[0][1]


async def test_recently_polled_source_is_skipped(env, tmp_path):
    """При частых запусках биржу не дёргаем чаще, чем раз в min_source_interval."""
    radar, storage, _bot = env
    await storage.seed_sources([SourceConfig(name="test", url="https://x/rss", title="Тест")])

    assert [c.name for c in await storage.source_configs()] == ["test"]
    await storage.record_source_run("test", 5, None)  # только что опросили

    configs, _errors, titles = await radar.collect()
    assert configs == [] and titles == {"test": "Тест"}


async def test_source_is_polled_again_after_the_pause(env):
    radar, storage, _bot = env
    await storage.seed_sources([SourceConfig(name="test", url="https://неведомый.invalid/rss")])
    await storage.record_source_run("test", 5, None)
    stale = (datetime.now(timezone.utc) - timedelta(seconds=3600)).isoformat(timespec="seconds")
    await storage.db.execute("UPDATE sources SET last_ok = ?", (stale,))
    await storage.db.commit()

    _orders, errors, _titles = await radar.collect()

    # пауза прошла — источник опрашивали снова (адрес заведомо нерабочий → ошибка)
    assert [name for name, _ in errors] == ["test"]
