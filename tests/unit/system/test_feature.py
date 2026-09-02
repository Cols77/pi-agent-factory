"""Tests for the deterministic feature dossier and its query adapters."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from factory.evidence import manifests as evidence_manifests
from factory.system.feature import _recent_changes, feature_context
from factory.system.models import SystemScopeRef
from factory.system.queries import (
    ScopeKindError,
    ScopeNotFoundError,
    query_feature_context,
    query_vcycle,
    query_validation,
)

from ._fixtures import write_run_manifest, write_validation_report

pytestmark = pytest.mark.unit


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _commit(
    root: Path,
    subject: str,
    author_timestamp: str,
    paths: list[str],
    *,
    committer_timestamp: str | None = None,
) -> None:
    env = {
        **os.environ,
        "GIT_AUTHOR_DATE": author_timestamp,
        "GIT_COMMITTER_DATE": committer_timestamp or author_timestamp,
    }
    subprocess.run(["git", "add", "--", *paths], cwd=root, check=True)
    subprocess.run(["git", "commit", "-qm", subject], cwd=root, env=env, check=True)


def _feature_repo(root: Path) -> None:
    _write(
        root / "docs" / "features" / "FEAT-CONTEXT-001.md",
        "---\n"
        "id: FEAT-CONTEXT-001\n"
        "title: Feature dossier\n"
        "contains: [SR-002, SR-001]\n"
        "illustrates: [ADR-001]\n"
        "---\n\n"
        "Provide a trace-backed implementation dossier.\n",
    )
    _write(
        root / "requirements" / "SR-001.md",
        "---\n"
        "id: SR-001\n"
        "title: Connected requirement\n"
        "statement: The system shall connect the dossier.\n"
        "domain: behavioral\n"
        "---\n",
    )
    _write(
        root / "requirements" / "SR-002.md",
        "---\n"
        "id: SR-002\n"
        "title: Second connected requirement\n"
        "statement: The system shall retain validation state.\n"
        "domain: behavioral\n"
        "---\n",
    )
    _write(
        root / "tasks" / "T-001.md",
        "---\n"
        "id: T-001\n"
        "title: Implement connected requirement\n"
        "status: done\n"
        "dod: []\n"
        "source_plan: docs/superpowers/plans/feature-context.md\n"
        "satisfies: [SR-001]\n"
        "---\n",
    )
    _write(
        root / "tasks" / "T-999.md",
        "---\n"
        "id: T-999\n"
        "title: Do not leak this task\n"
        "status: done\n"
        "dod: []\n"
        "satisfies: [SR-UNRELATED]\n"
        "---\n",
    )
    _write(
        root / "docs" / "adr" / "ADR-001.md",
        "---\n"
        "id: ADR-001\n"
        "title: Follow the trace graph\n"
        "status: accepted\n"
        "---\n\n"
        "## Decision\n\nUse recorded graph links.\n",
    )
    _write(
        root / "docs" / "superpowers" / "plans" / "feature-context.md",
        "# Feature context plan\n\nSee docs/superpowers/specs/feature-context.md.\n",
    )
    _write(
        root / "docs" / "superpowers" / "specs" / "feature-context.md",
        "# Feature context specification\n",
    )
    _write(
        root / "goals" / "GOAL-001.md",
        "---\n"
        "id: GOAL-001\n"
        "title: Dossier goal\n"
        "demonstrates: [SR-001]\n"
        "evaluates: [MET-001]\n"
        "---\n",
    )
    _write(
        root / "metrics" / "MET-001.md",
        "---\n"
        "id: MET-001\n"
        "title: Dossier metric\n"
        "---\n",
    )
    _write(root / "src" / "connected.py", "VALUE = 1\n")
    _write(root / "src" / "unrelated.py", "VALUE = 2\n")
    write_run_manifest(root, task_id="T-001", changed_files=["src/connected.py"])
    write_run_manifest(
        root,
        run_id="run-unrelated",
        task_id="T-999",
        changed_files=["src/unrelated.py"],
    )
    write_validation_report(
        root,
        [
            {"id": "SR-001", "passed": True, "stale": False, "artifacts": []},
            {"id": "SR-002", "passed": False, "stale": False, "artifacts": []},
        ],
    )


@pytest.mark.sr("SR-001")
def test_feature_context_contains_only_connected_recorded_facts(tmp_path):
    _feature_repo(tmp_path)
    _write(tmp_path / "docs" / "features" / "FEAT-BROKEN.md", "---\nnot: [valid\n")

    result = feature_context(tmp_path, "FEAT-CONTEXT-001")

    assert result["id"] == "FEAT-CONTEXT-001"
    assert result["title"] == "Feature dossier"
    assert result["intent"] == "Provide a trace-backed implementation dossier."
    assert [requirement["id"] for requirement in result["requirements"]] == ["SR-001", "SR-002"]
    assert [record["id"] for record in result["design_records"]] == [
        "ADR-001",
        "plan:feature-context.md",
        "spec:feature-context.md",
    ]
    assert [entry["task"]["id"] for entry in result["implementation"]] == ["T-001"]
    assert result["implementation"][0]["runs"][0]["implementation"]["changed_files"] == [
        "src/connected.py"
    ]
    assert result["implementation_files"] == ["src/connected.py"]
    assert result["verification"] == [
        {"id": "SR-001", "state": "passed", "stale": False},
        {"id": "SR-002", "state": "failed", "stale": False},
    ]
    assert result["goal_ids"] == ["GOAL-001"]
    assert result["metric_ids"] == ["MET-001"]
    assert result["latest_simulation_evidence"] is None
    assert result["recent_changes"] == []


def test_feature_queries_preserve_scope_shape_and_exact_resolution(tmp_path):
    _feature_repo(tmp_path)
    feature_scope = SystemScopeRef(kind="feat", ref="feat:FEAT-CONTEXT-001")

    dossier = query_feature_context(tmp_path, feature_scope)
    feature_vcycle = query_vcycle(tmp_path, feature_scope)
    sr_vcycle = query_vcycle(tmp_path, SystemScopeRef(kind="sr", ref="sr:SR-001"))

    assert dossier["scope"] == {"kind": "feat", "ref": "feat:FEAT-CONTEXT-001"}
    assert dossier["dossier"]["id"] == "FEAT-CONTEXT-001"
    assert feature_vcycle["scope"] == {"kind": "feat", "ref": "feat:FEAT-CONTEXT-001"}
    assert feature_vcycle["vcycle"]["anchor"] == "feat:FEAT-CONTEXT-001"
    assert sr_vcycle["vcycle"]["anchor"] == "sr:SR-001"

    with pytest.raises(ScopeKindError):
        feature_context(tmp_path, "feat:FEAT-CONTEXT-001")
    with pytest.raises(ScopeKindError):
        query_feature_context(tmp_path, SystemScopeRef(kind="sr", ref="sr:SR-001"))
    with pytest.raises(ScopeKindError):
        query_vcycle(tmp_path, SystemScopeRef(kind="task", ref="task:T-001"))
    with pytest.raises(ScopeNotFoundError):
        query_feature_context(tmp_path, SystemScopeRef(kind="feat", ref="feat:FEAT-UNKNOWN"))
    with pytest.raises(ScopeNotFoundError):
        query_vcycle(tmp_path, SystemScopeRef(kind="feat", ref="feat:FEAT-UNKNOWN"))


def test_vcycle_query_carries_an_additive_node_statuses_map(tmp_path):
    """Inc 6 Task 2: query_vcycle gains a `statuses` map so the human
    V-cycle view can colour failed/stale nodes without re-deriving any
    state in TS. Sources stay recorded-only: validation report for sr/br,
    goal registry for goals, task frontmatter for tasks."""
    _feature_repo(tmp_path)
    write_validation_report(
        tmp_path,
        [
            {"id": "SR-001", "passed": True, "stale": False, "metric": "m1"},
            {"id": "SR-002", "passed": False, "stale": True, "metric": "m2"},
        ],
    )
    _write(
        tmp_path / "goals" / "GOAL-001.md",
        "---\n"
        "id: GOAL-001\n"
        "title: Reach the dossier\n"
        "demonstrates: [SR-001]\n"
        "state: REACHED\n"
        "---\n",
    )

    result = query_vcycle(tmp_path, SystemScopeRef(kind="feat", ref="feat:FEAT-CONTEXT-001"))

    statuses = result["statuses"]
    assert statuses["SR-001"] == {"kind": "validation", "state": "passed", "stale": False}
    assert statuses["SR-002"] == {"kind": "validation", "state": "failed", "stale": True}
    assert statuses["GOAL-001"] == {"kind": "goal", "state": "REACHED"}
    assert statuses["T-001"] == {"kind": "task", "state": "done"}
    # A requirement outside the slice never appears, and node ids missing
    # from every status source are simply absent (TS renders them neutral).
    assert set(statuses) == {"SR-001", "SR-002", "GOAL-001", "T-001"}


def test_query_validation_assembles_goal_aware_status_and_evidence(tmp_path):
    """Inc 6 Task 4: query_validation -- a requirement's recorded validation
    state, its goal-aware D5 status (VALIDATED/REGRESSED/VERIFICATION_PENDING),
    the goals that produced it and the validating simulation runs."""
    _feature_repo(tmp_path)
    write_validation_report(tmp_path, [{"id": "SR-001", "passed": True, "stale": False}])
    _write(
        tmp_path / "goals" / "GOAL-001.md",
        "---\n"
        "id: GOAL-001\n"
        "title: Reach the dossier\n"
        "demonstrates: [SR-001]\n"
        "state: REACHED\n"
        "---\n",
    )
    evidence_manifests.write_run_manifest(
        tmp_path / "evidence",
        {
            "run": "RUN-20260811-1702",
            "experiment": "SIM-047",
            "feature": "FEAT-CONTEXT-001",
            "requirements": ["SR-001"],
            "goals": ["GOAL-001"],
            "commit": "f92b004",
            "result": "passed",
        },
    )

    result = query_validation(tmp_path, SystemScopeRef(kind="sr", ref="sr:SR-001"))

    assert result["scope"] == {"kind": "sr", "ref": "sr:SR-001"}
    validation = result["validation"]
    assert validation["id"] == "SR-001"
    assert validation["raw_state"] == "passed"
    assert validation["stale"] is False
    assert validation["goal_state"] == "VALIDATED"
    assert validation["goals"] == [{"id": "GOAL-001", "state": "REACHED"}]
    assert validation["runs"] == ["RUN-20260811-1702"]


def test_query_validation_reports_regressed_and_never_validated(tmp_path):
    """A REGRESSED goal flips the goal-aware status; an SR with no report
    entry is never_validated -- never a guessed pass. Non-sr scopes are
    rejected."""
    _feature_repo(tmp_path)
    _write(
        tmp_path / "goals" / "GOAL-002.md",
        "---\n"
        "id: GOAL-002\n"
        "title: Regressed goal\n"
        "demonstrates: [SR-002]\n"
        "state: REGRESSED\n"
        "---\n",
    )
    _write(
        tmp_path / "requirements" / "SR-003.md",
        "---\n"
        "id: SR-003\n"
        "title: Never validated\n"
        "statement: The system shall stay unvalidated in this fixture.\n"
        "domain: behavioral\n"
        "---\n",
    )

    # SR-002 is recorded as failed in _feature_repo's report; the goal-aware
    # status still follows the REGRESSED goal (D5 priority: REGRESSED wins).
    regressed = query_validation(tmp_path, SystemScopeRef(kind="sr", ref="sr:SR-002"))
    assert regressed["validation"]["raw_state"] == "failed"
    assert regressed["validation"]["goal_state"] == "REGRESSED"
    assert regressed["validation"]["runs"] == []
    assert regressed["validation"]["metrics"] == []

    # SR-003 has no report entry at all: never_validated, never a pass.
    never = query_validation(tmp_path, SystemScopeRef(kind="sr", ref="sr:SR-003"))
    assert never["validation"]["raw_state"] == "never_validated"
    assert never["validation"]["goal_state"] is None


def test_query_validation_live_staleness_reports_verification_stale(tmp_path):
    """Inc 7 Task 4: after a requirement's content changes (A→C spec §30),
    the live checksum recomputation in query_validation flips goal_state from
    VALIDATED to VERIFICATION_STALE without re-running the validation pipeline."""
    _feature_repo(tmp_path)

    # Write SR-100 with a binding + matching checksum.
    from factory.requirements.register import content_checksum, parse_requirement

    sr_path = tmp_path / "requirements" / "SR-100.md"
    sr_path.write_text(
        "---\n"
        "id: SR-100\n"
        "title: Stale test\n"
        "statement: The system shall connect.\n"
        "domain: behavioral\n"
        "upstream: []\n"
        "binding:\n"
        "  experiment: sim-001\n"
        "  metric: pass_rate\n"
        "  assert: '>= 0.9'\n"
        "  trials: 1\n"
        "---\n",
        encoding="utf-8",
    )
    req = parse_requirement(sr_path)
    checksum = content_checksum(req)
    # Rewrite with the checksum attached.
    sr_path.write_text(
        "---\n"
        "id: SR-100\n"
        "title: Stale test\n"
        "statement: The system shall connect.\n"
        "domain: behavioral\n"
        "upstream: []\n"
        "binding:\n"
        "  experiment: sim-001\n"
        "  metric: pass_rate\n"
        "  assert: '>= 0.9'\n"
        "  trials: 1\n"
        f"checksum: {checksum}\n"
        "---\n",
        encoding="utf-8",
    )

    write_validation_report(
        tmp_path,
        [{"id": "SR-100", "passed": True, "stale": False, "artifacts": []}],
    )
    _write(
        tmp_path / "goals" / "GOAL-100.md",
        "---\n"
        "id: GOAL-100\n"
        "title: Stale goal\n"
        "demonstrates: [SR-100]\n"
        "state: REACHED\n"
        "---\n",
    )

    # Before change: checksum matches → VALIDATED.
    result = query_validation(tmp_path, SystemScopeRef(kind="sr", ref="sr:SR-100"))
    assert result["validation"]["goal_state"] == "VALIDATED"
    assert result["validation"]["stale"] is False

    # Change the statement (A→C). The checksum no longer matches.
    sr_path.write_text(
        "---\n"
        "id: SR-100\n"
        "title: Stale test\n"
        "statement: The system shall REALLY connect.\n"
        "domain: behavioral\n"
        "upstream: []\n"
        "binding:\n"
        "  experiment: sim-001\n"
        "  metric: pass_rate\n"
        "  assert: '>= 0.9'\n"
        "  trials: 1\n"
        f"checksum: {checksum}\n"
        "---\n",
        encoding="utf-8",
    )

    result = query_validation(tmp_path, SystemScopeRef(kind="sr", ref="sr:SR-100"))
    assert result["validation"]["goal_state"] == "VERIFICATION_STALE"
    assert result["validation"]["stale"] is True

    with pytest.raises(ScopeKindError):
        query_validation(tmp_path, SystemScopeRef(kind="feat", ref="feat:FEAT-CONTEXT-001"))


def test_feature_context_recent_changes_is_empty_without_git_history(tmp_path):
    _feature_repo(tmp_path)

    result = feature_context(tmp_path, "FEAT-CONTEXT-001")

    assert result["implementation_files"] == ["src/connected.py"]
    assert result["recent_changes"] == []


def test_recent_changes_queries_all_evidenced_paths_once(tmp_path, monkeypatch):
    calls: list[list[str]] = []

    def run(command: list[str], **_kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, stdout="")

    monkeypatch.setattr("factory.system.feature.subprocess.run", run)

    assert _recent_changes(tmp_path, ["src/second.py", "src/*"], limit=3) == []
    assert calls == [
        [
            "git",
            "log",
            "-n",
            "3",
            "--format=%H%x00%aI%x00%s",
            "--",
            ":(literal)src/*",
            ":(literal)src/second.py",
        ],
    ]


def test_recent_changes_treats_wildcard_evidence_as_a_literal_pathspec(tmp_path):
    _write(tmp_path / "src" / "unrelated.py", "VERSION = 0\n")
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=tmp_path, check=True)
    _commit(tmp_path, "base", "2026-01-01T00:00:00+00:00", ["."])
    _write(tmp_path / "src" / "unrelated.py", "VERSION = 1\n")
    _commit(tmp_path, "unrelated wildcard match", "2026-01-02T00:00:00+00:00", ["src/unrelated.py"])

    changes = _recent_changes(tmp_path, ["src/*"], limit=1)

    assert changes == []


def test_recent_changes_preserves_single_git_log_order_for_inverse_author_dates(tmp_path, monkeypatch):
    _write(tmp_path / "src" / "evidenced.py", "VERSION = 0\n")
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=tmp_path, check=True)
    _commit(tmp_path, "base", "2026-01-01T00:00:00+00:00", ["."])
    _write(tmp_path / "src" / "evidenced.py", "VERSION = 1\n")
    _commit(
        tmp_path,
        "author newest parent",
        "2026-01-03T00:00:00+00:00",
        ["src/evidenced.py"],
        committer_timestamp="2026-01-01T01:00:00+00:00",
    )
    _write(tmp_path / "src" / "evidenced.py", "VERSION = 2\n")
    _commit(
        tmp_path,
        "author older child",
        "2026-01-02T00:00:00+00:00",
        ["src/evidenced.py"],
        committer_timestamp="2026-01-04T00:00:00+00:00",
    )
    expected_subjects = subprocess.run(
        ["git", "log", "-n", "2", "--format=%s", "--", ":(literal)src/evidenced.py"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()
    actual_run = subprocess.run
    calls: list[list[str]] = []

    def run(command: list[str], **kwargs):
        calls.append(command)
        return actual_run(command, **kwargs)

    monkeypatch.setattr("factory.system.feature.subprocess.run", run)

    changes = _recent_changes(tmp_path, ["src/evidenced.py"], limit=2)

    assert [change["subject"] for change in changes] == expected_subjects
    assert calls == [
        [
            "git",
            "log",
            "-n",
            "2",
            "--format=%H%x00%aI%x00%s",
            "--",
            ":(literal)src/evidenced.py",
        ]
    ]


@pytest.mark.sr("SR-001")
def test_feature_context_never_treats_missing_validation_as_a_pass(tmp_path):
    _feature_repo(tmp_path)
    (tmp_path / "validation" / "validation-report.json").unlink()

    result = feature_context(tmp_path, "FEAT-CONTEXT-001")

    assert result["verification"] == [
        {"id": "SR-001", "state": "never_validated", "stale": False},
        {"id": "SR-002", "state": "never_validated", "stale": False},
    ]


def test_feature_context_recent_changes_are_bounded_deduplicated_and_in_git_order(tmp_path):
    _feature_repo(tmp_path)
    evidenced_paths = [
        "src/connected.py",
        *[f"src/evidenced-{number}.py" for number in range(1, 7)],
        "src/evidenced-6-extra.py",
        "src/offset-early.py",
        "src/offset-late.py",
    ]
    for path in evidenced_paths[1:]:
        _write(tmp_path / path, "VERSION = 0\n")
    write_run_manifest(
        tmp_path,
        run_id="run-many",
        task_id="T-001",
        changed_files=evidenced_paths,
    )

    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=tmp_path, check=True)
    _commit(tmp_path, "base", "2026-01-01T00:00:00+00:00", ["."])
    for number in range(1, 6):
        path = f"src/evidenced-{number}.py"
        _write(tmp_path / path, f"VERSION = {number}\n")
        _commit(
            tmp_path,
            f"evidenced change {number}",
            f"2026-01-02T00:00:0{number}+00:00",
            [path],
        )
    _write(tmp_path / "src" / "evidenced-6.py", "VERSION = 6\n")
    _write(tmp_path / "src" / "evidenced-6-extra.py", "VERSION = 6\n")
    _commit(
        tmp_path,
        "evidenced change 6",
        "2026-01-02T00:00:06+00:00",
        ["src/evidenced-6.py", "src/evidenced-6-extra.py"],
    )
    _write(tmp_path / "src" / "offset-early.py", "OFFSET = 'early'\n")
    _commit(
        tmp_path,
        "offset early",
        "2026-01-03T00:00:00+10:00",
        ["src/offset-early.py"],
    )
    _write(tmp_path / "src" / "offset-late.py", "OFFSET = 'late'\n")
    _commit(
        tmp_path,
        "offset late",
        "2026-01-02T20:00:00+00:00",
        ["src/offset-late.py"],
    )
    _write(tmp_path / "src" / "unrelated.py", "VALUE = 3\n")
    _commit(
        tmp_path,
        "unrelated change",
        "2026-01-03T00:00:00+00:00",
        ["src/unrelated.py"],
    )
    expected_subjects = subprocess.run(
        [
            "git",
            "log",
            "-n",
            "5",
            "--format=%s",
            "--",
            *[f":(literal){path}" for path in sorted(evidenced_paths)],
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()

    changes = feature_context(tmp_path, "FEAT-CONTEXT-001")["recent_changes"]

    assert len(changes) == 5
    assert [change["subject"] for change in changes] == expected_subjects
    assert len({change["commit"] for change in changes}) == len(changes)
    assert "unrelated change" not in expected_subjects
    assert all("path" not in change for change in changes)
