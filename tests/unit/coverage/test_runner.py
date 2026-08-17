# tests/unit/coverage/test_runner.py
from __future__ import annotations

import json
from pathlib import Path

import pytest

from factory.coverage.runner import compose_audit_prompt, run
from factory.orchestrator.types import AgentResult

pytestmark = pytest.mark.unit


def _feat_scope(tmp_path: Path, *, with_task: bool = True) -> None:
    """Same fixture shape as test_cli but parameterised on the task."""
    (tmp_path / "docs" / "features").mkdir(parents=True)
    (tmp_path / "docs" / "features" / "FEAT-001.md").write_text(
        "---\nid: FEAT-001\ntitle: Test\nrequirements: [SR-001]\n---\n"
    )
    (tmp_path / "requirements").mkdir()
    (tmp_path / "requirements" / "SR-001.md").write_text(
        "---\nid: SR-001\ntitle: X\nstatement: shall do X\ndomain: behavioral\n"
        "binding:\n  harness: sim-testbench\n  experiment: tests/test_x.py\n"
        "  metric: unit_pass_rate\n  trials: 1\n  assert: '== 1.0'\nchecksum: null\n---\n"
    )
    (tmp_path / "tasks").mkdir()
    if with_task:
        (tmp_path / "tasks" / "T-001.md").write_text(
            "---\nid: T-001\ntitle: T\ndeliverables: []\nsatisfies: [SR-001]\n---\n"
        )
    (tmp_path / "evidence" / "runs").mkdir(parents=True)
    manifest = {
        "schema_version": 2, "run_id": "RUN-001", "task_id": "T-001",
        "started_at": "2026-08-01T00:00:00Z", "ended_at": "2026-08-01T01:00:00Z",
        "start_commit": "a" * 40, "result_commit": "b" * 40, "outcome": "completed",
        "inputs": {"task": {"path": "tasks/T-001.md", "sha256": "0"*64}, "requirements": [], "factory_config_sha256": "0"*64},
        "implementation": {
            "changed_files": ["src/x.py"],
            "patch": {"sha256": "0"*64, "size": 0, "media_type": "application/json"},
        },
        "dependencies": [], "validation": [], "reviews": [], "decisions": [],
        "publication": {"state": "local", "errors": []},
    }
    (tmp_path / "evidence" / "runs" / "RUN-001.json").write_text(json.dumps(manifest), encoding="utf-8")


def _verdict(implemented: bool = True, honest: bool = True) -> dict:
    return {
        "sr_id": "SR-001", "implemented": implemented, "honest": honest,
        "confidence": "high", "margin": None,
        "reasoning": "Test exercises the preempt path.",
        "checked": ["preempt path"], "assumed": ["fixture"],
        "verify": [],
    }


class _FakeBackend:
    """Stand-in for PiAgentBackend: returns a canned verdict without spawning."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        pass

    def run(self, role: object, prompt: str) -> AgentResult:
        self.prompt = prompt  # type: ignore[attr-defined]
        return AgentResult(ok=True, output=self._verdict, raw="", session_id="fake-session")

    _verdict: dict = _verdict()


def test_compose_audit_prompt_includes_packet_and_skill() -> None:
    sr_data = {
        "statement": "shall do X",
        "binding": {"experiment": "tests/test_x.py"},
        "checksum_state": "current",
        "tasks": [{"task_id": "T-001", "changed_files": ["src/x.py"]}],
        "measurement": None,
    }
    prompt = compose_audit_prompt("FEAT-001", "SR-001", sr_data, {"ok": True})
    assert "SR-001" in prompt
    assert "requirement-traceability-audit" in prompt
    assert "src/x.py" in prompt
    assert "implemented" in prompt


def test_run_pass_with_mocked_backend(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _feat_scope(tmp_path)
    monkeypatch.setattr("factory.coverage.runner.PiAgentBackend", _FakeBackend)
    rc = run(tmp_path, "FEAT-001", run_id="r1", no_gates=True)
    assert rc == 0
    run_dir = tmp_path / "coverage-reviews" / "FEAT-001-r1"
    assert (run_dir / "verdicts" / "SR-001.json").exists()
    assert (run_dir / "report.json").exists()
    status = json.loads((run_dir / "status.json").read_text(encoding="utf-8"))
    assert status["phase"] == "done"
    assert status["srs"]["SR-001"]["state"] == "done"


def test_run_fail_when_verdict_not_implemented(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _feat_scope(tmp_path)
    fake = _FakeBackend()
    fake._verdict = _verdict(implemented=False, honest=False)  # type: ignore[attr-defined]
    monkeypatch.setattr("factory.coverage.runner.PiAgentBackend", lambda *a, **k: fake)
    rc = run(tmp_path, "FEAT-001", run_id="r2", no_gates=True)
    assert rc == 1
    report = json.loads(
        (tmp_path / "coverage-reviews" / "FEAT-001-r2" / "report.json").read_text(encoding="utf-8")
    )
    assert report["gate"]["outcome"] == "fail"
    assert "SR-001" in report["gate"]["failed"]


def test_run_unlinked_no_subagent_spawn(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """An SR with no satisfying task is machine-classified; no child is spawned."""
    _feat_scope(tmp_path, with_task=False)
    calls: list[object] = []

    class _SpyBackend:
        def __init__(self, *a: object, **k: object) -> None:
            pass

        def run(self, role: object, prompt: str) -> AgentResult:
            calls.append(role)
            return AgentResult(ok=True, output={}, raw="")

    monkeypatch.setattr("factory.coverage.runner.PiAgentBackend", _SpyBackend)
    rc = run(tmp_path, "FEAT-001", run_id="r3", no_gates=True)
    assert calls == []
    assert rc == 1  # unlinked fails the gate
    status = json.loads(
        (tmp_path / "coverage-reviews" / "FEAT-001-r3" / "status.json").read_text(encoding="utf-8")
    )
    assert status["srs"]["SR-001"]["state"] == "skipped"
