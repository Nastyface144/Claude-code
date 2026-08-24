"""Список источников по умолчанию и сборка объектов Source."""

from __future__ import annotations

from .base import Source, SourceConfig
from .kwork import KworkSource
from .rss import RssSource

# Ленты бирж. Список проверен запуском `probe` 24.08.2026 из сети GitHub Actions:
#   FL.ru               — работает, ~60 свежих заказов за запрос
#   Хабр Фриланс        — 410 Gone, лента закрыта (tasks.rss, tasks/rss, tasks.atom, freelansim)
#   Freelance.ru        — 404 по всем известным адресам
#   Weblancer           — 403, режет запросы из дата-центров (с домашнего IP может работать)
#   Kwork               — RSS отдаёт услуги продавцов, зато биржа заказов доступна
#                         страницей: заказы лежат в JSON внутри HTML (kind="kwork")
#   Freelancehunt       — 403, Upwork — 403, YouDo — пустая лента, Workspace — 404
# Список правится прямо из бота: /sources — статус, /addsource <имя> <url>, /delsource <имя>.
DEFAULT_SOURCES: tuple[SourceConfig, ...] = (
    SourceConfig(name="fl", url="https://www.fl.ru/rss/all.xml", title="FL.ru"),
    SourceConfig(
        name="kwork",
        url="https://kwork.ru/projects?c=41",
        kind="kwork",
        title="Kwork · Разработка и IT",
    ),
)

KINDS: dict[str, type[Source]] = {"rss": RssSource, "kwork": KworkSource}


def build_source(config: SourceConfig) -> Source:
    factory = KINDS.get(config.kind)
    if factory is None:
        raise ValueError(f"Неизвестный тип источника: {config.kind}")
    return factory(config)


def build_sources(configs: list[SourceConfig] | tuple[SourceConfig, ...]) -> list[Source]:
    return [build_source(config) for config in configs]
