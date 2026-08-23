import subprocess
import pytest
from factory.orchestrator.types import AgentRole, AgentResult
from factory.orchestrator.ledger import Task
from factory.orchestrator.backends import FakeAgentBackend, FakeGateRunner
from factory.orchestrator.runner import run_task
from factory.orchestrator.status import FakeStatusReporter
from ._skill_fixtures import write_skill_stubs

pytestmark = pytest.mark.unit


def _repo(tmp_path):
    (tmp_path / "tasks").mkdir()
    (tmp_path / "tasks" / "T-001.md").write_text("dod", encoding="utf-8")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "x.py").write_text("x = 1\n", encoding="utf-8")
    write_skill_stubs(tmp_path)
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=tmp_path, check=True)
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=tmp_path, check=True)
    return tmp_path


def _manifest():
    return {
        "task_id": "T-001", "generated_by": "context-gatherer",
        "generated_at": "2026-07-16T14:32:10Z",
        "coherence": {"checks": [{"name": "c", "kind": "files_exist", "args": {"paths": ["src/x.py"]}}]},
        "context": {"task": "tasks/T-001.md", "source_files": ["src/x.py"], "skills": []},
        "reject": None,
    }


def _scripts():
    # review: changes once, then pass -> exercises the dev<->review loop
    return {
        AgentRole.CONTEXT_GATHERER: [AgentResult(True, _manifest())],
        AgentRole.DEV: [AgentResult(True, {}), AgentResult(True, {})],
        AgentRole.REVIEW: [
            AgentResult(True, {"dod_met": False, "findings": ["fix"]}),
            AgentResult(True, {"dod_met": True, "findings": []}),
        ],
    }


def test_full_pipeline_completes_and_is_deterministic(tmp_path):
    repo = _repo(tmp_path)
    task = Task("T-001", "t", "todo", ["c"], "body", repo / "tasks" / "T-001.md")

    def run():
        return run_task(task, FakeAgentBackend(_scripts()), FakeGateRunner(), repo,
                        max_review_cycles=3)

    r1 = run()
    r2 = run()
    assert r1.outcome == "completed" and r1.dod_met is True
    assert r1.iterations == 2
    seq1 = [(e.node, e.result) for e in r1.events]
    seq2 = [(e.node, e.result) for e in r2.events]
    assert seq1 == seq2  # deterministic routing
    assert ("review", "pass") in seq1


def test_context_reject_short_circuits(tmp_path):
    repo = _repo(tmp_path)
    task = Task("T-001", "t", "todo", ["c"], "body", repo / "tasks" / "T-001.md")
    scripts = {AgentRole.CONTEXT_GATHERER: [AgentResult(True, {**_manifest(), "reject": {"reason": "x"},
                                                              "coherence": {"checks": []}})]}
    r = run_task(task, FakeAgentBackend(scripts), FakeGateRunner(), repo)
    assert r.outcome == "rejected"


def test_validation_fails_until_exhausted(tmp_path):
    """Validation gate fails every cycle until max_review_cycles is exhausted.

    Expected: outcome='escalated', iterations=max_review_cycles
    Scenario: dev succeeds each cycle, unit gate passes, but sim gate fails every time.
    """
    repo = _repo(tmp_path)
    task = Task("T-001", "t", "todo", ["c"], "body", repo / "tasks" / "T-001.md")
    max_review_cycles = 2

    # Validation fails when sim gate returns non-zero
    # Each cycle: run_dev (calls unit once) -> run_validation (calls sim once)
    # Need: 2 DEV results, unit=[0,0], sim=[1,1]
    scripts = {
        AgentRole.CONTEXT_GATHERER: [AgentResult(True, _manifest())],
        AgentRole.DEV: [AgentResult(True, {}), AgentResult(True, {})],
    }
    gates = FakeGateRunner({
        "unit": [0, 0],  # unit passes both cycles
        "sim": [1, 1],   # sim fails both cycles
    })
    r = run_task(task, FakeAgentBackend(scripts), gates, repo, max_review_cycles=max_review_cycles)

    assert r.outcome == "escalated"
    assert r.iterations == max_review_cycles


def test_review_requests_changes_until_exhausted(tmp_path):
    """Review requests changes every cycle until max_review_cycles is exhausted.

    Expected: outcome='escalated', iterations=max_review_cycles
    Scenario: dev succeeds, gates pass, but review always returns dod_met=False.
    """
    repo = _repo(tmp_path)
    task = Task("T-001", "t", "todo", ["c"], "body", repo / "tasks" / "T-001.md")
    max_review_cycles = 2

    # Each cycle: run_dev (dev agent + unit gate) -> run_validation (sim gate) -> run_review (review agent + full gate)
    # Need: 2 DEV, 2 REVIEW (each with dod_met=False), unit=[0,0], sim=[0,0], full=[0,0]
    scripts = {
        AgentRole.CONTEXT_GATHERER: [AgentResult(True, _manifest())],
        AgentRole.DEV: [AgentResult(True, {}), AgentResult(True, {})],
        AgentRole.REVIEW: [
            AgentResult(True, {"dod_met": False, "findings": ["still broken"]}),
            AgentResult(True, {"dod_met": False, "findings": ["still broken"]}),
        ],
    }
    gates = FakeGateRunner({
        "unit": [0, 0],   # unit passes both cycles
        "sim": [0, 0],    # sim passes both cycles
        "full": [0, 0],   # full gate passes both cycles (but dod_met=False means review fails)
    })
    r = run_task(task, FakeAgentBackend(scripts), gates, repo, max_review_cycles=max_review_cycles)

    assert r.outcome == "escalated"
    assert r.iterations == max_review_cycles


def test_dev_escalates_immediately(tmp_path):
    """Dev exhausts its own max_dev_iters retries and escalates on first cycle.

    Expected: outcome='escalated', iterations=1
    Scenario: unit gate fails max_dev_iters times, causing dev to return ESCALATE.
    run_task should return immediately without continuing the review loop.
    """
    repo = _repo(tmp_path)
    task = Task("T-001", "t", "todo", ["c"], "body", repo / "tasks" / "T-001.md")
    max_dev_iters = 3

    # run_dev loops max_dev_iters times calling DEV agent and unit gate
    # All unit calls must fail (non-zero) to exhaust dev
    # Need: max_dev_iters DEV results, unit=[1,1,1]
    scripts = {
        AgentRole.CONTEXT_GATHERER: [AgentResult(True, _manifest())],
        AgentRole.DEV: [AgentResult(True, {}), AgentResult(True, {}), AgentResult(True, {})],
    }
    gates = FakeGateRunner({
        "unit": [1, 1, 1],  # unit fails all attempts, causing dev to escalate
    })
    r = run_task(task, FakeAgentBackend(scripts), gates, repo, max_dev_iters=max_dev_iters)

    assert r.outcome == "escalated"
    assert r.iterations == 1  # Should return after first iteration, not continue looping


def test_run_task_reports_final_outcome(tmp_path):
    repo = _repo(tmp_path)
    task = Task("T-001", "t", "todo", ["c"], "body", repo / "tasks" / "T-001.md")
    status = FakeStatusReporter()

    run_task(task, FakeAgentBackend(_scripts()), FakeGateRunner(), repo, status=status)

    final_calls = [c for c in status.calls if c["outcome"] is not None]
    assert final_calls[-1]["outcome"] == "completed"  # last outcome is completion
    # Intermediate nodes may also report outcomes (e.g. context-gather reject)
    assert len(final_calls) >= 1


def test_run_task_reports_node_result_after_each_node(tmp_path):
    repo = _repo(tmp_path)
    task = Task("T-001", "t", "todo", ["c"], "body", repo / "tasks" / "T-001.md")
    status = FakeStatusReporter()

    run_task(task, FakeAgentBackend(_scripts()), FakeGateRunner(), repo, status=status)

    node_states = [(c["node"], c["node_state"]) for c in status.calls]
    # "pass" for context-gather should appear (not just "running"), proving
    # run_task reports the definitive result after the node returns.
    assert ("context-gather", "pass") in node_states
    assert ("review", "pass") in node_states


def test_validation_exhaustion_reports_actual_last_node(tmp_path):
    """When validation fails until exhausted, final status report must report validation, not review.

    This is a regression test for the bug where the final status report hardcoded
    node="review"/node_state="changes-requested" regardless of the actual last node.
    When validation causes the exhaustion, the final report should have
    node="validation" and node_state="fail".
    """
    repo = _repo(tmp_path)
    task = Task("T-001", "t", "todo", ["c"], "body", repo / "tasks" / "T-001.md")
    max_review_cycles = 2
    status = FakeStatusReporter()

    scripts = {
        AgentRole.CONTEXT_GATHERER: [AgentResult(True, _manifest())],
        AgentRole.DEV: [AgentResult(True, {}), AgentResult(True, {})],
    }
    gates = FakeGateRunner({
        "unit": [0, 0],  # unit passes both cycles
        "sim": [1, 1],   # sim fails both cycles
    })
    r = run_task(task, FakeAgentBackend(scripts), gates, repo,
                 max_review_cycles=max_review_cycles, status=status)

    assert r.outcome == "escalated"

    # Find the final status call (the one with outcome set)
    final_calls = [c for c in status.calls if c["outcome"] is not None]
    assert len(final_calls) == 1
    final = final_calls[0]

    # The final report should reflect the actual last node that ran
    assert final["node"] == "validation", f"Expected node='validation', got {final['node']}"
    assert final["node_state"] == "fail", f"Expected node_state='fail', got {final['node_state']}"
    assert final["outcome"] == "escalated"
    # Cycle counts should reflect the number of review cycles exhausted
    assert final["attempt"] == max_review_cycles, f"Expected attempt={max_review_cycles}, got {final['attempt']}"
    assert final["max_attempts"] == max_review_cycles, f"Expected max_attempts={max_review_cycles}, got {final['max_attempts']}"


def test_review_exhaustion_reports_actual_last_node(tmp_path):
    """When review requests changes until exhausted, final status report must report review.

    Ensures the fix for validation exhaustion doesn't break the review exhaustion case:
    the final report should have node="review" and node_state="changes-requested".
    """
    repo = _repo(tmp_path)
    task = Task("T-001", "t", "todo", ["c"], "body", repo / "tasks" / "T-001.md")
    max_review_cycles = 2
    status = FakeStatusReporter()

    scripts = {
        AgentRole.CONTEXT_GATHERER: [AgentResult(True, _manifest())],
        AgentRole.DEV: [AgentResult(True, {}), AgentResult(True, {})],
        AgentRole.REVIEW: [
            AgentResult(True, {"dod_met": False, "findings": ["still broken"]}),
            AgentResult(True, {"dod_met": False, "findings": ["still broken"]}),
        ],
    }
    gates = FakeGateRunner({
        "unit": [0, 0],   # unit passes both cycles
        "sim": [0, 0],    # sim passes both cycles
        "full": [0, 0],   # full gate passes both cycles
    })
    r = run_task(task, FakeAgentBackend(scripts), gates, repo,
                 max_review_cycles=max_review_cycles, status=status)

    assert r.outcome == "escalated"

    # Find the final status call (the one with outcome set)
    final_calls = [c for c in status.calls if c["outcome"] is not None]
    assert len(final_calls) == 1
    final = final_calls[0]

    # The final report should reflect the actual last node that ran (review)
    assert final["node"] == "review", f"Expected node='review', got {final['node']}"
    assert final["node_state"] == "changes-requested", f"Expected node_state='changes-requested', got {final['node_state']}"
    assert final["outcome"] == "escalated"
    # Cycle counts should reflect the number of review cycles exhausted
    assert final["attempt"] == max_review_cycles, f"Expected attempt={max_review_cycles}, got {final['attempt']}"
    assert final["max_attempts"] == max_review_cycles, f"Expected max_attempts={max_review_cycles}, got {final['max_attempts']}"
