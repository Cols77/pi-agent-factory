from __future__ import annotations

import json
import subprocess

import pytest

from factory.freshness.model import FreshnessSeverity
from factory.orchestrator.git_ops import SubprocessGitOps
from factory.orchestrator.journal import RunCheckpoint, RunJournal
from factory.preflight.checks import run_preflight
from factory.preflight.cli import main

pytestmark = pytest.mark.unit


def _repo(tmp_path, *, exempt: bool = True):
    repo = tmp_path / "repo"
    repo.mkdir(parents=True)
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True)
    (repo / "tasks").mkdir()
    (repo / "requirements").mkdir()
    (repo / ".factory").mkdir()
    trace = "trace_exempt: true\ntrace_exempt_reason: tooling task\n" if exempt else ""
    (repo / "tasks" / "T-001-example.md").write_text(
        f"---\nid: T-001\ntitle: Example\nstatus: todo\ndod:\n  - works\n{trace}---\nbody\n",
        encoding="utf-8",
    )
    (repo / ".factory" / "factory.yaml").write_text(
        "gates:\n  unit:\n    - {cmd: 'python -m pytest'}\n", encoding="utf-8"
    )
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-qm", "base"], cwd=repo, check=True)
    return repo


def codes(report):
    return {issue.code: issue for issue in report.issues}


def test_clean_exempt_tooling_task_passes_preflight(tmp_path):
    report = run_preflight(_repo(tmp_path), "T-001")
    assert report.ok is True
    assert report.issues == []


def test_missing_selected_task_is_integrity_failure(tmp_path):
    report = run_preflight(_repo(tmp_path), "T-999")
    assert codes(report)["task_missing"].severity is FreshnessSeverity.INTEGRITY


def test_malformed_task_is_integrity_failure(tmp_path):
    repo = _repo(tmp_path)
    (repo / "tasks" / "T-001-example.md").write_text("not frontmatter", encoding="utf-8")
    report = run_preflight(repo, "T-001")
    assert codes(report)["task_register_invalid"].severity is FreshnessSeverity.INTEGRITY


def test_declared_missing_requirement_is_integrity_failure(tmp_path):
    repo = _repo(tmp_path)
    path = repo / "tasks" / "T-001-example.md"
    path.write_text(
        "---\nid: T-001\ntitle: Example\nstatus: todo\ndod:\n  - works\nsatisfies:\n  - SR-404\n---\nbody\n",
        encoding="utf-8",
    )
    report = run_preflight(repo, "T-001")
    assert codes(report)["requirement_missing"].severity is FreshnessSeverity.INTEGRITY


def test_missing_trace_links_block_non_exempt_task(tmp_path):
    report = run_preflight(_repo(tmp_path, exempt=False), "T-001")
    assert codes(report)["task_no_sr"].severity is FreshnessSeverity.BLOCKING
    assert codes(report)["task_no_plan"].severity is FreshnessSeverity.BLOCKING


def test_interrupted_run_requires_explicit_recovery_before_new_work(tmp_path):
    repo = _repo(tmp_path)
    git = SubprocessGitOps()
    head = git.head_commit(repo)
    run_dir = repo / "sessions" / ".factory-runs" / "by-session" / "run-1"
    RunJournal(run_dir).checkpoint(
        RunCheckpoint(
            1, "run-1", "T-001", "validation", 1, {}, head, head,
            git.worktree_fingerprint(repo, head), None, [], {}, None, [], "process_exit"
        )
    )
    issue = codes(run_preflight(repo, "T-001"))["interrupted_run"]
    assert issue.severity is FreshnessSeverity.BLOCKING
    assert "run-state inspect run-1" in issue.detail


def test_invalid_gate_config_is_integrity_failure(tmp_path):
    repo = _repo(tmp_path)
    (repo / ".factory" / "factory.yaml").write_text("gates: {}\n", encoding="utf-8")
    assert codes(run_preflight(repo, "T-001"))["factory_config_invalid"].severity is FreshnessSeverity.INTEGRITY


def test_non_git_directory_cannot_supply_a_baseline(tmp_path):
    repo = _repo(tmp_path)
    (repo / ".git").rename(repo / ".git-hidden")
    assert "baseline_unresolved" in codes(run_preflight(repo, "T-001"))


def test_cli_exit_codes_and_json_are_deterministic(tmp_path, capsys):
    clean = _repo(tmp_path / "clean")
    assert main(["--repo", str(clean), "--task", "T-001", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["ok"] is True

    blocked = _repo(tmp_path / "blocked", exempt=False)
    assert main(["--repo", str(blocked), "--task", "T-001", "--json"]) == 2
    assert json.loads(capsys.readouterr().out)["ok"] is False

    missing = _repo(tmp_path / "missing")
    assert main(["--repo", str(missing), "--task", "T-404", "--json"]) == 3
