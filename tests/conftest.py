"""Фейки Reddit-объектов: тесты не ходят в сеть и не требуют ключей API."""

from __future__ import annotations

import itertools
from types import SimpleNamespace

import pytest

from shorts_factory.config import (
    Paths,
    RedditConfig,
    ScraperConfig,
    Settings,
    SubredditSpec,
)

_ids = itertools.count(1)


class FakeAuthor(SimpleNamespace):
    pass


class FakeComment(SimpleNamespace):
    pass


class FakeCommentForest(list):
    """Имитация praw.models.comment_forest.CommentForest."""

    def __init__(self, comments):
        super().__init__(comments)
        self.replace_more_calls = []

    def replace_more(self, limit=0):
        self.replace_more_calls.append(limit)
        return []


class FakeSubmission(SimpleNamespace):
    pass


def make_comment(body: str, *, score: int = 100, author: str | None = "user",
                 stickied: bool = False) -> FakeComment:
    return FakeComment(
        body=body,
        score=score,
        author=FakeAuthor(name=author) if author else None,
        stickied=stickied,
    )


def make_submission(
    *,
    id: str | None = None,
    title: str = "Test title",
    selftext: str = "",
    score: int = 5000,
    upvote_ratio: float = 0.95,
    num_comments: int = 120,
    over_18: bool = False,
    stickied: bool = False,
    subreddit: str = "tifu",
    author: str | None = "storyteller",
    comments=None,
) -> FakeSubmission:
    post_id = id or f"post{next(_ids)}"
    return FakeSubmission(
        id=post_id,
        title=title,
        selftext=selftext,
        score=score,
        upvote_ratio=upvote_ratio,
        num_comments=num_comments,
        over_18=over_18,
        stickied=stickied,
        pinned=False,
        created_utc=1_700_000_000.0,
        permalink=f"/r/{subreddit}/comments/{post_id}/test/",
        link_flair_text="",
        subreddit=SimpleNamespace(display_name=subreddit),
        author=FakeAuthor(name=author) if author else None,
        comments=FakeCommentForest(comments or []),
    )


class FakeSubredditListing:
    def __init__(self, name: str, submissions, calls: list):
        self.display_name = name
        self._submissions = submissions
        self._calls = calls

    def top(self, time_filter="all", limit=None):
        self._calls.append((self.display_name, time_filter, limit))
        return iter(self._submissions[:limit] if limit else self._submissions)


class FakeReddit:
    """Минимальный praw.Reddit: отдаёт заранее заданные посты по сабреддитам."""

    def __init__(self, submissions_by_subreddit: dict[str, list], error: Exception | None = None):
        self._data = submissions_by_subreddit
        self._error = error
        self.calls: list = []
        self.read_only = True

    def subreddit(self, name: str):
        if self._error is not None:
            raise self._error
        return FakeSubredditListing(name, self._data.get(name, []), self.calls)


def words(n: int, word: str = "word") -> str:
    """Текст ровно из n слов."""
    return " ".join([word] * n)


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(
        reddit=RedditConfig(
            client_id="id", client_secret="secret", user_agent="test:agent:0.1"
        ),
        scraper=ScraperConfig(
            subreddits=(SubredditSpec("tifu", "selftext"),),
            time_filter="day",
            post_limit=10,
            min_words=100,
            max_words=200,
            min_score=500,
            min_upvote_ratio=0.85,
            allow_nsfw=False,
            max_stories_per_run=5,
            comment_limit=10,
            min_comment_words=25,
            request_delay_seconds=0.0,
            max_retries=3,
            retry_base_delay=0.0,
        ),
        paths=Paths(
            data_dir=tmp_path,
            queue_file=tmp_path / "queue.json",
            media_dir=tmp_path / "work",
            output_dir=tmp_path / "output",
            backgrounds_dir=tmp_path / "bg",
            log_dir=tmp_path / "logs",
        ),
    )
