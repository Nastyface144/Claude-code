"""Хранилище на SQLite: сигналы, отправленные сетапы, сделки, подписчики."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import aiosqlite

from .models import Signal

SCHEMA = """
CREATE TABLE IF NOT EXISTS subscribers (
    chat_id    INTEGER PRIMARY KEY,
    active     INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS signals (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    indicator   TEXT NOT NULL,
    symbol      TEXT NOT NULL,
    timeframe   TEXT NOT NULL,
    direction   TEXT NOT NULL,
    price       REAL NOT NULL,
    stop_loss   REAL,
    take_profit REAL,
    note        TEXT,
    received_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_signals_group
    ON signals(symbol, timeframe, direction, received_at DESC);

CREATE TABLE IF NOT EXISTS dispatches (
    symbol         TEXT NOT NULL,
    timeframe      TEXT NOT NULL,
    direction      TEXT NOT NULL,
    dispatched_at  TEXT NOT NULL,
    PRIMARY KEY (symbol, timeframe, direction)
);

CREATE TABLE IF NOT EXISTS trades (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol         TEXT NOT NULL,
    timeframe      TEXT NOT NULL,
    direction      TEXT NOT NULL,
    entry          REAL NOT NULL,
    stop_loss      REAL NOT NULL,
    take_profit    REAL,
    lots           REAL NOT NULL,
    risk_amount    REAL NOT NULL,
    risk_pct       REAL NOT NULL,
    confirmations  TEXT NOT NULL,
    ai_approved    INTEGER,
    ai_confidence  INTEGER,
    ai_reasoning   TEXT,
    created_at     TEXT NOT NULL,
    pnl_amount     REAL,
    closed_at      TEXT
);
CREATE INDEX IF NOT EXISTS idx_trades_created ON trades(created_at DESC);
"""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(moment: datetime) -> str:
    return moment.isoformat(timespec="seconds")


def _today_start() -> str:
    now = _now()
    return _iso(now.replace(hour=0, minute=0, second=0, microsecond=0))


class Storage:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._db: aiosqlite.Connection | None = None

    async def connect(self) -> "Storage":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(self.path)
        self._db.row_factory = aiosqlite.Row
        await self._db.execute("PRAGMA journal_mode=WAL")
        await self._db.executescript(SCHEMA)
        await self._db.commit()
        return self

    async def close(self) -> None:
        if self._db is not None:
            await self._db.close()
            self._db = None

    @property
    def db(self) -> aiosqlite.Connection:
        if self._db is None:
            raise RuntimeError("Storage не подключён: вызовите await storage.connect()")
        return self._db

    # --- подписчики -----------------------------------------------------
    async def add_subscriber(self, chat_id: int) -> None:
        await self.db.execute(
            "INSERT INTO subscribers (chat_id, active, created_at) VALUES (?, 1, ?) "
            "ON CONFLICT(chat_id) DO UPDATE SET active = 1",
            (chat_id, _iso(_now())),
        )
        await self.db.commit()

    async def set_active(self, chat_id: int, active: bool) -> None:
        await self.db.execute(
            "UPDATE subscribers SET active = ? WHERE chat_id = ?", (int(active), chat_id)
        )
        await self.db.commit()

    async def active_subscribers(self) -> list[aiosqlite.Row]:
        async with self.db.execute("SELECT * FROM subscribers WHERE active = 1") as cursor:
            return list(await cursor.fetchall())

    # --- сигналы и агрегация ---------------------------------------------
    async def save_signal(self, signal: Signal) -> int:
        cursor = await self.db.execute(
            "INSERT INTO signals "
            "(indicator, symbol, timeframe, direction, price, stop_loss, take_profit, note, received_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                signal.indicator,
                signal.symbol,
                signal.timeframe,
                signal.direction,
                signal.price,
                signal.stop_loss,
                signal.take_profit,
                signal.note,
                _iso(signal.received_at),
            ),
        )
        await self.db.commit()
        return cursor.lastrowid or 0

    async def recent_signals(
        self, symbol: str, timeframe: str, direction: str, window_seconds: int
    ) -> list[Signal]:
        edge = _iso(_now() - timedelta(seconds=window_seconds))
        async with self.db.execute(
            "SELECT * FROM signals WHERE symbol = ? AND timeframe = ? AND direction = ? "
            "AND received_at >= ? ORDER BY received_at ASC",
            (symbol, timeframe, direction, edge),
        ) as cursor:
            rows = await cursor.fetchall()
        return [
            Signal(
                indicator=row["indicator"],
                symbol=row["symbol"],
                timeframe=row["timeframe"],
                direction=row["direction"],
                price=row["price"],
                received_at=datetime.fromisoformat(row["received_at"]),
                stop_loss=row["stop_loss"],
                take_profit=row["take_profit"],
                note=row["note"] or "",
            )
            for row in rows
        ]

    async def recently_dispatched(
        self, symbol: str, timeframe: str, direction: str, cooldown_seconds: int
    ) -> bool:
        async with self.db.execute(
            "SELECT dispatched_at FROM dispatches WHERE symbol = ? AND timeframe = ? AND direction = ?",
            (symbol, timeframe, direction),
        ) as cursor:
            row = await cursor.fetchone()
        if row is None:
            return False
        dispatched_at = datetime.fromisoformat(row["dispatched_at"])
        return (_now() - dispatched_at).total_seconds() < cooldown_seconds

    async def mark_dispatched(self, symbol: str, timeframe: str, direction: str) -> None:
        await self.db.execute(
            "INSERT INTO dispatches (symbol, timeframe, direction, dispatched_at) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(symbol, timeframe, direction) DO UPDATE SET dispatched_at = excluded.dispatched_at",
            (symbol, timeframe, direction, _iso(_now())),
        )
        await self.db.commit()

    async def purge_old_signals(self, hours: int = 12) -> int:
        edge = _iso(_now() - timedelta(hours=hours))
        cursor = await self.db.execute("DELETE FROM signals WHERE received_at < ?", (edge,))
        await self.db.commit()
        return cursor.rowcount

    # --- сделки и дневной риск -------------------------------------------
    async def log_trade(
        self,
        *,
        symbol: str,
        timeframe: str,
        direction: str,
        entry: float,
        stop_loss: float,
        take_profit: float | None,
        lots: float,
        risk_amount: float,
        risk_pct: float,
        confirmations: list[str],
        ai_approved: bool | None,
        ai_confidence: int | None,
        ai_reasoning: str,
    ) -> int:
        cursor = await self.db.execute(
            "INSERT INTO trades "
            "(symbol, timeframe, direction, entry, stop_loss, take_profit, lots, risk_amount, "
            "risk_pct, confirmations, ai_approved, ai_confidence, ai_reasoning, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                symbol,
                timeframe,
                direction,
                entry,
                stop_loss,
                take_profit,
                lots,
                risk_amount,
                risk_pct,
                ", ".join(confirmations),
                None if ai_approved is None else int(ai_approved),
                ai_confidence,
                ai_reasoning,
                _iso(_now()),
            ),
        )
        await self.db.commit()
        return cursor.lastrowid or 0

    async def close_trade(self, trade_id: int, pnl_amount: float) -> bool:
        cursor = await self.db.execute(
            "UPDATE trades SET pnl_amount = ?, closed_at = ? WHERE id = ?",
            (pnl_amount, _iso(_now()), trade_id),
        )
        await self.db.commit()
        return cursor.rowcount > 0

    async def todays_trades(self) -> list[aiosqlite.Row]:
        async with self.db.execute(
            "SELECT * FROM trades WHERE created_at >= ? ORDER BY created_at DESC", (_today_start(),)
        ) as cursor:
            return list(await cursor.fetchall())

    async def todays_risk_summary(self) -> tuple[int, float, float]:
        """(число сделок сегодня, суммарный запрошенный риск $, реализованный убыток $)."""
        rows = await self.todays_trades()
        trade_count = len(rows)
        risk_budget = sum(row["risk_amount"] for row in rows)
        realized_loss = sum(-row["pnl_amount"] for row in rows if row["pnl_amount"] is not None and row["pnl_amount"] < 0)
        return trade_count, risk_budget, realized_loss

    async def recent_trades(self, limit: int = 10) -> list[aiosqlite.Row]:
        async with self.db.execute(
            "SELECT * FROM trades ORDER BY created_at DESC LIMIT ?", (limit,)
        ) as cursor:
            return list(await cursor.fetchall())
