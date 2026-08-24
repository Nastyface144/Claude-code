"""Модуль 1: Reddit Scraper.

Забирает топ-посты из заданных сабреддитов, фильтрует их по длине текста,
рейтингу и безопасности контента и складывает подходящие в очередь историй.

Поддерживаются два источника текста (задаются в SUBREDDITS через двоеточие):

* ``selftext`` — история находится в теле поста (r/tifu, r/confession);
* ``comments`` — пост это вопрос, а история собирается из топ-комментариев
  (r/AskReddit). Комментарии добираются по одному, пока суммарная длина не
  войдёт в окно MIN_WORDS..MAX_WORDS.

Работа с API:

* PRAW сам соблюдает rate limit Reddit (пауза по заголовкам X-Ratelimit-*);
* поверх него все сетевые вызовы обёрнуты в ретраи с экспоненциальной
  задержкой и уважением Retry-After (см. ``utils.retry``);
* между сабреддитами делается пауза REQUEST_DELAY_SECONDS;
* ошибка на одном сабреддите не роняет запуск — она логируется и попадает
  в отчёт, остальные сабреддиты обрабатываются дальше.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Sequence

from ..config import ConfigError, ScraperConfig, Settings, SubredditSpec
from ..models import Story, StoryStatus
from ..storage import StoryQueue
from ..utils.retry import call_with_retry
from ..utils.text import count_words, is_deleted, strip_markdown

logger = logging.getLogger(__name__)


class RejectReason:
    """Причины, по которым пост не попал в очередь (для отчёта и отладки)."""

    ALREADY_SEEN = "already_seen"
    STICKIED = "stickied"
    NSFW = "nsfw"
    NO_TEXT = "no_text"
    LOW_SCORE = "low_score"
    LOW_RATIO = "low_upvote_ratio"
    TOO_SHORT = "too_short"
    TOO_LONG = "too_long"
    NO_USABLE_COMMENTS = "no_usable_comments"
    ERROR = "error"


@dataclass
class ScrapeReport:
    """Итоги одного запуска скрапера."""

    fetched: int = 0
    accepted: int = 0
    rejected: dict[str, int] = field(default_factory=dict)
    stories: list[Story] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    per_subreddit: dict[str, int] = field(default_factory=dict)

    def reject(self, reason: str) -> None:
        self.rejected[reason] = self.rejected.get(reason, 0) + 1

    @property
    def rejected_total(self) -> int:
        return sum(self.rejected.values())

    def summary(self) -> str:
        parts = [f"просмотрено={self.fetched}", f"принято={self.accepted}"]
        if self.rejected:
            details = ", ".join(f"{k}={v}" for k, v in sorted(self.rejected.items()))
            parts.append(f"отклонено={self.rejected_total} ({details})")
        if self.errors:
            parts.append(f"ошибок={len(self.errors)}")
        return "; ".join(parts)


class RedditScraper:
    """Сбор историй с Reddit в :class:`StoryQueue`."""

    def __init__(
        self,
        settings: Settings,
        *,
        queue: StoryQueue | None = None,
        reddit: Any | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        """``reddit`` и ``queue`` можно подменить — так модуль тестируется без сети."""
        self.settings = settings
        self.config: ScraperConfig = settings.scraper
        self.queue = queue if queue is not None else StoryQueue(settings.paths.queue_file)
        self._reddit = reddit
        self._sleep = sleep

    # ------------------------------------------------------------------ #
    # Клиент Reddit
    # ------------------------------------------------------------------ #
    @property
    def reddit(self) -> Any:
        if self._reddit is None:
            self._reddit = self._build_client()
        return self._reddit

    def _build_client(self) -> Any:
        """Создаёт read-only PRAW-клиент (praw импортируется лениво)."""
        creds = self.settings.reddit
        creds.require_credentials()
        try:
            import praw
        except ImportError as exc:  # pragma: no cover - зависимость не установлена
            raise ConfigError(
                "Не установлен praw. Выполните: pip install -r requirements.txt"
            ) from exc

        kwargs: dict[str, Any] = {
            "client_id": creds.client_id,
            "client_secret": creds.client_secret,
            "user_agent": creds.user_agent,
            # PRAW сам подождёт, если Reddit просит притормозить, вместо 429.
            "ratelimit_seconds": 600,
        }
        if creds.username and creds.password:
            kwargs["username"] = creds.username
            kwargs["password"] = creds.password

        client = praw.Reddit(**kwargs)
        client.read_only = True
        logger.debug("PRAW-клиент создан (read_only=%s)", client.read_only)
        return client

    # ------------------------------------------------------------------ #
    # Основной цикл
    # ------------------------------------------------------------------ #
    def run(
        self,
        *,
        subreddits: Sequence[SubredditSpec] | None = None,
        time_filter: str | None = None,
        post_limit: int | None = None,
        max_stories: int | None = None,
        dry_run: bool = False,
    ) -> ScrapeReport:
        """Проходит по сабреддитам и добавляет подходящие истории в очередь.

        :param dry_run: ничего не записывать на диск (истории всё равно
            вернутся в отчёте — удобно для проверки фильтров).
        """
        specs = list(subreddits or self.config.subreddits)
        time_filter = time_filter or self.config.time_filter
        post_limit = post_limit or self.config.post_limit
        remaining = max_stories if max_stories is not None else self.config.max_stories_per_run

        # Клиент создаётся до цикла: нехватка ключей — это ошибка запуска,
        # а не сбой одного сабреддита.
        _ = self.reddit

        report = ScrapeReport()
        logger.info(
            "Старт сбора: %s | период=%s | лимит постов=%d | нужно историй=%d",
            ", ".join(str(spec) for spec in specs), time_filter, post_limit, remaining,
        )

        for index, spec in enumerate(specs):
            if remaining <= 0:
                logger.info("Набрано достаточно историй, остальные сабреддиты пропущены")
                break
            if index > 0 and self.config.request_delay_seconds > 0:
                self._sleep(self.config.request_delay_seconds)

            try:
                submissions = self._fetch_submissions(spec, time_filter, post_limit)
            except ConfigError:
                raise
            except Exception as exc:  # noqa: BLE001 - один сабреддит не роняет запуск
                message = f"{spec}: не удалось получить посты ({type(exc).__name__}: {exc})"
                logger.error(message)
                report.errors.append(message)
                report.reject(RejectReason.ERROR)
                continue

            accepted_here = 0
            for submission in submissions:
                if remaining <= 0:
                    break
                report.fetched += 1
                story = self._process(submission, spec, report)
                if story is None:
                    continue
                if self.queue.add(story):
                    report.stories.append(story)
                    report.accepted += 1
                    accepted_here += 1
                    remaining -= 1
                    logger.info(
                        "+ %s | r/%s | %d слов | %d апвоутов | %s",
                        story.id, story.subreddit, story.word_count, story.score,
                        story.title[:70],
                    )
            report.per_subreddit[spec.name] = accepted_here

        if dry_run:
            logger.info("dry-run: очередь на диск не сохранена")
        else:
            self.queue.save()
            logger.info("Очередь сохранена: %s (всего историй: %d)",
                        self.queue.path, len(self.queue))

        logger.info("Готово. %s", report.summary())
        return report

    # ------------------------------------------------------------------ #
    # Получение и фильтрация постов
    # ------------------------------------------------------------------ #
    def _fetch_submissions(self, spec: SubredditSpec, time_filter: str,
                           post_limit: int) -> list[Any]:
        """Материализует листинг топ-постов одним ретраебельным вызовом."""
        logger.debug("Запрашиваю top(%s, limit=%d) из %s", time_filter, post_limit, spec)
        subreddit = self.reddit.subreddit(spec.name)
        return call_with_retry(
            lambda: list(subreddit.top(time_filter=time_filter, limit=post_limit)),
            max_attempts=self.config.max_retries,
            base_delay=self.config.retry_base_delay,
            description=f"top-посты {spec}",
        )

    def _process(self, submission: Any, spec: SubredditSpec,
                 report: ScrapeReport) -> Story | None:
        """Прогоняет пост через фильтры и собирает :class:`Story`."""
        post_id = getattr(submission, "id", None)
        if not post_id:
            report.reject(RejectReason.ERROR)
            return None

        if self.queue.is_seen(post_id):
            report.reject(RejectReason.ALREADY_SEEN)
            return None

        reason = self._check_metadata(submission)
        if reason is not None:
            self.queue.mark_seen(post_id)
            report.reject(reason)
            return None

        try:
            if spec.source == "comments":
                text, segments, reason = self._text_from_comments(submission)
            else:
                text, segments, reason = self._text_from_selftext(submission)
        except Exception as exc:  # noqa: BLE001
            message = f"{post_id}: ошибка при чтении текста ({type(exc).__name__}: {exc})"
            logger.warning(message)
            report.errors.append(message)
            report.reject(RejectReason.ERROR)
            return None

        if reason is not None:
            # Пост «залипает» в seen: он не пройдёт фильтр и завтра.
            self.queue.mark_seen(post_id)
            report.reject(reason)
            return None

        return self._build_story(submission, spec, text, segments)

    def _check_metadata(self, submission: Any) -> str | None:
        """Дешёвые проверки по метаданным — до чтения комментариев."""
        cfg = self.config
        if getattr(submission, "stickied", False) or getattr(submission, "pinned", False):
            return RejectReason.STICKIED
        if getattr(submission, "over_18", False) and not cfg.allow_nsfw:
            return RejectReason.NSFW
        if int(getattr(submission, "score", 0) or 0) < cfg.min_score:
            return RejectReason.LOW_SCORE
        ratio = getattr(submission, "upvote_ratio", None)
        if ratio is not None and float(ratio) < cfg.min_upvote_ratio:
            return RejectReason.LOW_RATIO
        return None

    def _text_from_selftext(self, submission: Any) -> tuple[str, list[str], str | None]:
        raw = getattr(submission, "selftext", "") or ""
        if is_deleted(raw):
            return "", [], RejectReason.NO_TEXT
        text = strip_markdown(raw)
        words = count_words(text)
        if words < self.config.min_words:
            return text, [], RejectReason.TOO_SHORT
        if words > self.config.max_words:
            # Длинный пост не мусор: модуль Text Processor умеет его сокращать,
            # но на этом этапе окно длины держим строго — см. README.
            return text, [], RejectReason.TOO_LONG
        return text, [], None

    def _text_from_comments(self, submission: Any) -> tuple[str, list[str], str | None]:
        """Собирает историю из топ-комментариев (для r/AskReddit и подобных)."""
        cfg = self.config
        comments = call_with_retry(
            lambda: self._top_level_comments(submission),
            max_attempts=cfg.max_retries,
            base_delay=cfg.retry_base_delay,
            description=f"комментарии {getattr(submission, 'id', '?')}",
        )

        segments: list[str] = []
        total_words = 0
        for comment in comments[: cfg.comment_limit]:
            if getattr(comment, "stickied", False):
                continue
            if getattr(comment, "author", None) is None:
                continue
            body = getattr(comment, "body", "") or ""
            if is_deleted(body):
                continue
            cleaned = strip_markdown(body)
            words = count_words(cleaned)
            if words < cfg.min_comment_words:
                continue
            if total_words + words > cfg.max_words:
                continue  # не влезает — пробуем следующий, покороче
            segments.append(cleaned)
            total_words += words
            if total_words >= cfg.min_words:
                break

        if not segments:
            return "", [], RejectReason.NO_USABLE_COMMENTS
        if total_words < cfg.min_words:
            return "\n\n".join(segments), segments, RejectReason.TOO_SHORT
        return "\n\n".join(segments), segments, None

    @staticmethod
    def _top_level_comments(submission: Any) -> list[Any]:
        """Верхнеуровневые комментарии, отсортированные по рейтингу."""
        forest = submission.comments
        replace_more = getattr(forest, "replace_more", None)
        if callable(replace_more):
            replace_more(limit=0)  # не разворачивать «load more» — экономим запросы
        comments = list(forest)
        return sorted(comments, key=lambda c: int(getattr(c, "score", 0) or 0), reverse=True)

    # ------------------------------------------------------------------ #
    # Сборка модели
    # ------------------------------------------------------------------ #
    def _build_story(self, submission: Any, spec: SubredditSpec, text: str,
                     segments: list[str]) -> Story:
        author = getattr(submission, "author", None)
        subreddit = getattr(submission, "subreddit", None)
        return Story(
            id=str(submission.id),
            subreddit=str(getattr(subreddit, "display_name", None) or spec.name),
            title=strip_markdown(getattr(submission, "title", "") or ""),
            permalink=getattr(submission, "permalink", "") or "",
            author=str(getattr(author, "name", None) or "[deleted]"),
            source=spec.source,
            raw_text=(getattr(submission, "selftext", "") or "") if spec.source == "selftext"
            else "\n\n".join(segments),
            text=text,
            segments=segments,
            score=int(getattr(submission, "score", 0) or 0),
            upvote_ratio=float(getattr(submission, "upvote_ratio", 0.0) or 0.0),
            num_comments=int(getattr(submission, "num_comments", 0) or 0),
            created_utc=float(getattr(submission, "created_utc", 0.0) or 0.0),
            over_18=bool(getattr(submission, "over_18", False)),
            flair=str(getattr(submission, "link_flair_text", "") or ""),
            word_count=count_words(text),
            status=StoryStatus.NEW.value,
        )


def scrape(settings: Settings, **kwargs: Any) -> ScrapeReport:
    """Удобная обёртка для оркестратора и cron."""
    return RedditScraper(settings).run(**kwargs)


__all__ = ["RedditScraper", "ScrapeReport", "RejectReason", "scrape"]
