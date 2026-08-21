"""Tests for factory.memory.conflict: fingerprint-based conflict surfacing.

Inc 8 Task 3's failing-tests-first contract: a memory note whose root cause
contradicts current evidence/code fingerprints (reused `factory.freshness`)
is surfaced as a `conflict` with BOTH sides shown, never silently resolved;
a note that agrees with current evidence is not flagged. Fingerprint
conflicts keep the same dict contract `durable.query_memory` introduced:
{kind, memory{id, field, value}, evidence, citation, freshness} — and
`query_conflicts` merges them with the structural conflicts.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from factory.memory.conflict import query_conflicts

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

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

_FR_NO_HYPOTHESIS = """---
id: FR-NAV-0002
title: Latch re-arm failure
reproduced_by: run:RUN-0001
root_cause: "Resume path skipped the latch re-arm (code:src/a.py)."
fix: "Re-arm the latch on resume."
regression_link: null
linked_req: []
linked_feature: [FEAT-NAV-017]
---

## Symptom
Latch stays cleared.
"""

_FR_OTHER_FEATURE = """---
id: FR-OTHER-0001
title: Other feature failure
reproduced_by: run:RUN-0002
root_cause: "Other root cause (code:src/other.py)."
fix: "Other fix."
regression_link: null
linked_req: []
linked_feature: [FEAT-OTHER]
---

## Symptom
Other failure.
"""

_FR_ORPHAN_RUN = """---
id: FR-NAV-0003
title: Orphan run failure
reproduced_by: RUN-NONEXISTENT
root_cause: "Some root cause (code:src/a.py)."
fix: "Some fix."
regression_link: null
linked_req: []
linked_feature: [FEAT-NAV-017]
---

## Symptom
Orphan run.
"""


def _digest_of(content: str) -> str:
    """The `sha256:<hex>` digest `fingerprint_file` produces for `content`."""
    return "sha256:" + hashlib.sha256(content.encode("utf-8")).hexdigest()


def _write_failure(failures_dir: Path, filename: str, text: str) -> Path:
    failures_dir.mkdir(parents=True, exist_ok=True)
    path = failures_dir / filename
    path.write_text(text, encoding="utf-8")
    return path


def _write_code_file(repo_root: Path, relpath: str, content: str) -> Path:
    """Write the code file as raw bytes: `write_text` would translate newlines
    to CRLF on Windows and corrupt the digest the manifest records — the
    fingerprint comparison must see exactly the bytes `_digest_of` hashes."""
    path = repo_root / relpath
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content.encode("utf-8"))
    return path


def _write_evidence_run(
    repo_root: Path,
    run_id: str,
    *,
    dependencies: list[tuple[str, str]] | None = None,
    result_commit: str = "a" * 40,
    start_commit: str = "b" * 40,
) -> Path:
    """Write a schema-valid v1 evidence run manifest for `run_id`."""
    path = repo_root / "evidence" / "runs" / f"{run_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": 2,
        "run_id": run_id,
        "task_id": "T-001",
        "started_at": "2026-08-11T17:02:00Z",
        "ended_at": "2026-08-11T17:45:00Z",
        "start_commit": start_commit,
        "result_commit": result_commit,
        "outcome": "completed",
        "inputs": {
            "task": {"path": "tasks/T-001.md", "sha256": "f" * 64},
            "requirements": [],
            "factory_config_sha256": "c" * 64,
        },
        "implementation": {
            "changed_files": [source for source, _ in (dependencies or [])],
            "patch": {"sha256": "d" * 64, "size": 0, "media_type": "text/plain"},
        },
        "dependencies": [
            {"name": f"file:{source}", "kind": "file", "digest": digest, "source": source}
            for source, digest in (dependencies or [])
        ],
        "validation": [],
        "reviews": [],
        "decisions": [],
        "publication": {"state": "local", "errors": []},
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True, check=True
    )
    return result.stdout.strip()


def _git_init(repo: Path) -> Path:
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test")
    return repo


def _git_commit(repo: Path, message: str) -> str:
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", message)
    return _git(repo, "rev-parse", "HEAD")


# ---------------------------------------------------------------------------
# Code-fingerprint conflicts (code-changed)
# ---------------------------------------------------------------------------


def test_code_changed_conflict_shows_both_sides(tmp_path):
    """A root cause citing a code file whose current fingerprint differs from
    the digest a cited run recorded is surfaced as a code-changed conflict
    with both sides (recorded digest + current fingerprint) shown."""
    _write_code_file(tmp_path, "navigation/preemption.py", "latch armed\n")
    _write_evidence_run(
        tmp_path,
        "RUN-20260811-1702",
        dependencies=[("navigation/preemption.py", _digest_of("latch armed\n"))],
    )
    _write_failure(tmp_path / "docs" / "failures", "FR-NAV-0001.md", _WELL_FORMED_FR)
    # The code changes AFTER the record was written and its run recorded.
    _write_code_file(tmp_path, "navigation/preemption.py", "latch armed + resume re-arm\n")

    result = query_conflicts(tmp_path, "all")

    changed = [c for c in result["conflicts"] if c["kind"] == "code-changed"]
    assert len(changed) == 1
    c = changed[0]
    assert c["memory"]["id"] == "FR-NAV-0001"
    assert c["memory"]["field"] == "root_cause"
    assert c["memory"]["value"] == "code:navigation/preemption.py"
    # Both sides: the recorded digest and the current fingerprint.
    assert _digest_of("latch armed\n") in c["evidence"]
    assert _digest_of("latch armed + resume re-arm\n") in c["evidence"]
    assert "current fingerprint" in c["evidence"]
    assert c["citation"]["kind"] == "failure"
    assert c["citation"]["sha256"] is not None
    assert c["freshness"]["state"] == "fresh"


def test_note_that_agrees_with_evidence_is_not_flagged(tmp_path):
    """A note whose cited code file's current fingerprint matches the digest
    the cited run recorded produces no conflicts at all."""
    _write_code_file(tmp_path, "navigation/preemption.py", "latch armed\n")
    _write_evidence_run(
        tmp_path,
        "RUN-20260811-1702",
        dependencies=[("navigation/preemption.py", _digest_of("latch armed\n"))],
    )
    _write_failure(tmp_path / "docs" / "failures", "FR-NAV-0001.md", _WELL_FORMED_FR)
    # File untouched: the note agrees with current evidence.

    result = query_conflicts(tmp_path, "all")

    assert result["conflicts"] == []


def test_code_changed_via_hypothesis_evidence(tmp_path):
    """A rejected hypothesis whose evidence cites a code file whose
    fingerprint drifted is surfaced with the hypothesis's record id and the
    evidence field."""
    _write_code_file(tmp_path, "navigation/preemption.py", "v1\n")
    _write_evidence_run(
        tmp_path,
        "RUN-20260811-1702",
        dependencies=[("navigation/preemption.py", _digest_of("v1\n"))],
    )
    fr = _WELL_FORMED_FR.replace(
        'evidence: "run:RUN-20260811-1702"', 'evidence: "code:navigation/preemption.py"'
    )
    _write_failure(tmp_path / "docs" / "failures", "FR-NAV-0001.md", fr)
    _write_code_file(tmp_path, "navigation/preemption.py", "v2\n")

    result = query_conflicts(tmp_path, "all")

    changed = [c for c in result["conflicts"] if c["kind"] == "code-changed"]
    assert any(c["memory"]["field"] == "evidence" for c in changed)
    hyp = next(c for c in changed if c["memory"]["field"] == "evidence")
    assert hyp["memory"]["id"] == "FR-NAV-0001"
    assert hyp["memory"]["value"] == "code:navigation/preemption.py"
    assert _digest_of("v2\n") in hyp["evidence"]


def test_missing_cited_file_is_a_conflict(tmp_path):
    """A run recorded a digest for a file that no longer exists on disk: the
    current fingerprint is `missing`, which differs from the recorded digest."""
    _write_evidence_run(
        tmp_path,
        "RUN-0001",
        dependencies=[("src/a.py", _digest_of("v1\n"))],
    )
    _write_failure(tmp_path / "docs" / "failures", "FR-NAV-0002.md", _FR_NO_HYPOTHESIS)
    # src/a.py is never written to disk.

    result = query_conflicts(tmp_path, "all")

    changed = [c for c in result["conflicts"] if c["kind"] == "code-changed"]
    assert len(changed) == 1
    assert changed[0]["memory"]["value"] == "code:src/a.py"
    assert "missing" in changed[0]["evidence"]


def test_cited_code_with_no_recorded_digest_is_not_flagged(tmp_path):
    """A code ref whose file exists but no cited run manifest records a
    digest for it cannot be compared: it is skipped, never guessed."""
    _write_code_file(tmp_path, "src/other.py", "v1\n")
    _write_evidence_run(tmp_path, "RUN-0001", dependencies=[])  # no file deps
    _write_failure(tmp_path / "docs" / "failures", "FR-NAV-0002.md", _FR_NO_HYPOTHESIS)
    _write_code_file(tmp_path, "src/other.py", "v2\n")

    result = query_conflicts(tmp_path, "all")

    assert [c["kind"] for c in result["conflicts"]] == []


# ---------------------------------------------------------------------------
# Commit-reachability conflicts (commit-unreachable)
# ---------------------------------------------------------------------------


def test_cited_commit_ancestor_is_not_flagged(tmp_path):
    """A note citing a commit that is an ancestor of HEAD agrees with current
    history: no commit-unreachable conflict."""
    repo = _git_init(tmp_path)
    _write_code_file(tmp_path, "src/a.py", "v1\n")
    base = _git_commit(repo, "base")
    _write_code_file(tmp_path, "src/a.py", "v2\n")
    head = _git_commit(repo, "second")
    _write_failure(
        tmp_path / "docs" / "failures",
        "FR-NAV-0001.md",
        _WELL_FORMED_FR.replace(
            "resume (ADR-0002, code:navigation/preemption.py)",
            f"resume (regression introduced by {base}, code:navigation/preemption.py)",
        ),
    )

    result = query_conflicts(tmp_path, "all")

    assert head == _git(repo, "rev-parse", "HEAD")
    unreachable = [c for c in result["conflicts"] if c["kind"] == "commit-unreachable"]
    assert unreachable == []


def test_cited_commit_no_longer_reachable_is_a_conflict(tmp_path):
    """A commit the note relies on that is no longer reachable from HEAD is
    surfaced with both sides (the note's sha vs current HEAD)."""
    repo = _git_init(tmp_path)
    _write_code_file(tmp_path, "src/a.py", "v1\n")
    base = _git_commit(repo, "base")
    _write_code_file(tmp_path, "src/a.py", "v2\n")
    orphaned = _git_commit(repo, "second")
    # Rewrite history: the orphan branch makes `orphaned` unreachable.
    _git(repo, "checkout", "-q", "--orphan", "fresh")
    _git(repo, "reset", "-q", "--hard", base)
    assert _git(repo, "rev-parse", "HEAD") == base
    _write_failure(
        tmp_path / "docs" / "failures",
        "FR-NAV-0001.md",
        _WELL_FORMED_FR.replace(
            "resume (ADR-0002, code:navigation/preemption.py)",
            f"resume (root cause from {orphaned}, code:navigation/preemption.py)",
        ),
    )

    result = query_conflicts(tmp_path, "all")

    unreachable = [c for c in result["conflicts"] if c["kind"] == "commit-unreachable"]
    assert len(unreachable) == 1
    c = unreachable[0]
    assert c["memory"]["id"] == "FR-NAV-0001"
    assert c["memory"]["field"] == "root_cause"
    assert c["memory"]["value"] == orphaned
    assert orphaned in c["evidence"]
    assert base in c["evidence"]  # current HEAD, the other side of the pair


def test_40hex_token_that_is_not_a_commit_is_not_flagged(tmp_path):
    """A 40-hex token that resolves to a blob, not a commit, is skipped: only
    provable commit citations are checked, never guessed."""
    repo = _git_init(tmp_path)
    _write_code_file(tmp_path, "src/a.py", "v1\n")
    _git_commit(repo, "base")
    blob = _git(repo, "hash-object", "-w", "src/a.py")
    assert len(blob) == 40 and blob != _git(repo, "rev-parse", "HEAD")
    _write_failure(
        tmp_path / "docs" / "failures",
        "FR-NAV-0001.md",
        _WELL_FORMED_FR.replace(
            "resume (ADR-0002, code:navigation/preemption.py)",
            f"resume (evidence blob {blob}, code:navigation/preemption.py)",
        ),
    )

    result = query_conflicts(tmp_path, "all")

    unreachable = [c for c in result["conflicts"] if c["kind"] == "commit-unreachable"]
    assert unreachable == []


def test_commit_check_degrades_without_git(tmp_path):
    """Without a git baseline the commit check is skipped entirely — a 40-hex
    token never invents a conflict."""
    _write_failure(
        tmp_path / "docs" / "failures",
        "FR-NAV-0001.md",
        _WELL_FORMED_FR.replace(
            "resume (ADR-0002, code:navigation/preemption.py)",
            f"resume (regression from {'a' * 40}, code:navigation/preemption.py)",
        ),
    )

    result = query_conflicts(tmp_path, "all")

    unreachable = [c for c in result["conflicts"] if c["kind"] == "commit-unreachable"]
    assert unreachable == []


# ---------------------------------------------------------------------------
# Run-superseded conflicts
# ---------------------------------------------------------------------------


def test_cited_run_superseded_by_dependency_drift(tmp_path):
    """A cited run whose recorded dependency digest no longer matches the
    file's current fingerprint is a run-superseded conflict: the note relies
    on a run whose recorded evidence no longer matches current state."""
    _write_code_file(tmp_path, "src/a.py", "v1\n")
    _write_evidence_run(
        tmp_path,
        "RUN-0001",
        dependencies=[("src/a.py", _digest_of("v1\n"))],
    )
    _write_failure(tmp_path / "docs" / "failures", "FR-NAV-0002.md", _FR_NO_HYPOTHESIS)
    _write_code_file(tmp_path, "src/a.py", "v2\n")

    result = query_conflicts(tmp_path, "all")

    superseded = [c for c in result["conflicts"] if c["kind"] == "run-superseded"]
    assert len(superseded) == 1
    c = superseded[0]
    assert c["memory"]["id"] == "FR-NAV-0002"
    assert c["memory"]["field"] == "reproduced_by"
    assert c["memory"]["value"] == "run:RUN-0001"
    assert "src/a.py" in c["evidence"]
    assert _digest_of("v1\n") in c["evidence"]
    assert _digest_of("v2\n") in c["evidence"]


def test_cited_run_that_matches_current_state_is_not_superseded(tmp_path):
    """A cited run whose recorded dependency digests match current files is
    not superseded."""
    _write_code_file(tmp_path, "src/a.py", "v1\n")
    _write_evidence_run(
        tmp_path,
        "RUN-0001",
        dependencies=[("src/a.py", _digest_of("v1\n"))],
    )
    _write_failure(tmp_path / "docs" / "failures", "FR-NAV-0002.md", _FR_NO_HYPOTHESIS)

    result = query_conflicts(tmp_path, "all")

    assert result["conflicts"] == []


def test_cited_run_superseded_by_orphaned_result_commit(tmp_path):
    """A cited run whose result commit is no longer reachable from HEAD is a
    run-superseded conflict."""
    repo = _git_init(tmp_path)
    _write_code_file(tmp_path, "src/a.py", "v1\n")
    base = _git_commit(repo, "base")
    _write_code_file(tmp_path, "src/a.py", "v2\n")
    orphaned = _git_commit(repo, "second")
    _write_evidence_run(
        tmp_path,
        "RUN-0001",
        dependencies=[("src/a.py", _digest_of("v2\n"))],
        result_commit=orphaned,
        start_commit=base,
    )
    _write_failure(tmp_path / "docs" / "failures", "FR-NAV-0002.md", _FR_NO_HYPOTHESIS)

    # HEAD is `orphaned`: the run's result commit is reachable — no conflict.
    assert [c["kind"] for c in query_conflicts(tmp_path, "all")["conflicts"]] == []

    # Rewrite history so the run's validated commit becomes unreachable.
    _git(repo, "checkout", "-q", "--orphan", "fresh")
    _git(repo, "reset", "-q", "--hard", base)

    result = query_conflicts(tmp_path, "all")

    superseded = [c for c in result["conflicts"] if c["kind"] == "run-superseded"]
    assert len(superseded) == 1
    assert orphaned in superseded[0]["evidence"]
    assert "not an ancestor of HEAD" in superseded[0]["evidence"]


# ---------------------------------------------------------------------------
# query_conflicts contract
# ---------------------------------------------------------------------------


def test_query_conflicts_merges_structural_and_fingerprint_conflicts(tmp_path):
    """query_conflicts returns both the structural conflicts (missing run)
    and the fingerprint conflicts (code changed) in one read."""
    _write_evidence_run(
        tmp_path,
        "RUN-0001",
        dependencies=[("src/a.py", _digest_of("v1\n"))],
    )
    _write_failure(tmp_path / "docs" / "failures", "FR-NAV-0002.md", _FR_NO_HYPOTHESIS)
    _write_failure(tmp_path / "docs" / "failures", "FR-NAV-0003.md", _FR_ORPHAN_RUN)
    _write_code_file(tmp_path, "src/a.py", "v2\n")

    result = query_conflicts(tmp_path, "all")

    assert result["scope"] == "all"
    kinds = {c["kind"] for c in result["conflicts"]}
    assert "missing-run" in kinds  # structural (durable)
    assert "code-changed" in kinds  # fingerprint (Task 3)
    assert "run-superseded" in kinds


def test_query_conflicts_is_scope_aware(tmp_path):
    """feat: scope checks only the records linked to that feature — an
    out-of-scope record never drags its own conflict into the read."""
    _write_code_file(tmp_path, "src/a.py", "v1\n")
    _write_code_file(tmp_path, "src/other.py", "v1\n")
    _write_evidence_run(
        tmp_path,
        "RUN-0001",
        dependencies=[("src/a.py", _digest_of("v1\n")), ("src/other.py", _digest_of("v1\n"))],
    )
    _write_evidence_run(tmp_path, "RUN-0002", dependencies=[("src/other.py", _digest_of("v1\n"))])
    _write_failure(tmp_path / "docs" / "failures", "FR-NAV-0002.md", _FR_NO_HYPOTHESIS)
    _write_failure(tmp_path / "docs" / "failures", "FR-OTHER-0001.md", _FR_OTHER_FEATURE)
    _write_code_file(tmp_path, "src/a.py", "v2\n")
    _write_code_file(tmp_path, "src/other.py", "v2\n")

    result = query_conflicts(tmp_path, "feat:FEAT-NAV-017")

    ids = {c["memory"]["id"] for c in result["conflicts"]}
    assert "FR-NAV-0002" in ids
    assert "FR-OTHER-0001" not in ids


def test_fingerprint_conflict_keeps_durable_contract(tmp_path):
    """A fingerprint conflict has exactly the durable contract keys: kind,
    memory{id, field, value}, evidence, citation, freshness."""
    _write_code_file(tmp_path, "src/a.py", "v1\n")
    _write_evidence_run(
        tmp_path,
        "RUN-0001",
        dependencies=[("src/a.py", _digest_of("v1\n"))],
    )
    _write_failure(tmp_path / "docs" / "failures", "FR-NAV-0002.md", _FR_NO_HYPOTHESIS)
    _write_code_file(tmp_path, "src/a.py", "v2\n")

    result = query_conflicts(tmp_path, "all")

    c = next(c for c in result["conflicts"] if c["kind"] == "code-changed")
    assert set(c) == {"kind", "memory", "evidence", "citation", "freshness"}
    assert set(c["memory"]) == {"id", "field", "value"}
    assert set(c["citation"]) == {"kind", "path", "sha256", "anchor"}
    assert c["freshness"]["state"] == "fresh"
    assert c["memory"]["value"] != c["evidence"]  # the pair never collapses


def test_conflicts_are_deterministic(tmp_path):
    """Two identical reads produce identical conflicts, ordered by
    (kind, memory id, memory field) — never by mtime."""
    _write_code_file(tmp_path, "src/a.py", "v1\n")
    _write_evidence_run(
        tmp_path,
        "RUN-0001",
        dependencies=[("src/a.py", _digest_of("v1\n"))],
    )
    _write_failure(tmp_path / "docs" / "failures", "FR-NAV-0002.md", _FR_NO_HYPOTHESIS)
    _write_failure(tmp_path / "docs" / "failures", "FR-NAV-0003.md", _FR_ORPHAN_RUN)
    _write_code_file(tmp_path, "src/a.py", "v2\n")

    first = query_conflicts(tmp_path, "all")
    second = query_conflicts(tmp_path, "all")

    assert first == second
    keys = [
        (c["kind"], c["memory"]["id"], c["memory"].get("field", ""))
        for c in first["conflicts"]
    ]
    assert keys == sorted(keys)
