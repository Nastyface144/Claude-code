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
            ctype = response.headers.get("Content-Type", "?").split(";")[0]
            print(f"{mark} {status} · заказов: {len(orders):<4} · {ctype} · {len(raw)} б · {url}")
            if orders:
                print(f"      пример: {orders[0].title[:80]}")
            else:
                # не лента — покажем начало ответа, чтобы понять, что вернул сайт
                head = " ".join(raw[:1200].decode("utf-8", "replace").split())
                print(f"      ответ: {head[:300]}")


async def sample(url: str, count: int = 3) -> None:
    """Показать сырые поля ленты — чтобы понять, что биржа отдаёт по каждому заказу."""
    import aiohttp
    import feedparser

    from .sources.rss import USER_AGENT

    headers = {"User-Agent": USER_AGENT}
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=25), headers=headers) as session:
        async with session.get(url) as response:
            raw = await response.read()

    feed = feedparser.parse(raw)
    if not feed.entries:
        _inspect_html(raw)
        return

    for entry in feed.entries[:count]:
        print("=" * 70)
        for key, value in entry.items():
            text = str(value).replace("\n", " ")
            print(f"  {key}: {text[:400]}")


def _inspect_html(raw: bytes) -> None:
    """Не лента, а страница: ищем встроенный JSON с данными (Vue/Nuxt/React)."""
    import json
    import re

    text = raw.decode("utf-8", "replace")
    print(f"HTML, {len(text)} символов. Ищу встроенные данные…")

    markers = ("window.stateData", "__NUXT__", "__INITIAL_STATE__", "application/ld+json", "wantsListData")
    for marker in markers:
        position = text.find(marker)
        print(f"  {marker}: {'найден на позиции ' + str(position) if position >= 0 else 'нет'}")

    match = re.search(r"window\.stateData\s*=\s*(\{.*?\});?\s*</script>", text, re.DOTALL)
    if not match:
        match = re.search(r"window\.stateData\s*=\s*(\{.*?\})\s*;\s*\n", text, re.DOTALL)
    if not match:
        print("  stateData не разобран, показываю фрагмент вокруг слова «wants»:")
        spot = text.find("wants")
        if spot > 0:
            print("  " + " ".join(text[spot - 200 : spot + 800].split())[:900])
        return

    payload = match.group(1)
    print(f"  stateData: {len(payload)} символов")
    try:
        data = json.loads(payload)
    except json.JSONDecodeError as exc:
        print(f"  JSON не разобран: {exc}")
        print("  " + " ".join(payload[:600].split()))
        return

    print(f"  ключи: {list(data)[:25]}")
    for key, value in data.items():
        if isinstance(value, list) and value and isinstance(value[0], dict):
            print(f"  список «{key}»: {len(value)} элементов, поля: {list(value[0])[:20]}")
            print("  первый: " + " ".join(json.dumps(value[0], ensure_ascii=False)[:600].split()))
            break


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
    sample_cmd = sub.add_parser("sample", help="показать сырые поля первых записей ленты")
    sample_cmd.add_argument("url", help="адрес RSS-ленты")

    args = parser.parse_args(argv)
    _setup_logging(args.verbose)

    try:
        if args.command == "sample":
            asyncio.run(sample(args.url))
        elif args.command == "probe":
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
