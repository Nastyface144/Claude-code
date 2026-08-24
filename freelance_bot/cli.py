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


async def probe(urls: list[str]) -> None:
    """Проверить ленты-кандидаты: отвечает ли адрес и сколько в нём заказов."""
    import aiohttp

    from .sources.rss import USER_AGENT, parse_feed

    timeout = aiohttp.ClientTimeout(total=25)
    headers = {"User-Agent": USER_AGENT, "Accept": "application/rss+xml, application/xml, */*"}
    async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
        for url in urls:
            try:
                async with session.get(url) as response:
                    status = response.status
                    raw = await response.read()
            except Exception as exc:  # noqa: BLE001
                print(f"❌ {url}\n      {type(exc).__name__}: {exc}")
                continue
            orders = parse_feed(raw, "probe") if status == 200 else []
            mark = "✅" if orders else ("⚠️ " if status == 200 else "❌")
            print(f"{mark} {status} · заказов: {len(orders):<4} {url}")
            if orders:
                print(f"      пример: {orders[0].title[:80]}")


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

    border = sorted(
        (
            (match, order)
            for match, order in scored
            if not match.blocked and 0 < match.score < settings.min_score
        ),
        key=lambda pair: pair[0].score,
        reverse=True,
    )
    print(f"— Пограничные (балл 1..{settings.min_score - 1}): {len(border)}, показываю 10 —")
    for match, order in border[:10]:
        print(f"[{match.score:>3}] {order.title[:90]}")
        print(f"      {match.explain()[:100]}")

    await storage.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="freelance_bot",
        description="Радар фриланс-заказов: Telegram-боты, mini apps, лендинги.",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="подробные логи")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("run", help="запустить Telegram-бота (по умолчанию)")
    sub.add_parser("once", help="один цикл для cron/GitHub Actions: опросить и разослать")
    sub.add_parser("dryrun", help="опросить биржи и вывести находки в консоль")
    filter_cmd = sub.add_parser("filter", help="проверить оценку произвольного текста")
    filter_cmd.add_argument("text", nargs="+", help="текст заказа")
    probe_cmd = sub.add_parser("probe", help="проверить ленты-кандидаты по адресам")
    probe_cmd.add_argument("urls", nargs="+", help="адреса RSS-лент")

    args = parser.parse_args(argv)
    _setup_logging(args.verbose)

    try:
        if args.command == "probe":
            asyncio.run(probe(args.urls))
        elif args.command == "filter":
            check_filter(" ".join(args.text))
        elif args.command == "once":
            from .app import run_once

            report = asyncio.run(run_once())
            print(report.as_text())
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
