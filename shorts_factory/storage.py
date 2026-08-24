"""Очередь историй на JSON-файле.

Формат файла::

    {
      "version": 1,
      "stories": {"<reddit_id>": {...Story...}, ...},
      "seen": {"<reddit_id>": <timestamp>, ...}
    }

``seen`` хранит id всех рассмотренных постов (включая отклонённые фильтром),
чтобы не тратить квоту API и не показывать один и тот же пост дважды.

Запись атомарная (tmp-файл + ``os.replace``), поэтому прерванный cron-запуск
не оставит битый JSON. Для многопроцессной записи потребуется файловый lock
или переход на SQLite — интерфейс класса это переживёт.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
import time
from pathlib import Path
from typing import Iterable, Iterator

from .models import Story, StoryStatus

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1


class StoryQueue:
    """CRUD поверх JSON-файла очереди."""

    def __init__(self, path: Path | str, *, seen_ttl_days: float | None = 60.0) -> None:
        self.path = Path(path)
        self.seen_ttl_days = seen_ttl_days
        self._stories: dict[str, Story] = {}
        self._seen: dict[str, float] = {}
        self._load()

    # ------------------------------------------------------------------ #
    # Загрузка / сохранение
    # ------------------------------------------------------------------ #
    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            backup = self.path.with_suffix(self.path.suffix + ".corrupt")
            logger.error("Очередь %s повреждена (%s); переименовываю в %s",
                         self.path, exc, backup)
            try:
                self.path.replace(backup)
            except OSError:  # pragma: no cover - гонка/права доступа
                pass
            return

        self._stories = {
            story_id: Story.from_dict(raw)
            for story_id, raw in (data.get("stories") or {}).items()
        }
        self._seen = {k: float(v) for k, v in (data.get("seen") or {}).items()}
        self._prune_seen()

    def _prune_seen(self) -> None:
        if not self.seen_ttl_days:
            return
        cutoff = time.time() - self.seen_ttl_days * 86400
        self._seen = {
            story_id: ts
            for story_id, ts in self._seen.items()
            if ts >= cutoff or story_id in self._stories
        }

    def save(self) -> None:
        """Атомарно записывает очередь на диск."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": SCHEMA_VERSION,
            "stories": {sid: s.to_dict() for sid, s in self._stories.items()},
            "seen": self._seen,
        }
        fd, tmp_name = tempfile.mkstemp(
            dir=str(self.path.parent), prefix=self.path.name, suffix=".tmp"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_name, self.path)
        except BaseException:
            Path(tmp_name).unlink(missing_ok=True)
            raise

    # ------------------------------------------------------------------ #
    # Чтение
    # ------------------------------------------------------------------ #
    def __len__(self) -> int:
        return len(self._stories)

    def __iter__(self) -> Iterator[Story]:
        return iter(sorted(self._stories.values(), key=lambda s: s.fetched_at))

    def __contains__(self, story_id: object) -> bool:
        return story_id in self._stories

    def get(self, story_id: str) -> Story | None:
        return self._stories.get(story_id)

    def by_status(self, status: StoryStatus | str) -> list[Story]:
        value = status.value if isinstance(status, StoryStatus) else status
        return [s for s in self if s.status == value]

    def next_pending(self, status: StoryStatus | str = StoryStatus.NEW) -> Story | None:
        """Самая старая история в заданном статусе (FIFO для оркестратора)."""
        pending = self.by_status(status)
        return pending[0] if pending else None

    def is_seen(self, story_id: str) -> bool:
        return story_id in self._seen or story_id in self._stories

    def counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for story in self._stories.values():
            counts[story.status] = counts.get(story.status, 0) + 1
        return counts

    # ------------------------------------------------------------------ #
    # Запись
    # ------------------------------------------------------------------ #
    def mark_seen(self, story_id: str, *, when: float | None = None) -> None:
        self._seen.setdefault(story_id, when if when is not None else time.time())

    def mark_seen_many(self, story_ids: Iterable[str]) -> None:
        for story_id in story_ids:
            self.mark_seen(story_id)

    def add(self, story: Story) -> bool:
        """Добавляет историю. Возвращает False, если такой id уже в очереди."""
        if story.id in self._stories:
            return False
        story.updated_at = time.time()
        self._stories[story.id] = story
        self.mark_seen(story.id, when=story.fetched_at)
        return True

    def add_many(self, stories: Iterable[Story]) -> int:
        return sum(1 for story in stories if self.add(story))

    def update(self, story: Story) -> None:
        story.updated_at = time.time()
        self._stories[story.id] = story

    def set_status(self, story_id: str, status: StoryStatus | str,
                   *, error: str = "") -> Story:
        story = self._stories.get(story_id)
        if story is None:
            raise KeyError(f"История {story_id!r} не найдена в очереди")
        story.status = status.value if isinstance(status, StoryStatus) else status
        story.error = error
        story.updated_at = time.time()
        return story

    def remove(self, story_id: str) -> bool:
        """Удаляет историю из очереди; id остаётся в ``seen``."""
        return self._stories.pop(story_id, None) is not None
