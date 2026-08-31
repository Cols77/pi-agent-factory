"""Regression coverage for Task 4's retry-time KB reselection: the runner no
longer selects KB guidance once, up front, from an always-empty signature
list -- it reselects before every DEV/review attempt from the canonical
failure signatures the gates it already ran have produced (never a second
execution of the same gate merely to see its output)."""
import pytest

from factory.orchestrator.backends import FakeAgentBackend, FakeGateRunner, GateRun
from factory.orchestrator.git_ops import FakeGitOps
from factory.orchestrator.ledger import Task
from factory.orchestrator.runner import run_task
from factory.orchestrator.types import AgentRole, AgentResult
from ._repo_fixtures import write_repo_template

pytestmark = pytest.mark.unit


def _repo(tmp_path):
    return write_repo_template(tmp_path, "runner")


def _write_signature_only_kb_entry(repo, entry_id="kb-0002", signature="ConnectionResetError"):
    # No file glob at all -- this entry can ONLY be selected via a matching
    # canonical failure signature, never via manifest/review touched files.
    (repo / "kb").mkdir(exist_ok=True)
    (repo / "kb" / f"{entry_id}-signature-only.md").write_text(
        "---\n"
        f"id: {entry_id}\n"
        "title: \"Connection reset needs a retry with backoff\"\n"
        "status: active\n"
        "severity: medium\n"
        "created: \"2026-08-20\"\n"
        "last_seen: \"2026-08-20\"\n"
        "occurrences: 1\n"
        "tags: [example]\n"
        "scope:\n"
        "  files: []\n"
        "  error_signatures:\n"
        f"    - \"{signature}\"\n"
        "detection: \"\"\n"
        "---\n\n"
        "## Symptom\nflaky connection\n\n## Rule / fix\nretry with backoff\n",
        encoding="utf-8",
    )


def _manifest():
    return {
        "task_id": "T-001", "generated_by": "context-gatherer",
        "generated_at": "2026-07-16T14:32:10Z",
        "coherence": {"checks": [{"name": "c", "kind": "files_exist", "args": {"paths": ["src/x.py"]}}]},
        "context": {"task": "tasks/T-001.md", "source_files": ["src/x.py"], "skills": []},
        "reject": None,
    }


def _dev_prompts(backend: FakeAgentBackend) -> list[str]:
    return [prompt for role, prompt in backend.prompts if role is AgentRole.DEV]


def _review_prompts(backend: FakeAgentBackend) -> list[str]:
    return [prompt for role, prompt in backend.prompts if role is AgentRole.REVIEW]


def test_failed_unit_gate_signature_reselects_kb_for_next_dev_attempt(tmp_path):
    """A unit gate failure whose output carries a canonical ConnectionResetError
    signature makes a signature-only (no file-glob) KB entry appear in the
    NEXT dev attempt's prompt, even though it was absent from the first."""
    repo = _repo(tmp_path)
    _write_signature_only_kb_entry(repo)
    task = Task("T-001", "t", "todo", ["c"], "body", repo / "tasks" / "T-001.md")

    scripts = {
        AgentRole.CONTEXT_GATHERER: [AgentResult(True, _manifest())],
        AgentRole.DEV: [AgentResult(True, {}), AgentResult(True, {})],
        AgentRole.REVIEW: [AgentResult(True, {"dod_met": True, "findings": []})],
    }
    gates = FakeGateRunner({
        "unit": [
            GateRun(
                name="unit",
                returncode=1,
                output="E ConnectionResetError: connection reset by peer",
                applicable=True,
                commands=("python -m pytest -q",),
            ),
            0,
        ],
        "full": [0],
    })
    backend = FakeAgentBackend(scripts)

    r = run_task(
        task, backend, gates, repo, max_dev_iters=2, max_review_cycles=1, git_ops=FakeGitOps()
    )

    assert r.outcome == "completed"
    dev_prompts = _dev_prompts(backend)
    assert len(dev_prompts) == 2
    assert "kb-0002" not in dev_prompts[0]  # nothing failed yet
    assert "kb-0002" in dev_prompts[1]  # reselected after the failed unit gate
    assert "Connection reset needs a retry with backoff" in dev_prompts[1]


def test_nonmatching_failure_signature_never_selects_the_entry(tmp_path):
    """A unit failure whose signature does not match the entry's
    error_signatures must never surface it -- an empty signature history (or
    an unrelated one) is not a wildcard match."""
    repo = _repo(tmp_path)
    _write_signature_only_kb_entry(repo)
    task = Task("T-001", "t", "todo", ["c"], "body", repo / "tasks" / "T-001.md")

    scripts = {
        AgentRole.CONTEXT_GATHERER: [AgentResult(True, _manifest())],
        AgentRole.DEV: [AgentResult(True, {}), AgentResult(True, {})],
        AgentRole.REVIEW: [AgentResult(True, {"dod_met": True, "findings": []})],
    }
    gates = FakeGateRunner({
        "unit": [
            GateRun(
                name="unit",
                returncode=1,
                output="E TimeoutError: totally unrelated failure",
                applicable=True,
                commands=("python -m pytest -q",),
            ),
            0,
        ],
        "full": [0],
    })
    backend = FakeAgentBackend(scripts)

    r = run_task(
        task, backend, gates, repo, max_dev_iters=2, max_review_cycles=1, git_ops=FakeGitOps()
    )

    assert r.outcome == "completed"
    dev_prompts = _dev_prompts(backend)
    assert len(dev_prompts) == 2
    assert "kb-0002" not in dev_prompts[0]
    assert "kb-0002" not in dev_prompts[1]


def test_successful_gate_adds_no_signature_and_no_entry(tmp_path):
    """A unit gate that passes on the first attempt produces no failure
    signature at all, so the signature-only entry is never selected."""
    repo = _repo(tmp_path)
    _write_signature_only_kb_entry(repo)
    task = Task("T-001", "t", "todo", ["c"], "body", repo / "tasks" / "T-001.md")

    scripts = {
        AgentRole.CONTEXT_GATHERER: [AgentResult(True, _manifest())],
        AgentRole.DEV: [AgentResult(True, {})],
        AgentRole.REVIEW: [AgentResult(True, {"dod_met": True, "findings": []})],
    }
    gates = FakeGateRunner({"unit": [0], "full": [0]})
    backend = FakeAgentBackend(scripts)

    r = run_task(
        task, backend, gates, repo, max_dev_iters=2, max_review_cycles=1, git_ops=FakeGitOps()
    )

    assert r.outcome == "completed"
    dev_prompts = _dev_prompts(backend)
    assert len(dev_prompts) == 1
    assert "kb-0002" not in dev_prompts[0]


def test_self_resolving_dev_failure_signature_still_reaches_the_review_prompt(tmp_path):
    """Regression: a unit-gate failure that self-resolves within run_dev's OWN
    retry loop (fails attempt 1, passes attempt 2 -- the dev node returns
    PASS) must not vanish from the task-level signature_history just because
    the node's final outcome was a pass. The runner folds run_dev's returned
    event into signature_history regardless of outcome, so the SAME
    ConnectionResetError signature must still bias KB selection for the next
    node in this cycle (review), not just a hypothetical next dev attempt."""
    repo = _repo(tmp_path)
    _write_signature_only_kb_entry(repo)
    task = Task("T-001", "t", "todo", ["c"], "body", repo / "tasks" / "T-001.md")

    scripts = {
        AgentRole.CONTEXT_GATHERER: [AgentResult(True, _manifest())],
        AgentRole.DEV: [AgentResult(True, {}), AgentResult(True, {})],
        AgentRole.REVIEW: [AgentResult(True, {"dod_met": True, "findings": []})],
    }
    gates = FakeGateRunner({
        "unit": [
            GateRun(
                name="unit",
                returncode=1,
                output="E ConnectionResetError: connection reset by peer",
                applicable=True,
                commands=("python -m pytest -q",),
            ),
            0,  # passes on attempt 2 -- run_dev returns PASS, not ESCALATE
        ],
        "full": [0],
    })
    backend = FakeAgentBackend(scripts)

    r = run_task(
        task, backend, gates, repo, max_dev_iters=2, max_review_cycles=1, git_ops=FakeGitOps()
    )

    assert r.outcome == "completed"
    dev_prompts = _dev_prompts(backend)
    assert len(dev_prompts) == 2  # dev resolved the failure internally, no escalate
    review_prompts = _review_prompts(backend)
    assert len(review_prompts) == 1
    assert "kb-0002" in review_prompts[0]
    assert "Connection reset needs a retry with backoff" in review_prompts[0]


def test_gate_never_executed_twice_to_obtain_output(tmp_path, monkeypatch):
    """The runner must derive both the pass/fail decision AND the canonical
    signature from the SAME gate execution -- never re-run a gate merely to
    see its output."""
    repo = _repo(tmp_path)
    task = Task("T-001", "t", "todo", ["c"], "body", repo / "tasks" / "T-001.md")

    calls: list[str] = []
    real_run_detail = FakeGateRunner.run_detail

    def counting_run_detail(self, name):
        calls.append(name)
        return real_run_detail(self, name)

    monkeypatch.setattr(FakeGateRunner, "run_detail", counting_run_detail)

    scripts = {
        AgentRole.CONTEXT_GATHERER: [AgentResult(True, _manifest())],
        AgentRole.DEV: [AgentResult(True, {})],
        AgentRole.REVIEW: [AgentResult(True, {"dod_met": True, "findings": []})],
    }
    gates = FakeGateRunner({"unit": [0], "full": [0]})
    backend = FakeAgentBackend(scripts)

    run_task(
        task, backend, gates, repo, max_dev_iters=2, max_review_cycles=1, git_ops=FakeGitOps()
    )

    assert calls.count("unit") == 1
    assert calls.count("full") == 1
