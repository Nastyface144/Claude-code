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


def _extract_json_var(text: str, name: str):
    """Достать значение JS-переменной вида `window.name = {...};` из HTML страницы."""
    import json
    import re

    # переменная (`window.x = {...}`) или ключ внутри JSON (`"x": {...}`)
    pattern = rf'(?:{re.escape(name)}\s*=\s*|"{re.escape(name.split(".")[-1])}"\s*:\s*)'
    match = re.search(pattern, text)
    if not match:
        return None
    try:
        value, _end = json.JSONDecoder().raw_decode(text, match.end())
    except ValueError:
        return None
    return value


def _find_lists(node, path: str = "", depth: int = 0) -> list[tuple[str, list]]:
    """Все вложенные списки словарей — среди них и лежит перечень заказов."""
    found: list[tuple[str, list]] = []
    if depth > 4:
        return found
    if isinstance(node, dict):
        for key, value in node.items():
            found += _find_lists(value, f"{path}.{key}" if path else str(key), depth + 1)
    elif isinstance(node, list):
        if node and isinstance(node[0], dict) and len(node) >= 3:
            found.append((path or "root", node))
        elif node and isinstance(node[0], (dict, list)):
            found += _find_lists(node[0], f"{path}[0]", depth + 1)
    return found


def _visible_text(html: str, limit: int = 4000) -> str:
    """Грубая читалка: вырезать script/style/теги, оставить видимый текст."""
    import re

    html = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.I | re.S)
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"&nbsp;", " ", text)
    from html import unescape

    text = unescape(text)
    return " ".join(text.split())[:limit]


def _telegram_messages(html: str, limit: int = 8) -> list[str]:
    """Тексты постов из публичного превью канала (t.me/s/<channel>)."""
    import re
    from html import unescape

    blocks = re.findall(
        r'class="tgme_widget_message_text[^"]*"[^>]*>(.*?)</div>', html, re.S
    )
    messages = []
    for block in blocks[-limit:]:
        clean = unescape(re.sub(r"<[^>]+>", " ", block))
        clean = " ".join(clean.split())
        if clean:
            messages.append(clean)
    return messages


def _inspect_html(raw: bytes) -> None:
    """Не лента, а страница: ищем встроенный JSON с данными (Vue/Nuxt/React)."""
    import json

    text = raw.decode("utf-8", "replace")
    print(f"HTML, {len(text)} символов. Ищу встроенные данные…")

    found_json = False
    for name in ("window.stateData", "wantsListData", "window.__NUXT__", "window.__INITIAL_STATE__"):
        value = _extract_json_var(text, name)
        if value is None:
            print(f"  {name}: нет")
            continue
        found_json = True
        print(f"  {name}: {type(value).__name__}")
        for path, items in _find_lists(value):
            print(f"    «{path}»: {len(items)} шт., поля: {list(items[0])[:25]}")
        best = max((pair for pair in _find_lists(value)), key=lambda pair: len(pair[1]), default=None)
        if best:
            print(f"    пример из «{best[0]}»: "
                  + " ".join(json.dumps(best[1][0], ensure_ascii=False)[:1200].split()))

    messages = _telegram_messages(text)
    if messages:
        print(f"  посты канала (последние {len(messages)}):")
        for msg in messages:
            print(f"    • {msg[:300]}")

    if not found_json and not messages:
        print("  видимый текст страницы (первые символы, для ручной проверки разметки):")
        print("  " + _visible_text(text))


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
