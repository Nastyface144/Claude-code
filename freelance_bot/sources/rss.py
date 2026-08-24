"""Источник на базе RSS/Atom-ленты (так отдают заказы почти все биржи)."""

from __future__ import annotations

import logging
import os
import re
from datetime import datetime, timezone
from html import unescape
from urllib.parse import quote

import aiohttp
import feedparser

from ..models import Order
from .base import BROWSER_HEADERS, Source, fetch_bytes

log = logging.getLogger(__name__)

USER_AGENT = BROWSER_HEADERS["User-Agent"]

# Публичные read-прокси на запасной случай. Проверка 24.08.2026 показала, что для FL.ru
# они бесполезны (allorigins 408, r.jina.ai 403, codetabs 522), поэтому по умолчанию
# выключены — включаются переменной RSS_MIRRORS=1.
MIRROR_TEMPLATES: tuple[str, ...] = (
    "https://api.allorigins.win/raw?url={quoted}",
    "https://api.codetabs.com/v1/proxy?quest={quoted}",
)




# FL.ru и другие биржи пишут бюджет прямо в заголовок: «Сделать лендинг (Бюджет: 30 000 ₽)»
_TITLE_BUDGET_RE = re.compile(r"\s*\(\s*(?:бюджет|budget)\s*:\s*([^)]+?)\s*\)\s*$", re.IGNORECASE)


def split_budget(title: str) -> tuple[str, str | None]:
    """Отделить бюджет от заголовка. Возвращает (заголовок, бюджет|None)."""
    title = unescape(title or "").strip()
    match = _TITLE_BUDGET_RE.search(title)
    if not match:
        return title, None
    budget = " ".join(match.group(1).split())
    return title[: match.start()].strip(" .-—·"), budget or None


def _category(entry) -> str | None:
    """Раздел биржи, например «Веб-программирование / Сайт под ключ»."""
    for tag in entry.get("tags", []) or []:
        term = (tag.get("term") or "").strip()
        if term:
            return unescape(term)
    return None


def _published(entry) -> datetime | None:
    for key in ("published_parsed", "updated_parsed", "created_parsed"):
        parsed = entry.get(key)
        if parsed:
            return datetime(*parsed[:6], tzinfo=timezone.utc)
    return None


def _description(entry) -> str:
    parts: list[str] = []
    for key in ("summary", "description", "subtitle"):
        value = entry.get(key)
        if value:
            parts.append(str(value))
    for content in entry.get("content", []) or []:
        value = content.get("value")
        if value:
            parts.append(str(value))
    # Не тащим бесконечные полотна: для оценки хватает первых символов.
    return "\n".join(dict.fromkeys(parts))[:5000]


def parse_feed(raw: bytes | str, source_name: str) -> list[Order]:
    """Разбор ленты в список заказов (вынесено отдельно ради тестов)."""
    feed = feedparser.parse(raw)
    orders: list[Order] = []
    for entry in feed.entries:
        link = (entry.get("link") or "").strip()
        raw_title = (entry.get("title") or "").strip()
        if not link and not raw_title:
            continue
        title, budget = split_budget(raw_title)
        orders.append(
            Order(
                source=source_name,
                external_id=(entry.get("id") or link or raw_title).strip(),
                title=title or link,
                url=link,
                description=_description(entry),
                budget=budget,
                category=_category(entry),
                published_at=_published(entry),
            )
        )
    return orders


class RssSource(Source):
    """RSS-лента с повторами и обходными путями: биржи часто отвечают 403 через раз."""

    # FL.ru отвечает 403 «через раз», но следующая попытка обычно проходит.
    attempts = 3
    retry_pause = 3.0
    use_mirrors = os.getenv("RSS_MIRRORS", "").strip() in {"1", "true", "yes"}

    def _urls(self) -> list[str]:
        urls = [self.config.url]
        if self.use_mirrors:
            quoted = quote(self.config.url, safe="")
            urls += [tpl.format(quoted=quoted, url=self.config.url) for tpl in MIRROR_TEMPLATES]
        return urls

    async def fetch(self, session: aiohttp.ClientSession) -> list[Order]:
        last_error: Exception | None = None
        for index, url in enumerate(self._urls()):
            try:
                raw = await fetch_bytes(session, url, attempts=self.attempts, pause=self.retry_pause)
                orders = parse_feed(raw, self.name)
            except Exception as exc:  # noqa: BLE001 - пробуем следующий адрес
                last_error = exc
                log.debug("%s: %s (%s)", self.name, exc, url)
                continue
            if orders:
                if index:
                    log.info("%s: лента получена через обходной адрес", self.name)
                return orders
            last_error = last_error or RuntimeError("лента пустая")
        if last_error:
            raise last_error
        return []
