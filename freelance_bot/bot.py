"""Хендлеры Telegram-бота."""

from __future__ import annotations

import logging
from html import escape

from aiogram import Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import Message

from .formatting import HELP_TEXT, row_message
from .keywords import INCLUDE_RULES, PENALTY_RULES, STOP_RULES
from .service import Radar

log = logging.getLogger(__name__)


async def cmd_start(message: Message, radar: Radar) -> None:
    storage = radar.storage
    await storage.add_subscriber(message.chat.id)
    settings = radar.settings
    await message.answer(
        "✅ Рассылка включена.\n"
        f"Проверяю биржи каждые {settings.poll_interval // 60} мин "
        f"и присылаю заказы с баллом от {settings.min_score}.\n\n" + HELP_TEXT
    )


async def cmd_help(message: Message, radar: Radar) -> None:
    await message.answer(HELP_TEXT)


async def cmd_stop(message: Message, radar: Radar) -> None:
    await radar.storage.set_active(message.chat.id, False)
    await message.answer("⏸ Рассылка выключена. Включить обратно — /start")


async def cmd_check(message: Message, radar: Radar) -> None:
    await radar.storage.add_subscriber(message.chat.id)
    note = await message.answer("🔄 Опрашиваю биржи…")
    report = await radar.poll_once()
    await note.edit_text("📊 Готово.\n" + escape(report.as_text()))
    if report.sent == 0:
        await message.answer("Новых подходящих заказов нет. Последние находки — /last")


async def cmd_last(message: Message, command: CommandObject, radar: Radar) -> None:
    limit = 5
    if command.args and command.args.strip().isdigit():
        limit = max(1, min(20, int(command.args.strip())))
    subscriber = await radar.storage.get_subscriber(message.chat.id)
    min_score = (subscriber["min_score"] if subscriber else None) or radar.settings.min_score
    rows = await radar.storage.recent_orders(limit=limit, min_score=min_score)
    if not rows:
        await message.answer("Пока ничего подходящего не нашлось. Попробуй /check или снизь порог: /score 4")
        return
    blocks = [row_message(row, index) for index, row in enumerate(rows, start=1)]
    await message.answer("\n\n".join(blocks), disable_web_page_preview=True)


async def cmd_search(message: Message, command: CommandObject, radar: Radar) -> None:
    query = (command.args or "").strip()
    if not query:
        await message.answer("Как пользоваться: <code>/search мини апп</code>")
        return
    rows = await radar.storage.search_orders(query, limit=10)
    if not rows:
        await message.answer(f"По запросу «{escape(query)}» ничего не найдено среди собранных заказов.")
        return
    blocks = [row_message(row, index) for index, row in enumerate(rows, start=1)]
    await message.answer("\n\n".join(blocks), disable_web_page_preview=True)


async def cmd_status(message: Message, radar: Radar) -> None:
    storage = radar.storage
    subscriber = await storage.get_subscriber(message.chat.id)
    total, scored = await storage.count_orders()
    include, exclude = await storage.list_rules(message.chat.id)
    sources = await storage.list_sources()
    alive = sum(1 for row in sources if row["enabled"] and not row["last_error"])

    active = bool(subscriber and subscriber["active"])
    min_score = (subscriber["min_score"] if subscriber else None) or radar.settings.min_score

    lines = [
        "<b>Состояние</b>",
        f"Рассылка: {'включена ✅' if active else 'выключена ⏸'}",
        f"Порог релевантности: {min_score}",
        f"Интервал опроса: {radar.settings.poll_interval // 60} мин",
        f"Источников: {len(sources)} (рабочих {alive})",
        f"Заказов в базе: {total}, из них с ненулевым баллом: {scored}",
        f"Своих слов: +{len(include)} / −{len(exclude)}",
    ]
    if radar.last_report:
        lines += ["", "<b>Последний цикл</b>", escape(radar.last_report.as_text())]
    await message.answer("\n".join(lines))


async def cmd_score(message: Message, command: CommandObject, radar: Radar) -> None:
    raw = (command.args or "").strip()
    if not raw.lstrip("-").isdigit():
        await message.answer(
            "Как пользоваться: <code>/score 5</code>\n"
            "Чем выше число, тем строже фильтр. Обычные значения: 4–8."
        )
        return
    value = max(1, min(50, int(raw)))
    storage = radar.storage
    await storage.add_subscriber(message.chat.id)
    await storage.set_min_score(message.chat.id, value)
    await message.answer(f"✅ Порог релевантности: {value}")


async def cmd_keywords(message: Message, radar: Radar) -> None:
    include, exclude = await radar.storage.list_rules(message.chat.id)

    base_tags: dict[str, int] = {}
    for tag, weight, _pattern in INCLUDE_RULES:
        base_tags[tag] = max(base_tags.get(tag, 0), weight)

    lines = ["<b>Базовые темы</b> (вес)"]
    lines += [f"• {escape(tag)} +{weight}" for tag, weight in base_tags.items()]
    lines.append("")
    lines.append("<b>Штрафы</b>")
    lines += [f"• {escape(tag)} {weight}" for tag, weight, _ in PENALTY_RULES]
    lines.append("")
    lines.append("<b>Стоп-слова</b>: " + escape(", ".join(tag for tag, _ in STOP_RULES)))

    if include:
        lines += ["", "<b>Твои слова</b>"] + [f"• {escape(w)} +{weight}" for w, weight in include]
    if exclude:
        lines += ["", "<b>Твои исключения</b>: " + escape(", ".join(exclude))]
    lines += ["", "Добавить: <code>/add мини апп 6</code> · Исключить: <code>/ban казино</code>"]
    await message.answer("\n".join(lines))


async def cmd_add(message: Message, command: CommandObject, radar: Radar) -> None:
    raw = (command.args or "").strip()
    if not raw:
        await message.answer(
            "Как пользоваться: <code>/add чат бот 6</code>\n"
            "Последнее число — вес (по умолчанию 5). «*» = любое окончание: <code>/add лендинг*</code>"
        )
        return
    parts = raw.split()
    weight = 5
    if len(parts) > 1 and parts[-1].lstrip("-").isdigit():
        weight = max(-10, min(10, int(parts[-1])))
        parts = parts[:-1]
    word = " ".join(parts)
    storage = radar.storage
    await storage.add_subscriber(message.chat.id)
    await storage.add_rule(message.chat.id, "include", word, weight)
    await message.answer(f"✅ Слово «{escape(word)}» добавлено с весом {weight:+d}")


async def cmd_ban(message: Message, command: CommandObject, radar: Radar) -> None:
    word = (command.args or "").strip()
    if not word:
        await message.answer("Как пользоваться: <code>/ban wordpress</code>")
        return
    storage = radar.storage
    await storage.add_subscriber(message.chat.id)
    await storage.add_rule(message.chat.id, "exclude", word, 0)
    await message.answer(f"🚫 Заказы со словом «{escape(word)}» приходить не будут")


async def cmd_del(message: Message, command: CommandObject, radar: Radar) -> None:
    word = (command.args or "").strip()
    if not word:
        await message.answer("Как пользоваться: <code>/del wordpress</code>")
        return
    removed = await radar.storage.remove_rule(message.chat.id, word)
    await message.answer(
        f"🗑 Удалено: «{escape(word)}»" if removed else f"Слова «{escape(word)}» в твоём списке нет"
    )


async def cmd_sources(message: Message, radar: Radar) -> None:
    rows = await radar.storage.list_sources()
    if not rows:
        await message.answer("Источников нет. Добавь: <code>/addsource fl https://www.fl.ru/rss/all.xml</code>")
        return
    lines = ["<b>Источники</b>"]
    for row in rows:
        if not row["enabled"]:
            mark = "⏸"
        elif row["last_error"]:
            mark = "⚠️"
        elif row["last_ok"]:
            mark = "✅"
        else:
            mark = "…"
        lines.append(f"{mark} <b>{escape(row['name'])}</b> — {escape(row['title'] or row['url'])}")
        lines.append(f"   <code>{escape(row['url'])}</code>")
        if row["last_error"]:
            lines.append(f"   ошибка: {escape(row['last_error'][:150])}")
        elif row["last_ok"]:
            lines.append(f"   последний опрос: {escape(row['last_ok'])}, объявлений: {row['last_count']}")
    lines += ["", "Добавить: <code>/addsource имя url</code> · Удалить: <code>/delsource имя</code>"]
    await message.answer("\n".join(lines), disable_web_page_preview=True)


async def cmd_addsource(message: Message, command: CommandObject, radar: Radar) -> None:
    parts = (command.args or "").split()
    if len(parts) < 2 or not parts[1].startswith(("http://", "https://")):
        await message.answer(
            "Как пользоваться: <code>/addsource fl https://www.fl.ru/rss/all.xml</code>\n"
            "Обычно это ссылка на RSS-ленту биржи; страницы заказов Kwork тоже подойдут."
        )
        return
    name, url = parts[0], parts[1]
    kind = "kwork" if "kwork.ru" in url else "rss"
    title = " ".join(parts[2:])
    await radar.storage.add_source(name, url, kind, title)
    await message.answer(f"✅ Источник «{escape(name)}» добавлен. Проверить: /check")


async def cmd_delsource(message: Message, command: CommandObject, radar: Radar) -> None:
    name = (command.args or "").strip()
    if not name:
        await message.answer("Как пользоваться: <code>/delsource fl</code>")
        return
    removed = await radar.storage.remove_source(name)
    await message.answer(f"🗑 Источник «{escape(name)}» удалён" if removed else "Такого источника нет")


async def cmd_togglesource(message: Message, command: CommandObject, radar: Radar) -> None:
    name = (command.args or "").strip().lower()
    if not name:
        await message.answer("Как пользоваться: <code>/togglesource weblancer</code>")
        return
    storage = radar.storage
    rows = {row["name"]: row for row in await storage.list_sources()}
    row = rows.get(name)
    if row is None:
        await message.answer("Такого источника нет. Список — /sources")
        return
    new_state = not bool(row["enabled"])
    await storage.set_source_enabled(name, new_state)
    await message.answer(f"{'▶️ Включён' if new_state else '⏸ Выключен'}: {escape(name)}")


async def fallback(message: Message, radar: Radar) -> None:
    """Любой текст без команды воспринимаем как быстрый поиск."""
    text = (message.text or "").strip()
    if not text:
        return
    rows = await radar.storage.search_orders(text, limit=5)
    if not rows:
        await message.answer("Не понял команду. Список команд — /help")
        return
    blocks = [row_message(row, index) for index, row in enumerate(rows, start=1)]
    await message.answer(
        f"Нашёл по «{escape(text)}»:\n\n" + "\n\n".join(blocks), disable_web_page_preview=True
    )


def build_router() -> Router:
    """Свежий Router с командами. Router привязывается лишь к одному Dispatcher,
    поэтому создаём его функцией, а не на уровне модуля."""
    router = Router(name="freelance")
    router.message.register(cmd_start, CommandStart())
    router.message.register(cmd_help, Command("help"))
    router.message.register(cmd_stop, Command("stop"))
    router.message.register(cmd_check, Command("check"))
    router.message.register(cmd_last, Command("last"))
    router.message.register(cmd_search, Command("search"))
    router.message.register(cmd_status, Command("status"))
    router.message.register(cmd_score, Command("score"))
    router.message.register(cmd_keywords, Command("keywords"))
    router.message.register(cmd_add, Command("add"))
    router.message.register(cmd_ban, Command("ban"))
    router.message.register(cmd_del, Command("del"))
    router.message.register(cmd_sources, Command("sources"))
    router.message.register(cmd_addsource, Command("addsource"))
    router.message.register(cmd_delsource, Command("delsource"))
    router.message.register(cmd_togglesource, Command("togglesource"))
    router.message.register(fallback)
    return router
