"""Хранилище на SQLite: подписчики, найденные заказы, личные слова, источники."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable, Sequence

import aiosqlite

from .models import Order
from .sources.base import SourceConfig

SCHEMA = """
CREATE TABLE IF NOT EXISTS subscribers (
    chat_id    INTEGER PRIMARY KEY,
    active     INTEGER NOT NULL DEFAULT 1,
    min_score  INTEGER,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS orders (
    uid          TEXT PRIMARY KEY,
    source       TEXT NOT NULL,
    external_id  TEXT,
    title        TEXT NOT NULL,
    url          TEXT,
    description  TEXT,
    budget       TEXT,
    category     TEXT,
    published_at TEXT,
    score        INTEGER NOT NULL DEFAULT 0,
    tags         TEXT,
    found_at     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_orders_found ON orders(found_at DESC);
CREATE INDEX IF NOT EXISTS idx_orders_score ON orders(score DESC);

CREATE TABLE IF NOT EXISTS deliveries (
    chat_id INTEGER NOT NULL,
    uid     TEXT NOT NULL,
    sent_at TEXT NOT NULL,
    PRIMARY KEY (chat_id, uid)
);

CREATE TABLE IF NOT EXISTS user_rules (
    chat_id INTEGER NOT NULL,
    kind    TEXT NOT NULL CHECK (kind IN ('include', 'exclude')),
    word    TEXT NOT NULL,
    weight  INTEGER NOT NULL DEFAULT 5,
    PRIMARY KEY (chat_id, kind, word)
);

CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS sources (
    name       TEXT PRIMARY KEY,
    url        TEXT NOT NULL,
    kind       TEXT NOT NULL DEFAULT 'rss',
    title      TEXT,
    enabled    INTEGER NOT NULL DEFAULT 1,
    last_ok    TEXT,
    last_error TEXT,
    last_count INTEGER NOT NULL DEFAULT 0
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Storage:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._db: aiosqlite.Connection | None = None

    # --- жизненный цикл -------------------------------------------------
    async def connect(self) -> "Storage":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(self.path)
        self._db.row_factory = aiosqlite.Row
        await self._db.execute("PRAGMA journal_mode=WAL")
        await self._db.executescript(SCHEMA)
        await self._migrate()
        await self._db.commit()
        return self

    async def _migrate(self) -> None:
        """Досоздать колонки, появившиеся позже, — базы живут между запусками."""
        async with self._db.execute("PRAGMA table_info(orders)") as cursor:  # type: ignore[union-attr]
            columns = {row[1] for row in await cursor.fetchall()}
        for name, ddl in (("category", "TEXT"),):
            if name not in columns:
                await self._db.execute(f"ALTER TABLE orders ADD COLUMN {name} {ddl}")  # type: ignore[union-attr]

    async def close(self) -> None:
        if self._db is not None:
            await self._db.close()
            self._db = None

    @property
    def db(self) -> aiosqlite.Connection:
        if self._db is None:
            raise RuntimeError("Storage не подключён: вызовите await storage.connect()")
        return self._db

    # --- служебные значения ---
    async def get_meta(self, key: str, default: str | None = None) -> str | None:
        async with self.db.execute("SELECT value FROM meta WHERE key = ?", (key,)) as cursor:
            row = await cursor.fetchone()
        return row["value"] if row else default

    async def get_meta_int(self, key: str, default: int = 0) -> int:
        raw = await self.get_meta(key)
        try:
            return int(raw) if raw is not None else default
        except ValueError:
            return default

    async def set_meta(self, key: str, value: str | int) -> None:
        await self.db.execute(
            "INSERT INTO meta (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, str(value)),
        )
        await self.db.commit()

    # --- подписчики -----------------------------------------------------
    async def add_subscriber(self, chat_id: int) -> None:
        await self.db.execute(
            "INSERT INTO subscribers (chat_id, active, created_at) VALUES (?, 1, ?) "
            "ON CONFLICT(chat_id) DO UPDATE SET active = 1",
            (chat_id, _now()),
        )
        await self.db.commit()

    async def set_active(self, chat_id: int, active: bool) -> None:
        await self.db.execute(
            "UPDATE subscribers SET active = ? WHERE chat_id = ?", (int(active), chat_id)
        )
        await self.db.commit()

    async def set_min_score(self, chat_id: int, min_score: int | None) -> None:
        await self.db.execute(
            "UPDATE subscribers SET min_score = ? WHERE chat_id = ?", (min_score, chat_id)
        )
        await self.db.commit()

    async def get_subscriber(self, chat_id: int) -> aiosqlite.Row | None:
        async with self.db.execute(
            "SELECT * FROM subscribers WHERE chat_id = ?", (chat_id,)
        ) as cursor:
            return await cursor.fetchone()

    async def active_subscribers(self) -> list[aiosqlite.Row]:
        async with self.db.execute("SELECT * FROM subscribers WHERE active = 1") as cursor:
            return list(await cursor.fetchall())

    # --- заказы ---------------------------------------------------------
    async def save_order(self, order: Order, score: int, tags: Sequence[str]) -> bool:
        """Сохраняет заказ. Возвращает True, если он встретился впервые."""
        cursor = await self.db.execute(
            "INSERT OR IGNORE INTO orders "
            "(uid, source, external_id, title, url, description, budget, category, published_at, score, tags, found_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                order.uid,
                order.source,
                order.external_id,
                order.title,
                order.url,
                (order.description or "")[:4000],
                order.guess_budget(),
                order.category,
                order.published_at.isoformat() if order.published_at else None,
                score,
                ", ".join(tags),
                _now(),
            ),
        )
        await self.db.commit()
        return cursor.rowcount > 0

    async def recent_orders(self, limit: int = 10, min_score: int = 1) -> list[aiosqlite.Row]:
        async with self.db.execute(
            "SELECT * FROM orders WHERE score >= ? ORDER BY found_at DESC LIMIT ?",
            (min_score, limit),
        ) as cursor:
            return list(await cursor.fetchall())

    async def search_orders(self, query: str, limit: int = 10) -> list[aiosqlite.Row]:
        pattern = f"%{query.lower()}%"
        async with self.db.execute(
            "SELECT * FROM orders WHERE lower(title) LIKE ? OR lower(description) LIKE ? "
            "ORDER BY found_at DESC LIMIT ?",
            (pattern, pattern, limit),
        ) as cursor:
            return list(await cursor.fetchall())

    async def count_orders(self) -> tuple[int, int]:
        async with self.db.execute(
            "SELECT COUNT(*), COALESCE(SUM(score > 0), 0) FROM orders"
        ) as cursor:
            row = await cursor.fetchone()
        return (row[0], row[1]) if row else (0, 0)

    async def compact(self, keep_details_days: int = 2, keep_days: int = 14) -> None:
        """Ужать базу: у старых заказов нужен только uid для защиты от повторов.

        Важно для запуска по расписанию, когда файл базы возят между запусками.
        """
        now = datetime.now(timezone.utc)
        details_edge = (now - timedelta(days=keep_details_days)).isoformat(timespec="seconds")
        await self.db.execute(
            "UPDATE orders SET description = '' WHERE found_at < ? AND description != ''",
            (details_edge,),
        )
        await self.purge_old(days=keep_days)
        await self.db.commit()
        await self.db.execute("VACUUM")

    async def purge_old(self, days: int = 30) -> int:
        edge = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(timespec="seconds")
        cursor = await self.db.execute("DELETE FROM orders WHERE found_at < ?", (edge,))
        await self.db.execute("DELETE FROM deliveries WHERE sent_at < ?", (edge,))
        await self.db.commit()
        return cursor.rowcount

    # --- доставка -------------------------------------------------------
    async def was_delivered(self, chat_id: int, uid: str) -> bool:
        async with self.db.execute(
            "SELECT 1 FROM deliveries WHERE chat_id = ? AND uid = ?", (chat_id, uid)
        ) as cursor:
            return await cursor.fetchone() is not None

    async def mark_delivered(self, chat_id: int, uid: str) -> None:
        await self.db.execute(
            "INSERT OR IGNORE INTO deliveries (chat_id, uid, sent_at) VALUES (?, ?, ?)",
            (chat_id, uid, _now()),
        )
        await self.db.commit()

    # --- личные слова ---------------------------------------------------
    async def add_rule(self, chat_id: int, kind: str, word: str, weight: int = 5) -> None:
        await self.db.execute(
            "INSERT INTO user_rules (chat_id, kind, word, weight) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(chat_id, kind, word) DO UPDATE SET weight = excluded.weight",
            (chat_id, kind, word.strip().lower(), weight),
        )
        await self.db.commit()

    async def remove_rule(self, chat_id: int, word: str) -> int:
        cursor = await self.db.execute(
            "DELETE FROM user_rules WHERE chat_id = ? AND word = ?", (chat_id, word.strip().lower())
        )
        await self.db.commit()
        return cursor.rowcount

    async def list_rules(self, chat_id: int) -> tuple[list[tuple[str, int]], list[str]]:
        async with self.db.execute(
            "SELECT kind, word, weight FROM user_rules WHERE chat_id = ? ORDER BY kind, word",
            (chat_id,),
        ) as cursor:
            rows = await cursor.fetchall()
        include = [(row["word"], row["weight"]) for row in rows if row["kind"] == "include"]
        exclude = [row["word"] for row in rows if row["kind"] == "exclude"]
        return include, exclude

    # --- источники ------------------------------------------------------
    async def seed_sources(self, configs: Iterable[SourceConfig]) -> None:
        for config in configs:
            await self.db.execute(
                "INSERT OR IGNORE INTO sources (name, url, kind, title) VALUES (?, ?, ?, ?)",
                (config.name, config.url, config.kind, config.title),
            )
        await self.db.commit()

    async def list_sources(self, only_enabled: bool = False) -> list[aiosqlite.Row]:
        query = "SELECT * FROM sources"
        if only_enabled:
            query += " WHERE enabled = 1"
        async with self.db.execute(query + " ORDER BY name") as cursor:
            return list(await cursor.fetchall())

    async def source_configs(self) -> list[SourceConfig]:
        return [config for config, _last_ok in await self.source_configs_with_last_ok()]

    async def source_configs_with_last_ok(self) -> list[tuple[SourceConfig, datetime | None]]:
        """Конфиги включённых источников вместе со временем последнего удачного опроса."""
        result: list[tuple[SourceConfig, datetime | None]] = []
        for row in await self.list_sources(only_enabled=True):
            config = SourceConfig(
                name=row["name"], url=row["url"], kind=row["kind"], title=row["title"] or ""
            )
            last_ok = None
            if row["last_ok"]:
                try:
                    last_ok = datetime.fromisoformat(row["last_ok"])
                except ValueError:
                    last_ok = None
            result.append((config, last_ok))
        return result

    async def add_source(self, name: str, url: str, kind: str = "rss", title: str = "") -> None:
        await self.db.execute(
            "INSERT INTO sources (name, url, kind, title, enabled) VALUES (?, ?, ?, ?, 1) "
            "ON CONFLICT(name) DO UPDATE SET url = excluded.url, kind = excluded.kind, "
            "title = excluded.title, enabled = 1, last_error = NULL",
            (name.strip().lower(), url.strip(), kind, title),
        )
        await self.db.commit()

    async def remove_source(self, name: str) -> int:
        cursor = await self.db.execute("DELETE FROM sources WHERE name = ?", (name.strip().lower(),))
        await self.db.commit()
        return cursor.rowcount

    async def set_source_enabled(self, name: str, enabled: bool) -> int:
        cursor = await self.db.execute(
            "UPDATE sources SET enabled = ? WHERE name = ?", (int(enabled), name.strip().lower())
        )
        await self.db.commit()
        return cursor.rowcount

    async def record_source_run(self, name: str, count: int, error: str | None) -> None:
        if error:
            await self.db.execute(
                "UPDATE sources SET last_error = ? WHERE name = ?", (error, name)
            )
        else:
            await self.db.execute(
                "UPDATE sources SET last_ok = ?, last_error = NULL, last_count = ? WHERE name = ?",
                (_now(), count, name),
            )
        await self.db.commit()
