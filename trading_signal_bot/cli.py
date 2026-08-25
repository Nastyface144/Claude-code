"""Команда запуска бота."""

from __future__ import annotations

import argparse
import asyncio
import logging

log = logging.getLogger(__name__)


def _setup_logging(verbose: bool = False) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="trading_signal_bot",
        description="Агрегатор торговых сигналов TradingView с ИИ-проверкой и расчётом риска.",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="подробные логи")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("run", help="запустить бота (по умолчанию)")

    args = parser.parse_args(argv)
    _setup_logging(args.verbose)

    try:
        from .app import run

        asyncio.run(run())
    except KeyboardInterrupt:
        log.info("Остановлено пользователем")
    except RuntimeError as exc:
        parser.exit(2, f"Ошибка: {exc}\n")
    return 0
