"""Команды запуска: сам бот и офлайн-проверка фильтра без Telegram."""

from __future__ import annotations

import argparse
import asyncio
import logging

from .config import Settings
from .matcher import Matcher
from .service import Radar
from .sources import DEFAULT_SOURCES
from .storage import Storage

log = logging.getLogger(__name__)


def _setup_logging(verbose: bool = False) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    )


def check_filter(text: str) -> None:
    """Показать, как фильтр оценивает произвольный текст заказа."""
    result = Matcher().match_text(text)
    print(f"Балл: {result.score}")
    print(f"Теги: {', '.join(result.tags) if result.tags else '—'}")
    print(f"Почему: {result.explain()}")


async def dry_run(limit: int = 15) -> None:
    """Опросить биржи и напечатать находки в консоль (Telegram не нужен)."""
    settings = Settings.from_env(require_token=False)
    storage = await Storage(settings.db_path).connect()
    await storage.seed_sources(DEFAULT_SOURCES)
    radar = Radar(settings, storage, bot=None)  # type: ignore[arg-type]

    orders, errors, titles = await radar.collect()
    print(f"Собрано объявлений: {len(orders)}")
    for name, error in errors:
        print(f"  ⚠️  {name}: {error}")

    scored = [(radar.base_matcher.match(order), order) for order in orders]
    relevant = sorted(
        ((match, order) for match, order in scored if match.is_relevant(settings.min_score)),
        key=lambda pair: pair[0].score,
        reverse=True,
    )
    print(f"Подходящих (балл >= {settings.min_score}): {len(relevant)}\n")
    for match, order in relevant[:limit]:
        print(f"[{match.score:>3}] {order.title}")
        print(f"      {titles.get(order.source, order.source)} · {order.url}")
        print(f"      {match.explain()}\n")

    await storage.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="freelance_bot",
        description="Радар фриланс-заказов: Telegram-боты, mini apps, лендинги.",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="подробные логи")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("run", help="запустить Telegram-бота (по умолчанию)")
    sub.add_parser("dryrun", help="опросить биржи и вывести находки в консоль")
    filter_cmd = sub.add_parser("filter", help="проверить оценку произвольного текста")
    filter_cmd.add_argument("text", nargs="+", help="текст заказа")

    args = parser.parse_args(argv)
    _setup_logging(args.verbose)

    try:
        if args.command == "filter":
            check_filter(" ".join(args.text))
        elif args.command == "dryrun":
            asyncio.run(dry_run())
        else:
            from .app import run

            asyncio.run(run())
    except KeyboardInterrupt:
        log.info("Остановлено пользователем")
    except RuntimeError as exc:
        parser.exit(2, f"Ошибка: {exc}\n")
    return 0
