"""Публичные Telegram-каналы с подборками заказов.

Читаются как обычная веб-страница через t.me/s/<канал> — так Telegram отдаёт
HTML-превью канала без токена и авторизации. Формат постов конкретный
(канал «Хабр Фриланс» шлёт подборки вида «Подборка заказов ...: 1. Заголовок
(цена) ссылка 2. ...»), поэтому разбор регулярками, а не общий парсер.
"""

from __future__ import annotations

import re
from datetime import datetime
from html import unescape

import aiohttp

from ..models import Order
from .base import Source, fetch_bytes

_MESSAGE_RE = re.compile(r'<div class="tgme_widget_message[^"]*"[^>]*\sdata-post="([^"]+)"')
_TEXT_RE = re.compile(r'class="tgme_widget_message_text[^"]*"[^>]*>(.*?)</div>', re.S)
_TIME_RE = re.compile(r'<time datetime="([^"]+)"')
_HEADER_RE = re.compile(r"^(.*?):\s*\d+\.")
_HEADER_PREFIX_RE = re.compile(
    r"^Подборка\s+(?:заказов|проектов)\s*(?:в\s+категории|по\s+тегу|от)?\s*",
    re.I,
)
_ITEM_RE = re.compile(
    r"(\d+)\.\s*(.+?)\s*\((\d[\d\s]*\s*руб\.[^)]*|цена договорная)\)\s*(https?://\S+)", re.S
)


def _strip_tags(html: str) -> str:
    return " ".join(unescape(re.sub(r"<[^>]+>", " ", html)).split())


def parse_channel(html: str, source_name: str) -> list[Order]:
    """Разобрать HTML-превью канала на отдельные заказы из «подборок»."""
    positions = [m.start() for m in _MESSAGE_RE.finditer(html)]
    posts = [m.group(1) for m in _MESSAGE_RE.finditer(html)]
    positions.append(len(html))

    orders: list[Order] = []
    for _post_id, start, end in zip(posts, positions, positions[1:]):
        block = html[start:end]

        text_match = _TEXT_RE.search(block)
        if not text_match:
            continue
        message = _strip_tags(text_match.group(1))

        header_match = _HEADER_RE.match(message)
        category = None
        if header_match:
            category = _HEADER_PREFIX_RE.sub("", header_match.group(1).strip(" :")).strip()

        published_at = None
        time_match = _TIME_RE.search(block)
        if time_match:
            try:
                published_at = datetime.fromisoformat(time_match.group(1))
            except ValueError:
                published_at = None

        for _num, title, price, url in _ITEM_RE.findall(message):
            title = title.strip(" -–—:")
            if not title:
                continue
            orders.append(
                Order(
                    source=source_name,
                    external_id=url,
                    title=title,
                    url=url,
                    budget=None if price == "цена договорная" else " ".join(price.split()),
                    category=category,
                    published_at=published_at,
                )
            )
    return orders


class TelegramChannelSource(Source):
    """Публичный канал вида t.me/s/<имя> с подборками заказов."""

    attempts = 3
    retry_pause = 3.0

    async def fetch(self, session: aiohttp.ClientSession) -> list[Order]:
        raw = await fetch_bytes(
            session, self.config.url, attempts=self.attempts, pause=self.retry_pause
        )
        html = raw.decode("utf-8", "replace")
        orders = parse_channel(html, self.name)
        if not orders:
            raise RuntimeError(
                "в канале не нашлось подборок заказов (изменился формат постов?)"
            )
        return orders
