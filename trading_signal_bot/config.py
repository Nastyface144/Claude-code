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


def _float(name: str, default: float) -> float:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _bool(name: str, default: bool) -> bool:
    raw = os.getenv(name, "").strip().lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes", "on", "да")


@dataclass(frozen=True)
class Settings:
    bot_token: str
    db_path: Path
    port: int = 8080
    webhook_secret: str = ""
    admin_ids: tuple[int, ...] = ()
    target_chat_ids: tuple[int, ...] = ()

    # --- агрегация сигналов ---
    total_indicators: int = 7
    min_confirmations: int = 4
    signal_window_seconds: int = 900
    dispatch_cooldown_seconds: int = 1800

    # --- проверка через ИИ ---
    ai_enabled: bool = True
    anthropic_api_key: str = ""
    ai_model: str = "claude-opus-5"
    ai_block_on_reject: bool = True
    ai_notify_rejected: bool = True

    # --- риск и параметры аккаунта проп-компании ---
    account_balance: float = 100000.0
    account_currency: str = "USD"
    risk_per_trade_pct: float = 0.5
    max_daily_loss_pct: float = 4.0
    max_total_drawdown_pct: float = 8.0
    max_daily_trades: int = 5
    default_risk_reward: float = 2.0
    default_sl_pct: float = 0.5
    lot_step: float = 0.01
    min_lot: float = 0.01
    instruments_file: str = ""

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
                "Не задан BOT_TOKEN. Скопируйте trading_signal_bot/.env.example в .env "
                "и впишите токен от @BotFather."
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
            db_path=Path(os.getenv("DB_PATH", "data/trading.db")),
            port=max(1, _int("PORT", 8080)),
            webhook_secret=os.getenv("WEBHOOK_SECRET", "").strip(),
            admin_ids=_ids("ADMIN_IDS"),
            target_chat_ids=_ids("TARGET_CHAT_IDS"),
            total_indicators=max(1, _int("TOTAL_INDICATORS", 7)),
            min_confirmations=max(1, _int("MIN_CONFIRMATIONS", 4)),
            signal_window_seconds=max(30, _int("SIGNAL_WINDOW_SECONDS", 900)),
            dispatch_cooldown_seconds=max(0, _int("DISPATCH_COOLDOWN_SECONDS", 1800)),
            ai_enabled=_bool("AI_ENABLED", True),
            anthropic_api_key=os.getenv("ANTHROPIC_API_KEY", "").strip(),
            ai_model=os.getenv("AI_MODEL", "claude-opus-5").strip() or "claude-opus-5",
            ai_block_on_reject=_bool("AI_BLOCK_ON_REJECT", True),
            ai_notify_rejected=_bool("AI_NOTIFY_REJECTED", True),
            account_balance=max(0.0, _float("ACCOUNT_BALANCE", 100000.0)),
            account_currency=os.getenv("ACCOUNT_CURRENCY", "USD").strip().upper() or "USD",
            risk_per_trade_pct=max(0.01, _float("RISK_PER_TRADE_PCT", 0.5)),
            max_daily_loss_pct=max(0.1, _float("MAX_DAILY_LOSS_PCT", 4.0)),
            max_total_drawdown_pct=max(0.1, _float("MAX_TOTAL_DRAWDOWN_PCT", 8.0)),
            max_daily_trades=max(1, _int("MAX_DAILY_TRADES", 5)),
            default_risk_reward=max(0.1, _float("DEFAULT_RISK_REWARD", 2.0)),
            default_sl_pct=max(0.01, _float("DEFAULT_SL_PCT", 0.5)),
            lot_step=max(0.001, _float("LOT_STEP", 0.01)),
            min_lot=max(0.001, _float("MIN_LOT", 0.01)),
            instruments_file=os.getenv("INSTRUMENTS_FILE", "").strip(),
        )
