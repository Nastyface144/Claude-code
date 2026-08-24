"""Тесты модуля 1: фильтры, сборка истории из комментариев, ретраи, дедупликация."""

from __future__ import annotations

import pytest

from shorts_factory.config import SubredditSpec
from shorts_factory.models import StoryStatus
from shorts_factory.pipeline.reddit_scraper import RedditScraper, RejectReason
from shorts_factory.storage import StoryQueue

from .conftest import FakeReddit, make_comment, make_submission, words


def make_scraper(settings, submissions_by_sub, *, queue=None, reddit=None):
    return RedditScraper(
        settings,
        queue=queue if queue is not None else StoryQueue(settings.paths.queue_file),
        reddit=reddit if reddit is not None else FakeReddit(submissions_by_sub),
        sleep=lambda _: None,
    )


def test_accepts_post_in_word_window(settings):
    post = make_submission(selftext=words(150), title="So this happened")
    report = make_scraper(settings, {"tifu": [post]}).run()

    assert report.accepted == 1
    story = report.stories[0]
    assert story.id == post.id
    assert story.word_count == 150
    assert story.status == StoryStatus.NEW.value
    assert story.subreddit == "tifu"
    assert story.url.endswith(post.permalink)


@pytest.mark.parametrize(
    "kwargs, reason",
    [
        ({"selftext": words(40)}, RejectReason.TOO_SHORT),
        ({"selftext": words(400)}, RejectReason.TOO_LONG),
        ({"selftext": words(150), "score": 10}, RejectReason.LOW_SCORE),
        ({"selftext": words(150), "upvote_ratio": 0.5}, RejectReason.LOW_RATIO),
        ({"selftext": words(150), "over_18": True}, RejectReason.NSFW),
        ({"selftext": words(150), "stickied": True}, RejectReason.STICKIED),
        ({"selftext": "[removed]"}, RejectReason.NO_TEXT),
        ({"selftext": ""}, RejectReason.NO_TEXT),
    ],
)
def test_filters_reject_posts(settings, kwargs, reason):
    report = make_scraper(settings, {"tifu": [make_submission(**kwargs)]}).run()

    assert report.accepted == 0
    assert report.rejected == {reason: 1}


def test_nsfw_allowed_when_configured(settings):
    object.__setattr__(settings.scraper, "allow_nsfw", True)
    post = make_submission(selftext=words(120), over_18=True)

    report = make_scraper(settings, {"tifu": [post]}).run()

    assert report.accepted == 1
    assert report.stories[0].over_18 is True


def test_markdown_is_stripped_before_counting(settings):
    raw = f"**Bold** [link](https://example.com) {words(120)}\n\n> quote"
    report = make_scraper(settings, {"tifu": [make_submission(selftext=raw)]}).run()

    story = report.stories[0]
    assert "https://" not in story.text
    assert "**" not in story.text
    assert story.raw_text == raw  # оригинал сохраняется для отладки


def test_story_assembled_from_top_comments(settings):
    spec = SubredditSpec("AskReddit", "comments")
    post = make_submission(
        subreddit="AskReddit",
        title="What is your worst date?",
        selftext="",
        comments=[
            make_comment(words(30, "short"), score=10),
            make_comment(words(5, "tiny"), score=999),          # короче min_comment_words
            make_comment("[deleted]", score=900),                # удалён
            make_comment(words(60, "best"), score=800),
            make_comment(words(50, "second"), score=500, stickied=True),  # закреплён
            make_comment(words(45, "third"), score=400),
        ],
    )

    report = make_scraper(settings, {"AskReddit": [post]}).run(subreddits=[spec])

    assert report.accepted == 1
    story = report.stories[0]
    assert story.source == "comments"
    assert len(story.segments) == 2          # 60 + 45 = 105 >= min_words
    assert story.segments[0].startswith("best")
    assert story.segments[1].startswith("third")
    assert 100 <= story.word_count <= 200
    assert post.comments.replace_more_calls == [0]  # «load more» не разворачивали


def test_comments_mode_rejects_when_nothing_usable(settings):
    spec = SubredditSpec("AskReddit", "comments")
    post = make_submission(
        subreddit="AskReddit",
        comments=[make_comment(words(3), score=100), make_comment("[deleted]")],
    )

    report = make_scraper(settings, {"AskReddit": [post]}).run(subreddits=[spec])

    assert report.accepted == 0
    assert report.rejected == {RejectReason.NO_USABLE_COMMENTS: 1}


def test_duplicates_skipped_across_runs(settings):
    post = make_submission(selftext=words(150))
    queue = StoryQueue(settings.paths.queue_file)

    first = make_scraper(settings, {"tifu": [post]}, queue=queue).run()
    assert first.accepted == 1

    reloaded = StoryQueue(settings.paths.queue_file)
    second = make_scraper(settings, {"tifu": [post]}, queue=reloaded).run()

    assert second.accepted == 0
    assert second.rejected == {RejectReason.ALREADY_SEEN: 1}
    assert len(reloaded) == 1


def test_rejected_post_is_remembered_and_not_refetched(settings):
    post = make_submission(selftext=words(10))
    queue = StoryQueue(settings.paths.queue_file)

    make_scraper(settings, {"tifu": [post]}, queue=queue).run()
    second = make_scraper(settings, {"tifu": [post]}, queue=queue).run()

    assert second.rejected == {RejectReason.ALREADY_SEEN: 1}


def test_max_stories_per_run_respected(settings):
    posts = [make_submission(selftext=words(120)) for _ in range(6)]

    report = make_scraper(settings, {"tifu": posts}).run(max_stories=2)

    assert report.accepted == 2
    assert len(report.stories) == 2


def test_subreddit_error_does_not_stop_run(settings):
    specs = [SubredditSpec("broken"), SubredditSpec("tifu")]
    good = make_submission(selftext=words(130))

    class PartiallyBrokenReddit(FakeReddit):
        def subreddit(self, name):
            if name == "broken":
                raise RuntimeError("500 Server Error")
            return super().subreddit(name)

    report = make_scraper(
        settings, {"tifu": [good]}, reddit=PartiallyBrokenReddit({"tifu": [good]})
    ).run(subreddits=specs)

    assert report.accepted == 1
    assert len(report.errors) == 1
    assert report.rejected.get(RejectReason.ERROR) == 1


def test_retries_transient_failure_then_succeeds(settings):
    good = make_submission(selftext=words(130))
    attempts = {"n": 0}

    class FlakyListing:
        display_name = "tifu"

        def top(self, time_filter="all", limit=None):
            attempts["n"] += 1
            if attempts["n"] < 3:
                raise ConnectionError("сеть моргнула")
            return iter([good])

    class FlakyReddit:
        read_only = True

        def subreddit(self, name):
            return FlakyListing()

    report = make_scraper(settings, {}, reddit=FlakyReddit()).run()

    assert attempts["n"] == 3
    assert report.accepted == 1


def test_retries_give_up_and_report_error(settings):
    class AlwaysFailingListing:
        def top(self, time_filter="all", limit=None):
            raise ConnectionError("сеть недоступна")

    class FailingReddit:
        read_only = True

        def subreddit(self, name):
            return AlwaysFailingListing()

    report = make_scraper(settings, {}, reddit=FailingReddit()).run()

    assert report.accepted == 0
    assert report.errors and "tifu" in report.errors[0]


def test_dry_run_does_not_write_queue(settings):
    post = make_submission(selftext=words(150))

    report = make_scraper(settings, {"tifu": [post]}).run(dry_run=True)

    assert report.accepted == 1
    assert not settings.paths.queue_file.exists()


def test_time_filter_and_limit_passed_to_api(settings):
    reddit = FakeReddit({"tifu": [make_submission(selftext=words(150))]})

    make_scraper(settings, {}, reddit=reddit).run(time_filter="week", post_limit=7)

    assert reddit.calls == [("tifu", "week", 7)]
