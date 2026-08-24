"""Единая настройка логирования для всех модулей пайплайна."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

_FORMAT = "%(asctime)s %(levelname)-7s %(name)s | %(message)s"
_DATEFMT = "%Y-%m-%d %H:%M:%S"


def configure_logging(level: str = "INFO", log_dir: Path | None = None,
                      filename: str = "shorts_factory.log") -> None:
    """Пишет логи в stderr и (опционально) в файл; повторный вызов безопасен."""
    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    for handler in list(root.handlers):
        root.removeHandler(handler)

    formatter = logging.Formatter(_FORMAT, datefmt=_DATEFMT)

    stream = logging.StreamHandler(sys.stderr)
    stream.setFormatter(formatter)
    root.addHandler(stream)

    if log_dir is not None:
        log_dir.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_dir / filename, encoding="utf-8")
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)

    # PRAW/urllib3 очень болтливы на DEBUG
    logging.getLogger("prawcore").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
