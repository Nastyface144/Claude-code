"""Доменные модели пайплайна.

`Story` — единица работы: она создаётся скрапером и по мере прохождения
пайплайна обрастает путями к артефактам (текст, аудио, субтитры, видео).
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class StoryStatus(str, Enum):
    """Статус истории в очереди. Порядок соответствует шагам пайплайна."""

    NEW = "new"                      # 1. собрана скрапером
    TEXT_READY = "text_ready"        # 2. текст очищен/адаптирован
    AUDIO_READY = "audio_ready"      # 3. озвучка готова
    SUBS_READY = "subs_ready"        # 4. .ass субтитры готовы
    VIDEO_READY = "video_ready"      # 6. видео собрано
    PENDING_REVIEW = "pending_review"  # 8. ждёт ручной проверки
    APPROVED = "approved"            # 8. проверено человеком
    UPLOADED = "uploaded"            # 7. опубликовано на YouTube
    REJECTED = "rejected"            # отклонено человеком
    FAILED = "failed"                # ошибка на каком-то шаге


@dataclass
class Story:
    """История с Reddit и её артефакты."""

    # --- источник ---
    id: str                       # id поста на Reddit, напр. "1a2b3c"
    subreddit: str
    title: str
    permalink: str
    author: str
    source: str = "selftext"      # selftext | comments
    raw_text: str = ""            # текст как есть (markdown)
    text: str = ""                # очищенный текст для озвучки
    segments: list[str] = field(default_factory=list)  # для source=comments

    # --- метаданные поста ---
    score: int = 0
    upvote_ratio: float = 0.0
    num_comments: int = 0
    created_utc: float = 0.0
    over_18: bool = False
    flair: str = ""
    word_count: int = 0

    # --- состояние пайплайна ---
    status: str = StoryStatus.NEW.value
    fetched_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    error: str = ""

    # --- артефакты последующих модулей ---
    script_path: str = ""
    audio_path: str = ""
    audio_duration: float = 0.0
    subtitle_path: str = ""
    background_path: str = ""
    video_path: str = ""
    youtube_video_id: str = ""

    @property
    def url(self) -> str:
        return f"https://www.reddit.com{self.permalink}" if self.permalink else ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Story":
        """Терпимо относится к лишним/недостающим полям (миграции схемы)."""
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in data.items() if k in known})
