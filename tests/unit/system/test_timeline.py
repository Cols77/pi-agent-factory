"""Tests for factory.system.queries.query_timeline (design SS4.3, SS7.4).

Timeline carries the highest-risk rules in the whole navigator: ordering,
fallback, and unknown-actor handling are exactly the places a query could
assert something the evidence does not support. Every test here pins one of
those rules against real files in a temp repo -- nothing is asserted from a
mock or a hand-built dataclass standing in for a query result.

Recorded source: the `reviews` array inside each durable run evidence
manifest, `evidence/runs/<run_id>.json` -- a flat file, written and read
through the real `factory.evidence.manifests` loader/writer (see the comment
block above `_iter_decision_records` in `queries.py` for the full chain:
`human_review.py` writes per-run transcript scratch that `.gitignore`
excludes from the repo; `finalize.py` folds it into the durable manifest's
`reviews` array; that array is what this module actually reads).

An earlier version of this file (and of `queries.py`) assumed a directory
layout, `evidence/runs/<run_id>/reviews/review-*.json`, that no producer in
this repo ever writes. Several tests below exist specifically to prevent
that regressing silently -- see the "Regression: real manifest layout"
section.
"""
from __future__ import annotations

import pytest

from factory.system.queries import query_timeline
from factory.system.models import SystemScopeRef
from factory.validation.schema_validator import SCHEMA_DIR, validate

from ._fixtures import (
    review_record,
    write_bundle,
    write_decision_artifact,
    write_raw_manifest_json,
    write_run_manifest,
    write_sr,
    write_task,
)

pytestmark = pytest.mark.unit

TIMELINE_EVENT_SCHEMA = SCHEMA_DIR / "system_timeline_event.schema.json"


# ---------------------------------------------------------------------------
# Regression: real manifest layout, not the old (wrong) directory glob
# ---------------------------------------------------------------------------


def test_events_come_back_from_a_real_manifest_built_the_real_way(tmp_path):
    # Builds the manifest through the real `factory.evidence.manifests`
    # writer (schema-validated) -- proves the query actually reads
    # `evidence/runs/<run_id>.json`'s `reviews` array end to end.
    write_task(tmp_path / "tasks", "T-001", status="done")
    write_bundle(tmp_path / "bundles", "b1", "Bundle", ["task:T-001"])
    write_run_manifest(
        tmp_path,
        run_id="run-001",
        task_id="T-001",
        reviews=[review_record(task_id="T-001", decision="approve", reviewed_at="2026-08-08T12:00:00Z")],
    )

    result = query_timeline(tmp_path, SystemScopeRef(kind="bundle", ref="bundle:b1"))

    assert len(result["events"]) == 1
    assert result["events"][0]["action"] == "approved"
    assert result["events"][0]["at"] == "2026-08-08T12:00:00Z"


def test_a_directory_shaped_like_the_old_wrong_layout_produces_no_events(tmp_path):
    # `evidence/runs/<run_id>/reviews/review-*.json` is not a layout any
    # producer in this repo writes (evidence/runs/<run_id> is always a
    # *file*, per `factory.evidence.manifests.write_run_manifest`). If a
    # stray directory happens to exist in that shape, it must be inert --
    # proves the query no longer globs it.
    write_task(tmp_path / "tasks", "T-001", status="done")
    write_bundle(tmp_path / "bundles", "b1", "Bundle", ["task:T-001"])
    stray = tmp_path / "evidence" / "runs" / "run-001" / "reviews" / "review-001.json"
    stray.parent.mkdir(parents=True, exist_ok=True)
    stray.write_text(
        '{"version": 1, "reviewed_at": "2026-08-08T12:00:00Z", "task_id": "T-001", '
        '"start_commit": "abc123", "decision": "approve", "annotations": [], "reviewed_files": []}',
        encoding="utf-8",
    )

    result = query_timeline(tmp_path, SystemScopeRef(kind="bundle", ref="bundle:b1"))

    assert result["events"] == []
    assert result["degraded"] is False


# ---------------------------------------------------------------------------
# Ordering is deterministic from recorded timestamps
# ---------------------------------------------------------------------------


def test_ordering_is_deterministic_from_recorded_timestamps(tmp_path):
    write_task(tmp_path / "tasks", "T-001", status="done")
    write_bundle(tmp_path / "bundles", "b1", "Bundle", ["task:T-001"])
    # Written out of chronological order, and with run-id naming that would
    # sort the *other* way if ordering were accidentally keyed off manifest
    # listing order instead of the recorded `reviewed_at`.
    write_decision_artifact(tmp_path, task_id="T-001", run_id="run-b", reviewed_at="2026-08-08T15:00:00Z", decision="approve")
    write_decision_artifact(tmp_path, task_id="T-001", run_id="run-a", reviewed_at="2026-08-08T09:00:00Z", decision="reject")
    write_decision_artifact(tmp_path, task_id="T-001", run_id="run-c", reviewed_at="2026-08-08T12:00:00Z", decision="approve")

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
# Missing timestamps fall back to a recorded sequence number, with a warning
# ---------------------------------------------------------------------------


def test_missing_timestamp_falls_back_to_recorded_position_in_reviews_array(tmp_path):
    write_task(tmp_path / "tasks", "T-001", status="done")
    write_bundle(tmp_path / "bundles", "b1", "Bundle", ["task:T-001"])
    write_run_manifest(
        tmp_path,
        run_id="run-a",
        task_id="T-001",
        reviews=[review_record(task_id="T-001", reviewed_at=None, decision="approve")],
    )

    result = query_timeline(tmp_path, SystemScopeRef(kind="bundle", ref="bundle:b1"))

    assert len(result["events"]) == 1
    event = result["events"][0]
    assert event["at"] is None
    assert event["sequence"] == 1
    # The fallback is visible, not silent.
    assert event["freshness"]["state"] == "degraded"
    assert "reviews array" in event["freshness"]["reason"]


def test_events_with_timestamps_sort_before_sequence_only_fallback_events(tmp_path):
    write_task(tmp_path / "tasks", "T-001", status="done")
    write_bundle(tmp_path / "bundles", "b1", "Bundle", ["task:T-001"])
    write_run_manifest(
        tmp_path,
        run_id="run-a",
        task_id="T-001",
        reviews=[review_record(task_id="T-001", reviewed_at=None, decision="approve")],
    )
    write_run_manifest(
        tmp_path,
        run_id="run-b",
        task_id="T-001",
        reviews=[review_record(task_id="T-001", reviewed_at="2026-08-08T09:00:00Z", decision="reject")],
    )

    result = query_timeline(tmp_path, SystemScopeRef(kind="bundle", ref="bundle:b1"))

    assert [e["at"] for e in result["events"]] == ["2026-08-08T09:00:00Z", None]


def test_sequence_only_events_within_one_manifest_sort_by_array_position(tmp_path):
    write_task(tmp_path / "tasks", "T-001", status="done")
    write_bundle(tmp_path / "bundles", "b1", "Bundle", ["task:T-001"])
    write_run_manifest(
        tmp_path,
        run_id="run-a",
        task_id="T-001",
        reviews=[
            review_record(task_id="T-001", reviewed_at=None, decision="approve"),
            review_record(task_id="T-001", reviewed_at=None, decision="reject"),
            review_record(task_id="T-001", reviewed_at=None, decision="approve"),
        ],
    )

    result = query_timeline(tmp_path, SystemScopeRef(kind="bundle", ref="bundle:b1"))

    # Array position (1-based), the manifest's own recorded structure --
    # never reordered by content (both entries approve/reject/approve).
    assert [e["sequence"] for e in result["events"]] == [1, 2, 3]
    assert [e["action"] for e in result["events"]] == ["approved", "rejected", "approved"]


def test_sequence_only_events_across_manifests_order_by_manifest_ended_at_then_position(tmp_path):
    # Array position is only meaningful *within* one manifest -- nothing
    # recorded says run-a's 1st review happened before or after run-b's 1st
    # review. Events must group by manifest (ordered by the manifest's own
    # recorded `ended_at`), never interleave by raw sequence number across
    # manifests. run-b's `ended_at` is earlier than run-a's, and run-b was
    # written to disk *after* run-a, so neither insertion order nor sequence
    # number alone would produce the correct result here.
    write_task(tmp_path / "tasks", "T-001", status="done")
    write_bundle(tmp_path / "bundles", "b1", "Bundle", ["task:T-001"])
    write_run_manifest(
        tmp_path,
        run_id="run-a",
        task_id="T-001",
        ended_at="2026-08-08T15:00:00Z",
        reviews=[
            review_record(task_id="T-001", decision="approve", reviewed_at=None),
            review_record(task_id="T-001", decision="approve", reviewed_at=None),
            review_record(task_id="T-001", decision="approve", reviewed_at=None),
        ],
    )
    write_run_manifest(
        tmp_path,
        run_id="run-b",
        task_id="T-001",
        ended_at="2026-08-08T09:00:00Z",
        reviews=[
            review_record(task_id="T-001", decision="reject", reviewed_at=None),
            review_record(task_id="T-001", decision="reject", reviewed_at=None),
        ],
    )

    result = query_timeline(tmp_path, SystemScopeRef(kind="bundle", ref="bundle:b1"))

    # All of run-b (earlier ended_at) before all of run-a (later ended_at) --
    # never run-a[0], run-b[0], run-a[1], run-b[1], run-a[2], which is what a
    # bare-sequence-number sort (ignoring which manifest owns each position)
    # would produce.
    actions = [e["action"] for e in result["events"]]
    assert actions == ["rejected", "rejected", "approved", "approved", "approved"]
    sequences = [e["sequence"] for e in result["events"]]
    assert sequences == [1, 2, 1, 2, 3]


def test_sequence_only_events_across_manifests_with_identical_ended_at_still_never_interleave(tmp_path):
    # `manifest_ended_at` alone is not enough to disambiguate: two runs can
    # legitimately complete in the same second (plausible in bulk runs).
    # Ordering by (ended_at, sequence, path) instead of (ended_at, path,
    # sequence) would let raw position numbers from different manifests
    # compare to each other again the moment ended_at ties -- exactly the
    # original cross-manifest interleaving bug, just gated behind a tie
    # instead of always reachable. `citation.path` (unique per manifest)
    # must outrank `sequence` so this can never happen, tie or not.
    write_task(tmp_path / "tasks", "T-001", status="done")
    write_bundle(tmp_path / "bundles", "b1", "Bundle", ["task:T-001"])
    write_run_manifest(
        tmp_path,
        run_id="run-a",
        task_id="T-001",
        ended_at="2026-08-08T12:00:00Z",
        reviews=[
            review_record(task_id="T-001", decision="approve", reviewed_at=None),
            review_record(task_id="T-001", decision="approve", reviewed_at=None),
        ],
    )
    write_run_manifest(
        tmp_path,
        run_id="run-b",
        task_id="T-001",
        ended_at="2026-08-08T12:00:00Z",  # identical to run-a's
        reviews=[
            review_record(task_id="T-001", decision="reject", reviewed_at=None),
            review_record(task_id="T-001", decision="reject", reviewed_at=None),
        ],
    )

    result = query_timeline(tmp_path, SystemScopeRef(kind="bundle", ref="bundle:b1"))

    # All four events grouped by their owning manifest -- either
    # [approve, approve, reject, reject] or [reject, reject, approve,
    # approve] (path ordering between run-a.json/run-b.json is
    # deterministic but not the point under test); what must never appear
    # is an interleaved [approve, reject, approve, reject].
    actions = [e["action"] for e in result["events"]]
    assert actions in (
        ["approved", "approved", "rejected", "rejected"],
        ["rejected", "rejected", "approved", "approved"],
    )
    # Sequence numbers within each manifest-group are still in order.
    assert [e["sequence"] for e in result["events"][:2]] == [1, 2]
    assert [e["sequence"] for e in result["events"][2:]] == [1, 2]


# ---------------------------------------------------------------------------
# Absent actor/action is unknown/not-recorded; the event is marked degraded
# ---------------------------------------------------------------------------


def test_actor_is_not_recorded_never_guessed(tmp_path):
    # The review-decision record shape has no field naming a reviewer at
    # all -- actor must never be filled in with a plausible value (e.g.
    # "human", because only a human review gate produces this record type).
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
    first_record = review_record(task_id="T-001", decision="approve", reviewed_at="2026-08-08T15:00:00Z")
    first_record["annotations"] = [{"file": "x", "body": "this happened first, before anything else"}]
    second_record = review_record(task_id="T-001", decision="reject", reviewed_at="2026-08-08T09:00:00Z")
    second_record["annotations"] = [{"file": "x", "body": "this happened last, after everything else"}]
    write_run_manifest(tmp_path, run_id="run-a", task_id="T-001", reviews=[first_record])
    write_run_manifest(tmp_path, run_id="run-b", task_id="T-001", reviews=[second_record])

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
# Events retain their citation
# ---------------------------------------------------------------------------


def test_events_retain_citation_to_the_owning_manifest_and_array_position(tmp_path):
    write_task(tmp_path / "tasks", "T-001", status="done")
    write_bundle(tmp_path / "bundles", "b1", "Bundle", ["task:T-001"])
    manifest_path = write_decision_artifact(tmp_path, task_id="T-001", run_id="run-a")

    result = query_timeline(tmp_path, SystemScopeRef(kind="bundle", ref="bundle:b1"))

    citation = result["events"][0]["citation"]
    assert citation["path"] == str(manifest_path)
    assert citation["kind"] == "decision"
    assert citation["anchor"] == "reviews[0]"
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
# A missing/unreadable blob reference inside a review record never affects
# the timeline -- query_timeline never dereferences patch/guide blob content.
# ---------------------------------------------------------------------------


def test_a_review_records_blob_reference_never_needs_to_resolve(tmp_path):
    write_task(tmp_path / "tasks", "T-001", status="done")
    write_bundle(tmp_path / "bundles", "b1", "Bundle", ["task:T-001"])
    record = review_record(task_id="T-001", decision="approve", reviewed_at="2026-08-08T12:00:00Z")
    # This sha256 corresponds to no real blob anywhere on disk or in any
    # artifact store -- the fixture never writes one for any test in this
    # file. The event must still be built correctly regardless.
    record["patch"] = {
        "sha256": "0" * 64,
        "size": 999,
        "media_type": "text/x-diff",
        "local": True,
        "publication": "local",
        "uri": None,
    }
    write_run_manifest(tmp_path, run_id="run-a", task_id="T-001", reviews=[record])

    result = query_timeline(tmp_path, SystemScopeRef(kind="bundle", ref="bundle:b1"))

    assert len(result["events"]) == 1
    assert result["events"][0]["action"] == "approved"
    assert result["events"][0]["at"] == "2026-08-08T12:00:00Z"


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


def test_manifest_with_empty_reviews_array_is_empty_not_degraded(tmp_path):
    # A task that has been run but never reviewed yet -- a real, valid
    # manifest with `reviews: []`, not a corruption or an absence.
    write_task(tmp_path / "tasks", "T-001", status="done")
    write_bundle(tmp_path / "bundles", "b1", "Bundle", ["task:T-001"])
    write_run_manifest(tmp_path, run_id="run-a", task_id="T-001", reviews=[])

    result = query_timeline(tmp_path, SystemScopeRef(kind="bundle", ref="bundle:b1"))

    assert result["events"] == []
    assert result["degraded"] is False
    assert result["degraded_reasons"] == []


def test_corrupt_manifest_is_skipped_but_still_degrades_the_timeline(tmp_path):
    # `list_run_manifests` silently skips a manifest it cannot parse -- fine
    # for "don't crash", wrong for "don't hide" (design SS8): a scope whose
    # decisions genuinely could not be read must not report the same clean
    # "degraded: false" a scope with truly nothing recorded would report.
    # The corrupt file's own task_id cannot be read (that's the failure),
    # so this cannot be attributed to one specific scope -- see the
    # module-level comment above `_unreadable_manifest_count` in
    # queries.py; the signal is necessarily repo-wide while any manifest
    # anywhere is unreadable.
    write_task(tmp_path / "tasks", "T-001", status="done")
    write_task(tmp_path / "tasks", "T-002", status="done")
    write_bundle(tmp_path / "bundles", "b1", "Bundle", ["task:T-001"])
    write_bundle(tmp_path / "bundles", "b2", "Bundle Two", ["task:T-002"])
    write_raw_manifest_json(tmp_path, run_id="run-corrupt", payload="{not valid json")
    write_decision_artifact(tmp_path, task_id="T-002", run_id="run-b")

    scope_a = query_timeline(tmp_path, SystemScopeRef(kind="bundle", ref="bundle:b1"))
    scope_b = query_timeline(tmp_path, SystemScopeRef(kind="bundle", ref="bundle:b2"))

    # Events stay correct either way -- the corrupt manifest never becomes a
    # phantom event, and never affects which real events are returned.
    assert scope_a["events"] == []
    assert len(scope_b["events"]) == 1
    assert scope_b["events"][0]["subject"]["ref"] == "task:T-002"

    # Both are flagged degraded -- for T-002 this is also (redundantly) true
    # via its own event's freshness, but for T-001 (zero events) this is the
    # *only* signal that something could not be read, and it is exactly the
    # case the old `any(event freshness degraded)`-only definition missed.
    # `degraded_reasons` distinguishes the two causes precisely: T-001's
    # scope has *only* the unreadable-manifest reason (zero events, so no
    # actor-related reason can apply), while T-002's scope has *both* --
    # its own event's missing actor, plus the same repo-wide unreadable
    # count. Neither list invents a reason it did not count.
    assert scope_a["degraded"] is True
    assert scope_a["degraded_reasons"] == ["1 run manifest(s) under evidence/runs could not be read"]
    assert scope_b["degraded"] is True
    assert scope_b["degraded_reasons"] == [
        "1 event(s) do not have a recorded actor",
        "1 run manifest(s) under evidence/runs could not be read",
    ]


def test_schema_invalid_manifest_degrades_the_timeline_instead_of_reporting_clean(tmp_path):
    # Valid JSON, but fails `evidence_manifest.schema.json` (missing every
    # required field) -- `list_run_manifests` already skips this. Before the
    # fix, this scope reported `degraded: false` -- indistinguishable from
    # "no decisions were ever recorded" -- even though evidence for this
    # exact scope may have existed and simply failed to load. That is the
    # asserting-something-the-evidence-does-not-support failure mode this
    # whole design exists to prevent, just in the "everything is fine"
    # direction instead of the "nothing is here" direction.
    write_task(tmp_path / "tasks", "T-001", status="done")
    write_bundle(tmp_path / "bundles", "b1", "Bundle", ["task:T-001"])
    write_raw_manifest_json(tmp_path, run_id="run-bad", payload={"not": "a valid manifest"})

    result = query_timeline(tmp_path, SystemScopeRef(kind="bundle", ref="bundle:b1"))

    assert result["events"] == []
    assert result["degraded"] is True
    assert result["degraded_reasons"] == ["1 run manifest(s) under evidence/runs could not be read"]


def test_degraded_reasons_counts_unrecognized_action_and_sequence_fallback_separately(tmp_path):
    # Two distinct, independently-counted causes on the *same* event: an
    # unrecognized `decision` value (action not-recorded) and a missing
    # `reviewed_at` (sequence fallback) -- plus the always-present
    # missing-actor cause. Each reason's count must reflect exactly what was
    # counted, not be conflated into a single generic message.
    write_task(tmp_path / "tasks", "T-001", status="done")
    write_bundle(tmp_path / "bundles", "b1", "Bundle", ["task:T-001"])
    write_decision_artifact(tmp_path, task_id="T-001", decision="defer", reviewed_at=None)

    result = query_timeline(tmp_path, SystemScopeRef(kind="bundle", ref="bundle:b1"))

    assert result["degraded_reasons"] == [
        "1 event(s) do not have a recorded actor",
        "1 event(s) do not have a recognized recorded action",
        "1 event(s) have no recorded timestamp and fall back to their manifest's "
        "recorded reviews-array position",
    ]


def test_review_entry_with_no_task_id_is_ignored_not_guessed(tmp_path):
    # A review entry that names no task at all cannot be attributed to any
    # scope -- it must not be guessed into belonging to this one.
    write_task(tmp_path / "tasks", "T-001", status="done")
    write_bundle(tmp_path / "bundles", "b1", "Bundle", ["task:T-001"])
    orphan = review_record(decision="approve")
    del orphan["task_id"]
    write_run_manifest(tmp_path, run_id="run-a", task_id="T-001", reviews=[orphan])

    result = query_timeline(tmp_path, SystemScopeRef(kind="bundle", ref="bundle:b1"))

    assert result["events"] == []
    assert result["degraded"] is False
    assert result["degraded_reasons"] == []


def test_unreadable_manifest_degrades_the_affected_scope_while_other_scopes_events_stay_intact(tmp_path):
    """Brief Step 4: "a missing manifest or missing blob degrades only that
    scope." T-001's manifest is unreadable; a completely unrelated scope
    (SR-002/T-003) has its own clean, correctly-recorded decision.

    Attribution honesty note: an unreadable manifest's own `task_id` field
    is exactly what failed to load, so this module cannot say *which*
    scope's evidence is missing without reading the very file that could
    not be read (that would be a parallel parser). `degraded` is therefore
    a repo-wide signal while any manifest anywhere is unreadable, not a
    scope-local one -- both the directly-affected scope and the unrelated
    scope report `degraded: true` here. What *does* stay correctly scoped,
    and is what this test pins, is each scope's `events` list: the
    unrelated scope's real, correctly-ordered event is never displaced,
    duplicated, or lost because of the other scope's unreadable manifest.
    """
    write_sr(tmp_path / "requirements", "SR-002")
    write_task(tmp_path / "tasks", "T-001", status="done")
    write_task(tmp_path / "tasks", "T-003", status="done", satisfies=["SR-002"])
    write_bundle(tmp_path / "bundles", "affected", "Affected", ["task:T-001"])
    write_raw_manifest_json(tmp_path, run_id="run-bad", payload={"not": "a valid manifest"})
    write_decision_artifact(tmp_path, task_id="T-003", run_id="run-clean", reviewed_at="2026-08-08T10:00:00Z")

    affected = query_timeline(tmp_path, SystemScopeRef(kind="bundle", ref="bundle:affected"))
    unrelated = query_timeline(tmp_path, SystemScopeRef(kind="sr", ref="sr:SR-002"))

    assert affected["events"] == []
    assert affected["degraded"] is True
    assert affected["degraded_reasons"] == ["1 run manifest(s) under evidence/runs could not be read"]

    assert len(unrelated["events"]) == 1
    assert unrelated["events"][0]["subject"]["ref"] == "task:T-003"
    assert unrelated["events"][0]["action"] == "approved"
    assert unrelated["events"][0]["at"] == "2026-08-08T10:00:00Z"
    # The unrelated scope's *own* reason (missing actor) plus the same
    # repo-wide unreadable-manifest reason -- not a fabricated third reason
    # implying T-003's own evidence was unreadable, which it was not.
    assert unrelated["degraded_reasons"] == [
        "1 event(s) do not have a recorded actor",
        "1 run manifest(s) under evidence/runs could not be read",
    ]


def test_unknown_scope_kind_raises():
    from factory.system.queries import ScopeKindError

    with pytest.raises(ScopeKindError):
        query_timeline(None, SystemScopeRef(kind="task", ref="task:T-001"))
