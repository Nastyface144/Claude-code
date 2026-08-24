"""Биржа заказов Kwork.

RSS у заказов нет: страница отдаёт готовый JSON во встроенном `wantsListData`,
откуда и берём проекты (на Kwork они называются «wants»).
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

import aiohttp

from ..models import Order
from .base import Source, fetch_bytes

log = logging.getLogger(__name__)

PROJECT_URL = "https://kwork.ru/projects/{id}"
_VAR_RE = re.compile(r'(?:window\.stateData\s*=\s*|"wantsListData"\s*:\s*)')


def _find_wants(node: Any, depth: int = 0) -> list[dict]:
    """Найти список заказов в разобранном JSON страницы."""
    if depth > 5:
        return []
    if isinstance(node, dict):
        wants = node.get("wants")
        if isinstance(wants, list) and wants and isinstance(wants[0], dict):
            return wants
        for value in node.values():
            found = _find_wants(value, depth + 1)
            if found:
                return found
    elif isinstance(node, list):
        for item in node[:5]:
            found = _find_wants(item, depth + 1)
            if found:
                return found
    return []


def extract_wants(html: str) -> list[dict]:
    """Достать заказы из встроенного в страницу JSON."""
    decoder = json.JSONDecoder()
    for match in _VAR_RE.finditer(html):
        try:
            payload, _end = decoder.raw_decode(html, match.end())
        except ValueError:
            continue
        wants = _find_wants(payload)
        if wants:
            return wants
    return []


def _money(value: Any) -> int | None:
    try:
        amount = int(float(value))
    except (TypeError, ValueError):
        return None
    return amount or None


def _budget(want: dict) -> str | None:
    """«от 500 до 1500 ₽» — Kwork хранит вилку в двух полях."""
    low = _money(want.get("priceLimit"))
    high = _money(want.get("possiblePriceLimit"))
    if low and high and high > low:
        return f"от {low:,} до {high:,} ₽".replace(",", " ")
    amount = low or high
    return f"от {amount:,} ₽".replace(",", " ") if amount else None


def parse_wants(wants: list[dict], source_name: str) -> list[Order]:
    orders: list[Order] = []
    for want in wants:
        want_id = want.get("id")
        title = (want.get("name") or "").strip()
        if not want_id or not title:
            continue
        if want.get("status") not in (None, "active") and not want.get("isWantActive", True):
            continue

        extra: dict[str, str] = {}
        if want.get("max_days"):
            extra["Срок"] = f"до {want['max_days']} дн."
        offers = want.get("kwork_count")
        if isinstance(offers, int):
            extra["Предложений"] = str(offers)
        dates = want.get("wantDates") or {}
        if dates.get("dateCreate"):
            extra["Опубликован"] = str(dates["dateCreate"])

        orders.append(
            Order(
                source=source_name,
                external_id=str(want_id),
                title=title,
                url=PROJECT_URL.format(id=want_id),
                description=(want.get("description") or "").strip(),
                budget=_budget(want),
                extra=extra,
            )
        )
    return orders


class KworkSource(Source):
    """Заказы с биржи Kwork: страница проектов со встроенным JSON."""

    attempts = 3
    retry_pause = 3.0

    async def fetch(self, session: aiohttp.ClientSession) -> list[Order]:
        raw = await fetch_bytes(
            session, self.config.url, attempts=self.attempts, pause=self.retry_pause
        )
        html = raw.decode("utf-8", "replace")
        wants = extract_wants(html)
        if not wants:
            raise RuntimeError("на странице Kwork не нашлось списка заказов (изменилась вёрстка?)")
        log.debug("%s: найдено %s заказов", self.name, len(wants))
        return parse_wants(wants, self.name)
