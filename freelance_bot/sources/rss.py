"""Источник на базе RSS/Atom-ленты (так отдают заказы почти все биржи)."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from html import unescape

import aiohttp
import feedparser

from ..models import Order
from .base import Source

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0 Safari/537.36 FreelanceRadar/1.0"
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
    async def fetch(self, session: aiohttp.ClientSession) -> list[Order]:
        headers = {"User-Agent": USER_AGENT, "Accept": "application/rss+xml, application/xml, text/xml, */*"}
        async with session.get(self.config.url, headers=headers) as response:
            response.raise_for_status()
            raw = await response.read()
        return parse_feed(raw, self.name)
