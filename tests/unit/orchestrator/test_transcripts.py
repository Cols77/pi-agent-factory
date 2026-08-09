from __future__ import annotations

import pytest
from factory.orchestrator.transcripts import write_role_transcript

pytestmark = pytest.mark.unit


def test_writes_transcript_to_the_expected_path(tmp_path):
    path = write_role_transcript(tmp_path, "dev", 2, "raw agent output")
    assert path == tmp_path / "dev-attempt2.log"
    assert path.read_text(encoding="utf-8") == "raw agent output"


def test_creates_intermediate_directories(tmp_path):
    target = tmp_path / "nested" / "dir"
    write_role_transcript(target, "review", 1, "x")
    assert target.is_dir()


def test_separate_attempts_do_not_overwrite_each_other(tmp_path):
    write_role_transcript(tmp_path, "dev", 1, "first attempt")
    write_role_transcript(tmp_path, "dev", 2, "second attempt")
    assert (tmp_path / "dev-attempt1.log").read_text(encoding="utf-8") == "first attempt"
    assert (tmp_path / "dev-attempt2.log").read_text(encoding="utf-8") == "second attempt"


def test_streaming_message_updates_are_not_persisted(tmp_path):
    """`message_update` is a cumulative snapshot, not a delta.

    Pi emits one per streamed chunk, each carrying the whole message so far, so
    persisting them makes a transcript grow with the SQUARE of message length.
    Measured on one real context-gather run: 21,278 update records across 26
    messages (818 per message) = 666MB of a 671MB log. `message_end` carries
    the final content, so nothing durable is lost by dropping them.
    """
    import json

    raw = "\n".join([
        json.dumps({"type": "session", "id": "s1"}),
        json.dumps({"type": "message_start", "message": {"role": "assistant"}}),
        json.dumps({"type": "message_update", "message": {"content": "He"}}),
        json.dumps({"type": "message_update", "message": {"content": "Hello"}}),
        json.dumps({"type": "message_update", "message": {"content": "Hello wo"}}),
        json.dumps({"type": "message_end", "message": {"content": "Hello world"}}),
        json.dumps({"type": "agent_end"}),
    ])
    path = write_role_transcript(tmp_path, "dev", 1, raw)
    kept = [json.loads(line)["type"] for line in path.read_text(encoding="utf-8").splitlines() if line]

    assert "message_update" not in kept
    assert kept == ["session", "message_start", "message_end", "agent_end"]
    # The final content survives -- that is why dropping the updates is safe.
    assert "Hello world" in path.read_text(encoding="utf-8")


def test_non_json_lines_are_passed_through_unchanged(tmp_path):
    """A backend that is not emitting pi's JSONL stream (or a crash dump
    interleaved into it) must still be recorded verbatim."""
    raw = "traceback: boom\nnot json at all\n"
    path = write_role_transcript(tmp_path, "dev", 1, raw)
    assert path.read_text(encoding="utf-8") == raw
