# tests/unit/coverage/test_runner.py
from __future__ import annotations

import json
from pathlib import Path

import pytest

from coherence.gate.model import Decision, DecisionFile
from coherence.gate.store import decision_path, write_decision
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
        "tasks": [
            {
                "task_id": "T-001",
                "changed_files": ["src/x.py"],
                "manifests": ["RUN-001"],
                "record_paths": ["evidence/records/manual-T-001-proof.json"],
                "evidence_state": "present",
            }
        ],
        "measurement": None,
    }
    prompt = compose_audit_prompt("FEAT-001", "SR-001", sr_data, {"ok": True})
    assert "SR-001" in prompt
    assert "requirement-traceability-audit" in prompt
    assert "src/x.py" in prompt
    assert "Evidence: T-001: run manifest, historical record, changed files: src/x.py" in prompt
    assert "RUN-001" not in prompt
    assert "manual-T-001-proof.json" not in prompt
    assert "implemented" in prompt


def test_compose_audit_prompt_describes_missing_evidence_without_raw_overlap_details() -> None:
    sr_data = {
        "statement": "shall do X",
        "binding": {"experiment": "tests/test_x.py"},
        "checksum_state": "current",
        "tasks": [
            {
                "task_id": "T-058",
                "changed_files": [],
                "manifests": [],
                "record_paths": [],
                "evidence_state": "missing",
            },
            {
                "task_id": "T-067",
                "changed_files": [],
                "manifests": [],
                "record_paths": [],
                "evidence_state": "missing",
            },
        ],
        "measurement": None,
    }

    prompt = compose_audit_prompt(
        "FEAT-NAV-017",
        "SR-NAV-001",
        sr_data,
        {
            "ok": False,
            "reason": "missing evidence for tasks",
            "missing_task_ids": ["T-058", "T-067"],
        },
    )

    assert "Evidence: T-058: evidence missing; T-067: evidence missing" in prompt
    assert "missing evidence for tasks" not in prompt
    assert "missing_task_ids" not in prompt


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


def test_feature_unlinked_no_subagent_spawn(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
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


def _feat_scope_proposed(tmp_path: Path) -> None:
    """A feature that also declares SR-002, which is NOT in the register.

    That produces a ``declared_not_in_register`` completeness finding -- the
    runner's ``proposed`` (new-requirement) gate items -- so the human gate
    phase is entered without needing a warned SR.
    """
    (tmp_path / "docs" / "features").mkdir(parents=True)
    (tmp_path / "docs" / "features" / "FEAT-001.md").write_text(
        "---\nid: FEAT-001\ntitle: Test\nrequirements: [SR-001, SR-002]\n---\n"
    )
    (tmp_path / "requirements").mkdir()
    (tmp_path / "requirements" / "SR-001.md").write_text(
        "---\nid: SR-001\ntitle: X\nstatement: shall do X\ndomain: behavioral\n"
        "binding:\n  harness: sim-testbench\n  experiment: tests/test_x.py\n"
        "  metric: unit_pass_rate\n  trials: 1\n  assert: '== 1.0'\nchecksum: null\n---\n"
    )
    (tmp_path / "tasks").mkdir()
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


def _proposal_decision(run_id: str) -> DecisionFile:
    return DecisionFile(
        gate_id=f"coverage:{run_id}",
        artifact_ref="artifact:coverage-reviews/FEAT-001/report.json",
        decisions=(Decision(f"coverage:{run_id}:proposal:SR-002", "accept"),),
        decided_at="2026-08-20T00:00:00Z",
        decided_by="human@example.invalid",
    )


def test_former_300s_timeout_no_longer_auto_finalises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test 1: an unreviewed run must NOT auto-finalise after "waiting".

    The old path polled up to 300s then treated the run as reviewed. The
    DecisionFile adapter must short-circuit immediately and return non-zero
    WITHOUT writing a finalised report when no decision exists.
    """
    _feat_scope_proposed(tmp_path)
    monkeypatch.setattr("factory.coverage.runner.PiAgentBackend", _FakeBackend)
    rc = run(tmp_path, "FEAT-001", run_id="r-t1", no_gates=False)
    assert rc != 0
    status = json.loads(
        (tmp_path / "coverage-reviews" / "FEAT-001-r-t1" / "status.json").read_text(encoding="utf-8")
    )
    # Terminal state is "gates_blocked", NOT the finalised "done": nothing auto-finalises.
    assert status["phase"] == "gates_blocked"
    # The report, if a consumer reads one, must NOT carry a fabricated review verdict.
    report = json.loads(
        (tmp_path / "coverage-reviews" / "FEAT-001-r-t1" / "report.json").read_text(encoding="utf-8")
    )
    assert "human_decisions" not in report


def test_unattended_run_without_decision_exits_nonzero(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test 2: unattended + no decision -> resolve returns "blocked" -> hard failure."""
    _feat_scope_proposed(tmp_path)
    monkeypatch.setattr("factory.coverage.runner.PiAgentBackend", _FakeBackend)
    rc = run(tmp_path, "FEAT-001", run_id="r-ua", no_gates=False, unattended=True)
    assert rc != 0
    status = json.loads(
        (tmp_path / "coverage-reviews" / "FEAT-001-r-ua" / "status.json").read_text(encoding="utf-8")
    )
    assert status["phase"] == "gates_blocked"


def test_existing_valid_decision_resumes_without_prompt(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test 3: an existing valid DecisionFile short-circuits the gate and
    resumes (finalises) without re-prompting for a human decision."""
    _feat_scope_proposed(tmp_path)
    run_dir = tmp_path / "coverage-reviews" / "FEAT-001-r4"
    run_dir.mkdir(parents=True)
    written = write_decision(run_dir, _proposal_decision("r4"))
    assert written == decision_path(run_dir, "coverage:r4")

    monkeypatch.setattr("factory.coverage.runner.PiAgentBackend", _FakeBackend)
    rc = run(tmp_path, "FEAT-001", run_id="r4", no_gates=False)
    report_path = run_dir / "report.json"
    assert report_path.exists()
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["human_decisions"]["gate_id"] == "coverage:r4"
    assert report["human_decisions"]["decisions"][0]["action"] == "accept"
    status = json.loads((run_dir / "status.json").read_text(encoding="utf-8"))
    assert status["phase"] == "done"
    assert rc == 1  # residual classifier gate (SR-002 unlinked) fail, but resumed


def test_no_gates_remains_explicit_opt_out(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test 4: --no-gates skips the human gate entirely and finalises."""
    _feat_scope_proposed(tmp_path)
    monkeypatch.setattr("factory.coverage.runner.PiAgentBackend", _FakeBackend)
    rc = run(tmp_path, "FEAT-001", run_id="r5", no_gates=True)
    report_path = tmp_path / "coverage-reviews" / "FEAT-001-r5" / "report.json"
    assert report_path.exists()
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert "human_decisions" not in report
    assert rc == 1  # SR-002 unlinked still fails the classifier gate
    status = json.loads(
        (tmp_path / "coverage-reviews" / "FEAT-001-r5" / "status.json").read_text(encoding="utf-8")
    )
    assert status["phase"] == "done"
