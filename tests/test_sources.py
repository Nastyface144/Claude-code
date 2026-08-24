from datetime import timezone

from freelance_bot.sources.rss import parse_feed

SAMPLE = """<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0">
  <channel>
    <title>Тестовая биржа</title>
    <item>
      <title>Нужен телеграм-бот для записи</title>
      <link>https://example.com/projects/1</link>
      <guid>https://example.com/projects/1</guid>
      <description><![CDATA[<p>Бот на python, бюджет 30 000 руб.</p>]]></description>
      <pubDate>Mon, 24 Aug 2026 10:00:00 +0000</pubDate>
    </item>
    <item>
      <title>Лендинг под ключ</title>
      <link>https://example.com/projects/2</link>
      <description>Одностраничный сайт</description>
    </item>
  </channel>
</rss>
"""


def test_parse_feed_reads_entries():
    orders = parse_feed(SAMPLE, "test")
    assert [o.title for o in orders] == ["Нужен телеграм-бот для записи", "Лендинг под ключ"]

    first = orders[0]
    assert first.url == "https://example.com/projects/1"
    assert first.source == "test"
    assert first.published_at is not None
    assert first.published_at.tzinfo is timezone.utc
    assert "python" in first.description


def test_budget_is_extracted_from_description():
    orders = parse_feed(SAMPLE, "test")
    assert orders[0].guess_budget() == "30 000 руб"
    assert orders[1].guess_budget() is None


def test_uid_is_stable_and_unique():
    first_run = parse_feed(SAMPLE, "test")
    second_run = parse_feed(SAMPLE, "test")
    assert first_run[0].uid == second_run[0].uid
    assert first_run[0].uid != first_run[1].uid
    assert parse_feed(SAMPLE, "other")[0].uid != first_run[0].uid


def test_broken_feed_does_not_raise():
    assert parse_feed("не xml вовсе", "test") == []
