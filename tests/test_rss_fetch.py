"""Загрузка ленты: повторы при «плавающем» 403 и запасные адреса."""

from types import SimpleNamespace

import aiohttp
import pytest

from freelance_bot.sources.base import SourceConfig
from freelance_bot.sources.rss import RssSource

FEED_OK = """<?xml version="1.0"?><rss version="2.0"><channel>
<item><title>Нужен телеграм-бот</title><link>https://x/1</link></item>
</channel></rss>
"""


class FakeResponse:
    def __init__(self, status: int, body: str, url: str = "https://www.fl.ru/rss/all.xml") -> None:
        self.status = status
        self.reason = "Forbidden" if status == 403 else "OK"
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
    """Отдаёт заранее заданные ответы по очереди и запоминает запрошенные адреса."""

    def __init__(self, responses: list[FakeResponse]) -> None:
        self.responses = responses
        self.urls: list[str] = []

    def get(self, url: str, **kwargs) -> FakeResponse:
        self.urls.append(url)
        return self.responses.pop(0) if self.responses else FakeResponse(500, "")


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    async def instant(_seconds):
        return None

    monkeypatch.setattr("freelance_bot.sources.rss.asyncio.sleep", instant)


def make_source(**kwargs) -> RssSource:
    source = RssSource(SourceConfig(name="fl", url="https://www.fl.ru/rss/all.xml"))
    for key, value in kwargs.items():
        setattr(source, key, value)
    return source


async def test_retries_after_flaky_403():
    session = FakeSession([FakeResponse(403, ""), FakeResponse(200, FEED_OK)])
    orders = await make_source(use_mirrors=False).fetch(session)
    assert [o.title for o in orders] == ["Нужен телеграм-бот"]
    assert len(session.urls) == 2  # вторая попытка по тому же адресу


async def test_gives_up_after_all_attempts_and_reports_error():
    session = FakeSession([FakeResponse(403, "") for _ in range(3)])
    with pytest.raises(aiohttp.ClientResponseError):
        await make_source(use_mirrors=False).fetch(session)
    assert len(session.urls) == 3


async def test_mirror_is_used_only_when_enabled():
    session = FakeSession([FakeResponse(403, ""), FakeResponse(403, ""), FakeResponse(403, ""), FakeResponse(200, FEED_OK)])
    orders = await make_source(use_mirrors=True).fetch(session)
    assert orders
    assert "allorigins" in session.urls[-1]


async def test_error_from_source_is_wrapped_by_safe_fetch():
    session = FakeSession([FakeResponse(500, "") for _ in range(3)])
    result = await make_source(use_mirrors=False).safe_fetch(session)
    assert not result.ok and "500" in (result.error or "")
