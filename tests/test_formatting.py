"""Карточка заказа, которая уходит в Telegram."""

from datetime import datetime, timedelta, timezone

from freelance_bot.formatting import order_message
from freelance_bot.matcher import Matcher
from freelance_bot.models import Order


def make_order(**kwargs) -> Order:
    data = dict(
        source="fl",
        external_id="1",
        title="Разработать телеграм-бота для записи клиентов",
        url="https://www.fl.ru/projects/1/bot.html",
        description="Нужен бот на aiogram: запись на услуги, напоминания, оплата через ЮKassa.",
        budget="30 000 ₽",
        category="Программирование / Разработка ботов",
        published_at=datetime.now(timezone.utc) - timedelta(minutes=17),
    )
    data.update(kwargs)
    return Order(**data)


def render(order: Order) -> str:
    return order_message(order, Matcher().match(order), "FL.ru")


def test_card_contains_all_key_fields():
    text = render(make_order())
    assert "<b>Разработать телеграм-бота для записи клиентов</b>" in text
    assert "💰 <b>30 000 ₽</b>" in text
    assert "🗂 Программирование / Разработка ботов" in text
    assert "оплата через ЮKassa" in text
    assert "🏷 подходит по: telegram-бот" in text
    assert "📰 FL.ru" in text
    assert "🕒 17 мин назад" in text
    assert '<a href="https://www.fl.ru/projects/1/bot.html">' in text


def test_missing_budget_is_stated_explicitly():
    text = render(make_order(budget=None, description="Нужен телеграм бот"))
    assert "💰 бюджет не указан" in text


def test_missing_category_is_skipped():
    assert "🗂" not in render(make_order(category=None))


def test_long_description_is_cut_on_word_boundary():
    text = render(make_order(description="телеграм бот " + "слово " * 400))
    assert "…" in text
    assert len(text) < 1200


def test_html_in_source_is_escaped_and_stripped():
    order = make_order(
        title="Бот <script>alert(1)</script> & лендинг",
        description="<p>Текст <b>жирный</b> &amp; ссылка</p>",
    )
    text = render(order)
    # теги биржи вырезаются, а спецсимволы экранируются — Telegram не сломается
    assert "<script>" not in text and "alert(1)" in text
    assert "&amp; лендинг" in text
    assert "Текст жирный &amp; ссылка" in text
