"""Модель заказа, общая для всех источников."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone

_TAG_RE = re.compile(r"<[^>]+>")
_BUDGET_RE = re.compile(
    r"(\d[\d\s  ]{2,}|\d+)\s*(?:руб\w*|рублей|₽|р\.|usd|\$|у\.?е\.?|eur|€)",
    re.IGNORECASE,
)


def strip_html(text: str) -> str:
    return _TAG_RE.sub(" ", text or "")


@dataclass(slots=True)
class Order:
    """Один заказ с биржи."""

    source: str
    external_id: str
    title: str
    url: str
    description: str = ""
    budget: str | None = None
    category: str | None = None
    published_at: datetime | None = None
    extra: dict[str, str] = field(default_factory=dict)

    @property
    def uid(self) -> str:
        """Стабильный идентификатор заказа — по нему отсекаются дубли."""
        raw = f"{self.source}:{self.external_id or self.url or self.title}"
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()

    @property
    def text(self) -> str:
        """Всё, по чему оцениваем релевантность, включая раздел биржи."""
        return "\n".join(filter(None, [self.title, self.category, strip_html(self.description)]))

    def guess_budget(self) -> str | None:
        """Если источник не отдал бюджет отдельно — пытаемся вытащить из текста."""
        if self.budget:
            return self.budget
        match = _BUDGET_RE.search(strip_html(self.description))
        return match.group(0).strip() if match else None

    def published_ts(self) -> float:
        if self.published_at is None:
            return 0.0
        moment = self.published_at
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=timezone.utc)
        return moment.timestamp()
