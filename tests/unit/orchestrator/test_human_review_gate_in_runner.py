from __future__ import annotations

import subprocess
import pytest
from factory.orchestrator.backends import FakeAgentBackend, FakeGateRunner
from factory.orchestrator.git_ops import FakeGitOps
from factory.orchestrator.human_review import FakeHumanReviewGate, HumanReviewDecision
from factory.orchestrator.runner import run_next
from factory.orchestrator.types import AgentRole, AgentResult
from ._skill_fixtures import write_skill_stubs

pytestmark = pytest.mark.unit


def _repo(tmp_path):
    (tmp_path / "tasks").mkdir()
    (tmp_path / "tasks" / "T-001.md").write_text(
        "---\nid: T-001\ntitle: t\nstatus: todo\ndod:\n  - c\n---\nbody\n", encoding="utf-8")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "x.py").write_text("x = 1\n", encoding="utf-8")
    write_skill_stubs(tmp_path)
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=tmp_path, check=True)
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=tmp_path, check=True)
    return tmp_path


def _scripts(review_findings=None, n_review_calls=1):
    manifest = {
        "task_id": "T-001", "generated_by": "context-gatherer",
        "generated_at": "2026-07-16T14:32:10Z",
        "coherence": {"proven": True, "checks": [{"name": "x", "pass": True}]},
        "context": {"task": "tasks/T-001.md", "source_files": ["src/x.py"], "skills": []},
        "reject": None,
    }
    review_result = AgentResult(True, {"dod_met": True, "findings": review_findings or []})
    return {
        AgentRole.CONTEXT_GATHERER: [AgentResult(True, manifest)],
        AgentRole.DEV: [AgentResult(True, {})] * n_review_calls,
        AgentRole.REVIEW: [review_result] * n_review_calls,
        AgentRole.SESSION_REVIEW: [AgentResult(True, {})],
    }


def test_approve_marks_task_done_and_commits_uncommitted_edits(tmp_path):
    repo = _repo(tmp_path)
    git_ops = FakeGitOps(head="abc123", has_uncommitted=True)
    human_review = FakeHumanReviewGate([HumanReviewDecision("approve", {})])

    path = run_next(
        repo, FakeAgentBackend(_scripts()), FakeGateRunner(),
        session_id="s1", git_info={"branch": "main"},
        human_review=human_review, git_ops=git_ops,
    )

    assert path is not None
    assert human_review.requests == [("T-001", "abc123")]
    assert git_ops.commit_messages == ["review: address direct edits during human review"]


def test_reject_feeds_comments_back_as_dev_feedback_and_retries(tmp_path):
    repo = _repo(tmp_path)
    git_ops = FakeGitOps(head="abc123", has_uncommitted=False)
    human_review = FakeHumanReviewGate([
        HumanReviewDecision("reject", {"src/x.py": "add a docstring"}),
        HumanReviewDecision("approve", {}),
    ])

    path = run_next(
        repo, FakeAgentBackend(_scripts(n_review_calls=2)), FakeGateRunner(),
        session_id="s1", git_info={"branch": "main"},
        human_review=human_review, git_ops=git_ops,
    )

    assert path is not None
    assert len(human_review.requests) == 2
    assert git_ops.commit_messages == []  # no uncommitted changes this time


def test_no_gate_configured_behaves_exactly_as_before(tmp_path):
    repo = _repo(tmp_path)
    path = run_next(
        repo, FakeAgentBackend(_scripts()), FakeGateRunner(),
        session_id="s1", git_info={"branch": "main"},
    )
    assert path is not None
