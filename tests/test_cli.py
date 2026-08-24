"""Тесты CLI (без сети: подменяем скрапер и переменные окружения)."""

from __future__ import annotations

import json

import pytest

from shorts_factory import cli
from shorts_factory.models import Story, StoryStatus
from shorts_factory.storage import StoryQueue


@pytest.fixture
def env(monkeypatch, tmp_path):
    monkeypatch.setenv("REDDIT_CLIENT_ID", "cid")
    monkeypatch.setenv("REDDIT_CLIENT_SECRET", "secret")
    monkeypatch.setenv("REDDIT_USER_AGENT", "python:test:0.1")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("QUEUE_FILE", str(tmp_path / "queue.json"))
    monkeypatch.setenv("LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("MEDIA_DIR", str(tmp_path / "work"))
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path / "output"))
    return tmp_path


def seed_queue(path, story_id="a1", status=StoryStatus.NEW):
    queue = StoryQueue(path)
    queue.add(Story(id=story_id, subreddit="tifu", title="Заголовок",
                    permalink=f"/r/tifu/{story_id}/", author="u",
                    text="текст", word_count=140, status=status.value))
    queue.save()
    return queue


def test_list_and_stats(env, capsys):
    seed_queue(env / "queue.json")

    assert cli.main(["--env-file", "/dev/null", "list"]) == 0
    assert "a1" in capsys.readouterr().out

    assert cli.main(["--env-file", "/dev/null", "stats"]) == 0
    out = capsys.readouterr().out
    assert "new" in out and "ИТОГО" in out


def test_show_missing_story_returns_error(env, capsys):
    seed_queue(env / "queue.json")

    assert cli.main(["--env-file", "/dev/null", "show", "a1"]) == 0
    assert json.loads(capsys.readouterr().out)["id"] == "a1"

    assert cli.main(["--env-file", "/dev/null", "show", "nope"]) == 1


def test_remove(env):
    seed_queue(env / "queue.json")

    assert cli.main(["--env-file", "/dev/null", "remove", "a1"]) == 0
    assert len(StoryQueue(env / "queue.json")) == 0
    assert cli.main(["--env-file", "/dev/null", "remove", "a1"]) == 1


def test_scrape_passes_cli_overrides(env, monkeypatch):
    captured = {}

    class FakeScraper:
        def __init__(self, settings, queue=None):
            captured["settings"] = settings

        def run(self, **kwargs):
            captured["run"] = kwargs
            return _EmptyReport()

    class _EmptyReport:
        stories: list = []
        errors: list = []

        def summary(self):
            return "просмотрено=0; принято=0"

    monkeypatch.setattr(cli, "RedditScraper", FakeScraper)

    assert cli.main(["--env-file", "/dev/null", "scrape", "--subreddits",
                     "tifu,AskReddit:comments", "--time-filter", "week",
                     "--post-limit", "5", "--max-stories", "2", "--dry-run"]) == 0

    run = captured["run"]
    assert [s.name for s in run["subreddits"]] == ["tifu", "AskReddit"]
    assert run["subreddits"][1].source == "comments"
    assert run["time_filter"] == "week"
    assert run["post_limit"] == 5
    assert run["max_stories"] == 2
    assert run["dry_run"] is True


def test_missing_credentials_exit_code(monkeypatch, tmp_path, capsys):
    for key in ("REDDIT_CLIENT_ID", "REDDIT_CLIENT_SECRET"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("QUEUE_FILE", str(tmp_path / "queue.json"))
    monkeypatch.setenv("LOG_DIR", str(tmp_path / "logs"))

    assert cli.main(["--env-file", "/dev/null", "scrape"]) == 2
    assert "REDDIT_CLIENT_ID" in capsys.readouterr().err
