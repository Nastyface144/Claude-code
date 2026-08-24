"""Ретраи с экспоненциальной задержкой для сетевых вызовов.

PRAW сам соблюдает rate limit Reddit (читает заголовки X-Ratelimit-*), но
поверх этого нужна защита от 429/5xx и обрывов соединения: их мы повторяем
с экспоненциальным ростом паузы и джиттером, уважая заголовок Retry-After.
"""

from __future__ import annotations

import logging
import random
import time
from typing import Callable, Iterable, TypeVar

T = TypeVar("T")

logger = logging.getLogger(__name__)


class RetryError(RuntimeError):
    """Все попытки исчерпаны."""


def retryable_exceptions() -> tuple[type[BaseException], ...]:
    """Исключения prawcore/requests, которые имеет смысл повторять.

    Импорт ленивый: модуль остаётся полезным (и тестируемым) без praw.
    """
    exceptions: list[type[BaseException]] = [ConnectionError, TimeoutError]
    try:
        from prawcore.exceptions import (
            RequestException,
            ServerError,
            TooManyRequests,
        )
    except ImportError:  # pragma: no cover - praw не установлен
        pass
    else:
        exceptions.extend([RequestException, ServerError, TooManyRequests])
    return tuple(exceptions)


def _retry_after(exc: BaseException) -> float | None:
    """Достаёт Retry-After из исключения prawcore, если он там есть."""
    value = getattr(exc, "retry_after", None)
    if value is None:
        response = getattr(exc, "response", None)
        headers = getattr(response, "headers", None) or {}
        value = headers.get("retry-after") if hasattr(headers, "get") else None
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def call_with_retry(
    func: Callable[[], T],
    *,
    max_attempts: int = 4,
    base_delay: float = 2.0,
    max_delay: float = 60.0,
    exceptions: Iterable[type[BaseException]] | None = None,
    sleep: Callable[[float], None] = time.sleep,
    description: str = "запрос",
) -> T:
    """Вызывает ``func`` с ретраями: 2s, 4s, 8s, 16s (+ джиттер).

    Если исключение несёт Retry-After (429 от Reddit), пауза берётся из него.
    Неповторяемые ошибки (404, 403, неверные креды) пробрасываются сразу.
    """
    retry_on = tuple(exceptions) if exceptions is not None else retryable_exceptions()
    last_exc: BaseException | None = None

    for attempt in range(1, max(1, max_attempts) + 1):
        try:
            return func()
        except retry_on as exc:  # type: ignore[misc]
            last_exc = exc
            if attempt >= max_attempts:
                break
            delay = _retry_after(exc)
            if delay is None:
                delay = min(base_delay * (2 ** (attempt - 1)), max_delay)
                delay += random.uniform(0, delay * 0.1)  # джиттер
            logger.warning(
                "%s: попытка %d/%d не удалась (%s: %s); повтор через %.1f c",
                description, attempt, max_attempts, type(exc).__name__, exc, delay,
            )
            sleep(delay)

    raise RetryError(
        f"{description}: исчерпаны {max_attempts} попыток ({type(last_exc).__name__}: {last_exc})"
    ) from last_exc
