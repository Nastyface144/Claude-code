"""Тесты очистки текста и ретраев."""

from __future__ import annotations

import pytest

from shorts_factory.utils.retry import RetryError, call_with_retry
from shorts_factory.utils.text import count_words, is_deleted, strip_markdown


def test_strip_markdown_removes_reddit_noise():
    raw = (
        "# Заголовок\n"
        "**жирный** и *курсив* и ~~зачёркнутый~~\n"
        "> цитата\n"
        "- пункт списка\n"
        "[текст ссылки](https://example.com/x)\n"
        "Смотри https://reddit.com/r/tifu и /u/someone\n"
        "&amp; символ\n"
        "```\nprint('code')\n```"
    )
    cleaned = strip_markdown(raw)

    assert "**" not in cleaned and "~~" not in cleaned
    assert "https://" not in cleaned
    assert "print(" not in cleaned
    assert "текст ссылки" in cleaned
    assert "& символ" in cleaned
    assert cleaned.startswith("Заголовок")


def test_count_words_ignores_markup():
    assert count_words("**one** [two](https://x.com) three") == 3
    assert count_words("") == 0
    assert count_words("don't hyphen-word 42") == 3


@pytest.mark.parametrize("text, expected", [
    ("[removed]", True), ("[deleted]", True), ("  ", True), (None, True), ("текст", False),
])
def test_is_deleted(text, expected):
    assert is_deleted(text) is expected


def test_retry_succeeds_after_transient_errors():
    calls = {"n": 0}
    delays: list[float] = []

    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise ConnectionError("timeout")
        return "ok"

    result = call_with_retry(flaky, max_attempts=4, base_delay=2.0,
                             sleep=delays.append, exceptions=[ConnectionError])

    assert result == "ok"
    assert calls["n"] == 3
    assert len(delays) == 2
    assert 2.0 <= delays[0] < 2.3 and 4.0 <= delays[1] < 4.5  # экспонента + джиттер


def test_retry_gives_up_after_max_attempts():
    delays: list[float] = []

    def always_fails():
        raise ConnectionError("сеть недоступна")

    with pytest.raises(RetryError):
        call_with_retry(always_fails, max_attempts=3, base_delay=1.0,
                        sleep=delays.append, exceptions=[ConnectionError])

    assert len(delays) == 2  # после последней попытки не ждём


def test_retry_honours_retry_after_header():
    delays: list[float] = []

    class TooMany(Exception):
        retry_after = "17"

    calls = {"n": 0}

    def rate_limited():
        calls["n"] += 1
        if calls["n"] == 1:
            raise TooMany()
        return 42

    assert call_with_retry(rate_limited, max_attempts=2, base_delay=1.0,
                           sleep=delays.append, exceptions=[TooMany]) == 42
    assert delays == [17.0]


def test_non_retryable_error_propagates_immediately():
    def forbidden():
        raise PermissionError("403")

    with pytest.raises(PermissionError):
        call_with_retry(forbidden, max_attempts=3, sleep=lambda _: None,
                        exceptions=[ConnectionError])
