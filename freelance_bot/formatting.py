"""Форматирование сообщений бота (HTML-разметка Telegram)."""

from __future__ import annotations

from datetime import datetime, timezone
from html import escape, unescape

from .matcher import MatchResult
from .models import Order, strip_html

MAX_TITLE = 150
MAX_SNIPPET = 700


def _clean(text: str, limit: int) -> str:
    """Убираем HTML и лишние пробелы, режем по границе слова."""
    plain = " ".join(unescape(strip_html(text or "")).split())
    if len(plain) > limit:
        plain = plain[:limit].rsplit(" ", 1)[0] + "…"
    return escape(plain)


def _when(moment: datetime | None) -> str:
    if moment is None:
        return ""
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    delta = datetime.now(timezone.utc) - moment
    minutes = int(delta.total_seconds() // 60)
    if minutes < 1:
        return "только что"
    if minutes < 60:
        return f"{minutes} мин назад"
    hours = minutes // 60
    if hours < 24:
        return f"{hours} ч назад"
    return f"{hours // 24} дн назад"


def order_message(order: Order, match: MatchResult, source_title: str = "") -> str:
    """Карточка заказа: название, бюджет, раздел биржи, описание и ссылка."""
    lines = [f"🔎 <b>{_clean(order.title, MAX_TITLE)}</b>"]

    budget = order.guess_budget()
    lines.append(f"💰 <b>{escape(budget)}</b>" if budget else "💰 бюджет не указан")

    if order.category:
        lines.append(f"🗂 {_clean(order.category, 90)}")

    snippet = _clean(order.description, MAX_SNIPPET)
    if snippet:
        lines += ["", snippet, ""]
    else:
        lines.append("")

    if order.extra:
        details = " · ".join(f"{key}: {value}" for key, value in list(order.extra.items())[:3])
        lines.append("⏳ " + escape(details))

    if match.tags:
        lines.append("🏷 подходит по: " + escape(", ".join(match.tags[:5])))

    meta = [f"⭐ {match.score}"]
    if source_title or order.source:
        meta.append(f"📰 {escape(source_title or order.source)}")
    when = _when(order.published_at)
    if when:
        meta.append(f"🕒 {when}")
    lines.append(" · ".join(meta))

    if order.url:
        lines.append(f'👉 <a href="{escape(order.url, quote=True)}">Открыть заказ на бирже</a>')

    return "\n".join(lines)


def row_message(row, index: int | None = None) -> str:
    """Короткая строка для /last и /search (строка из БД)."""
    prefix = f"{index}. " if index else ""
    title = escape((row["title"] or "")[:MAX_TITLE])
    parts = [f"{prefix}<b>{title}</b>"]
    tail = [f"⭐ {row['score']}", f"📰 {escape(row['source'])}"]
    if row["budget"]:
        tail.insert(0, f"💰 {escape(row['budget'])}")
    parts.append(" · ".join(tail))
    category = row["category"] if "category" in row.keys() else None
    if category:
        parts.append(f"🗂 {escape(category[:90])}")
    if row["url"]:
        parts.append(f'👉 <a href="{escape(row["url"], quote=True)}">ссылка</a>')
    return "\n".join(parts)


HELP_TEXT = """<b>Радар фриланс-заказов</b>
Слежу за биржами и присылаю только то, что подходит под твои темы:
боты (Telegram, Discord, VK), Telegram Mini Apps и лендинги.

<b>Основное</b>
/start — включить рассылку
/stop — выключить рассылку
/check — опросить биржи прямо сейчас
/last [N] — последние найденные заказы (по умолчанию 5)
/search &lt;текст&gt; — поиск по уже найденным заказам
/status — что происходит: источники, счётчики, настройки

<b>Настройка фильтра</b>
/score &lt;N&gt; — минимальный балл релевантности (сейчас чем выше, тем строже)
/keywords — какие правила сейчас работают
/add &lt;слово&gt; [вес] — добавить своё ключевое слово (можно «слово*»)
/ban &lt;слово&gt; — слово-исключение: заказы с ним не приходят
/del &lt;слово&gt; — убрать своё слово

<b>Источники</b>
/sources — список лент и их состояние
/addsource &lt;имя&gt; &lt;url&gt; — добавить RSS-ленту биржи
/delsource &lt;имя&gt; — удалить ленту
/togglesource &lt;имя&gt; — включить/выключить ленту
"""
