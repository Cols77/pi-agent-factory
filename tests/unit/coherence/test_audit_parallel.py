# tests/unit/coherence/test_audit_parallel.py
"""Bounded, deterministic parallel per-SR audit review.

Task 3 (Increment 4) parallelises coherence.audit.runner.run()'s per-SR
audit loop behind a small ThreadPoolExecutor: Phase 0 (scope/overlap),
resume checks, consolidation, and the gate stay serial; only the "needs a
subagent verdict" set is dispatched to bounded workers. These tests use a
fake backend (matching tests/unit/coverage/test_runner.py's _FakeBackend
pattern) extended with a lock+counter to observe real concurrency, and
verify: bounded concurrency, argument validation, the resume shortcut,
degraded semantics on a worker failure, and that completion order never
leaks into the coordinator's sorted, deterministic output.
"""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path

import pytest

from coherence.audit.cli import main as cli_main
from coherence.audit.runner import run
from factory.orchestrator.types import AgentResult

pytestmark = pytest.mark.unit


def _feat_scope(tmp_path: Path, sr_ids: list[str]) -> None:
    """A feature with N independent SRs, each linked to its own task and
    manifest -- same fixture shape as test_runner.py's _feat_scope, extended
    to more than one SR so workers can genuinely run concurrently."""
    (tmp_path / "docs" / "features").mkdir(parents=True)
    (tmp_path / "docs" / "features" / "FEAT-001.md").write_text(
        "---\nid: FEAT-001\ntitle: Test\nrequirements: ["
        + ", ".join(sr_ids)
        + "]\n---\n"
    )
    (tmp_path / "requirements").mkdir()
    (tmp_path / "tasks").mkdir()
    (tmp_path / "evidence" / "runs").mkdir(parents=True)
    for i, sr_id in enumerate(sr_ids, start=1):
        task_id = f"T-{i:03d}"
        run_id = f"RUN-{i:03d}"
        (tmp_path / "requirements" / f"{sr_id}.md").write_text(
            f"---\nid: {sr_id}\ntitle: X\nstatement: shall do X\ndomain: behavioral\n"
            f"binding:\n  harness: sim-testbench\n  experiment: tests/test_x{i}.py\n"
            "  metric: unit_pass_rate\n  trials: 1\n  assert: '== 1.0'\nchecksum: null\n---\n"
        )
        (tmp_path / "tasks" / f"{task_id}.md").write_text(
            f"---\nid: {task_id}\ntitle: T\ndeliverables: []\nsatisfies: [{sr_id}]\n---\n"
        )
        manifest = {
            "schema_version": 2, "run_id": run_id, "task_id": task_id,
            "started_at": "2026-08-01T00:00:00Z", "ended_at": "2026-08-01T01:00:00Z",
            "start_commit": "a" * 40, "result_commit": "b" * 40, "outcome": "completed",
            "inputs": {
                "task": {"path": f"tasks/{task_id}.md", "sha256": "0" * 64},
                "requirements": [], "factory_config_sha256": "0" * 64,
            },
            "implementation": {
                "changed_files": [f"src/x{i}.py"],
                "patch": {"sha256": "0" * 64, "size": 0, "media_type": "application/json"},
            },
            "dependencies": [], "validation": [], "reviews": [], "decisions": [],
            "publication": {"state": "local", "errors": []},
        }
        (tmp_path / "evidence" / "runs" / f"{run_id}.json").write_text(
            json.dumps(manifest), encoding="utf-8"
        )


def _verdict(sr_id: str, *, implemented: bool = True, honest: bool = True) -> dict:
    return {
        "sr_id": sr_id, "implemented": implemented, "honest": honest,
        "confidence": "high", "margin": None,
        "reasoning": "Test exercises the preempt path.",
        "checked": ["preempt path"], "assumed": ["fixture"],
        "verify": [],
    }


class _ConcurrencyTrackingBackend:
    """Shared across all worker calls (constructed once, returned by every
    ``PiAgentBackend(...)`` invocation via monkeypatch) so a class-level
    lock+counter can observe how many workers are inside ``run()`` at once.

    Concurrency is proven deterministically with a ``threading.Barrier``,
    not timing. The runner submits every ``needs_worker`` future to the
    bounded executor up front (see runner.py), so with ``max_workers=N``
    exactly the first ``N`` dispatched calls start running immediately and
    truly concurrently; only those first ``barrier_parties`` calls are made
    to rendezvous on the barrier -- ``barrier.wait()`` cannot return for any
    of them until all of them have entered ``run()``, which forces the
    active-worker count to have genuinely reached ``barrier_parties`` at
    that instant, no sleep window or scheduler luck required. Calls beyond
    ``barrier_parties`` (there is no guaranteed further concurrent partner
    for them under a bounded pool) skip the barrier and return immediately."""

    def __init__(self, *, barrier_parties: int = 2) -> None:
        self._lock = threading.Lock()
        self._active = 0
        self.max_active = 0
        self._entry_count = 0
        self._barrier_parties = barrier_parties
        self._barrier = threading.Barrier(barrier_parties)
        self.calls: list[str] = []

    def run(self, role: object, prompt: str) -> AgentResult:
        with self._lock:
            self._active += 1
            self.max_active = max(self.max_active, self._active)
            self.calls.append(prompt)
            self._entry_count += 1
            use_barrier = self._entry_count <= self._barrier_parties
        if use_barrier:
            self._barrier.wait()
        with self._lock:
            self._active -= 1
        return AgentResult(ok=True, output=_verdict("SR-generic"), raw="", session_id="fake")


def test_bounded_concurrency_exceeds_one_and_respects_max_workers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _feat_scope(tmp_path, ["SR-001", "SR-002", "SR-003"])
    backend = _ConcurrencyTrackingBackend(barrier_parties=2)
    monkeypatch.setattr("coherence.audit.runner.PiAgentBackend", lambda *a, **k: backend)

    rc = run(tmp_path, "FEAT-001", run_id="r1", no_gates=True, max_workers=2)

    assert rc == 0
    assert len(backend.calls) == 3
    assert 1 < backend.max_active <= 2


def test_max_workers_nonpositive_rejected_by_run(tmp_path: Path) -> None:
    _feat_scope(tmp_path, ["SR-001"])
    with pytest.raises(ValueError, match="max_workers"):
        run(tmp_path, "FEAT-001", run_id="r-bad", no_gates=True, max_workers=0)


@pytest.mark.parametrize("bad_value", ["0", "-1"])
def test_cli_max_workers_nonpositive_fails_argument_validation(
    bad_value: str, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as exc_info:
        cli_main(["run", "FEAT-001", "--max-workers", bad_value])
    assert exc_info.value.code == 2


def test_preexisting_verdict_launches_no_worker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _feat_scope(tmp_path, ["SR-001", "SR-002"])
    run_dir = tmp_path / "coverage-reviews" / "FEAT-001-r2"
    verdict_dir = run_dir / "verdicts"
    verdict_dir.mkdir(parents=True)
    (verdict_dir / "SR-001.json").write_text(
        json.dumps(_verdict("SR-001")), encoding="utf-8"
    )

    calls: list[str] = []

    class _SpyBackend:
        def __init__(self, *a: object, **k: object) -> None:
            pass

        def run(self, role: object, prompt: str) -> AgentResult:
            calls.append(prompt)
            return AgentResult(ok=True, output=_verdict("SR-002"), raw="", session_id="s")

    monkeypatch.setattr("coherence.audit.runner.PiAgentBackend", _SpyBackend)

    rc = run(tmp_path, "FEAT-001", run_id="r2", no_gates=True, max_workers=2)

    assert rc == 0
    assert len(calls) == 1
    # The loaded audit skill's own worked example mentions "SR-001" as
    # sample JSON, so a bare substring check is unreliable -- match the
    # runner's own "auditing SR-<id>" header line instead.
    assert "auditing SR-SR-002" in calls[0]
    assert "auditing SR-SR-001" not in calls[0]
    status = json.loads((run_dir / "status.json").read_text(encoding="utf-8"))
    assert status["srs"]["SR-001"]["state"] == "done"
    assert status["srs"]["SR-002"]["state"] == "done"


def test_one_worker_failure_yields_degraded_semantics(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _feat_scope(tmp_path, ["SR-001", "SR-002"])

    class _MixedBackend:
        def __init__(self, *a: object, **k: object) -> None:
            pass

        def run(self, role: object, prompt: str) -> AgentResult:
            # "auditing SR-SR-<id>" (the runner's own header line), not a
            # bare sr_id substring -- the loaded skill's worked example
            # mentions "SR-001" regardless of which SR is being audited.
            if "auditing SR-SR-001" in prompt:
                return AgentResult(ok=False, output={}, raw="boom", session_id=None)
            return AgentResult(ok=True, output=_verdict("SR-002"), raw="", session_id="s")

    monkeypatch.setattr("coherence.audit.runner.PiAgentBackend", _MixedBackend)

    rc = run(tmp_path, "FEAT-001", run_id="r3", no_gates=True, max_workers=2)

    run_dir = tmp_path / "coverage-reviews" / "FEAT-001-r3"
    audit = json.loads((run_dir / "audit.json").read_text(encoding="utf-8"))
    assert audit["tool_failures"] == [{"sr_id": "SR-001", "issue": "subagent failed: boom"}]
    report = json.loads((run_dir / "report.json").read_text(encoding="utf-8"))
    assert report["gate"]["outcome"] == "degraded"
    assert report["gate"]["degraded"] == ["SR-001"]
    assert rc == 2


def test_completion_order_does_not_affect_sorted_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two runs where SR-002 and SR-003 fail, but finish in opposite wall-
    clock order, must still produce identically ordered (sorted by SR id)
    tool_failures and report state/gate output -- the coordinator sorts
    before writing, so completion order can never leak into the artifacts.
    generated_at/run_id necessarily differ between the two runs, so this
    compares only the order-sensitive substructures, not raw file bytes."""
    _feat_scope(tmp_path, ["SR-001", "SR-002", "SR-003"])

    def _make_backend(*, slow_sr: str) -> type:
        class _Backend:
            def __init__(self, *a: object, **k: object) -> None:
                pass

            def run(self, role: object, prompt: str) -> AgentResult:
                # Match the runner's own "auditing SR-SR-<id>" header line,
                # not a bare sr_id substring -- see the note in
                # test_preexisting_verdict_launches_no_worker.
                if "auditing SR-SR-002" in prompt or "auditing SR-SR-003" in prompt:
                    sr = "SR-002" if "auditing SR-SR-002" in prompt else "SR-003"
                    time.sleep(0.08 if sr == slow_sr else 0.02)
                    return AgentResult(
                        ok=False, output={}, raw=f"boom-{sr[-1]}", session_id=None
                    )
                return AgentResult(ok=True, output=_verdict("SR-001"), raw="", session_id="s")

        return _Backend

    monkeypatch.setattr(
        "coherence.audit.runner.PiAgentBackend", _make_backend(slow_sr="SR-002")
    )
    rc_a = run(tmp_path, "FEAT-001", run_id="rA", no_gates=True, max_workers=3)

    monkeypatch.setattr(
        "coherence.audit.runner.PiAgentBackend", _make_backend(slow_sr="SR-003")
    )
    rc_b = run(tmp_path, "FEAT-001", run_id="rB", no_gates=True, max_workers=3)

    assert rc_a == rc_b == 2

    audit_a = json.loads(
        (tmp_path / "coverage-reviews" / "FEAT-001-rA" / "audit.json").read_text(encoding="utf-8")
    )
    audit_b = json.loads(
        (tmp_path / "coverage-reviews" / "FEAT-001-rB" / "audit.json").read_text(encoding="utf-8")
    )
    expected_tool_failures = [
        {"sr_id": "SR-002", "issue": "subagent failed: boom-2"},
        {"sr_id": "SR-003", "issue": "subagent failed: boom-3"},
    ]
    assert audit_a["tool_failures"] == expected_tool_failures
    assert audit_b["tool_failures"] == expected_tool_failures

    report_a = json.loads(
        (tmp_path / "coverage-reviews" / "FEAT-001-rA" / "report.json").read_text(encoding="utf-8")
    )
    report_b = json.loads(
        (tmp_path / "coverage-reviews" / "FEAT-001-rB" / "report.json").read_text(encoding="utf-8")
    )
    assert list(report_a["states"].keys()) == ["SR-001", "SR-002", "SR-003"]
    assert list(report_b["states"].keys()) == ["SR-001", "SR-002", "SR-003"]
    assert report_a["gate"] == report_b["gate"]
    assert json.dumps(report_a["states"], sort_keys=True) == json.dumps(
        report_b["states"], sort_keys=True
    )
