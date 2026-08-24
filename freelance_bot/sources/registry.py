"""Список источников по умолчанию и сборка объектов Source."""

from __future__ import annotations

from .base import Source, SourceConfig
from .rss import RssSource

# Ленты бирж. Если какая-то биржа сменит адрес — правится прямо из бота:
# /sources — статус, /addsource <имя> <url> — добавить, /delsource <имя> — убрать.
DEFAULT_SOURCES: tuple[SourceConfig, ...] = (
    SourceConfig(name="fl", url="https://www.fl.ru/rss/all.xml", title="FL.ru"),
    SourceConfig(name="habr", url="https://freelance.habr.com/tasks.rss", title="Хабр Фриланс"),
    SourceConfig(name="weblancer", url="https://www.weblancer.net/rss/projects/", title="Weblancer"),
    SourceConfig(name="freelanceru", url="https://freelance.ru/rss/projects", title="Freelance.ru"),
)

KINDS: dict[str, type[Source]] = {"rss": RssSource}


def build_source(config: SourceConfig) -> Source:
    factory = KINDS.get(config.kind)
    if factory is None:
        raise ValueError(f"Неизвестный тип источника: {config.kind}")
    return factory(config)


def build_sources(configs: list[SourceConfig] | tuple[SourceConfig, ...]) -> list[Source]:
    return [build_source(config) for config in configs]
