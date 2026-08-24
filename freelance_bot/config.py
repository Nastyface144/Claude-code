"""Настройки приложения (читаются из окружения / .env)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


def _int(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    bot_token: str
    db_path: Path
    poll_interval: int = 600
    request_timeout: int = 20
    min_score: int = 5
    max_per_cycle: int = 10
    admin_ids: tuple[int, ...] = ()
    target_chat_ids: tuple[int, ...] = ()

    @classmethod
    def from_env(
        cls,
        env_file: str | os.PathLike[str] | None = ".env",
        require_token: bool = True,
    ) -> "Settings":
        if env_file and Path(env_file).exists():
            load_dotenv(env_file)

        token = os.getenv("BOT_TOKEN", "").strip()
        if not token and require_token:
            raise RuntimeError(
                "Не задан BOT_TOKEN. Скопируйте .env.example в .env и впишите токен от @BotFather."
            )

        def _ids(name: str) -> tuple[int, ...]:
            values: list[int] = []
            for chunk in os.getenv(name, "").replace(";", ",").split(","):
                chunk = chunk.strip()
                if not chunk:
                    continue
                try:
                    values.append(int(chunk))
                except ValueError:
                    continue
            return tuple(values)

        return cls(
            bot_token=token,
            db_path=Path(os.getenv("DB_PATH", "data/freelance.db")),
            poll_interval=max(60, _int("POLL_INTERVAL", 600)),
            request_timeout=max(5, _int("REQUEST_TIMEOUT", 20)),
            min_score=_int("MIN_SCORE", 5),
            max_per_cycle=max(1, _int("MAX_PER_CYCLE", 10)),
            admin_ids=_ids("ADMIN_IDS"),
            target_chat_ids=_ids("TARGET_CHAT_IDS"),
        )
