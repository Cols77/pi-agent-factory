"""Tests for factory.memory.durable: durable-memory projection.

query_memory(root, scope) returns, in one read: decisions (from `adr:`),
failure records, rejected hypotheses, open goals, and conflicts — all with
provenance citations; it never re-states requirement/ADR/evidence prose it
links.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from factory.memory.durable import query_memory

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

_ADR_WELL_FORMED = """---
id: ADR-0002
title: Pre-emption latch discipline
status: accepted
superseded_by: null
---

## Decision
Use a hardware latch for pre-emption state.

## Consequences
Race conditions are prevented.
"""

_ADR_SUPERSEDED = """---
id: ADR-0003
title: Old latch design
status: superseded
superseded_by: ADR-0002
---

## Decision
Use software latch instead.

## Consequences
Races are possible.
"""

_ADR_ORPHAN_SUPERSEDED = """---
id: ADR-0004
title: Orphaned design
status: superseded
superseded_by: ADR-9999
---

## Decision
Something.
"""

_GOAL_OPEN = """---
id: GOAL-NAV-001
title: Reacquisition accuracy
feature: [FEAT-NAV-017]
requirements: [SR-032]
metric: {name: reacquisition_rate, source_experiment: SIM-047}
target: {operator: ">=", value: 0.90}
state: ACTIVE
---

Body.
"""

_GOAL_CLOSED = """---
id: GOAL-NAV-002
title: Old goal
feature: [FEAT-NAV-017]
requirements: [SR-032]
metric: {name: old_metric}
target: {operator: ">=", value: 1.0}
state: REACHED
---

Body.
"""

_GOAL_OTHER_FEATURE = """---
id: GOAL-NAV-003
title: Different feature goal
feature: [FEAT-OTHER]
requirements: [SR-066]
metric: {name: precision}
target: {operator: ">=", value: 0.85}
state: DECLARED
---

Body.
"""

_WELL_FORMED_FR = """---
id: FR-NAV-0001
title: False re-acquisition after pre-emption handoff
reproduced_by: RUN-20260811-1702
root_cause: "Pre-emption cleared the acquisition latch without re-arming it on resume (ADR-0002, code:navigation/preemption.py)."
fix: "Re-arm the latch in the resume path; regression covered by acceptance test."
regression_link: null
linked_req: [SR-017]
linked_feature: [FEAT-NAV-017]
rejected_hypotheses:
  - hypothesis: "Sensor noise caused the re-acquisition"
    why_rejected: "Replay of RUN-20260811-1702 reproduced it deterministically without noise"
    evidence: "run:RUN-20260811-1702"
---

## Symptom
After a pre-emption handoff the drone re-acquires a target it had already locked.
"""

_FR_OTHER_FEATURE = """---
id: FR-OTHER-0001
title: Other feature failure
reproduced_by: null
root_cause: "Other root cause"
fix: "Other fix"
regression_link: null
linked_req: [SR-999]
linked_feature: [FEAT-OTHER]
---

## Symptom
Other failure.
"""

_FR_ORPHAN_RUN = """---
id: FR-NAV-0002
title: Orphan run failure
reproduced_by: RUN-NONEXISTENT
root_cause: "Some root cause"
fix: "Some fix"
regression_link: null
linked_req: []
linked_feature: [FEAT-NAV-017]
---

## Symptom
Orphan run.
"""

_FR_BARE_HYPOTHESIS_EVIDENCE = """---
id: FR-NAV-0003
title: Bare evidence failure
reproduced_by: null
root_cause: "Some root cause"
fix: "Some fix"
regression_link: null
linked_req: []
linked_feature: [FEAT-NAV-017]
rejected_hypotheses:
  - hypothesis: "Bare run id hypothesis"
    why_rejected: "Replay ruled it out"
    evidence: "RUN-NONEXISTENT"
---

## Symptom
Bare run evidence.
"""


def _write_adr(adr_dir: Path, filename: str, text: str) -> Path:
    adr_dir.mkdir(parents=True, exist_ok=True)
    path = adr_dir / filename
    path.write_text(text, encoding="utf-8")
    return path


def _write_goal(root: Path, name: str, text: str) -> Path:
    (root / "goals").mkdir(parents=True, exist_ok=True)
    path = root / "goals" / name
    path.write_text(text, encoding="utf-8")
    return path


def _write_failure(failures_dir: Path, filename: str, text: str) -> Path:
    failures_dir.mkdir(parents=True, exist_ok=True)
    path = failures_dir / filename
    path.write_text(text, encoding="utf-8")
    return path


def _write_evidence_run(repo_root: Path, run_id: str) -> Path:
    """Write a minimal evidence run manifest for `run_id`."""
    path = repo_root / "evidence" / "runs" / f"{run_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": 2,
        "run_id": run_id,
        "task_id": "T-001",
        "started_at": "2026-08-11T17:02:00Z",
        "ended_at": "2026-08-11T17:45:00Z",
        "outcome": "completed",
        "implementation": {"changed_files": ["src/a.py"]},
        "validation": [],
        "reviews": [],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _write_bundle(bundles_dir: Path, bundle_id: str, members: list[str]) -> Path:
    """Write a minimal declared bundle whose members are exact refs."""
    bundles_dir.mkdir(parents=True, exist_ok=True)
    path = bundles_dir / f"{bundle_id}.json"
    payload = {"id": bundle_id, "label": bundle_id, "members": members}
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_query_memory_returns_all_sections(tmp_path):
    """The projection has five sections: decisions, failure_records,
    rejected_hypotheses, open_goals, conflicts."""
    _write_adr(tmp_path / "docs" / "adr", "0001-latch.md", _ADR_WELL_FORMED)
    _write_failure(tmp_path / "docs" / "failures", "FR-NAV-0001.md", _WELL_FORMED_FR)
    _write_goal(tmp_path, "GOAL-NAV-001.md", _GOAL_OPEN)
    _write_evidence_run(tmp_path, "RUN-20260811-1702")

    result = query_memory(tmp_path, "all")

    assert set(result) == {"scope", "decisions", "failure_records", "rejected_hypotheses", "open_goals", "conflicts"}
    assert result["scope"] == "all"
    assert len(result["decisions"]) == 1
    assert len(result["failure_records"]) == 1
    assert len(result["rejected_hypotheses"]) == 1
    assert len(result["open_goals"]) == 1


def test_decisions_have_frontmatter_fields_and_citation_no_sections(tmp_path):
    """Decisions carry id, title, status, superseded_by, citation and
    freshness — but never the ADR body sections (Decision/Consequences
    prose)."""
    _write_adr(tmp_path / "docs" / "adr", "0001-latch.md", _ADR_WELL_FORMED)

    result = query_memory(tmp_path, "all")

    assert len(result["decisions"]) == 1
    d = result["decisions"][0]
    assert d["id"] == "ADR-0002"
    assert d["title"] == "Pre-emption latch discipline"
    assert d["status"] == "accepted"
    assert d["superseded_by"] is None
    assert "citation" in d
    assert d["citation"]["kind"] == "decision"
    assert "adr" in Path(d["citation"]["path"]).parts
    assert "freshness" in d
    # No section prose
    assert "sections" not in d
    assert "Decision" not in json.dumps(d)


def test_failure_records_have_structured_fields_and_citation(tmp_path):
    """Failure records carry id, title, reproduced_by, root_cause, fix,
    linked_req, linked_feature, scope_errors, citation and freshness."""
    _write_failure(tmp_path / "docs" / "failures", "FR-NAV-0001.md", _WELL_FORMED_FR)

    result = query_memory(tmp_path, "all")

    assert len(result["failure_records"]) == 1
    fr = result["failure_records"][0]
    assert fr["id"] == "FR-NAV-0001"
    assert fr["title"] == "False re-acquisition after pre-emption handoff"
    assert fr["reproduced_by"] == "RUN-20260811-1702"
    assert "ADR-0002" in fr["root_cause"]
    assert fr["fix"].startswith("Re-arm the latch")
    assert fr["linked_req"] == ["SR-017"]
    assert fr["linked_feature"] == ["FEAT-NAV-017"]
    assert fr["scope_errors"] == []
    assert "citation" in fr
    assert fr["citation"]["kind"] == "failure"
    assert "failures" in Path(fr["citation"]["path"]).parts
    assert "freshness" in fr


def test_rejected_hypotheses_are_surfaced_from_failure_records(tmp_path):
    """Each hypothesis carries its text, why_rejected, evidence, source
    record id, and citation."""
    _write_failure(tmp_path / "docs" / "failures", "FR-NAV-0001.md", _WELL_FORMED_FR)

    result = query_memory(tmp_path, "all")

    assert len(result["rejected_hypotheses"]) == 1
    h = result["rejected_hypotheses"][0]
    assert h["record"] == "FR-NAV-0001"
    assert h["hypothesis"] == "Sensor noise caused the re-acquisition"
    assert "deterministically" in h["why_rejected"]
    assert h["evidence"] == "run:RUN-20260811-1702"
    assert "citation" in h
    assert h["citation"]["kind"] == "failure"


def test_open_goals_excludes_terminal_states(tmp_path):
    """Only goals whose state is not REACHED or NOT_REACHED are open."""
    _write_goal(tmp_path, "GOAL-NAV-001.md", _GOAL_OPEN)       # ACTIVE → open
    _write_goal(tmp_path, "GOAL-NAV-002.md", _GOAL_CLOSED)      # REACHED → closed
    _write_goal(tmp_path, "GOAL-NAV-003.md", _GOAL_OTHER_FEATURE)  # DECLARED → open

    result = query_memory(tmp_path, "all")

    open_ids = [g["id"] for g in result["open_goals"]]
    assert "GOAL-NAV-001" in open_ids
    assert "GOAL-NAV-002" not in open_ids
    assert "GOAL-NAV-003" in open_ids


def test_open_goals_have_citation_and_freshness(tmp_path):
    _write_goal(tmp_path, "GOAL-NAV-001.md", _GOAL_OPEN)

    result = query_memory(tmp_path, "all")

    assert len(result["open_goals"]) == 1
    g = result["open_goals"][0]
    assert g["id"] == "GOAL-NAV-001"
    assert g["state"] == "ACTIVE"
    assert g["feature"] == ["FEAT-NAV-017"]
    assert "citation" in g
    assert g["citation"]["kind"] == "goal"
    assert "freshness" in g


def test_conflict_missing_reproduced_by_run(tmp_path):
    """A failure record whose reproduced_by run does not exist in evidence
    manifests is surfaced as a conflict."""
    _write_failure(tmp_path / "docs" / "failures", "FR-NAV-0002.md", _FR_ORPHAN_RUN)

    result = query_memory(tmp_path, "all")

    assert len(result["conflicts"]) >= 1
    c = next(c for c in result["conflicts"] if c["kind"] == "missing-run")
    assert c["memory"]["id"] == "FR-NAV-0002"
    assert c["memory"]["field"] == "reproduced_by"
    assert c["memory"]["value"] == "RUN-NONEXISTENT"
    assert "no run" in c["evidence"].lower() or "not found" in c["evidence"].lower()


def test_conflict_missing_superseded_by_adr(tmp_path):
    """An ADR whose superseded_by points to a non-existent ADR is surfaced
    as a conflict."""
    _write_adr(tmp_path / "docs" / "adr", "0004-orphan.md", _ADR_ORPHAN_SUPERSEDED)

    result = query_memory(tmp_path, "all")

    assert len(result["conflicts"]) >= 1
    c = next(c for c in result["conflicts"] if c["kind"] == "missing-adr")
    assert c["memory"]["id"] == "ADR-0004"
    assert c["memory"]["field"] == "superseded_by"
    assert c["memory"]["value"] == "ADR-9999"


def test_conflict_shows_both_sides_no_silent_resolution(tmp_path):
    """A conflict shows the memory claim and the evidence side; it does not
    silently choose one."""
    _write_failure(tmp_path / "docs" / "failures", "FR-NAV-0002.md", _FR_ORPHAN_RUN)

    result = query_memory(tmp_path, "all")

    c = next(c for c in result["conflicts"] if c["kind"] == "missing-run")
    # Both sides
    assert "memory" in c
    assert c["memory"]["id"] == "FR-NAV-0002"
    assert "evidence" in c
    assert c["memory"]["value"] != c["evidence"]  # They disagree


def test_scope_feat_filters_by_linked_feature(tmp_path):
    """feat: scope filters failure records and goals to those linked to the
    feature."""
    _write_failure(tmp_path / "docs" / "failures", "FR-NAV-0001.md", _WELL_FORMED_FR)
    _write_failure(tmp_path / "docs" / "failures", "FR-OTHER-0001.md", _FR_OTHER_FEATURE)
    _write_goal(tmp_path, "GOAL-NAV-001.md", _GOAL_OPEN)
    _write_goal(tmp_path, "GOAL-NAV-003.md", _GOAL_OTHER_FEATURE)

    result = query_memory(tmp_path, "feat:FEAT-NAV-017")

    assert len(result["failure_records"]) == 1
    assert result["failure_records"][0]["id"] == "FR-NAV-0001"
    assert len(result["open_goals"]) == 1
    assert result["open_goals"][0]["id"] == "GOAL-NAV-001"


def test_scope_sr_filters_by_linked_req(tmp_path):
    _write_failure(tmp_path / "docs" / "failures", "FR-NAV-0001.md", _WELL_FORMED_FR)
    _write_failure(tmp_path / "docs" / "failures", "FR-OTHER-0001.md", _FR_OTHER_FEATURE)

    result = query_memory(tmp_path, "sr:SR-017")

    assert len(result["failure_records"]) == 1
    assert result["failure_records"][0]["id"] == "FR-NAV-0001"


def test_scope_goal_filters_open_goals_to_that_goal(tmp_path):
    _write_goal(tmp_path, "GOAL-NAV-001.md", _GOAL_OPEN)
    _write_goal(tmp_path, "GOAL-NAV-003.md", _GOAL_OTHER_FEATURE)

    result = query_memory(tmp_path, "goal:GOAL-NAV-001")

    assert len(result["open_goals"]) == 1
    assert result["open_goals"][0]["id"] == "GOAL-NAV-001"


def test_scope_adr_filters_decisions_to_that_adr(tmp_path):
    _write_adr(tmp_path / "docs" / "adr", "0001-latch.md", _ADR_WELL_FORMED)
    _write_adr(tmp_path / "docs" / "adr", "0003-old.md", _ADR_SUPERSEDED)

    result = query_memory(tmp_path, "adr:ADR-0002")

    assert len(result["decisions"]) == 1
    assert result["decisions"][0]["id"] == "ADR-0002"


def test_scope_fr_filters_failure_records_to_that_record(tmp_path):
    _write_failure(tmp_path / "docs" / "failures", "FR-NAV-0001.md", _WELL_FORMED_FR)
    _write_failure(tmp_path / "docs" / "failures", "FR-OTHER-0001.md", _FR_OTHER_FEATURE)

    result = query_memory(tmp_path, "fr:FR-NAV-0001")

    assert len(result["failure_records"]) == 1
    assert result["failure_records"][0]["id"] == "FR-NAV-0001"
    assert len(result["rejected_hypotheses"]) == 1  # From that record


def test_scope_fr_with_no_hypotheses_returns_empty_hypotheses(tmp_path):
    _write_failure(tmp_path / "docs" / "failures", "FR-OTHER-0001.md", _FR_OTHER_FEATURE)

    result = query_memory(tmp_path, "fr:FR-OTHER-0001")

    assert len(result["failure_records"]) == 1
    assert len(result["rejected_hypotheses"]) == 0


def test_unknown_scope_ref_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="invalid scope"):
        query_memory(tmp_path, "bogus:xxx")


def test_unsupported_scope_kind_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="unsupported scope kind"):
        query_memory(tmp_path, "bundle:test")


def test_absent_artifacts_produce_empty_sections_not_errors(tmp_path):
    """A repo with no memory artifacts returns empty sections, never errors."""
    result = query_memory(tmp_path, "all")

    assert result["decisions"] == []
    assert result["failure_records"] == []
    assert result["rejected_hypotheses"] == []
    assert result["open_goals"] == []
    assert result["conflicts"] == []


def test_rejected_hypotheses_use_evidence_field_not_broken_ref(tmp_path):
    """Hypothesis evidence field is surfaced as-is (we never re-state it).
    The evidence field is a ref like run:RUN-..., not prose."""
    _write_failure(tmp_path / "docs" / "failures", "FR-NAV-0001.md", _WELL_FORMED_FR)

    result = query_memory(tmp_path, "all")

    h = result["rejected_hypotheses"][0]
    assert h["evidence"].startswith("run:")
    # No prose restatement of the evidence run
    assert "completed" not in h["evidence"]  # Not the run's content


def test_decision_citation_includes_sha256(tmp_path):
    _write_adr(tmp_path / "docs" / "adr", "0001-latch.md", _ADR_WELL_FORMED)

    result = query_memory(tmp_path, "all")

    d = result["decisions"][0]
    assert d["citation"]["sha256"] is not None
    assert len(d["citation"]["sha256"]) == 64


def test_failure_record_no_reproduced_by_does_not_cause_conflict(tmp_path):
    """A failure record with reproduced_by: null is not a conflict — it simply
    has no reproduction run."""
    _write_failure(tmp_path / "docs" / "failures", "FR-OTHER-0001.md", _FR_OTHER_FEATURE)

    result = query_memory(tmp_path, "all")

    # No conflict about missing-run for this record
    run_conflicts = [c for c in result["conflicts"] if c["kind"] == "missing-run"]
    assert not any(c["memory"]["id"] == "FR-OTHER-0001" for c in run_conflicts)


def test_scope_feat_returns_bundle_linked_decisions(tmp_path):
    """T-001 regression: a feat: scope resolves its decisions through the
    bundle map, so a linked decision must appear even though the ADR's id
    is bare (ADR-0002) while the bundle member ref is prefixed
    (adr:ADR-0002). Previously the prefixed ref never matched the adrs
    dict key and the decision was silently dropped."""
    _write_adr(tmp_path / "docs" / "adr", "0001-latch.md", _ADR_WELL_FORMED)
    _write_bundle(
        tmp_path / "bundles",
        "nav-latch",
        ["feat:FEAT-NAV-017", "adr:ADR-0002"],
    )

    result = query_memory(tmp_path, "feat:FEAT-NAV-017")

    assert len(result["decisions"]) == 1
    assert result["decisions"][0]["id"] == "ADR-0002"


def test_scope_sr_returns_bundle_linked_decisions(tmp_path):
    """T-001 regression, sr: side: same bundle-map normalization."""
    _write_adr(tmp_path / "docs" / "adr", "0001-latch.md", _ADR_WELL_FORMED)
    _write_bundle(tmp_path / "bundles", "nav-latch", ["sr:SR-017", "adr:ADR-0002"])

    result = query_memory(tmp_path, "sr:SR-017")

    assert len(result["decisions"]) == 1
    assert result["decisions"][0]["id"] == "ADR-0002"


def test_scope_feat_surfaces_missing_superseded_adr_via_bundle(tmp_path):
    """T-001 regression: a feat: scope's bundle-linked ADR whose
    superseded_by names a non-declared ADR surfaces as a missing-adr
    conflict — previously the prefixed member ref never resolved against
    the adrs dict, so the conflict check was silently skipped."""
    _write_adr(tmp_path / "docs" / "adr", "0004-orphan.md", _ADR_ORPHAN_SUPERSEDED)
    _write_bundle(
        tmp_path / "bundles",
        "nav-orphan",
        ["feat:FEAT-NAV-017", "adr:ADR-0004"],
    )

    result = query_memory(tmp_path, "feat:FEAT-NAV-017")

    assert len(result["decisions"]) == 1
    assert result["decisions"][0]["id"] == "ADR-0004"
    conflicts = [c for c in result["conflicts"] if c["kind"] == "missing-adr"]
    assert len(conflicts) == 1
    assert conflicts[0]["memory"]["id"] == "ADR-0004"
    assert conflicts[0]["memory"]["field"] == "superseded_by"
    assert conflicts[0]["memory"]["value"] == "ADR-9999"


def test_conflict_hypothesis_evidence_bare_run_missing(tmp_path):
    """T-002 regression: a hypothesis whose evidence is a BARE run id (no
    run: prefix) is detected the same way as reproduced_by's bare id and
    surfaces as a conflict when no manifest records it — previously only
    run:-prefixed evidence was checked, so the bare id passed silently."""
    _write_failure(
        tmp_path / "docs" / "failures", "FR-NAV-0003.md", _FR_BARE_HYPOTHESIS_EVIDENCE
    )

    result = query_memory(tmp_path, "all")

    hyp_conflicts = [
        c
        for c in result["conflicts"]
        if c["kind"] == "missing-run" and c["memory"]["field"] == "evidence"
    ]
    assert len(hyp_conflicts) == 1
    assert hyp_conflicts[0]["memory"]["id"] == "FR-NAV-0003"
    assert hyp_conflicts[0]["memory"]["value"] == "RUN-NONEXISTENT"
    assert "RUN-NONEXISTENT" in hyp_conflicts[0]["evidence"]


def test_conflict_hypothesis_evidence_run_missing(tmp_path):
    """A rejected hypothesis whose evidence ref is a run: that does not exist
    is surfaced as a conflict."""
    _write_failure(tmp_path / "docs" / "failures", "FR-NAV-0001.md", _WELL_FORMED_FR)
    # Do NOT write the evidence run — RUN-20260811-1702 does not exist

    result = query_memory(tmp_path, "all")

    # The hypothesis's evidence run:RUN-20260811-1702 does not exist
    hyp_conflicts = [c for c in result["conflicts"] if c["kind"] == "missing-run"]
    assert any("RUN-20260811-1702" in c["evidence"] for c in hyp_conflicts)

def test_decisions_ordered_by_declared_id(tmp_path):
    """Decision entries sort by declared ADR id, not by file order (determinism)."""
    # Filename order (0001 < 0002) is the opposite of declared id order
    # (ADR-0002 > ADR-0001), so an unsorted projection would expose file order.
    _write_adr(
        tmp_path / "docs" / "adr",
        "0001-first.md",
        _ADR_WELL_FORMED,  # id ADR-0002
    )
    _write_adr(
        tmp_path / "docs" / "adr",
        "0002-second.md",
        _ADR_SUPERSEDED,  # id ADR-0003
    )

    result = query_memory(tmp_path, "all")

    ids = [d["id"] for d in result["decisions"]]
    assert ids == sorted(ids)


def test_task_ref_reproduced_by_never_conflicts(tmp_path):
    """A `reproduced_by` that names a task (`task:T-###` or bare `T-###`) is a
    task ref, not a run ref: it must never surface a missing-run conflict."""
    task_ref_fr = (
        _WELL_FORMED_FR.replace("id: FR-NAV-0001", "id: FR-TASK-0001")
        .replace("reproduced_by: RUN-20260811-1702", 'reproduced_by: "task:T-042"')
    )
    bare_task_fr = (
        _WELL_FORMED_FR.replace("id: FR-NAV-0001", "id: FR-TASK-0002")
        .replace("reproduced_by: RUN-20260811-1702", 'reproduced_by: "T-042"')
    )
    _write_failure(tmp_path / "docs" / "failures", "FR-TASK-0001.md", task_ref_fr)
    _write_failure(tmp_path / "docs" / "failures", "FR-TASK-0002.md", bare_task_fr)

    result = query_memory(tmp_path, "all")

    run_conflicts = [
        c
        for c in result["conflicts"]
        if c["kind"] == "missing-run" and c["memory"]["field"] == "reproduced_by"
    ]
    assert run_conflicts == []


def test_run_prefixed_reproduced_by_missing_conflict(tmp_path):
    """A `run:`-prefixed `reproduced_by` whose run has no manifest surfaces as
    a missing-run conflict (the other accepted run-ref spelling)."""
    _write_failure(
        tmp_path / "docs" / "failures",
        "FR-RUNPREFIX-0001.md",
        _WELL_FORMED_FR.replace(
            "reproduced_by: RUN-20260811-1702", "reproduced_by: run:RUN-MISSING-001"
        ),
    )

    result = query_memory(tmp_path, "all")

    conflicts = [
        c
        for c in result["conflicts"]
        if c["kind"] == "missing-run" and c["memory"]["field"] == "reproduced_by"
    ]
    assert len(conflicts) == 1
    assert conflicts[0]["memory"]["value"] == "run:RUN-MISSING-001"
    assert "RUN-MISSING-001" in conflicts[0]["evidence"]


def test_goal_scope_terminal_goal_yields_no_open_entry(tmp_path):
    """A `goal:` ref that resolves to a terminal-state goal (REACHED) is
    recorded but not open: the read resolves with an empty open_goals list."""
    _write_goal(tmp_path, "GOAL-NAV-002.md", _GOAL_CLOSED)

    result = query_memory(tmp_path, "goal:GOAL-NAV-002")

    assert result["scope"] == "goal:GOAL-NAV-002"
    assert result["open_goals"] == []
