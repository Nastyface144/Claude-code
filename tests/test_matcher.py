import pytest

from freelance_bot.matcher import Matcher, normalize
from freelance_bot.models import Order

MIN_SCORE = 5


def order(title: str, description: str = "") -> Order:
    return Order(source="test", external_id=title, title=title, url="https://x/1", description=description)


@pytest.fixture()
def matcher() -> Matcher:
    return Matcher()


def test_normalize_collapses_punctuation_and_yo():
    assert normalize("Тёплый  Telegram-бот!!!") == " теплый telegram бот "


@pytest.mark.parametrize(
    "title, description",
    [
        ("Нужен телеграм бот для записи клиентов", "Бот с админкой"),
        ("Разработка Telegram-бота", ""),
        ("Требуется разработчик aiogram", "Доработать существующего бота"),
        ("Telegram Mini App для магазина", "TWA с оплатой"),
        ("Сделать лендинг для онлайн-курса", "Одностраничный сайт, адаптив"),
        ("Landing page + бот", "Нужен лендинг и чат-бот в тг"),
        ("Нужен тг-бот", "Простой бот-визитка"),
    ],
)
def test_relevant_orders(matcher, title, description):
    result = matcher.match(order(title, description))
    assert result.is_relevant(MIN_SCORE), result.explain()


@pytest.mark.parametrize(
    "title, description",
    [
        ("Бот для Discord", "Модерация сервера дискорд"),
        ("Нужен сайт на WordPress", "Правки в теме"),
        ("Ищем менеджера по продажам", "Офис Москва, график 5/2"),
        ("Мобильное приложение на Flutter", "iOS и Android"),
        ("Написать статью про фриланс", "3000 знаков"),
    ],
)
def test_irrelevant_orders(matcher, title, description):
    result = matcher.match(order(title, description))
    assert not result.is_relevant(MIN_SCORE), result.explain()


def test_stop_words_block_order(matcher):
    result = matcher.match(order("Телеграм бот для накрутки подписчиков", "накрутка дешево"))
    assert result.blocked
    assert result.score == 0
    assert "накрутка" in result.explain()


def test_title_hit_adds_bonus(matcher):
    in_title = matcher.match(order("Нужен телеграм-бот", "детали в личке"))
    in_body = matcher.match(order("Нужен исполнитель", "детали: нужен телеграм-бот"))
    assert in_title.score > in_body.score


def test_user_include_word_lifts_score(matcher):
    personal = matcher.with_user_rules(include=[("уведомлени*", 6)])
    task = order("Скрипт уведомлений", "рассылка уведомлений клиентам")
    assert not matcher.match(task).is_relevant(MIN_SCORE)
    assert personal.match(task).is_relevant(MIN_SCORE)


def test_user_exclude_word_blocks_order(matcher):
    personal = matcher.with_user_rules(exclude=["криптобирж*"])
    task = order("Телеграм бот для криптобиржи", "торговый бот")
    assert matcher.match(task).is_relevant(MIN_SCORE)
    blocked = personal.match(task)
    assert blocked.blocked and not blocked.is_relevant(MIN_SCORE)


def test_base_matcher_not_mutated_by_user_rules(matcher):
    before = len(matcher.include)
    matcher.with_user_rules(include=[("что-то", 5)], exclude=["и-ещё"])
    assert len(matcher.include) == before
