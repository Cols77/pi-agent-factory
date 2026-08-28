from __future__ import annotations

import json
from pathlib import Path

import pytest

from coherence.planning.resolution import ResolutionError, append_resolution_event, read_resolution_events

pytestmark = pytest.mark.unit


def test_resolution_events_are_sequenced_and_append_only(tmp_path: Path) -> None:
    first = append_resolution_event(
        tmp_path, run_id="run-1", stage="spec_alignment", iteration=1,
        finding_id="f-1", disposition="resolve_in_loop", actor_kind="agent",
        prompt="fix it", answer_or_fix="fixed", pre_artifact_hashes={"a": "0" * 64}, post_artifact_hashes={"a": "1" * 64},
    )
    second = append_resolution_event(
        tmp_path, run_id="run-1", stage="spec_alignment", iteration=2,
        finding_id="f-1", disposition="informational", actor_kind="human",
        prompt="ok", answer_or_fix="noted", pre_artifact_hashes={"a": "1" * 64}, post_artifact_hashes={"a": "1" * 64},
    )
    assert first == second
    events = read_resolution_events(tmp_path, "run-1")
    assert [event["sequence"] for event in events] == [1, 2]
    assert len(first.read_text(encoding="utf-8").splitlines()) == 2


def test_resolution_rejects_invalid_disposition_and_secrets(tmp_path: Path) -> None:
    with pytest.raises(ResolutionError):
        append_resolution_event(
            tmp_path, run_id="run", stage="spec_alignment", iteration=1,
            finding_id="f", disposition="approve", actor_kind="agent", prompt="p",
            answer_or_fix="x", pre_artifact_hashes={}, post_artifact_hashes={},
        )
    with pytest.raises(ResolutionError):
        append_resolution_event(
            tmp_path, run_id="run", stage="spec_alignment", iteration=1,
            finding_id="f", disposition="informational", actor_kind="agent", prompt="token: abc",
            answer_or_fix="x", pre_artifact_hashes={}, post_artifact_hashes={},
        )


def test_resolution_reader_revalidates_hashes_and_sensitive_text(tmp_path: Path) -> None:
    journal = tmp_path / ".factory" / "planning" / "run" / "resolution-events.jsonl"
    journal.parent.mkdir(parents=True)
    event = {
        "schema": 1, "run_id": "run", "sequence": 1, "stage": "spec_alignment",
        "iteration": 1, "finding_id": "f", "disposition": "informational",
        "prompt": "prompt", "answer_or_fix": "answer", "pre_artifact_hashes": {"a": "bad"},
        "post_artifact_hashes": {}, "actor_kind": "agent", "timestamp": "2026-01-01T00:00:00Z",
    }
    journal.write_text(json.dumps(event) + "\n", encoding="utf-8")
    with pytest.raises(ResolutionError):
        read_resolution_events(tmp_path, "run")

    event["pre_artifact_hashes"] = {}
    event["prompt"] = "token: leaked"
    journal.write_text(json.dumps(event) + "\n", encoding="utf-8")
    with pytest.raises(ResolutionError):
        read_resolution_events(tmp_path, "run")
