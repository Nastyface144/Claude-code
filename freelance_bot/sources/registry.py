"""Список источников по умолчанию и сборка объектов Source."""

from __future__ import annotations

from .base import Source, SourceConfig
from .kwork import KworkSource
from .rss import RssSource
from .telegram_channel import TelegramChannelSource

# Ленты бирж. Список проверен запуском `probe` 24.08.2026 из сети GitHub Actions:
#   FL.ru               — работает технически (~60 заказов за запрос), но убран по
#                         решению пользователя — платная биржа, не устраивает как площадка
#   Хабр Фриланс        — 410 Gone, лента закрыта (tasks.rss, tasks/rss, tasks.atom, freelansim)
#   Freelance.ru        — 404 по всем известным адресам
#   Weblancer           — 403, режет запросы из дата-центров (с домашнего IP может работать)
#   Kwork               — RSS отдаёт услуги продавцов, зато биржа заказов доступна
#                         страницей: заказы лежат в JSON внутри HTML (kind="kwork")
#   Freelancehunt       — 403, Upwork — 403, YouDo — пустая лента, Workspace — 404
#   Upwork/Fiverr       — 403/410, закрыты для дата-центров или без открытой ленты заявок
#   Jobbers.io          — 403 Cloudflare-челлендж, репутация не проверена
#   napodrabotku.ru     — похож на SEO-каталог бытовых услуг (репетиторы, ремонт),
#                         не биржа IT-заказов — не используется
#   Хабр Фриланс (Telegram) — канал t.me/s/freelansim_ru жив и постит подборки
#                         заказов с ценами, но все ссылки на заказы (u.habr.com/...)
#                         отдают 410 с текстом «Сервис Хабр Фриланс закрылся
#                         навсегда» — сама биржа закрыта, откликаться некуда.
#                         Парсер оставлен (kind="telegram_channel", см. ниже),
#                         но НЕ включён по умолчанию: карточки были бы с мёртвыми
#                         ссылками. Пригодится через /addsource для другого
#                         канала с живой биржой за ним.
# Список правится прямо из бота: /sources — статус, /addsource <имя> <url>, /delsource <имя>.
DEFAULT_SOURCES: tuple[SourceConfig, ...] = (
    SourceConfig(
        name="kwork",
        url="https://kwork.ru/projects?c=41",
        kind="kwork",
        title="Kwork · Разработка и IT",
    ),
)

KINDS: dict[str, type[Source]] = {
    "rss": RssSource,
    "kwork": KworkSource,
    "telegram_channel": TelegramChannelSource,
}


def build_source(config: SourceConfig) -> Source:
    factory = KINDS.get(config.kind)
    if factory is None:
        raise ValueError(f"Неизвестный тип источника: {config.kind}")
    return factory(config)


def build_sources(configs: list[SourceConfig] | tuple[SourceConfig, ...]) -> list[Source]:
    return [build_source(config) for config in configs]
