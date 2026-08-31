from __future__ import annotations

import pytest
from factory.orchestrator.backends import FakeAgentBackend, FakeGateRunner
from factory.orchestrator.git_ops import FakeGitOps, SubprocessGitOps
from factory.orchestrator.human_review import Annotation, FakeHumanReviewGate, HumanReviewDecision
from factory.orchestrator.runner import run_next
from factory.orchestrator.status import FakeStatusReporter
from factory.orchestrator.types import AgentRole, AgentResult
from ._repo_fixtures import copy_repo_seed

pytestmark = pytest.mark.unit


def _repo(tmp_path):
    return copy_repo_seed(tmp_path, "run_next")


def _scripts(review_findings=None, n_review_calls=1):
    manifest = {
        "task_id": "T-001", "generated_by": "context-gatherer",
        "generated_at": "2026-07-16T14:32:10Z",
        "coherence": {"checks": [{"name": "c", "kind": "files_exist", "args": {"paths": ["src/x.py"]}}]},
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
    human_review = FakeHumanReviewGate([HumanReviewDecision("approve", [])])

    path = run_next(
        repo, FakeAgentBackend(_scripts()), FakeGateRunner(),
        session_id="s1", git_info={"branch": "main"},
        human_review=human_review, git_ops=git_ops,
    )

    assert path is not None
    assert human_review.requests == [("T-001", "abc123")]
    assert git_ops.commit_messages == ["T-001: t"]


def test_auto_mode_commits_when_review_passes(tmp_path):
    # No human in the loop: the LLM reviewer passing is the only gate, but the
    # task's work must still land in a commit -- not just a `status: done`
    # flip with the diff sitting uncommitted in the working tree.
    repo = _repo(tmp_path)
    git_ops = FakeGitOps(head="abc123", has_uncommitted=True)

    path = run_next(
        repo, FakeAgentBackend(_scripts()), FakeGateRunner(),
        session_id="s1", git_info={"branch": "main"}, git_ops=git_ops,
    )

    assert path is not None
    assert git_ops.commit_messages == ["T-001: t"]


def test_reject_feeds_comments_back_as_dev_feedback_and_retries(tmp_path):
    repo = _repo(tmp_path)
    git_ops = FakeGitOps(head="abc123", has_uncommitted=False)
    human_review = FakeHumanReviewGate([
        HumanReviewDecision("reject", [Annotation(file="src/x.py", body="add a docstring")]),
        HumanReviewDecision("approve", []),
    ])

    path = run_next(
        repo, FakeAgentBackend(_scripts(n_review_calls=2)), FakeGateRunner(),
        session_id="s1", git_info={"branch": "main"},
        human_review=human_review, git_ops=git_ops,
    )

    assert path is not None
    assert len(human_review.requests) == 2
    assert git_ops.commit_messages == []  # no uncommitted changes this time


def test_blocked_report_carries_start_commit_for_diff_browser(tmp_path):
    repo = _repo(tmp_path)
    status = FakeStatusReporter()
    human_review = FakeHumanReviewGate([HumanReviewDecision("approve", [])])
    expected_start_commit = SubprocessGitOps().head_commit(repo)

    path = run_next(
        repo, FakeAgentBackend(_scripts()), FakeGateRunner(),
        session_id="s1", git_info={"branch": "main"},
        human_review=human_review, status=status,
    )

    assert path is not None
    blocked_calls = [
        c for c in status.calls if c["node"] == "human-review" and c["node_state"] == "blocked"
    ]
    assert len(blocked_calls) == 1
    assert blocked_calls[0]["start_commit"] == expected_start_commit


def test_no_gate_configured_behaves_exactly_as_before(tmp_path):
    repo = _repo(tmp_path)
    path = run_next(
        repo, FakeAgentBackend(_scripts()), FakeGateRunner(),
        session_id="s1", git_info={"branch": "main"},
    )
    assert path is not None


def test_human_review_entry_resolves_after_each_decision(tmp_path):
    # Regression: the human-review pipeline entry must leave "blocked" once the
    # gate returns, otherwise the dashboard shows it stuck waiting forever and
    # the interactive review poll's guard never resets (suppressing a later
    # blocked round on the same task after a reject).
    repo = _repo(tmp_path)
    status = FakeStatusReporter()
    human_review = FakeHumanReviewGate([
        HumanReviewDecision("reject", [Annotation(file="src/x.py", body="add a docstring")]),
        HumanReviewDecision("approve", []),
    ])

    run_next(
        repo, FakeAgentBackend(_scripts(n_review_calls=2)), FakeGateRunner(),
        session_id="s1", git_info={"branch": "main"},
        human_review=human_review, status=status,
    )

    states = [c["node_state"] for c in status.calls if c["node"] == "human-review"]
    assert states == ["blocked", "changes-requested", "blocked", "approved"]


def test_human_review_entry_resolves_on_approve(tmp_path):
    repo = _repo(tmp_path)
    status = FakeStatusReporter()
    human_review = FakeHumanReviewGate([HumanReviewDecision("approve", [])])

    run_next(
        repo, FakeAgentBackend(_scripts()), FakeGateRunner(),
        session_id="s1", git_info={"branch": "main"},
        human_review=human_review, status=status,
    )

    states = [c["node_state"] for c in status.calls if c["node"] == "human-review"]
    assert states == ["blocked", "approved"]


def _already_done_scripts(with_dev=False):
    manifest = {
        "task_id": "T-001", "generated_by": "context-gatherer",
        "generated_at": "2026-07-16T14:32:10Z",
        "coherence": {"checks": [{"name": "c", "kind": "files_exist", "args": {"paths": ["src/x.py"]}}]},
        "context": {"task": "tasks/T-001.md", "source_files": ["src/x.py"], "skills": []},
        "reject": None, "already_done": True,
    }
    scripts = {
        AgentRole.CONTEXT_GATHERER: [AgentResult(True, manifest)],
        AgentRole.REVIEW: [AgentResult(True, {"dod_met": True, "findings": []})],
        AgentRole.SESSION_REVIEW: [AgentResult(True, {})],
    }
    if with_dev:
        scripts[AgentRole.DEV] = [AgentResult(True, {})]
    return scripts


def test_already_done_skips_dev_runs_validation_and_completes(tmp_path):
    repo = _repo(tmp_path)
    status = FakeStatusReporter()
    # No DEV script: if dev were called, FakeAgentBackend would raise -- proving
    # dev is skipped on the already-done first pass.
    path = run_next(
        repo, FakeAgentBackend(_already_done_scripts()), FakeGateRunner(),
        session_id="s1", git_info={"branch": "main"}, status=status,
    )
    assert path is not None
    nodes = [c["node"] for c in status.calls]
    assert "validation" in nodes          # validation (sim gate) still runs
    assert "dev" not in nodes             # dev skipped on the already-done pass
    completed = [c for c in status.calls if c["node"] == "review" and c.get("outcome") == "completed"]
    assert completed


def test_already_done_human_review_block_carries_deliverables(tmp_path):
    repo = _repo(tmp_path)
    (repo / "tasks" / "T-001.md").write_text(
        "---\nid: T-001\ntitle: t\nstatus: todo\ndod:\n  - c\n---\n- Create: `src/x.py`\n",
        encoding="utf-8")
    status = FakeStatusReporter()
    human_review = FakeHumanReviewGate([HumanReviewDecision("approve", [])])
    # Explicit task_id: an already-on-disk task is skipped by next_todo (the
    # picker-hide feature), so run it explicitly to exercise the already-done route.
    run_next(
        repo, FakeAgentBackend(_already_done_scripts()), FakeGateRunner(),
        session_id="s1", git_info={"branch": "main"}, task_id="T-001",
        human_review=human_review, status=status,
    )
    blocked = [c for c in status.calls if c["node"] == "human-review" and c["node_state"] == "blocked"]
    assert len(blocked) == 1
    assert blocked[0]["already_done"] is True
    assert blocked[0]["deliverables"] == ["src/x.py"]


def test_already_done_but_sim_fails_falls_through_to_dev(tmp_path):
    repo = _repo(tmp_path)
    status = FakeStatusReporter()
    # sim fails on the already-done first pass -> loop back; dev runs on pass 2
    # (unit green), sim green on the second call.
    gates = FakeGateRunner({"sim": [1, 0], "unit": [0], "full": [0]})
    path = run_next(
        repo, FakeAgentBackend(_already_done_scripts(with_dev=True)), gates,
        session_id="s1", git_info={"branch": "main"}, status=status,
    )
    assert path is not None
    nodes = [c["node"] for c in status.calls]
    assert "dev" in nodes                 # dev ran on the self-correct pass


def _base_manifest():
    return {
        "task_id": "T-001", "generated_by": "context-gatherer", "generated_at": "2026-07-16T14:32:10Z",
        "coherence": {"checks": [{"name": "c", "kind": "files_exist", "args": {"paths": ["src/x.py"]}}]},
        "context": {"task": "tasks/T-001.md", "source_files": ["src/x.py"], "skills": []},
        "reject": None,
    }


def test_reject_then_llm_keeps_requesting_changes_still_returns_to_human(tmp_path):
    # The T-032 regression: after a human reject, if the LLM reviewer keeps
    # returning changes-requested, control must STILL come back to the human
    # (never silently escalate).
    repo = _repo(tmp_path)
    scripts = {
        AgentRole.CONTEXT_GATHERER: [AgentResult(True, _base_manifest())],
        AgentRole.DEV: [AgentResult(True, {}) for _ in range(5)],
        AgentRole.REVIEW: [
            AgentResult(True, {"dod_met": True, "findings": []}),                  # round 0: pass -> human
            AgentResult(True, {"dod_met": False, "findings": ["needs docstring"]}),  # round 1 inner cycles: all changes
            AgentResult(True, {"dod_met": False, "findings": ["needs docstring"]}),
            AgentResult(True, {"dod_met": False, "findings": ["needs docstring"]}),
        ],
        AgentRole.SESSION_REVIEW: [AgentResult(True, {})],
    }
    human_review = FakeHumanReviewGate([
        HumanReviewDecision("reject", [Annotation(file="src/x.py", body="add a docstring")]),
        HumanReviewDecision("approve", []),
    ])
    status = FakeStatusReporter()
    path = run_next(repo, FakeAgentBackend(scripts), FakeGateRunner(),
                    session_id="s1", git_info={"branch": "main"},
                    human_review=human_review, status=status)
    assert path is not None
    hr = [c for c in status.calls if c["node"] == "human-review"]
    assert [c["node_state"] for c in hr] == ["blocked", "changes-requested", "blocked", "approved"]
    second_blocked = [c for c in hr if c["node_state"] == "blocked"][1]
    assert "reviewer couldn't confirm" in second_blocked["handoff"]
    assert len(human_review.requests) == 2


def test_escalates_only_after_max_human_rounds_of_rejects(tmp_path):
    repo = _repo(tmp_path)
    scripts = {
        AgentRole.CONTEXT_GATHERER: [AgentResult(True, _base_manifest())],
        AgentRole.DEV: [AgentResult(True, {}) for _ in range(6)],
        AgentRole.REVIEW: [AgentResult(True, {"dod_met": True, "findings": []}) for _ in range(6)],
        AgentRole.SESSION_REVIEW: [AgentResult(True, {})],
    }
    human_review = FakeHumanReviewGate(
        [HumanReviewDecision("reject", [Annotation(file="src/x.py", body="c")]) for _ in range(3)]
    )
    status = FakeStatusReporter()
    run_next(repo, FakeAgentBackend(scripts), FakeGateRunner(),
             session_id="s1", git_info={"branch": "main"},
             human_review=human_review, status=status)
    blocked = [c for c in status.calls if c["node"] == "human-review" and c["node_state"] == "blocked"]
    assert len(blocked) == 3  # max_human_rounds
    assert [c for c in status.calls if c.get("outcome") == "escalated"]


def test_human_review_writes_a_focus_guide(tmp_path):
    repo = _repo(tmp_path)
    td = repo / "sessions" / ".factory-transcripts" / "s1"
    td.mkdir(parents=True)
    (td / "sim-gate.log").write_text("12 passed in 1s\n", encoding="utf-8")
    # review agent returns a guide
    scripts = _already_done_scripts()  # context-gather already_done -> review -> human-review
    scripts[AgentRole.REVIEW] = [AgentResult(True, {
        "dod_met": True, "findings": [],
        "confidence": "medium", "verify": [{"item": "check X"}],
    })]
    human_review = FakeHumanReviewGate([HumanReviewDecision("approve", [])])
    run_next(
        repo, FakeAgentBackend(scripts), FakeGateRunner(),
        session_id="s1", git_info={"branch": "main"}, task_id="T-001",
        human_review=human_review, status=FakeStatusReporter(), transcript_dir=td,
    )
    import json
    guide = json.loads((td / "review-guide.json").read_text(encoding="utf-8"))
    assert guide["confidence"] == "medium"
    assert guide["verify"] == [{"item": "check X"}]
    assert {"gate": "sim", "ok": True, "summary": "12 passed"} in guide["validation"]


def test_addressed_accumulator_survives_human_reject_round_and_reblocks(tmp_path):
    # Regression: `addressed` must accumulate the human's own comment text
    # across the OUTER human-round loop (not just LLM review findings), and
    # the on-disk guide must be re-written with it when the task re-blocks
    # for the human's next round.
    repo = _repo(tmp_path)
    td = repo / "sessions" / ".factory-transcripts" / "s1"
    td.mkdir(parents=True)
    human_review = FakeHumanReviewGate([
        HumanReviewDecision("reject", [Annotation(file="src/x.py", body="please fix the docstring")]),
        HumanReviewDecision("approve", []),
    ])
    run_next(
        repo, FakeAgentBackend(_scripts(n_review_calls=2)), FakeGateRunner(),
        session_id="s1", git_info={"branch": "main"},
        human_review=human_review, status=FakeStatusReporter(), transcript_dir=td,
    )
    import json
    guide = json.loads((td / "review-guide.json").read_text(encoding="utf-8"))
    assert "your comment (round 1) on src/x.py: please fix the docstring" in guide["addressed"]


def test_auto_still_escalates_when_llm_never_passes(tmp_path):
    repo = _repo(tmp_path)
    scripts = {
        AgentRole.CONTEXT_GATHERER: [AgentResult(True, _base_manifest())],
        AgentRole.DEV: [AgentResult(True, {}) for _ in range(4)],
        AgentRole.REVIEW: [AgentResult(True, {"dod_met": False, "findings": ["x"]}) for _ in range(4)],
        AgentRole.SESSION_REVIEW: [AgentResult(True, {})],
    }
    status = FakeStatusReporter()
    run_next(repo, FakeAgentBackend(scripts), FakeGateRunner(),
             session_id="s1", git_info={"branch": "main"}, status=status)  # no human_review -> auto
    assert not [c for c in status.calls if c["node"] == "human-review"]
    assert [c for c in status.calls if c.get("outcome") == "escalated"]
