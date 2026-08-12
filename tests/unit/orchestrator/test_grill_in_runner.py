from __future__ import annotations

import subprocess
import pytest

from factory.orchestrator.backends import FakeAgentBackend, FakeGateRunner
from factory.orchestrator.git_ops import SubprocessGitOps
from factory.orchestrator.grill import FakeGrillGate, GrillResult
from factory.orchestrator.human_review import FakeHumanReviewGate, HumanReviewDecision
from factory.orchestrator.runner import run_next
from factory.orchestrator.status import FakeStatusReporter
from factory.orchestrator.types import AgentRole, AgentResult
from ._skill_fixtures import write_skill_stubs

pytestmark = pytest.mark.unit


def _repo(tmp_path):
    (tmp_path / "tasks").mkdir()
    (tmp_path / "tasks" / "T-001.md").write_text(
        "---\nid: T-001\ntitle: t\nstatus: todo\ndod:\n  - c\n---\nbody\n", encoding="utf-8"
    )
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "x.py").write_text("x = 1\n", encoding="utf-8")
    write_skill_stubs(tmp_path)
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=tmp_path, check=True)
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=tmp_path, check=True)
    return tmp_path


def _scripts():
    manifest = {
        "task_id": "T-001",
        "generated_by": "context-gatherer",
        "generated_at": "2026-07-16T14:32:10Z",
        "coherence": {"checks": []},
        "context": {"task": "tasks/T-001.md", "source_files": ["src/x.py"], "skills": []},
        "reject": None,
    }
    return {
        AgentRole.CONTEXT_GATHERER: [AgentResult(True, manifest)],
        AgentRole.DEV: [AgentResult(True, {})],
        AgentRole.REVIEW: [AgentResult(True, {"dod_met": True, "findings": []})],
        AgentRole.SESSION_REVIEW: [AgentResult(True, {})],
    }


def _approve_human():
    return FakeHumanReviewGate([HumanReviewDecision("approve", [])])


def test_grill_runs_after_context_gather_and_proceeds(tmp_path):
    repo = _repo(tmp_path)
    grill = FakeGrillGate([GrillResult("agreed")])
    path = run_next(
        repo,
        FakeAgentBackend(_scripts()),
        FakeGateRunner(),
        session_id="s1",
        git_info={"branch": "main"},
        human_review=_approve_human(),
        grill_gate=grill,
    )
    assert path is not None
    assert grill.requests == ["T-001"]


def test_grill_skipped_verdict_proceeds(tmp_path):
    repo = _repo(tmp_path)
    grill = FakeGrillGate([GrillResult("skipped")])
    path = run_next(
        repo,
        FakeAgentBackend(_scripts()),
        FakeGateRunner(),
        session_id="s1",
        git_info={"branch": "main"},
        human_review=_approve_human(),
        grill_gate=grill,
    )
    assert path is not None
    assert grill.requests == ["T-001"]


def test_grill_not_agreed_proceeds_and_does_not_hard_block(tmp_path):
    repo = _repo(tmp_path)
    grill = FakeGrillGate([GrillResult("not-agreed", "failed to demonstrate understanding")])
    path = run_next(
        repo,
        FakeAgentBackend(_scripts()),
        FakeGateRunner(),
        session_id="s1",
        git_info={"branch": "main"},
        human_review=_approve_human(),
        grill_gate=grill,
    )
    # The grill never forbids dev: not-agreed still completes the run.
    assert path is not None
    assert grill.requests == ["T-001"]


def test_grill_reports_blocked_then_completed(tmp_path):
    repo = _repo(tmp_path)
    status = FakeStatusReporter()
    run_next(
        repo,
        FakeAgentBackend(_scripts()),
        FakeGateRunner(),
        session_id="s1",
        git_info={"branch": "main"},
        human_review=_approve_human(),
        grill_gate=FakeGrillGate([GrillResult("agreed")]),
        status=status,
    )
    states = [c["node_state"] for c in status.calls if c["node"] == "grill"]
    assert states == ["blocked", "completed"]


def test_auto_mode_skips_the_grill_even_if_gate_supplied(tmp_path):
    repo = _repo(tmp_path)
    grill = FakeGrillGate([GrillResult("agreed")])
    path = run_next(
        repo,
        FakeAgentBackend(_scripts()),
        FakeGateRunner(),
        session_id="s1",
        git_info={"branch": "main"},
        human_review=None,
        grill_gate=grill,  # no human => auto => grill skipped
    )
    assert path is not None
    assert grill.requests == []


def test_human_present_but_no_grill_gate_skips_grill(tmp_path):
    repo = _repo(tmp_path)
    # No grill gate is supplied to run_task -- grill must be a no-op, never crash.
    path = run_next(
        repo,
        FakeAgentBackend(_scripts()),
        FakeGateRunner(),
        session_id="s1",
        git_info={"branch": "main"},
        human_review=_approve_human(),
        grill_gate=None,
    )
    assert path is not None


def test_grill_uses_real_git_ops_head_commit(tmp_path):
    repo = _repo(tmp_path)
    grill = FakeGrillGate([GrillResult("not-agreed")])
    status = FakeStatusReporter()
    run_next(
        repo,
        FakeAgentBackend(_scripts()),
        FakeGateRunner(),
        session_id="s1",
        git_info={"branch": "main"},
        human_review=_approve_human(),
        grill_gate=grill,
        status=status,
        git_ops=SubprocessGitOps(),
    )
    assert grill.requests == ["T-001"]
    assert [c["node_state"] for c in status.calls if c["node"] == "grill"] == [
        "blocked",
        "completed",
    ]
