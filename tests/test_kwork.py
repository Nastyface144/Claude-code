"""Разбор биржи заказов Kwork (данные лежат в JSON внутри страницы)."""

import json
from types import SimpleNamespace

import aiohttp
import pytest

from freelance_bot.matcher import Matcher
from freelance_bot.sources.base import SourceConfig
from freelance_bot.sources.kwork import KworkSource, extract_wants, parse_wants

WANT = {
    "id": 3241244,
    "status": "active",
    "isWantActive": True,
    "name": "Нужен телеграм-бот для записи клиентов",
    "description": "Бот на aiogram с админкой и оплатой.",
    "priceLimit": "500.00",
    "possiblePriceLimit": 1500,
    "max_days": "10",
    "kwork_count": 2,
    "category_id": "41",
    "wantDates": {"dateCreate": "24 августа"},
    "user": {"username": "vlad9111"},
}


def page(wants: list[dict]) -> str:
    payload = json.dumps({"wantsListData": {"wants": wants, "pagination": {}}}, ensure_ascii=False)
    return f"<html><script>window.stateData = {payload};\nvar other = 1;</script></html>"


def test_wants_are_extracted_from_page():
    wants = extract_wants(page([WANT]))
    assert [w["id"] for w in wants] == [3241244]


def test_page_without_orders_returns_nothing():
    assert extract_wants("<html><body>заглушка</body></html>") == []
    assert extract_wants("window.stateData = {\"other\": 1};") == []


def test_order_fields_are_filled():
    order = parse_wants(extract_wants(page([WANT])), "kwork")[0]
    assert order.title == "Нужен телеграм-бот для записи клиентов"
    assert order.url == "https://kwork.ru/projects/3241244"
    assert order.external_id == "3241244"
    assert order.budget == "от 500 до 1 500 ₽"
    assert order.extra == {"Срок": "до 10 дн.", "Предложений": "2", "Опубликован": "24 августа"}


@pytest.mark.parametrize(
    "prices, expected",
    [
        (("500.00", 1500), "от 500 до 1 500 ₽"),
        (("2000.00", 2000), "от 2 000 ₽"),
        ((None, 3000), "от 3 000 ₽"),
        ((None, None), None),
        (("0.00", 0), None),
    ],
)
def test_budget_variants(prices, expected):
    want = dict(WANT, priceLimit=prices[0], possiblePriceLimit=prices[1])
    assert parse_wants([want], "kwork")[0].budget == expected


def test_broken_entries_are_skipped():
    orders = parse_wants([{"id": 1}, {"name": "без id"}, WANT], "kwork")
    assert [o.external_id for o in orders] == ["3241244"]


def test_kwork_order_passes_the_filter():
    order = parse_wants([WANT], "kwork")[0]
    assert Matcher().match(order).is_relevant(5)


class FakeResponse:
    def __init__(self, status: int, body: str, url: str = "https://kwork.ru/projects?c=41") -> None:
        self.status = status
        self.reason = "err"
        self._body = body
        self.request_info = SimpleNamespace(real_url=url)
        self.history = ()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def read(self) -> bytes:
        return self._body.encode()

    def raise_for_status(self) -> None:
        if self.status >= 400:
            raise aiohttp.ClientResponseError(
                self.request_info, self.history, status=self.status, message=self.reason
            )


class FakeSession:
    def __init__(self, by_url: dict[str, FakeResponse]) -> None:
        self.by_url = by_url
        self.urls: list[str] = []

    def get(self, url: str, **kwargs) -> FakeResponse:
        self.urls.append(url)
        return self.by_url.get(url, FakeResponse(500, ""))


WANT_2 = dict(WANT, id=9999999, name="Лендинг для запуска продукта")


def make_source() -> KworkSource:
    return KworkSource(SourceConfig(name="kwork", url="https://kwork.ru/projects?c=41", kind="kwork"))


async def test_second_page_orders_are_merged_in():
    session = FakeSession(
        {
            "https://kwork.ru/projects?c=41": FakeResponse(200, page([WANT])),
            "https://kwork.ru/projects?c=41&page=2": FakeResponse(200, page([WANT_2])),
        }
    )
    orders = await make_source().fetch(session)
    assert {o.external_id for o in orders} == {"3241244", "9999999"}


async def test_missing_second_page_does_not_break_the_first():
    session = FakeSession({"https://kwork.ru/projects?c=41": FakeResponse(200, page([WANT]))})
    orders = await make_source().fetch(session)
    assert [o.external_id for o in orders] == ["3241244"]


async def test_duplicate_ids_on_second_page_are_not_added_twice():
    session = FakeSession(
        {
            "https://kwork.ru/projects?c=41": FakeResponse(200, page([WANT])),
            "https://kwork.ru/projects?c=41&page=2": FakeResponse(200, page([WANT])),
        }
    )
    orders = await make_source().fetch(session)
    assert [o.external_id for o in orders] == ["3241244"]
