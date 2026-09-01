"""Integration test: the full navigator projection (brief + matrix + timeline)
over a real temp repo, exercised through both the Python query layer and the
`python -m factory.system` CLI entry point.

Builds its own repo scaffold directly (matching
`tests/integration/orchestrator/test_resume_run.py`'s convention) rather than
importing `tests/unit/system/_fixtures.py` -- `tests/unit`/`tests/integration`
are separate top-level test packages with no shared `__init__.py` chain, so a
cross-directory relative import would be fragile; a self-contained scaffold
keeps this test independent of unit-test internals. It does, however, write
every run evidence manifest through the real
`factory.evidence.manifests.write_run_manifest` writer -- the same real
loader `query_timeline` reads through -- specifically so this file cannot
silently drift back to a directory layout no producer actually writes (see
"Regression: real manifest layout" below; that drift is exactly what an
earlier version of `queries.py` got wrong).

Two scopes are built in the same repo specifically to prove degradation is
scoped, not global (design SS8): `bundle:good` has a well-formed spec, SR,
task, validation report, and decision artifact (a real run manifest with a
`reviews` entry) and must project cleanly; `bundle:broken` shares the same
repo but additionally references:

- `task:T-999`, which has no ledger entry and no run manifest anywhere ever
  mentions it -- a "missing manifest" in the most literal sense this
  navigator's evidence model has; degrades `bundle:broken`'s brief only.
- `task:T-002`, whose only decision record is real and readable but has no
  recorded `reviewed_at` -- a "missing blob" in the sense that the evidence
  is incomplete rather than absent: ordering falls back to the record's
  recorded position within its manifest's own `reviews` array, visibly
  marked degraded, never fabricated; unique to `bundle:broken`, so it must
  not affect `bundle:good`'s timeline.

A third, genuinely corrupt (unparseable) manifest file is also present in
the repo, attached to neither bundle's task set because its `task_id` cannot
even be read -- this proves unattributable corruption does not leak into
*any* scope's `degraded` flag, which would be worse than attributing it to
the wrong one.

Both `task:T-999` and `task:T-002` are unique to `bundle:broken`;
`bundle:good` shares only `task:T-001`, so it must remain entirely clean.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

from factory.evidence.manifests import write_run_manifest
from factory.system.models import SystemScopeRef
from factory.system.queries import query_brief, query_guide, query_matrix, query_timeline
from factory.validation.schema_validator import SCHEMA_DIR, validate

pytestmark = pytest.mark.integration

RESPONSE_SCHEMA = SCHEMA_DIR / "system_response.schema.json"
CLAIM_SCHEMA = SCHEMA_DIR / "system_claim.schema.json"
MATRIX_ROW_SCHEMA = SCHEMA_DIR / "system_matrix_row.schema.json"
TIMELINE_EVENT_SCHEMA = SCHEMA_DIR / "system_timeline_event.schema.json"

_SR_BOUND = """---
id: SR-001
title: "Demo requirement"
statement: "When X happens, the system shall Y."
domain: behavioral
upstream: []
binding:
  harness: sim-testbench
  experiment: demo_experiment
  metric: demo_rate
  trials: 1
  assert: ">= 0.5"
checksum: null
---
Rationale.
"""

_TASK_T001 = """---
id: T-001
title: "Implement the demo"
status: done
dod:
  - done
satisfies: ["SR-001"]
---
body
"""

_TASK_T002 = """---
id: T-002
title: "Unrelated task"
status: done
dod:
  - done
---
body
"""

_SPEC = "# Demo spec\n\nSpec body.\n"


def _review_record(*, task_id: str, decision: str = "approve", reviewed_at: str | None) -> dict:
    """One entry as `factory.evidence.finalize._review_evidence` leaves it in
    `manifest["reviews"]` -- the real shape `query_timeline` reads."""
    return {
        "version": 1,
        "reviewed_at": reviewed_at,
        "task_id": task_id,
        "start_commit": "a" * 40,
        "decision": decision,
        "annotations": [],
        "reviewed_files": [],
        "patch": {
            "sha256": "f" * 64,
            "size": 10,
            "media_type": "text/x-diff",
            "local": True,
            "publication": "local",
            "uri": None,
        },
    }


def _write_manifest(root: Path, *, run_id: str, task_id: str, reviews: list[dict]) -> Path:
    """Write a schema-valid run evidence manifest through the real writer --
    guarantees this fixture matches what `factory.evidence.finalize` and
    `factory.system.queries.query_timeline` actually agree on, not an
    invented shape."""
    manifest = {
        "schema_version": 2,
        "run_id": run_id,
        "task_id": task_id,
        "started_at": "2026-08-08T08:00:00Z",
        "ended_at": "2026-08-08T09:00:00Z",
        "start_commit": "a" * 40,
        "result_commit": "b" * 40,
        "outcome": "completed",
        "inputs": {
            "task": {"path": f"tasks/{task_id}-slug.md", "sha256": "c" * 64},
            "requirements": [],
            "factory_config_sha256": "d" * 64,
        },
        "dependencies": [],
        "implementation": {
            "changed_files": [],
            "patch": {"sha256": "e" * 64, "size": 0, "media_type": "text/x-diff"},
        },
        "validation": [],
        "reviews": reviews,
        "decisions": [],
        "publication": {"state": "local", "errors": []},
    }
    return write_run_manifest(root / "evidence", manifest)


def _envelope(repo_root: Path, scope: SystemScopeRef) -> dict:
    return {
        "scope": {"kind": scope.kind, "ref": scope.ref},
        "brief": query_brief(repo_root, scope),
        "matrix": query_matrix(repo_root, scope),
        "timeline": query_timeline(repo_root, scope),
        "guide": query_guide(repo_root, scope),
    }


def _write_common_repo(root: Path) -> None:
    (root / "requirements").mkdir(parents=True, exist_ok=True)
    (root / "requirements" / "SR-001.md").write_text(_SR_BOUND, encoding="utf-8")

    (root / "tasks").mkdir(parents=True, exist_ok=True)
    (root / "tasks" / "T-001-slug.md").write_text(_TASK_T001, encoding="utf-8")
    (root / "tasks" / "T-002-slug.md").write_text(_TASK_T002, encoding="utf-8")

    specs_dir = root / "docs" / "superpowers" / "specs"
    specs_dir.mkdir(parents=True, exist_ok=True)
    (specs_dir / "demo.md").write_text(_SPEC, encoding="utf-8")

    validation_dir = root / "validation"
    validation_dir.mkdir(parents=True, exist_ok=True)
    (validation_dir / "validation-report.json").write_text(
        json.dumps({"provenance": {"recorded_by": "harness", "recorded_at": "2026-01-01T00:00:00Z", "command": "coherence-measurement run"}, "requirements": [{"id": "SR-001", "passed": True, "stale": False, "artifacts": []}]}),
        encoding="utf-8",
    )

    # T-001's decision record: well-formed, timestamped -- shared by both
    # bundle:good and bundle:broken, so it must appear identically in both.
    _write_manifest(
        root,
        run_id="run-001",
        task_id="T-001",
        reviews=[_review_record(task_id="T-001", decision="approve", reviewed_at="2026-08-08T12:00:00Z")],
    )

    # T-002's decision record: real, readable, names its task -- but
    # `reviewed_at` was never recorded. This is the "missing blob" case in
    # the loose sense this navigator's evidence model has: the evidence
    # exists and is attributable, but is incomplete, so ordering falls back
    # to the record's own recorded position in `manifest["reviews"]`
    # (visibly marked degraded), never fabricated. Unique to bundle:broken
    # (T-002 is not a member of bundle:good).
    _write_manifest(
        root,
        run_id="run-002",
        task_id="T-002",
        reviews=[_review_record(task_id="T-002", decision="approve", reviewed_at=None)],
    )

    # A genuinely corrupt (unparseable) run manifest. Its task_id cannot be
    # read at all, so it cannot be attributed to any scope -- it must not
    # wrongly degrade bundle:good, bundle:broken, or anything else. Written
    # directly (not through the real writer, which would refuse this).
    (root / "evidence" / "runs" / "run-003.json").write_text("{not valid json at all", encoding="utf-8")

    bundles_dir = root / "bundles"
    bundles_dir.mkdir(parents=True, exist_ok=True)
    (bundles_dir / "good.json").write_text(
        json.dumps(
            {
                "id": "good",
                "label": "Good bundle",
                "members": [
                    "spec:docs/superpowers/specs/demo.md",
                    "sr:SR-001",
                    "task:T-001",
                ],
            }
        ),
        encoding="utf-8",
    )
    # References task:T-999, which has no ledger entry and no run manifest
    # anywhere ever mentions it (the "missing manifest" scenario), and
    # task:T-002, whose only decision record is incomplete rather than
    # absent (the "missing blob" scenario, see above).
    (bundles_dir / "broken.json").write_text(
        json.dumps(
            {
                "id": "broken",
                "label": "Broken bundle",
                "members": ["task:T-001", "task:T-002", "task:T-999"],
            }
        ),
        encoding="utf-8",
    )


@pytest.fixture()
def repo(tmp_path) -> Path:
    _write_common_repo(tmp_path)
    return tmp_path


# ---------------------------------------------------------------------------
# Regression: real manifest layout, not the old (wrong) directory glob
# ---------------------------------------------------------------------------


def test_stray_transcript_style_directory_does_not_produce_phantom_events(repo):
    # A stray `evidence/runs/<run_id>/reviews/review-*.json` directory
    # (the old, incorrect assumption `queries.py` made before this fix) must
    # be completely inert -- `evidence/runs/<run_id>` is always a *file* per
    # `factory.evidence.manifests.write_run_manifest`; nothing in this repo
    # ever writes that directory shape as durable evidence.
    stray = repo / "evidence" / "runs" / "run-999" / "reviews" / "review-001.json"
    stray.parent.mkdir(parents=True, exist_ok=True)
    stray.write_text(
        '{"version": 1, "reviewed_at": "2026-08-08T12:00:00Z", "task_id": "T-001", '
        '"start_commit": "abc123", "decision": "reject", "annotations": [], "reviewed_files": []}',
        encoding="utf-8",
    )

    result = query_timeline(repo, SystemScopeRef(kind="bundle", ref="bundle:good"))

    # Still exactly the one real event from run-001.json's manifest --
    # the stray directory contributed nothing.
    assert len(result["events"]) == 1
    assert result["events"][0]["action"] == "approved"


# ---------------------------------------------------------------------------
# The clean scope projects fully and validates against every schema
# ---------------------------------------------------------------------------


def test_full_envelope_for_clean_bundle_validates_against_response_schema(repo):
    scope = SystemScopeRef(kind="bundle", ref="bundle:good")
    envelope = _envelope(repo, scope)

    assert validate(envelope, RESPONSE_SCHEMA) == []
    for claim in envelope["brief"]["claims"]:
        assert validate(claim, CLAIM_SCHEMA) == []
    for row in envelope["matrix"]["rows"]:
        assert validate(row, MATRIX_ROW_SCHEMA) == []
    for event in envelope["timeline"]["events"]:
        assert validate(event, TIMELINE_EVENT_SCHEMA) == []

    assert envelope["brief"]["degraded"] is False
    assert len(envelope["timeline"]["events"]) == 1
    assert envelope["timeline"]["events"][0]["action"] == "approved"
    assert envelope["timeline"]["events"][0]["actor"] == "not-recorded"
    # This artifact type never names an actor, so a non-empty timeline is
    # always degraded in that one, honest dimension -- see the module-level
    # comment above `query_timeline` in queries.py.
    assert envelope["timeline"]["degraded"] is True


def test_timeline_event_citation_points_at_the_real_manifest_file_with_matching_hash(repo):
    scope = SystemScopeRef(kind="bundle", ref="bundle:good")
    result = query_timeline(repo, scope)

    event = result["events"][0]
    citation = event["citation"]
    citation_path = Path(citation["path"])
    assert citation_path == repo / "evidence" / "runs" / "run-001.json"
    assert citation_path.is_file()
    assert citation["sha256"] == hashlib.sha256(citation_path.read_bytes()).hexdigest()
    assert citation["anchor"] == "reviews[0]"


# ---------------------------------------------------------------------------
# A missing task reference ("missing manifest") and an incomplete decision
# record ("missing blob") each degrade only their own scope -- the clean
# scope is unaffected (design SS8).
# ---------------------------------------------------------------------------


def test_missing_task_reference_degrades_only_the_broken_bundles_brief(repo):
    broken_scope = SystemScopeRef(kind="bundle", ref="bundle:broken")
    good_scope = SystemScopeRef(kind="bundle", ref="bundle:good")

    broken_envelope = _envelope(repo, broken_scope)
    good_envelope = _envelope(repo, good_scope)

    # The missing task:T-999 member ("missing manifest": no ledger entry and
    # no run manifest anywhere mentions it) degrades the broken bundle's
    # brief only.
    assert broken_envelope["brief"]["degraded"] is True
    missing_claims = [c for c in broken_envelope["brief"]["claims"] if c["kind"] == "missing"]
    assert any(c["text"] == "task:T-999" for c in missing_claims)

    assert good_envelope["brief"]["degraded"] is False


def test_incomplete_decision_record_affects_only_the_broken_bundles_timeline(repo):
    broken_scope = SystemScopeRef(kind="bundle", ref="bundle:broken")
    good_scope = SystemScopeRef(kind="bundle", ref="bundle:good")

    broken_envelope = _envelope(repo, broken_scope)
    good_envelope = _envelope(repo, good_scope)

    broken_events = {e["subject"]["ref"]: e for e in broken_envelope["timeline"]["events"]}
    assert set(broken_events) == {"task:T-001", "task:T-002"}
    # T-002's record ("missing blob") falls back to its recorded position in
    # its manifest's reviews array -- not fabricated, and visibly marked.
    assert broken_events["task:T-002"]["at"] is None
    assert broken_events["task:T-002"]["sequence"] == 1
    assert "reviews array" in broken_events["task:T-002"]["freshness"]["reason"]

    # T-002 is not a member of bundle:good, so its incomplete record has no
    # effect there at all -- degradation is scoped, not global.
    good_refs = [e["subject"]["ref"] for e in good_envelope["timeline"]["events"]]
    assert good_refs == ["task:T-001"]
    assert good_envelope["timeline"]["events"][0]["at"] is not None

    # Both envelopes still validate -- degradation never crashes the
    # projection.
    assert validate(broken_envelope, RESPONSE_SCHEMA) == []
    assert validate(good_envelope, RESPONSE_SCHEMA) == []


def test_unattributable_corrupt_manifest_leaves_events_correct_in_every_scope(repo):
    # run-003.json is unparseable and names no task_id at all (it can't even
    # be read as JSON) -- it must not be guessed into belonging to
    # bundle:good, bundle:broken, or any other scope. Silently attributing
    # it to the wrong scope would be worse than dropping it: it would be
    # evidence pointed at the wrong place, not merely absent evidence.
    #
    # `degraded` itself is a different story: `queries._unreadable_manifest_
    # count` cannot attribute an unreadable manifest to a task without
    # reading the very field that failed to read, so it is a repo-wide
    # signal for as long as *any* manifest anywhere is unreadable -- both
    # scopes below correctly report `degraded: true` because of it (on top
    # of `bundle:good`/`bundle:broken` already being `true` via their own
    # events' freshness regardless). What stays precisely scoped is each
    # query's `events` list.
    good_scope = SystemScopeRef(kind="bundle", ref="bundle:good")
    broken_scope = SystemScopeRef(kind="bundle", ref="bundle:broken")

    good_timeline = query_timeline(repo, good_scope)
    broken_timeline = query_timeline(repo, broken_scope)

    # Exactly the events explained by T-001 (both scopes) and T-002 (broken
    # only) -- nothing extra, nothing missing, because of the corrupt file.
    assert len(good_timeline["events"]) == 1
    assert len(broken_timeline["events"]) == 2
    assert good_timeline["degraded"] is True
    assert broken_timeline["degraded"] is True
    # `degraded_reasons` names the unreadable-manifest cause explicitly,
    # not a generic "something is wrong" -- a caller can tell this apart
    # from "this artifact type never records an actor" (the other cause
    # also present here via each scope's own events).
    assert "1 run manifest(s) under evidence/runs could not be read" in good_timeline["degraded_reasons"]
    assert "1 run manifest(s) under evidence/runs could not be read" in broken_timeline["degraded_reasons"]


def test_sr_scope_also_projects_cleanly_in_the_same_repo(repo):
    scope = SystemScopeRef(kind="sr", ref="sr:SR-001")
    envelope = _envelope(repo, scope)

    assert validate(envelope, RESPONSE_SCHEMA) == []
    assert len(envelope["timeline"]["events"]) == 1
    assert envelope["timeline"]["events"][0]["subject"]["ref"] == "task:T-001"
    assert envelope["matrix"]["rows"][0]["status"] == "passed"


# ---------------------------------------------------------------------------
# The real CLI entry point, end to end (design SS5.1/SS12: `python -m
# factory.system`), not just the Python query functions directly.
# ---------------------------------------------------------------------------


def test_cli_timeline_subcommand_end_to_end(repo):
    result = subprocess.run(
        [sys.executable, "-m", "factory.system", "timeline", "--scope", "bundle:good", "--repo-root", str(repo), "--json"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["scope"]["ref"] == "bundle:good"
    assert len(payload["events"]) == 1
    assert payload["events"][0]["action"] == "approved"
    assert validate(payload["events"][0], TIMELINE_EVENT_SCHEMA) == []


def test_cli_timeline_subcommand_on_broken_bundle_does_not_crash(repo):
    result = subprocess.run(
        [sys.executable, "-m", "factory.system", "timeline", "--scope", "bundle:broken", "--repo-root", str(repo), "--json"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert len(payload["events"]) == 2
