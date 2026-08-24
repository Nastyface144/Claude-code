"""Разбор биржи заказов Kwork (данные лежат в JSON внутри страницы)."""

import json

import pytest

from freelance_bot.matcher import Matcher
from freelance_bot.sources.kwork import extract_wants, parse_wants

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
