import pytest
from pathlib import Path
from factory.orchestrator.types import AgentRole, AgentResult, NodeOutcome
from factory.orchestrator.ledger import Task
from factory.orchestrator.backends import FakeAgentBackend, FakeGateRunner, GateRun
from factory.orchestrator.nodes import run_context_gatherer, run_dev, _summarize_manifest
from factory.orchestrator.status import FakeStatusReporter
from ._skill_fixtures import write_skill_stubs

pytestmark = pytest.mark.unit


def _task():
    return Task("T-001", "t", "todo", ["c"], "body", Path("t"))


def _manifest(tmp_path, checks=None, reject=None):
    (tmp_path / "tasks").mkdir(exist_ok=True)
    (tmp_path / "tasks" / "T-001.md").write_text("dod", encoding="utf-8")
    return {
        "task_id": "T-001", "generated_by": "context-gatherer",
        "generated_at": "2026-07-16T14:32:10Z",
        "coherence": {"checks": checks if checks is not None else []},
        "context": {"task": "tasks/T-001.md", "source_files": [], "skills": []},
        "reject": reject,
    }


def test_context_gatherer_pass(tmp_path):
    write_skill_stubs(tmp_path)
    b = FakeAgentBackend({AgentRole.CONTEXT_GATHERER: [AgentResult(True, _manifest(tmp_path))]})
    outcome, manifest, ev = run_context_gatherer(b, _task(), tmp_path)
    assert outcome == NodeOutcome.PASS and manifest is not None and ev.result == "pass"


def test_context_gatherer_reject_on_reject_field(tmp_path):
    write_skill_stubs(tmp_path)
    m = _manifest(tmp_path, reject={"reason": "DoD unclear"})
    b = FakeAgentBackend({AgentRole.CONTEXT_GATHERER: [AgentResult(True, m)]})
    outcome, manifest, ev = run_context_gatherer(b, _task(), tmp_path)
    assert outcome == NodeOutcome.REJECT and manifest is None


def test_context_gatherer_pass_with_covered_modify_and_check(tmp_path):
    write_skill_stubs(tmp_path)
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "b.py").write_text("x", encoding="utf-8")
    task = Task("T-001", "t", "todo", ["c"], "- Modify: `src/b.py`", Path("t"))
    m = _manifest(tmp_path, checks=[{"name": "c", "kind": "files_exist", "args": {"paths": ["src/b.py"]}}])
    m["context"]["source_files"] = ["src/b.py"]
    b = FakeAgentBackend({AgentRole.CONTEXT_GATHERER: [AgentResult(True, m)]})
    outcome, manifest, ev = run_context_gatherer(b, task, tmp_path, gates=FakeGateRunner())
    assert outcome == NodeOutcome.PASS


def test_context_gatherer_rejects_when_modify_uncovered(tmp_path):
    write_skill_stubs(tmp_path)
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "b.py").write_text("x", encoding="utf-8")
    task = Task("T-001", "t", "todo", ["c"], "- Modify: `src/b.py`", Path("t"))
    # source_files omits the Modify: deliverable -> coverage floor fails both attempts.
    m = _manifest(tmp_path)
    b = FakeAgentBackend({AgentRole.CONTEXT_GATHERER: [AgentResult(True, m), AgentResult(True, m)]})
    outcome, manifest, ev = run_context_gatherer(b, task, tmp_path, gates=FakeGateRunner())
    assert outcome == NodeOutcome.REJECT


def test_context_gatherer_already_done(tmp_path):
    write_skill_stubs(tmp_path)
    m = _manifest(tmp_path)
    m["already_done"] = True
    m["already_done_reason"] = "deliverables exist and match the DoD"
    b = FakeAgentBackend({AgentRole.CONTEXT_GATHERER: [AgentResult(True, m)]})
    outcome, manifest, ev = run_context_gatherer(b, _task(), tmp_path)
    assert outcome == NodeOutcome.ALREADY_DONE
    assert manifest is not None
    assert ev.result == "already-done"


def test_dev_passes_when_unit_green(tmp_path):
    write_skill_stubs(tmp_path)
    b = FakeAgentBackend({AgentRole.DEV: [AgentResult(True, {})]})
    g = FakeGateRunner({"unit": [0]})
    outcome, ev = run_dev(b, g, _task(), {}, [], tmp_path)
    assert outcome == NodeOutcome.PASS


def test_dev_escalates_when_unit_never_green(tmp_path):
    write_skill_stubs(tmp_path)
    b = FakeAgentBackend({AgentRole.DEV: [AgentResult(True, {}) for _ in range(3)]})
    g = FakeGateRunner({"unit": [1, 1, 1]})
    outcome, ev = run_dev(b, g, _task(), {}, [], tmp_path, max_iters=3)
    assert outcome == NodeOutcome.ESCALATE and ev.attempts == 3


def test_context_gatherer_notes_backend_failure(tmp_path):
    write_skill_stubs(tmp_path)
    b = FakeAgentBackend({AgentRole.CONTEXT_GATHERER: [
        AgentResult(False, {}, "simulated backend failure"),
        AgentResult(False, {}, "simulated backend failure"),
    ]})
    outcome, manifest, ev = run_context_gatherer(b, _task(), tmp_path)
    assert outcome == NodeOutcome.REJECT and manifest is None
    assert ev.extra["backend_ok"] is False
    assert ev.extra["backend_raw"] == "simulated backend failure"


def test_dev_notes_backend_failure_on_escalate(tmp_path):
    write_skill_stubs(tmp_path)
    b = FakeAgentBackend({AgentRole.DEV: [
        AgentResult(False, {}, "simulated backend failure") for _ in range(3)
    ]})
    g = FakeGateRunner({"unit": [1, 1, 1]})
    outcome, ev = run_dev(b, g, _task(), {}, [], tmp_path, max_iters=3)
    assert outcome == NodeOutcome.ESCALATE
    assert ev.extra["backend_ok"] is False
    assert ev.extra["backend_raw"] == "simulated backend failure"


def test_dev_does_not_note_backend_failure_when_ok(tmp_path):
    write_skill_stubs(tmp_path)
    b = FakeAgentBackend({AgentRole.DEV: [AgentResult(True, {})]})
    g = FakeGateRunner({"unit": [0]})
    outcome, ev = run_dev(b, g, _task(), {}, [], tmp_path)
    assert outcome == NodeOutcome.PASS
    assert "backend_ok" not in ev.extra


def test_context_gatherer_reports_running_each_attempt(tmp_path):
    write_skill_stubs(tmp_path)
    status = FakeStatusReporter()
    b = FakeAgentBackend({AgentRole.CONTEXT_GATHERER: [AgentResult(True, _manifest(tmp_path))]})
    run_context_gatherer(b, _task(), tmp_path, status=status)
    assert status.calls[0]["node"] == "context-gather"
    assert status.calls[0]["node_state"] == "running"
    assert status.calls[0]["attempt"] == 1
    assert status.calls[0]["max_attempts"] == 2


def test_dev_reports_running_each_attempt_and_passes_on_snippet(tmp_path):
    write_skill_stubs(tmp_path)
    status = FakeStatusReporter()

    class SnippetCapturingBackend:
        def run(self, role, prompt, on_snippet=None, on_session_id=None):
            if on_session_id is not None:
                on_session_id("dev-session-id")
            if on_snippet is not None:
                on_snippet("partial output")
            return AgentResult(True, {})

    b = SnippetCapturingBackend()
    g = FakeGateRunner({"unit": [0]})
    run_dev(b, g, _task(), {}, [], tmp_path, status=status)
    assert status.calls[0]["node"] == "dev"
    assert status.calls[0]["node_state"] == "running"
    snippets = [c["snippet"] for c in status.calls if c["snippet"]]
    assert snippets == ["partial output"]


def test_dev_reports_session_id_while_running(tmp_path):
    # Feature A: the session id must reach status *during* the run (as soon as
    # the backend streams pi's `session` event), not only on the final report
    # -- otherwise the dashboard can't open the live session and shows
    # "session not ready".
    write_skill_stubs(tmp_path)
    status = FakeStatusReporter()

    class SessionIdBackend:
        def run(self, role, prompt, on_snippet=None, on_session_id=None):
            if on_session_id is not None:
                on_session_id("abc-123")
            if on_snippet is not None:
                on_snippet("partial")
            return AgentResult(True, {})

    run_dev(SessionIdBackend(), FakeGateRunner({"unit": [0]}), _task(), {}, [], tmp_path, status=status)
    running_with_session = [
        c for c in status.calls
        if c["node"] == "dev" and c["node_state"] == "running" and c.get("session_id") == "abc-123"
    ]
    assert running_with_session, "expected a 'running' dev report carrying the streamed session id"


def test_run_context_gatherer_writes_transcript_when_dir_given(tmp_path):
    write_skill_stubs(tmp_path)
    b = FakeAgentBackend({
        AgentRole.CONTEXT_GATHERER: [AgentResult(True, _manifest(tmp_path), "raw gather output")]
    })
    transcript_dir = tmp_path / "transcripts"
    run_context_gatherer(b, _task(), tmp_path, transcript_dir=transcript_dir)
    assert (transcript_dir / "context-gather-attempt1.log").read_text(encoding="utf-8") == "raw gather output"


def test_run_context_gatherer_no_transcript_when_dir_not_given(tmp_path):
    write_skill_stubs(tmp_path)
    b = FakeAgentBackend({
        AgentRole.CONTEXT_GATHERER: [AgentResult(True, _manifest(tmp_path), "raw gather output")]
    })
    run_context_gatherer(b, _task(), tmp_path)
    assert not (tmp_path / "transcripts").exists()
    assert not list(tmp_path.rglob("*-attempt*.log"))


def test_context_gatherer_pass_reports_session_id_and_summary(tmp_path):
    write_skill_stubs(tmp_path)
    status = FakeStatusReporter()
    manifest = _manifest(tmp_path)
    b = FakeAgentBackend({
        AgentRole.CONTEXT_GATHERER: [AgentResult(True, manifest, "raw", "sess-ctx-1")]
    })
    run_context_gatherer(b, _task(), tmp_path, status=status)
    pass_call = status.calls[-1]
    assert pass_call["node_state"] == "pass"
    assert pass_call["session_id"] == "sess-ctx-1"
    assert pass_call["summary"] == _summarize_manifest(manifest)


def test_dev_pass_reports_session_id_and_summary(tmp_path):
    write_skill_stubs(tmp_path)
    status = FakeStatusReporter()
    b = FakeAgentBackend({AgentRole.DEV: [AgentResult(True, {}, "raw", "sess-dev-1")]})
    g = FakeGateRunner({"unit": [0]})
    run_dev(b, g, _task(), {}, [], tmp_path, status=status)
    pass_call = status.calls[-1]
    assert pass_call["node_state"] == "pass"
    assert pass_call["session_id"] == "sess-dev-1"
    assert "unit tests pass" in pass_call["summary"]


def test_dev_escalate_carries_gate_detail_and_signatures(tmp_path):
    write_skill_stubs(tmp_path)
    b = FakeAgentBackend({AgentRole.DEV: [AgentResult(True, {}) for _ in range(2)]})
    scripted = GateRun(
        name="unit",
        returncode=1,
        output="E ConnectionResetError: connection reset by peer",
        applicable=True,
        commands=("python -m pytest -q",),
    )
    g = FakeGateRunner({"unit": [scripted, scripted]})
    outcome, ev = run_dev(b, g, _task(), {"context": {"source_files": []}}, [], tmp_path, max_iters=2)
    assert outcome == NodeOutcome.ESCALATE
    assert ev.extra["gate_detail"] == scripted.to_dict()
    assert ev.extra["gate_signatures"] == ["ConnectionResetError: connection reset by peer"]


def test_select_kb_is_called_fresh_each_attempt_with_growing_signature_history(tmp_path):
    write_skill_stubs(tmp_path)
    b = FakeAgentBackend({AgentRole.DEV: [AgentResult(True, {}), AgentResult(True, {})]})
    gates = FakeGateRunner({
        "unit": [
            GateRun(name="unit", returncode=1, output="E TimeoutError: slow", applicable=True),
            0,
        ]
    })
    calls: list[tuple[list, list]] = []

    def select_kb(files, signatures):
        calls.append((list(files), list(signatures)))
        return [{"id": "kb-x", "title": "t"}] if signatures else []

    outcome, ev = run_dev(
        b, gates, _task(), {"context": {"source_files": ["a.py"]}}, [], tmp_path,
        max_iters=2, select_kb=select_kb,
    )
    assert outcome == NodeOutcome.PASS
    assert ev.attempts == 2
    assert calls[0] == (["a.py"], [])
    assert calls[1] == (["a.py"], ["TimeoutError: slow"])
    assert "kb-x" in b.prompts[1][1]
    assert "kb-x" not in b.prompts[0][1]


def test_select_kb_seeds_from_caller_signature_history_without_mutating_it(tmp_path):
    write_skill_stubs(tmp_path)
    b = FakeAgentBackend({AgentRole.DEV: [AgentResult(True, {})]})
    gates = FakeGateRunner({"unit": [0]})
    seen = []
    caller_history = ["PriorError: from an earlier cycle"]

    def select_kb(files, signatures):
        seen.append(list(signatures))
        return []

    run_dev(
        b, gates, _task(), {"context": {"source_files": []}}, [], tmp_path,
        select_kb=select_kb, signature_history=caller_history,
    )
    assert seen == [["PriorError: from an earlier cycle"]]
    assert caller_history == ["PriorError: from an earlier cycle"]  # not mutated


def test_run_dev_writes_one_transcript_per_attempt(tmp_path):
    write_skill_stubs(tmp_path)
    b = FakeAgentBackend({AgentRole.DEV: [
        AgentResult(True, {}, "dev attempt 1 raw"),
        AgentResult(True, {}, "dev attempt 2 raw"),
    ]})
    g = FakeGateRunner({"unit": [1, 0]})
    transcript_dir = tmp_path / "transcripts"
    outcome, ev = run_dev(b, g, _task(), {}, [], tmp_path, transcript_dir=transcript_dir)
    assert outcome == NodeOutcome.PASS
    assert ev.attempts == 2
    assert (transcript_dir / "dev-attempt1.log").read_text(encoding="utf-8") == "dev attempt 1 raw"
    assert (transcript_dir / "dev-attempt2.log").read_text(encoding="utf-8") == "dev attempt 2 raw"


def test_summarize_manifest_lists_basenames():
    m = {"context": {"source_files": ["src/a/rtb.py", "src/waypoint.py", "nav.py"]}}
    assert _summarize_manifest(m) == "provided: rtb.py, waypoint.py, nav.py"


def test_summarize_manifest_truncates_over_three_files():
    m = {"context": {"source_files": ["a.py", "b.py", "c.py", "d.py", "e.py"]}}
    assert _summarize_manifest(m) == "provided: a.py, b.py, c.py (+2)"


def test_summarize_manifest_no_files():
    assert _summarize_manifest({"context": {}}) == "no source files"


def test_summarize_manifest_none():
    assert _summarize_manifest(None) == "no manifest"
