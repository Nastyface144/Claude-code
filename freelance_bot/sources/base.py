"""Базовые сущности источников заказов."""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

import aiohttp

from ..models import Order

# Биржи закрываются от «не-браузеров», поэтому ходим как обычный браузер.
BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/127.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/rss+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
}

# Ответы, которые обычно означают «нас приняли за робота» — стоит повторить.
BLOCKED_STATUSES = frozenset({401, 403, 429, 451, 500, 502, 503, 520, 521, 522})


async def fetch_bytes(
    session: aiohttp.ClientSession,
    url: str,
    *,
    attempts: int = 3,
    pause: float = 3.0,
) -> bytes:
    """Скачать адрес, повторяя при «плавающих» отказах бирж."""
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            async with session.get(url, headers=BROWSER_HEADERS) as response:
                if response.status in BLOCKED_STATUSES:
                    raise aiohttp.ClientResponseError(
                        response.request_info,
                        response.history,
                        status=response.status,
                        message=response.reason or "",
                    )
                response.raise_for_status()
                return await response.read()
        except Exception as exc:  # noqa: BLE001 - повторяем и пробрасываем последнюю
            last_error = exc
            if attempt + 1 < attempts:
                await asyncio.sleep(pause * (attempt + 1))
    raise last_error if last_error else RuntimeError(f"не удалось скачать {url}")


@dataclass(frozen=True, slots=True)
class SourceConfig:
    """Описание источника: имя (уникальное), адрес ленты, тип."""

    name: str
    url: str
    kind: str = "rss"
    title: str = ""

    @property
    def label(self) -> str:
        return self.title or self.name


@dataclass(slots=True)
class SourceResult:
    source: str
    orders: list[Order] = field(default_factory=list)
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


class Source(ABC):
    """Источник заказов. Наследники обязаны вернуть список Order."""

    def __init__(self, config: SourceConfig) -> None:
        self.config = config

    @property
    def name(self) -> str:
        return self.config.name

    @abstractmethod
    async def fetch(self, session: aiohttp.ClientSession) -> list[Order]:
        ...

    async def safe_fetch(self, session: aiohttp.ClientSession) -> SourceResult:
        """Ошибка одного источника не должна ронять весь опрос."""
        try:
            orders = await self.fetch(session)
        except Exception as exc:  # noqa: BLE001 - показываем текст ошибки пользователю
            return SourceResult(source=self.name, error=f"{type(exc).__name__}: {exc}"[:300])
        return SourceResult(source=self.name, orders=orders)
