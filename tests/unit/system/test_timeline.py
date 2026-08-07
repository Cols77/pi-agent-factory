"""Tests for factory.system.queries.query_timeline (design SS4.3, SS7.4).

Timeline carries the highest-risk rules in the whole navigator: ordering,
fallback, and unknown-actor handling are exactly the places a query could
assert something the evidence does not support. Every test here pins one of
those rules against real files in a temp repo -- nothing is asserted from a
mock or a hand-built dataclass standing in for a query result.

Recorded source: signed review decision records at
`evidence/runs/<run_id>/reviews/review-<NNN>.json` (the shape
`factory.orchestrator.human_review.FileHumanReviewGate._archive` writes).
See the comment block above `_iter_decision_records` in `queries.py` for why
this is the only source used, and why validation-report entries and task
ledger status are deliberately excluded (no recorded timestamp or sequence
number backs either one in this repo).
"""
from __future__ import annotations

import pytest

from factory.system.queries import query_timeline
from factory.system.models import SystemScopeRef
from factory.validation.schema_validator import SCHEMA_DIR, validate

from ._fixtures import (
    write_bundle,
    write_decision_artifact,
    write_decision_artifact_raw,
    write_sr,
    write_task,
)

pytestmark = pytest.mark.unit

TIMELINE_EVENT_SCHEMA = SCHEMA_DIR / "system_timeline_event.schema.json"


# ---------------------------------------------------------------------------
# Ordering is deterministic from recorded timestamps
# ---------------------------------------------------------------------------


def test_ordering_is_deterministic_from_recorded_timestamps(tmp_path):
    write_task(tmp_path / "tasks", "T-001", status="done")
    write_bundle(tmp_path / "bundles", "b1", "Bundle", ["task:T-001"])
    # Written out of chronological order, and with run/sequence numbering
    # that would sort the *other* way if ordering were accidentally keyed
    # off the filename glob instead of the recorded timestamp.
    write_decision_artifact(
        tmp_path, task_id="T-001", run_id="run-b", sequence=1, reviewed_at="2026-08-08T15:00:00Z", decision="approve"
    )
    write_decision_artifact(
        tmp_path, task_id="T-001", run_id="run-a", sequence=1, reviewed_at="2026-08-08T09:00:00Z", decision="reject"
    )
    write_decision_artifact(
        tmp_path, task_id="T-001", run_id="run-c", sequence=1, reviewed_at="2026-08-08T12:00:00Z", decision="approve"
    )

    result = query_timeline(tmp_path, SystemScopeRef(kind="bundle", ref="bundle:b1"))

    timestamps = [e["at"] for e in result["events"]]
    assert timestamps == sorted(timestamps)
    assert timestamps == [
        "2026-08-08T09:00:00Z",
        "2026-08-08T12:00:00Z",
        "2026-08-08T15:00:00Z",
    ]


def test_ordering_is_stable_and_repeatable_across_calls(tmp_path):
    write_task(tmp_path / "tasks", "T-001", status="done")
    write_bundle(tmp_path / "bundles", "b1", "Bundle", ["task:T-001"])
    write_decision_artifact(tmp_path, task_id="T-001", run_id="run-a", reviewed_at="2026-08-08T09:00:00Z")
    write_decision_artifact(tmp_path, task_id="T-001", run_id="run-b", reviewed_at="2026-08-08T10:00:00Z")

    first = query_timeline(tmp_path, SystemScopeRef(kind="bundle", ref="bundle:b1"))
    second = query_timeline(tmp_path, SystemScopeRef(kind="bundle", ref="bundle:b1"))

    assert first == second


# ---------------------------------------------------------------------------
# Missing timestamps fall back to recorded sequence numbers, with a warning
# ---------------------------------------------------------------------------


def test_missing_timestamp_falls_back_to_recorded_sequence_number(tmp_path):
    write_task(tmp_path / "tasks", "T-001", status="done")
    write_bundle(tmp_path / "bundles", "b1", "Bundle", ["task:T-001"])
    write_decision_artifact(
        tmp_path, task_id="T-001", run_id="run-a", sequence=1, reviewed_at=None, decision="approve"
    )

    result = query_timeline(tmp_path, SystemScopeRef(kind="bundle", ref="bundle:b1"))

    assert len(result["events"]) == 1
    event = result["events"][0]
    assert event["at"] is None
    assert event["sequence"] == 1
    # The fallback is visible, not silent.
    assert event["freshness"]["state"] == "degraded"
    assert "sequence" in event["freshness"]["reason"]


def test_events_with_timestamps_sort_before_sequence_only_fallback_events(tmp_path):
    write_task(tmp_path / "tasks", "T-001", status="done")
    write_bundle(tmp_path / "bundles", "b1", "Bundle", ["task:T-001"])
    write_decision_artifact(
        tmp_path, task_id="T-001", run_id="run-a", sequence=1, reviewed_at=None, decision="approve"
    )
    write_decision_artifact(
        tmp_path, task_id="T-001", run_id="run-b", sequence=1, reviewed_at="2026-08-08T09:00:00Z", decision="reject"
    )

    result = query_timeline(tmp_path, SystemScopeRef(kind="bundle", ref="bundle:b1"))

    assert [e["at"] for e in result["events"]] == ["2026-08-08T09:00:00Z", None]


def test_sequence_only_events_sort_by_sequence_among_themselves(tmp_path):
    write_task(tmp_path / "tasks", "T-001", status="done")
    write_bundle(tmp_path / "bundles", "b1", "Bundle", ["task:T-001"])
    write_decision_artifact(
        tmp_path, task_id="T-001", run_id="run-a", sequence=3, reviewed_at=None, decision="approve"
    )
    write_decision_artifact(
        tmp_path, task_id="T-001", run_id="run-a", sequence=1, reviewed_at=None, decision="reject"
    )
    write_decision_artifact(
        tmp_path, task_id="T-001", run_id="run-a", sequence=2, reviewed_at=None, decision="approve"
    )

    result = query_timeline(tmp_path, SystemScopeRef(kind="bundle", ref="bundle:b1"))

    assert [e["sequence"] for e in result["events"]] == [1, 2, 3]


def test_record_with_neither_timestamp_nor_sequence_is_dropped_and_degrades_scope(tmp_path):
    # No `review-<N>.json` filename to derive a sequence from, and no
    # reviewed_at -- there is no recorded ordering basis at all, so this
    # record must not become a fabricated event. It is dropped, and the
    # drop is surfaced via `degraded`, not silently absorbed.
    write_task(tmp_path / "tasks", "T-001", status="done")
    write_bundle(tmp_path / "bundles", "b1", "Bundle", ["task:T-001"])
    write_decision_artifact_raw(
        tmp_path,
        run_id="run-a",
        filename="review-unordered.json",
        payload={
            "version": 1,
            "reviewed_at": None,
            "task_id": "T-001",
            "start_commit": "abc123",
            "decision": "approve",
            "annotations": [],
            "reviewed_files": [],
        },
    )

    result = query_timeline(tmp_path, SystemScopeRef(kind="bundle", ref="bundle:b1"))

    assert result["events"] == []
    assert result["degraded"] is True


# ---------------------------------------------------------------------------
# Absent actor/action is unknown/not-recorded; the event is marked degraded
# ---------------------------------------------------------------------------


def test_actor_is_not_recorded_never_guessed(tmp_path):
    # The review-decision artifact shape has no field naming a reviewer at
    # all -- actor must never be filled in with a plausible value (e.g.
    # "human", because a human review gate wrote the file).
    write_task(tmp_path / "tasks", "T-001", status="done")
    write_bundle(tmp_path / "bundles", "b1", "Bundle", ["task:T-001"])
    write_decision_artifact(tmp_path, task_id="T-001")

    result = query_timeline(tmp_path, SystemScopeRef(kind="bundle", ref="bundle:b1"))

    assert len(result["events"]) == 1
    event = result["events"][0]
    assert event["actor"] == "not-recorded"
    assert event["freshness"]["state"] == "degraded"
    assert "actor" in event["freshness"]["reason"]


def test_unrecognized_decision_value_is_action_not_recorded(tmp_path):
    write_task(tmp_path / "tasks", "T-001", status="done")
    write_bundle(tmp_path / "bundles", "b1", "Bundle", ["task:T-001"])
    write_decision_artifact(tmp_path, task_id="T-001", decision="defer")  # not approve/reject

    result = query_timeline(tmp_path, SystemScopeRef(kind="bundle", ref="bundle:b1"))

    assert len(result["events"]) == 1
    assert result["events"][0]["action"] == "not-recorded"
    assert result["events"][0]["freshness"]["state"] == "degraded"


@pytest.mark.parametrize("decision,expected_action", [("approve", "approved"), ("reject", "rejected")])
def test_recognized_decision_values_map_to_recorded_action(tmp_path, decision, expected_action):
    write_task(tmp_path / "tasks", "T-001", status="done")
    write_bundle(tmp_path / "bundles", "b1", "Bundle", ["task:T-001"])
    write_decision_artifact(tmp_path, task_id="T-001", decision=decision)

    result = query_timeline(tmp_path, SystemScopeRef(kind="bundle", ref="bundle:b1"))

    assert result["events"][0]["action"] == expected_action


# ---------------------------------------------------------------------------
# Ordering is never inferred from content or rationale
# ---------------------------------------------------------------------------


def test_ordering_never_reads_annotation_or_review_body_text(tmp_path):
    # A record whose annotation text reads like it happened "first" or
    # "last" must not influence ordering -- only reviewed_at/sequence do.
    write_task(tmp_path / "tasks", "T-001", status="done")
    write_bundle(tmp_path / "bundles", "b1", "Bundle", ["task:T-001"])
    write_decision_artifact_raw(
        tmp_path,
        run_id="run-a",
        filename="review-001.json",
        payload={
            "version": 1,
            "reviewed_at": "2026-08-08T15:00:00Z",  # later timestamp
            "task_id": "T-001",
            "start_commit": "abc123",
            "decision": "approve",
            "annotations": [{"file": "x", "body": "this happened first, before anything else"}],
            "reviewed_files": [],
        },
    )
    write_decision_artifact_raw(
        tmp_path,
        run_id="run-b",
        filename="review-001.json",
        payload={
            "version": 1,
            "reviewed_at": "2026-08-08T09:00:00Z",  # earlier timestamp
            "task_id": "T-001",
            "start_commit": "abc123",
            "decision": "reject",
            "annotations": [{"file": "x", "body": "this happened last, after everything else"}],
            "reviewed_files": [],
        },
    )

    result = query_timeline(tmp_path, SystemScopeRef(kind="bundle", ref="bundle:b1"))

    # Chronological order (09:00 before 15:00) wins, regardless of what the
    # annotation prose claims.
    assert [e["at"] for e in result["events"]] == ["2026-08-08T09:00:00Z", "2026-08-08T15:00:00Z"]
    assert [e["action"] for e in result["events"]] == ["rejected", "approved"]


def test_no_validation_events_synthesized_without_a_recorded_timestamp_or_sequence(tmp_path):
    # validation-report.json entries carry neither a timestamp nor a
    # sequence number in this repo -- query_timeline must not invent one
    # (e.g. by using array position) to produce a "validated" event.
    from ._fixtures import write_validation_report

    write_sr(tmp_path / "requirements", "SR-001")
    write_validation_report(tmp_path, [{"id": "SR-001", "passed": True, "stale": False, "artifacts": []}])

    result = query_timeline(tmp_path, SystemScopeRef(kind="sr", ref="sr:SR-001"))

    assert result["events"] == []
    assert result["degraded"] is False  # legitimately nothing recorded, not a failure


# ---------------------------------------------------------------------------
# Events retain their citations
# ---------------------------------------------------------------------------


def test_events_retain_citation_to_the_source_review_file(tmp_path):
    write_task(tmp_path / "tasks", "T-001", status="done")
    write_bundle(tmp_path / "bundles", "b1", "Bundle", ["task:T-001"])
    path = write_decision_artifact(tmp_path, task_id="T-001", run_id="run-a", sequence=1)

    result = query_timeline(tmp_path, SystemScopeRef(kind="bundle", ref="bundle:b1"))

    citation = result["events"][0]["citation"]
    assert citation["path"] == str(path)
    assert citation["kind"] == "decision"
    assert citation["sha256"] is not None
    assert len(citation["sha256"]) == 64


def test_events_validate_against_timeline_event_schema(tmp_path):
    write_task(tmp_path / "tasks", "T-001", status="done")
    write_bundle(tmp_path / "bundles", "b1", "Bundle", ["task:T-001"])
    write_decision_artifact(tmp_path, task_id="T-001")

    result = query_timeline(tmp_path, SystemScopeRef(kind="bundle", ref="bundle:b1"))

    for event in result["events"]:
        assert validate(event, TIMELINE_EVENT_SCHEMA) == []


# ---------------------------------------------------------------------------
# Scope resolution and filtering
# ---------------------------------------------------------------------------


def test_timeline_for_bundle_only_includes_member_tasks(tmp_path):
    write_task(tmp_path / "tasks", "T-001", status="done")
    write_task(tmp_path / "tasks", "T-002", status="done")
    write_bundle(tmp_path / "bundles", "b1", "Bundle", ["task:T-001"])
    write_decision_artifact(tmp_path, task_id="T-001", run_id="run-a")
    write_decision_artifact(tmp_path, task_id="T-002", run_id="run-b")

    result = query_timeline(tmp_path, SystemScopeRef(kind="bundle", ref="bundle:b1"))

    assert len(result["events"]) == 1
    assert result["events"][0]["subject"]["ref"] == "task:T-001"


def test_timeline_for_sr_includes_events_for_tasks_that_satisfy_it(tmp_path):
    write_sr(tmp_path / "requirements", "SR-001")
    write_task(tmp_path / "tasks", "T-001", status="done", satisfies=["SR-001"])
    write_task(tmp_path / "tasks", "T-002", status="done")  # does not satisfy SR-001
    write_decision_artifact(tmp_path, task_id="T-001", run_id="run-a")
    write_decision_artifact(tmp_path, task_id="T-002", run_id="run-b")

    result = query_timeline(tmp_path, SystemScopeRef(kind="sr", ref="sr:SR-001"))

    assert len(result["events"]) == 1
    assert result["events"][0]["subject"]["ref"] == "task:T-001"


def test_timeline_on_empty_repo_is_empty_not_an_error(tmp_path):
    write_task(tmp_path / "tasks", "T-001", status="todo")
    write_bundle(tmp_path / "bundles", "b1", "Bundle", ["task:T-001"])

    result = query_timeline(tmp_path, SystemScopeRef(kind="bundle", ref="bundle:b1"))

    assert result["events"] == []
    assert result["degraded"] is False


def test_corrupt_review_file_is_skipped_and_degrades_only_this_scope(tmp_path):
    write_task(tmp_path / "tasks", "T-001", status="done")
    write_task(tmp_path / "tasks", "T-002", status="done")
    write_bundle(tmp_path / "bundles", "b1", "Bundle", ["task:T-001"])
    write_bundle(tmp_path / "bundles", "b2", "Bundle Two", ["task:T-002"])
    write_decision_artifact_raw(
        tmp_path, run_id="run-a", filename="review-001.json", payload="{not valid json"
    )
    write_decision_artifact(tmp_path, task_id="T-002", run_id="run-b")

    scope_a = query_timeline(tmp_path, SystemScopeRef(kind="bundle", ref="bundle:b1"))
    scope_b = query_timeline(tmp_path, SystemScopeRef(kind="bundle", ref="bundle:b2"))

    assert scope_a["events"] == []
    assert scope_a["degraded"] is False  # nothing recorded for T-001; the corrupt file names no task
    assert len(scope_b["events"]) == 1  # the corrupt file in another run does not affect this scope
    assert scope_b["degraded"] is False


def test_unknown_scope_kind_raises():
    from factory.system.queries import ScopeKindError

    with pytest.raises(ScopeKindError):
        query_timeline(None, SystemScopeRef(kind="task", ref="task:T-001"))
