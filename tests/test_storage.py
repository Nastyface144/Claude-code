"""Тесты очереди историй."""

from __future__ import annotations

import json
import time

import pytest

from shorts_factory.models import Story, StoryStatus
from shorts_factory.storage import StoryQueue


def make_story(story_id: str = "abc", **kwargs) -> Story:
    defaults = dict(
        id=story_id, subreddit="tifu", title="T", permalink=f"/r/tifu/{story_id}/",
        author="u", text="text", word_count=120,
    )
    defaults.update(kwargs)
    return Story(**defaults)


def test_add_and_persist_roundtrip(tmp_path):
    path = tmp_path / "queue.json"
    queue = StoryQueue(path)
    assert queue.add(make_story("a1")) is True
    queue.save()

    reloaded = StoryQueue(path)
    assert len(reloaded) == 1
    story = reloaded.get("a1")
    assert story is not None and story.word_count == 120
    assert json.loads(path.read_text(encoding="utf-8"))["version"] == 1


def test_add_is_idempotent(tmp_path):
    queue = StoryQueue(tmp_path / "q.json")
    assert queue.add(make_story("a1")) is True
    assert queue.add(make_story("a1")) is False
    assert len(queue) == 1


def test_seen_survives_removal(tmp_path):
    queue = StoryQueue(tmp_path / "q.json")
    queue.add(make_story("a1"))
    assert queue.remove("a1") is True
    assert len(queue) == 0
    assert queue.is_seen("a1") is True


def test_status_transitions_and_counts(tmp_path):
    queue = StoryQueue(tmp_path / "q.json")
    queue.add(make_story("a1"))
    queue.add(make_story("a2"))
    queue.set_status("a2", StoryStatus.AUDIO_READY)

    assert queue.counts() == {"new": 1, "audio_ready": 1}
    assert [s.id for s in queue.by_status(StoryStatus.NEW)] == ["a1"]
    with pytest.raises(KeyError):
        queue.set_status("nope", StoryStatus.FAILED)


def test_next_pending_is_fifo(tmp_path):
    queue = StoryQueue(tmp_path / "q.json")
    queue.add(make_story("old", fetched_at=time.time() - 100))
    queue.add(make_story("new", fetched_at=time.time()))

    pending = queue.next_pending()
    assert pending is not None and pending.id == "old"


def test_corrupt_file_is_backed_up_not_fatal(tmp_path):
    path = tmp_path / "q.json"
    path.write_text("{ это не json", encoding="utf-8")

    queue = StoryQueue(path)

    assert len(queue) == 0
    assert (tmp_path / "q.json.corrupt").exists()


def test_unknown_fields_are_ignored_on_load(tmp_path):
    path = tmp_path / "q.json"
    path.write_text(json.dumps({
        "version": 1,
        "stories": {"a1": {"id": "a1", "subreddit": "tifu", "title": "T",
                           "permalink": "/p/", "author": "u",
                           "legacy_field": "убрано в новой схеме"}},
        "seen": {"a1": time.time()},
    }), encoding="utf-8")

    queue = StoryQueue(path)
    assert queue.get("a1").title == "T"


def test_old_seen_ids_are_pruned(tmp_path):
    path = tmp_path / "q.json"
    old = time.time() - 200 * 86400
    path.write_text(json.dumps({"version": 1, "stories": {},
                                "seen": {"old": old, "fresh": time.time()}}),
                    encoding="utf-8")

    queue = StoryQueue(path, seen_ttl_days=60)

    assert queue.is_seen("old") is False
    assert queue.is_seen("fresh") is True
