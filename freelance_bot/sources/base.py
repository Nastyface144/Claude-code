"""Базовые сущности источников заказов."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

import aiohttp

from ..models import Order


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
