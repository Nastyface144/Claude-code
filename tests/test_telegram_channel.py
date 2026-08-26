"""Публичный превью Telegram-канала (t.me/s/<канал>) с подборками заказов."""

from freelance_bot.matcher import Matcher
from freelance_bot.sources.telegram_channel import parse_channel

SAMPLE = """
<div class="tgme_widget_message text_not_supported_wrap js-widget_message" data-post="freelansim_ru/5606">
  <div class="tgme_widget_message_text js-message_text" dir="auto">Подборка заказов в категории Разработка (Боты и парсинг данных): 1. Разработать веб апп дизайн для телеграм бота (10 000 руб. за проект) <a href="https://u.habr.com/OVsYg">https://u.habr.com/OVsYg</a> 2. Разработать автоматизацию написания писем через n8n (5 000 руб. за проект) <a href="https://u.habr.com/NxZWE">https://u.habr.com/NxZWE</a></div>
  <div class="tgme_widget_message_info short js-message_info"><span class="tgme_widget_message_meta"><a class="tgme_widget_message_date" href="https://t.me/freelansim_ru/5606"><time datetime="2026-08-25T09:00:32+00:00" class="time">09:00</time></a></span></div>
</div>
<div class="tgme_widget_message text_not_supported_wrap js-widget_message" data-post="freelansim_ru/5607">
  <div class="tgme_widget_message_text js-message_text" dir="auto">Подборка заказов по тегу #python : 1. Настроить телеграм бота для робокассы (5 000 руб. за проект) <a href="https://u.habr.com/UOl0b">https://u.habr.com/UOl0b</a></div>
  <div class="tgme_widget_message_info short js-message_info"><span class="tgme_widget_message_meta"><a class="tgme_widget_message_date" href="https://t.me/freelansim_ru/5607"><time datetime="2026-08-25T10:00:00+00:00" class="time">10:00</time></a></span></div>
</div>
<div class="tgme_widget_message text_not_supported_wrap js-widget_message" data-post="freelansim_ru/5608">
  <div class="tgme_widget_message_text js-message_text" dir="auto">Подборка проектов от проверенных заказчиков: 1. Доработка фронта такси ( клиент, водитель, админка ) на react по ТЗ (цена договорная) <a href="https://u.habr.com/h1XPw">https://u.habr.com/h1XPw</a></div>
  <div class="tgme_widget_message_info short js-message_info"><span class="tgme_widget_message_meta"><a class="tgme_widget_message_date" href="https://t.me/freelansim_ru/5608"><time datetime="2026-08-25T11:00:00+00:00" class="time">11:00</time></a></span></div>
</div>
<div class="tgme_widget_message text_not_supported_wrap js-widget_message" data-post="freelansim_ru/5609">
  <div class="tgme_widget_message_text js-message_text" dir="auto">С 1 марта меняются правила подачи заявок в чате.</div>
</div>
"""


def test_items_are_extracted_from_batched_posts():
    orders = parse_channel(SAMPLE, "habr_tg")
    assert [o.title for o in orders] == [
        "Разработать веб апп дизайн для телеграм бота",
        "Разработать автоматизацию написания писем через n8n",
        "Настроить телеграм бота для робокассы",
        "Доработка фронта такси ( клиент, водитель, админка ) на react по ТЗ",
    ]


def test_budget_is_kept_and_dogovornaya_becomes_none():
    orders = parse_channel(SAMPLE, "habr_tg")
    assert orders[0].budget == "10 000 руб. за проект"
    assert orders[3].budget is None  # «цена договорная»


def test_category_strips_boilerplate_lead_in():
    orders = parse_channel(SAMPLE, "habr_tg")
    assert orders[0].category == "Разработка (Боты и парсинг данных)"
    assert orders[2].category == "#python"
    assert orders[3].category == "проверенных заказчиков"


def test_published_at_comes_from_message_time():
    orders = parse_channel(SAMPLE, "habr_tg")
    assert orders[0].published_at.isoformat() == "2026-08-25T09:00:32+00:00"
    assert orders[2].published_at.isoformat() == "2026-08-25T10:00:00+00:00"


def test_url_and_external_id_point_to_the_order_link_not_the_post():
    orders = parse_channel(SAMPLE, "habr_tg")
    assert orders[0].url == "https://u.habr.com/OVsYg"
    assert orders[0].external_id == "https://u.habr.com/OVsYg"


def test_non_batch_message_yields_nothing():
    orders = parse_channel(SAMPLE, "habr_tg")
    assert all("правила подачи заявок" not in o.title for o in orders)


def test_duplicate_links_across_runs_collapse_by_uid():
    first = parse_channel(SAMPLE, "habr_tg")
    second = parse_channel(SAMPLE, "habr_tg")
    assert {o.uid for o in first} == {o.uid for o in second}
    assert len({o.uid for o in first}) == 4


def test_telegram_bot_order_passes_the_filter():
    orders = parse_channel(SAMPLE, "habr_tg")
    bot_order = orders[0]
    assert Matcher().match(bot_order).is_relevant(5)
