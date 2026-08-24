import pytest

from freelance_bot.models import Order
from freelance_bot.sources.base import SourceConfig
from freelance_bot.storage import Storage


@pytest.fixture()
async def storage(tmp_path):
    store = await Storage(tmp_path / "test.db").connect()
    yield store
    await store.close()


def make_order(external_id: str = "1", title: str = "Телеграм бот") -> Order:
    return Order(
        source="test",
        external_id=external_id,
        title=title,
        url=f"https://example.com/{external_id}",
        description="Бюджет 20 000 руб",
    )


async def test_subscribers_lifecycle(storage):
    await storage.add_subscriber(42)
    assert [row["chat_id"] for row in await storage.active_subscribers()] == [42]

    await storage.set_active(42, False)
    assert await storage.active_subscribers() == []

    await storage.add_subscriber(42)  # /start после /stop снова включает
    assert len(await storage.active_subscribers()) == 1


async def test_save_order_is_idempotent(storage):
    order = make_order()
    assert await storage.save_order(order, 10, ["бот"]) is True
    assert await storage.save_order(order, 10, ["бот"]) is False

    rows = await storage.recent_orders(limit=5)
    assert len(rows) == 1
    assert rows[0]["budget"] == "20 000 руб"
    assert rows[0]["tags"] == "бот"


async def test_recent_orders_respects_min_score(storage):
    await storage.save_order(make_order("1", "Телеграм бот"), 9, ["бот"])
    await storage.save_order(make_order("2", "Что-то другое"), 1, [])
    assert len(await storage.recent_orders(min_score=5)) == 1
    assert len(await storage.recent_orders(min_score=1)) == 2


async def test_deliveries_are_tracked_per_chat(storage):
    order = make_order()
    assert await storage.was_delivered(1, order.uid) is False
    await storage.mark_delivered(1, order.uid)
    assert await storage.was_delivered(1, order.uid) is True
    assert await storage.was_delivered(2, order.uid) is False


async def test_user_rules_crud(storage):
    await storage.add_rule(7, "include", "Мини Апп", 6)
    await storage.add_rule(7, "exclude", "WordPress")
    include, exclude = await storage.list_rules(7)
    assert include == [("мини апп", 6)]
    assert exclude == ["wordpress"]

    await storage.add_rule(7, "include", "мини апп", 8)  # обновление веса, не дубль
    include, _ = await storage.list_rules(7)
    assert include == [("мини апп", 8)]

    assert await storage.remove_rule(7, "мини апп") == 1
    assert await storage.list_rules(7) == ([], ["wordpress"])


async def test_sources_seed_and_toggle(storage):
    await storage.seed_sources([SourceConfig(name="fl", url="https://fl/rss", title="FL.ru")])
    await storage.seed_sources([SourceConfig(name="fl", url="https://other", title="FL.ru")])
    rows = await storage.list_sources()
    assert len(rows) == 1 and rows[0]["url"] == "https://fl/rss"  # повторный сид не перетирает

    await storage.add_source("kwork", "https://kwork/rss")
    assert len(await storage.source_configs()) == 2

    await storage.set_source_enabled("kwork", False)
    assert [c.name for c in await storage.source_configs()] == ["fl"]

    await storage.record_source_run("fl", 12, None)
    assert (await storage.list_sources())[0]["last_count"] == 12

    await storage.record_source_run("fl", 0, "timeout")
    assert (await storage.list_sources())[0]["last_error"] == "timeout"

    assert await storage.remove_source("kwork") == 1
