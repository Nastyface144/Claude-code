"""CLI пайплайна. Пока доступен модуль 1 (сбор историй) и работа с очередью.

    python -m shorts_factory.cli scrape --time-filter week --dry-run
    python -m shorts_factory.cli list --status new
    python -m shorts_factory.cli show <story_id>
    python -m shorts_factory.cli stats
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone

from .config import ConfigError, Settings, SubredditSpec, VALID_TIME_FILTERS
from .logging_setup import configure_logging
from .models import StoryStatus
from .pipeline.reddit_scraper import RedditScraper
from .storage import StoryQueue


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="shorts-factory",
        description="Reddit -> YouTube Shorts: сбор историй и управление очередью.",
    )
    parser.add_argument("--env-file", default=".env", help="путь к .env (по умолчанию .env)")
    parser.add_argument("--log-level", default=None, help="DEBUG/INFO/WARNING/ERROR")
    sub = parser.add_subparsers(dest="command", required=True)

    scrape = sub.add_parser("scrape", help="собрать истории с Reddit в очередь")
    scrape.add_argument("--subreddits", help="переопределить SUBREDDITS, напр. 'tifu,AskReddit:comments'")
    scrape.add_argument("--time-filter", choices=VALID_TIME_FILTERS, help="период выборки топа")
    scrape.add_argument("--post-limit", type=int, help="сколько постов запрашивать из сабреддита")
    scrape.add_argument("--max-stories", type=int, help="сколько историй добавить за запуск")
    scrape.add_argument("--dry-run", action="store_true", help="не сохранять очередь на диск")

    listing = sub.add_parser("list", help="показать истории в очереди")
    listing.add_argument("--status", default=None, help="фильтр по статусу, напр. new")
    listing.add_argument("--limit", type=int, default=20)

    show = sub.add_parser("show", help="показать историю целиком (JSON)")
    show.add_argument("story_id")

    sub.add_parser("stats", help="счётчики по статусам")

    remove = sub.add_parser("remove", help="убрать историю из очереди")
    remove.add_argument("story_id")
    return parser


def _fmt_time(ts: float) -> str:
    if not ts:
        return "-"
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        settings = Settings.load(args.env_file)
    except ConfigError as exc:
        print(f"Ошибка конфигурации: {exc}", file=sys.stderr)
        return 2

    configure_logging(args.log_level or settings.log_level, settings.paths.log_dir)
    settings.paths.ensure()
    queue = StoryQueue(settings.paths.queue_file)

    if args.command == "scrape":
        specs = None
        if args.subreddits:
            specs = [SubredditSpec.parse(item) for item in args.subreddits.split(",") if item.strip()]
        try:
            report = RedditScraper(settings, queue=queue).run(
                subreddits=specs,
                time_filter=args.time_filter,
                post_limit=args.post_limit,
                max_stories=args.max_stories,
                dry_run=args.dry_run,
            )
        except ConfigError as exc:
            print(f"Ошибка конфигурации: {exc}", file=sys.stderr)
            return 2
        print(report.summary())
        for story in report.stories:
            print(f"  {story.id}  r/{story.subreddit:<16} {story.word_count:>4} сл.  {story.title[:60]}")
        return 0 if not report.errors else 1

    if args.command == "list":
        stories = queue.by_status(args.status) if args.status else list(queue)
        if not stories:
            print("Очередь пуста.")
            return 0
        for story in stories[: args.limit]:
            print(f"{story.id}  {story.status:<14} r/{story.subreddit:<16} "
                  f"{story.word_count:>4} сл.  {_fmt_time(story.fetched_at)}  {story.title[:50]}")
        print(f"\nПоказано {min(len(stories), args.limit)} из {len(stories)}.")
        return 0

    if args.command == "show":
        story = queue.get(args.story_id)
        if story is None:
            print(f"История {args.story_id} не найдена.", file=sys.stderr)
            return 1
        print(json.dumps(story.to_dict(), ensure_ascii=False, indent=2))
        return 0

    if args.command == "stats":
        counts = queue.counts()
        if not counts:
            print("Очередь пуста.")
            return 0
        for status in StoryStatus:
            if status.value in counts:
                print(f"{status.value:<16} {counts[status.value]}")
        print(f"{'ИТОГО':<16} {len(queue)}")
        return 0

    if args.command == "remove":
        if queue.remove(args.story_id):
            queue.save()
            print(f"История {args.story_id} удалена из очереди.")
            return 0
        print(f"История {args.story_id} не найдена.", file=sys.stderr)
        return 1

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
