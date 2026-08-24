"""Тесты конфигурации."""

from __future__ import annotations

import pytest

from shorts_factory.config import ConfigError, Settings, SubredditSpec


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for key in list(__import__("os").environ):
        if key.startswith(("REDDIT_", "SUBREDDITS", "TIME_FILTER", "MIN_", "MAX_",
                           "POST_LIMIT", "ALLOW_NSFW", "DATA_DIR", "QUEUE_FILE")):
            monkeypatch.delenv(key, raising=False)


def test_subreddit_spec_parsing():
    assert SubredditSpec.parse("tifu") == SubredditSpec("tifu", "selftext")
    assert SubredditSpec.parse("r/AskReddit:comments") == SubredditSpec("AskReddit", "comments")
    assert SubredditSpec.parse(" /r/tifu : selftext ") == SubredditSpec("tifu", "selftext")


def test_subreddit_spec_rejects_unknown_source():
    with pytest.raises(ConfigError):
        SubredditSpec.parse("tifu:magic")


def test_load_from_env(monkeypatch, tmp_path):
    monkeypatch.setenv("REDDIT_CLIENT_ID", "cid")
    monkeypatch.setenv("REDDIT_CLIENT_SECRET", "secret")
    monkeypatch.setenv("REDDIT_USER_AGENT", "python:test:0.1")
    monkeypatch.setenv("SUBREDDITS", "tifu, AskReddit:comments")
    monkeypatch.setenv("MIN_WORDS", "80")
    monkeypatch.setenv("MAX_WORDS", "160")
    monkeypatch.setenv("ALLOW_NSFW", "yes")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))

    settings = Settings.load(env_file=None)

    assert settings.reddit.client_id == "cid"
    assert [s.name for s in settings.scraper.subreddits] == ["tifu", "AskReddit"]
    assert settings.scraper.subreddits[1].source == "comments"
    assert settings.scraper.min_words == 80
    assert settings.scraper.allow_nsfw is True
    assert settings.paths.queue_file == tmp_path / "queue.json"


def test_invalid_values_are_rejected(monkeypatch):
    monkeypatch.setenv("MIN_WORDS", "200")
    monkeypatch.setenv("MAX_WORDS", "100")
    with pytest.raises(ConfigError):
        Settings.load(env_file=None)

    monkeypatch.setenv("MAX_WORDS", "300")
    monkeypatch.setenv("TIME_FILTER", "decade")
    with pytest.raises(ConfigError):
        Settings.load(env_file=None)

    monkeypatch.delenv("TIME_FILTER")
    monkeypatch.setenv("POST_LIMIT", "много")
    with pytest.raises(ConfigError):
        Settings.load(env_file=None)


def test_missing_credentials_reported_clearly():
    settings = Settings.load(env_file=None)
    with pytest.raises(ConfigError) as exc:
        settings.reddit.require_credentials()
    assert "REDDIT_CLIENT_ID" in str(exc.value)


def test_env_file_does_not_override_real_env(monkeypatch, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("REDDIT_CLIENT_ID=from_file\n", encoding="utf-8")
    monkeypatch.setenv("REDDIT_CLIENT_ID", "from_env")

    settings = Settings.load(env_file)

    assert settings.reddit.client_id == "from_env"
