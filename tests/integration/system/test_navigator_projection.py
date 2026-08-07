"""Integration test: the full navigator projection (brief + matrix + timeline)
over a real temp repo, exercised through both the Python query layer and the
`python -m factory.system` CLI entry point.

Builds its own repo scaffold directly (matching
`tests/integration/orchestrator/test_resume_run.py`'s convention) rather than
importing `tests/unit/system/_fixtures.py` -- `tests/unit`/`tests/integration`
are separate top-level test packages with no shared `__init__.py` chain, so a
cross-directory relative import would be fragile; a self-contained scaffold
keeps this test independent of unit-test internals.

Two scopes are built in the same repo specifically to prove degradation is
scoped, not global (design SS8): `bundle:good` has a well-formed spec, SR,
task, validation report, and decision artifact and must project cleanly;
`bundle:broken` shares the same repo but additionally references:

- `task:T-999`, which has no ledger entry at all -- a "missing manifest" in
  the loose sense this navigator has (there is no first-class "manifest"
  citation type yet, only bundle members that fail to resolve); degrades
  `bundle:broken`'s brief only.
- `task:T-002`, whose only decision record parses fine (it is not corrupt)
  but carries neither a recorded timestamp nor a recognizable sequence
  number -- a "missing blob" in the sense that the evidence exists but
  cannot be turned into a usable event, so it is dropped rather than
  fabricated; degrades `bundle:broken`'s timeline only.

A third, genuinely corrupt (unparseable) decision-artifact file is also
present in the repo, attached to neither bundle's task set because its
`task_id` cannot even be read -- this proves unattributable corruption does
not leak into *any* scope's `degraded` flag, which would be worse than
attributing it to the wrong one.

Both `task:T-999` and `task:T-002` are unique to `bundle:broken`;
`bundle:good` shares only `task:T-001`, so it must remain entirely clean.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from factory.system.models import SystemScopeRef
from factory.system.queries import query_brief, query_matrix, query_timeline
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


def _envelope(repo_root: Path, scope: SystemScopeRef) -> dict:
    return {
        "scope": {"kind": scope.kind, "ref": scope.ref},
        "brief": query_brief(repo_root, scope),
        "matrix": query_matrix(repo_root, scope),
        "timeline": query_timeline(repo_root, scope),
        "freshness": {"state": "fresh", "details": []},
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
        json.dumps({"requirements": [{"id": "SR-001", "passed": True, "stale": False, "artifacts": []}]}),
        encoding="utf-8",
    )

    # T-001's decision record: well-formed, timestamped -- shared by both
    # bundle:good and bundle:broken, so it must appear identically in both.
    reviews_dir = root / "evidence" / "runs" / "run-001" / "reviews"
    reviews_dir.mkdir(parents=True, exist_ok=True)
    (reviews_dir / "review-001.json").write_text(
        json.dumps(
            {
                "version": 1,
                "reviewed_at": "2026-08-08T12:00:00Z",
                "task_id": "T-001",
                "start_commit": "abc123",
                "decision": "approve",
                "annotations": [],
                "reviewed_files": [],
            }
        ),
        encoding="utf-8",
    )

    # T-002's decision record: valid JSON, a real task_id, but neither a
    # recorded timestamp nor a filename matching the `review-<N>.json`
    # sequence convention -- no recorded ordering basis at all. This is the
    # "missing blob" case: the evidence exists and names its task, but
    # cannot honestly become a timeline event, so it must be dropped and
    # must degrade only bundle:broken (T-002 is not a member of bundle:good).
    t002_reviews_dir = root / "evidence" / "runs" / "run-002" / "reviews"
    t002_reviews_dir.mkdir(parents=True, exist_ok=True)
    (t002_reviews_dir / "review-unordered.json").write_text(
        json.dumps(
            {
                "version": 1,
                "reviewed_at": None,
                "task_id": "T-002",
                "start_commit": "def456",
                "decision": "approve",
                "annotations": [],
                "reviewed_files": [],
            }
        ),
        encoding="utf-8",
    )

    # A genuinely corrupt (unparseable) decision-artifact file. Its task_id
    # cannot be read at all, so it cannot be attributed to any scope -- it
    # must not wrongly degrade bundle:good, bundle:broken, or anything else.
    corrupt_reviews_dir = root / "evidence" / "runs" / "run-003" / "reviews"
    corrupt_reviews_dir.mkdir(parents=True, exist_ok=True)
    (corrupt_reviews_dir / "review-001.json").write_text("{not valid json at all", encoding="utf-8")

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
    # References task:T-999, which has no ledger entry at all (the "missing
    # manifest" scenario -- there is no first-class manifest citation type
    # yet, only bundle members that fail to resolve), and task:T-002, whose
    # only decision record has no recorded ordering basis (the "missing
    # blob" scenario, see above).
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
    assert envelope["timeline"]["degraded"] is False
    assert len(envelope["timeline"]["events"]) == 1
    assert envelope["timeline"]["events"][0]["action"] == "approved"
    assert envelope["timeline"]["events"][0]["actor"] == "not-recorded"


def test_timeline_event_citation_points_at_a_real_file_with_matching_hash(repo):
    import hashlib

    scope = SystemScopeRef(kind="bundle", ref="bundle:good")
    result = query_timeline(repo, scope)

    event = result["events"][0]
    citation = event["citation"]
    citation_path = Path(citation["path"])
    assert citation_path.is_file()
    assert citation["sha256"] == hashlib.sha256(citation_path.read_bytes()).hexdigest()


# ---------------------------------------------------------------------------
# A missing task reference ("missing manifest") and an unusable decision
# artifact ("missing blob") each degrade only their own scope -- the clean
# scope is unaffected (design SS8).
# ---------------------------------------------------------------------------


def test_missing_task_reference_degrades_only_the_broken_bundles_brief(repo):
    broken_scope = SystemScopeRef(kind="bundle", ref="bundle:broken")
    good_scope = SystemScopeRef(kind="bundle", ref="bundle:good")

    broken_envelope = _envelope(repo, broken_scope)
    good_envelope = _envelope(repo, good_scope)

    # The missing task:T-999 member ("missing manifest") degrades the broken
    # bundle's brief only.
    assert broken_envelope["brief"]["degraded"] is True
    missing_claims = [c for c in broken_envelope["brief"]["claims"] if c["kind"] == "missing"]
    assert any(c["text"] == "task:T-999" for c in missing_claims)

    assert good_envelope["brief"]["degraded"] is False


def test_unusable_decision_artifact_degrades_only_the_broken_bundles_timeline(repo):
    broken_scope = SystemScopeRef(kind="bundle", ref="bundle:broken")
    good_scope = SystemScopeRef(kind="bundle", ref="bundle:good")

    broken_envelope = _envelope(repo, broken_scope)
    good_envelope = _envelope(repo, good_scope)

    # T-002's ordering-less decision record ("missing blob") is dropped, not
    # fabricated into an event, and it visibly degrades bundle:broken's
    # timeline. T-001's own well-formed decision still appears.
    assert broken_envelope["timeline"]["degraded"] is True
    assert [e["subject"]["ref"] for e in broken_envelope["timeline"]["events"]] == ["task:T-001"]

    # T-002 is not a member of bundle:good, so its unusable record has no
    # effect there at all -- degradation is scoped, not global.
    assert good_envelope["timeline"]["degraded"] is False
    assert len(good_envelope["timeline"]["events"]) == 1

    # Both envelopes still validate -- degradation never crashes the
    # projection, it only flips a flag/drops an unrepresentable record.
    assert validate(broken_envelope, RESPONSE_SCHEMA) == []
    assert validate(good_envelope, RESPONSE_SCHEMA) == []


def test_unattributable_corrupt_decision_artifact_degrades_no_scope(repo):
    # run-003's review-001.json is unparseable and names no task_id at all
    # (it can't even be read as JSON) -- it must not be guessed into
    # belonging to bundle:good, bundle:broken, or any other scope's
    # `degraded` flag. Silently attributing it to the wrong scope would be
    # worse than dropping it: it would be evidence pointed at the wrong
    # place, not merely absent evidence.
    good_scope = SystemScopeRef(kind="bundle", ref="bundle:good")
    broken_scope = SystemScopeRef(kind="bundle", ref="bundle:broken")

    good_timeline = query_timeline(repo, good_scope)
    broken_timeline = query_timeline(repo, broken_scope)

    assert good_timeline["degraded"] is False
    # bundle:broken is still True, but only because of T-002's own record,
    # not because of the unattributable corrupt file -- verified separately
    # by the T-002-only assertion in the previous test.
    assert len(good_timeline["events"]) == 1
    assert len(broken_timeline["events"]) == 1


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
    assert len(payload["events"]) == 1
