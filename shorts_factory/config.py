"""Загрузка и валидация конфигурации из переменных окружения (.env).

Секреты живут только в .env — в коде нет ни одного значения по умолчанию,
которое было бы ключом. Всё остальное имеет разумные дефолты, чтобы модули
можно было запускать сразу после `cp .env.example .env`.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence

VALID_TIME_FILTERS = ("hour", "day", "week", "month", "year", "all")
VALID_SOURCES = ("selftext", "comments")


class ConfigError(RuntimeError):
    """Конфигурация отсутствует или некорректна."""


# --------------------------------------------------------------------------- #
# Помощники разбора переменных окружения
# --------------------------------------------------------------------------- #
def _get_str(name: str, default: str = "") -> str:
    value = os.getenv(name)
    return default if value is None else value.strip()


def _get_int(name: str, default: int) -> int:
    raw = _get_str(name)
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} должно быть целым числом, получено {raw!r}") from exc


def _get_float(name: str, default: float) -> float:
    raw = _get_str(name)
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} должно быть числом, получено {raw!r}") from exc


def _get_bool(name: str, default: bool) -> bool:
    raw = _get_str(name).lower()
    if not raw:
        return default
    if raw in ("1", "true", "yes", "y", "on"):
        return True
    if raw in ("0", "false", "no", "n", "off"):
        return False
    raise ConfigError(f"{name} должно быть true/false, получено {raw!r}")


def _get_list(name: str, default: Sequence[str] = ()) -> list[str]:
    raw = _get_str(name)
    if not raw:
        return list(default)
    return [item.strip() for item in raw.split(",") if item.strip()]


# --------------------------------------------------------------------------- #
# Секции конфигурации
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class SubredditSpec:
    """Сабреддит и способ извлечения истории из него."""

    name: str
    source: str = "selftext"

    @classmethod
    def parse(cls, raw: str) -> "SubredditSpec":
        """Разбирает запись вида ``tifu`` или ``AskReddit:comments``."""
        name, _, source = raw.partition(":")
        name = name.strip().lstrip("/").removeprefix("r/")
        source = (source.strip() or "selftext").lower()
        if not name:
            raise ConfigError(f"Пустое имя сабреддита в SUBREDDITS: {raw!r}")
        if source not in VALID_SOURCES:
            raise ConfigError(
                f"Неизвестный источник текста {source!r} для r/{name}. "
                f"Допустимо: {', '.join(VALID_SOURCES)}"
            )
        return cls(name=name, source=source)

    def __str__(self) -> str:  # pragma: no cover - только для логов
        return f"r/{self.name}[{self.source}]"


@dataclass(frozen=True)
class RedditConfig:
    client_id: str
    client_secret: str
    user_agent: str
    username: str = ""
    password: str = ""

    def require_credentials(self) -> None:
        """Бросает ConfigError, если не хватает данных для подключения к API."""
        missing = [
            env_name
            for env_name, value in (
                ("REDDIT_CLIENT_ID", self.client_id),
                ("REDDIT_CLIENT_SECRET", self.client_secret),
                ("REDDIT_USER_AGENT", self.user_agent),
            )
            if not value
        ]
        if missing:
            raise ConfigError(
                "Не заданы переменные окружения: "
                + ", ".join(missing)
                + ". Скопируйте .env.example в .env и заполните их "
                "(приложение типа 'script' создаётся на https://www.reddit.com/prefs/apps)."
            )


@dataclass(frozen=True)
class ScraperConfig:
    subreddits: tuple[SubredditSpec, ...]
    time_filter: str = "day"
    post_limit: int = 50
    min_words: int = 100
    max_words: int = 200
    min_score: int = 500
    min_upvote_ratio: float = 0.85
    allow_nsfw: bool = False
    max_stories_per_run: int = 10
    comment_limit: int = 30
    min_comment_words: int = 25
    request_delay_seconds: float = 2.0
    max_retries: int = 4
    retry_base_delay: float = 2.0

    def validate(self) -> None:
        if not self.subreddits:
            raise ConfigError("SUBREDDITS не задан — нечего скрапить.")
        if self.time_filter not in VALID_TIME_FILTERS:
            raise ConfigError(
                f"TIME_FILTER={self.time_filter!r}; допустимо: "
                + ", ".join(VALID_TIME_FILTERS)
            )
        if self.min_words < 1:
            raise ConfigError("MIN_WORDS должно быть >= 1")
        if self.max_words < self.min_words:
            raise ConfigError("MAX_WORDS должно быть >= MIN_WORDS")
        if not 0.0 <= self.min_upvote_ratio <= 1.0:
            raise ConfigError("MIN_UPVOTE_RATIO должно быть в диапазоне 0..1")
        if self.post_limit < 1:
            raise ConfigError("POST_LIMIT должно быть >= 1")
        if self.max_stories_per_run < 1:
            raise ConfigError("MAX_STORIES_PER_RUN должно быть >= 1")


@dataclass(frozen=True)
class Paths:
    data_dir: Path = Path("data")
    queue_file: Path = Path("data/queue.json")
    media_dir: Path = Path("work")
    output_dir: Path = Path("output")
    backgrounds_dir: Path = Path("assets/backgrounds")
    log_dir: Path = Path("logs")

    def ensure(self) -> None:
        """Создаёт рабочие каталоги (кроме библиотеки фонов — её готовит человек)."""
        for path in (self.data_dir, self.media_dir, self.output_dir, self.log_dir):
            path.mkdir(parents=True, exist_ok=True)
        self.queue_file.parent.mkdir(parents=True, exist_ok=True)


@dataclass(frozen=True)
class Settings:
    reddit: RedditConfig
    scraper: ScraperConfig
    paths: Paths = field(default_factory=Paths)
    log_level: str = "INFO"

    @classmethod
    def load(cls, env_file: str | os.PathLike[str] | None = ".env") -> "Settings":
        """Читает .env (если есть) и переменные окружения.

        Переменные, уже выставленные в окружении, имеют приоритет над .env —
        это удобно для запуска из cron/CI.
        """
        if env_file is not None:
            _load_env_file(Path(env_file))

        reddit = RedditConfig(
            client_id=_get_str("REDDIT_CLIENT_ID"),
            client_secret=_get_str("REDDIT_CLIENT_SECRET"),
            user_agent=_get_str("REDDIT_USER_AGENT", "python:shorts-factory:0.1.0"),
            username=_get_str("REDDIT_USERNAME"),
            password=_get_str("REDDIT_PASSWORD"),
        )

        specs = tuple(
            SubredditSpec.parse(item)
            for item in _get_list("SUBREDDITS", ("tifu:selftext",))
        )
        scraper = ScraperConfig(
            subreddits=specs,
            time_filter=_get_str("TIME_FILTER", "day").lower(),
            post_limit=_get_int("POST_LIMIT", 50),
            min_words=_get_int("MIN_WORDS", 100),
            max_words=_get_int("MAX_WORDS", 200),
            min_score=_get_int("MIN_SCORE", 500),
            min_upvote_ratio=_get_float("MIN_UPVOTE_RATIO", 0.85),
            allow_nsfw=_get_bool("ALLOW_NSFW", False),
            max_stories_per_run=_get_int("MAX_STORIES_PER_RUN", 10),
            comment_limit=_get_int("COMMENT_LIMIT", 30),
            min_comment_words=_get_int("MIN_COMMENT_WORDS", 25),
            request_delay_seconds=_get_float("REQUEST_DELAY_SECONDS", 2.0),
            max_retries=_get_int("MAX_RETRIES", 4),
            retry_base_delay=_get_float("RETRY_BASE_DELAY", 2.0),
        )
        scraper.validate()

        data_dir = Path(_get_str("DATA_DIR", "data"))
        paths = Paths(
            data_dir=data_dir,
            queue_file=Path(_get_str("QUEUE_FILE", str(data_dir / "queue.json"))),
            media_dir=Path(_get_str("MEDIA_DIR", "work")),
            output_dir=Path(_get_str("OUTPUT_DIR", "output")),
            backgrounds_dir=Path(_get_str("BACKGROUNDS_DIR", "assets/backgrounds")),
            log_dir=Path(_get_str("LOG_DIR", "logs")),
        )

        return cls(
            reddit=reddit,
            scraper=scraper,
            paths=paths,
            log_level=_get_str("LOG_LEVEL", "INFO").upper(),
        )


def _load_env_file(path: Path) -> None:
    """Подхватывает .env через python-dotenv; без него — простой парсер."""
    if not path.exists():
        return
    try:
        from dotenv import load_dotenv
    except ImportError:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip().strip("'\""))
    else:
        load_dotenv(path, override=False)
