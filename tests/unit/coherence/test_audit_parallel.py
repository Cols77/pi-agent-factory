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


def test_max_reruns_negative_rejected_by_run(tmp_path: Path) -> None:
    """Finding 5: run() is a library function other callers/tests can call
    directly, bypassing the CLI's _nonnegative_int argparse type -- it must
    validate max_reruns itself, mirroring the existing max_workers guard."""
    _feat_scope(tmp_path, ["SR-001"])
    with pytest.raises(ValueError, match="max_reruns"):
        run(tmp_path, "FEAT-001", run_id="r-bad-reruns", no_gates=True, max_reruns=-1)


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


class _CallTrackingBackend:
    """Records which SR each dispatched call audited (via the runner's own
    "auditing SR-<id>" header line), independent of dispatch order."""

    def __init__(self, *a: object, **k: object) -> None:
        pass

    calls: list[str] = []

    def run(self, role: object, prompt: str) -> AgentResult:
        type(self).calls.append(prompt)
        for sr_id in ("SR-001", "SR-002", "SR-003"):
            if f"auditing SR-{sr_id}" in prompt:
                return AgentResult(ok=True, output=_verdict(sr_id), raw="", session_id="s")
        raise AssertionError(f"unrecognised prompt: {prompt!r}")


def _audited_srs(calls: list[str]) -> set[str]:
    audited = set()
    for prompt in calls:
        for sr_id in ("SR-001", "SR-002", "SR-003"):
            if f"auditing SR-{sr_id}" in prompt:
                audited.add(sr_id)
    return audited


def test_policy_bound_and_max_reruns_are_inert_without_the_flag(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Without --policy-bound, an SR with an existing verdict is always
    accepted as-is -- even though (with no validation-report.json at all)
    its verification_result obligation would be unsatisfied. Behaviour must
    be byte-identical to before this task regardless of what max_reruns is
    set to."""
    _feat_scope(tmp_path, ["SR-001", "SR-002"])
    run_dir = tmp_path / "coverage-reviews" / "FEAT-001-inert"
    verdict_dir = run_dir / "verdicts"
    verdict_dir.mkdir(parents=True)
    (verdict_dir / "SR-001.json").write_text(json.dumps(_verdict("SR-001")), encoding="utf-8")

    _CallTrackingBackend.calls = []
    monkeypatch.setattr("coherence.audit.runner.PiAgentBackend", _CallTrackingBackend)

    rc = run(
        tmp_path, "FEAT-001", run_id="inert", no_gates=True, max_workers=2,
        policy_bound=False, max_reruns=0,
    )

    assert rc == 0
    assert _audited_srs(_CallTrackingBackend.calls) == {"SR-002"}
    audit = json.loads((run_dir / "audit.json").read_text(encoding="utf-8"))
    assert "skipped_by_max_reruns" not in audit


def test_policy_bound_resubmits_sr_whose_verification_result_is_unsatisfied(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With --policy-bound, an SR with an existing verdict but no recorded
    (harness) validation at all has an open verification_result obligation,
    so its stale verdict is resubmitted -- unlike the non-policy-bound
    resume shortcut."""
    _feat_scope(tmp_path, ["SR-001", "SR-002"])
    run_dir = tmp_path / "coverage-reviews" / "FEAT-001-resubmit"
    verdict_dir = run_dir / "verdicts"
    verdict_dir.mkdir(parents=True)
    (verdict_dir / "SR-001.json").write_text(json.dumps(_verdict("SR-001")), encoding="utf-8")

    _CallTrackingBackend.calls = []
    monkeypatch.setattr("coherence.audit.runner.PiAgentBackend", _CallTrackingBackend)

    rc = run(
        tmp_path, "FEAT-001", run_id="resubmit", no_gates=True, max_workers=2,
        policy_bound=True, max_reruns=10,
    )

    assert rc == 0
    assert _audited_srs(_CallTrackingBackend.calls) == {"SR-001", "SR-002"}
    audit = json.loads((run_dir / "audit.json").read_text(encoding="utf-8"))
    assert audit["skipped_by_max_reruns"] == []


def test_policy_bound_skips_sr_whose_verification_result_is_satisfied(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With --policy-bound, an SR whose existing verdict AND recorded
    (passing, non-stale) harness validation both hold is not resubmitted --
    checking the verdict file alone, or the obligation state alone, would
    both be wrong (see the fail-open-avoidance note in runner.run's
    docstring)."""
    _feat_scope(tmp_path, ["SR-001", "SR-002"])
    (tmp_path / "validation").mkdir()
    (tmp_path / "validation" / "validation-report.json").write_text(
        json.dumps({"requirements": [{"id": "SR-001", "passed": True, "stale": False}]}),
        encoding="utf-8",
    )
    run_dir = tmp_path / "coverage-reviews" / "FEAT-001-satisfied"
    verdict_dir = run_dir / "verdicts"
    verdict_dir.mkdir(parents=True)
    (verdict_dir / "SR-001.json").write_text(json.dumps(_verdict("SR-001")), encoding="utf-8")

    _CallTrackingBackend.calls = []
    monkeypatch.setattr("coherence.audit.runner.PiAgentBackend", _CallTrackingBackend)

    rc = run(
        tmp_path, "FEAT-001", run_id="satisfied", no_gates=True, max_workers=2,
        policy_bound=True, max_reruns=10,
    )

    assert rc == 0
    assert _audited_srs(_CallTrackingBackend.calls) == {"SR-002"}
    audit = json.loads((run_dir / "audit.json").read_text(encoding="utf-8"))
    assert audit["skipped_by_max_reruns"] == []
    status = json.loads((run_dir / "status.json").read_text(encoding="utf-8"))
    assert status["srs"]["SR-001"]["state"] == "done"


def test_policy_bound_survives_compile_obligations_crash_for_unregistered_sr(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Finding 1: a feature can declare `satisfies: [SR-999]` for an SR with
    no requirements/SR-999.md file -- coherence.trace.model emits the
    `contains` edge regardless, so compile_obligations(root, "sr:SR-999")
    raises UnsupportedScopeError for that scope. Under --policy-bound this
    must not crash the whole run: the SR must be treated as NOT satisfied
    (fail-closed) and land in the resubmission set, never silently skipped
    as "done"."""
    (tmp_path / "docs" / "features").mkdir(parents=True)
    (tmp_path / "docs" / "features" / "FEAT-001.md").write_text(
        "---\nid: FEAT-001\ntitle: Test\nrequirements: [SR-999]\n---\n"
    )
    (tmp_path / "requirements").mkdir()  # SR-999.md is deliberately absent
    (tmp_path / "tasks").mkdir()
    (tmp_path / "tasks" / "T-001.md").write_text(
        "---\nid: T-001\ntitle: T\ndeliverables: []\nsatisfies: [SR-999]\n---\n"
    )
    (tmp_path / "evidence" / "runs").mkdir(parents=True)
    manifest = {
        "schema_version": 2, "run_id": "RUN-001", "task_id": "T-001",
        "started_at": "2026-08-01T00:00:00Z", "ended_at": "2026-08-01T01:00:00Z",
        "start_commit": "a" * 40, "result_commit": "b" * 40, "outcome": "completed",
        "inputs": {
            "task": {"path": "tasks/T-001.md", "sha256": "0" * 64},
            "requirements": [], "factory_config_sha256": "0" * 64,
        },
        "implementation": {
            "changed_files": ["src/x.py"],
            "patch": {"sha256": "0" * 64, "size": 0, "media_type": "application/json"},
        },
        "dependencies": [], "validation": [], "reviews": [], "decisions": [],
        "publication": {"state": "local", "errors": []},
    }
    (tmp_path / "evidence" / "runs" / "RUN-001.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )

    run_dir = tmp_path / "coverage-reviews" / "FEAT-001-unreg"
    verdict_dir = run_dir / "verdicts"
    verdict_dir.mkdir(parents=True)
    (verdict_dir / "SR-999.json").write_text(json.dumps(_verdict("SR-999")), encoding="utf-8")

    calls: list[str] = []

    class _Backend:
        def __init__(self, *a: object, **k: object) -> None:
            pass

        def run(self, role: object, prompt: str) -> AgentResult:
            calls.append(prompt)
            return AgentResult(ok=True, output=_verdict("SR-999"), raw="", session_id="s")

    monkeypatch.setattr("coherence.audit.runner.PiAgentBackend", _Backend)

    rc = run(
        tmp_path, "FEAT-001", run_id="unreg", no_gates=True, max_workers=2,
        policy_bound=True, max_reruns=10,
    )

    # Must complete (not raise an unhandled UnsupportedScopeError) and must
    # resubmit SR-999 rather than silently treating it as done.
    assert rc in (0, 1, 2)
    assert any("auditing SR-SR-999" in p for p in calls)
    audit = json.loads((run_dir / "audit.json").read_text(encoding="utf-8"))
    assert audit["skipped_by_max_reruns"] == []


def test_policy_bound_caps_unregistered_sr_when_max_reruns_is_zero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Same crash-guard scenario as above, but with --max-reruns 0: the SR
    must be recorded in skipped_by_max_reruns (capped, "cannot prove
    satisfied" fails closed into the rerun-candidate set which the cap then
    holds back) -- not resubmitted, and never treated as a silent pass."""
    (tmp_path / "docs" / "features").mkdir(parents=True)
    (tmp_path / "docs" / "features" / "FEAT-001.md").write_text(
        "---\nid: FEAT-001\ntitle: Test\nrequirements: [SR-999]\n---\n"
    )
    (tmp_path / "requirements").mkdir()
    (tmp_path / "tasks").mkdir()
    (tmp_path / "tasks" / "T-001.md").write_text(
        "---\nid: T-001\ntitle: T\ndeliverables: []\nsatisfies: [SR-999]\n---\n"
    )
    (tmp_path / "evidence" / "runs").mkdir(parents=True)
    manifest = {
        "schema_version": 2, "run_id": "RUN-001", "task_id": "T-001",
        "started_at": "2026-08-01T00:00:00Z", "ended_at": "2026-08-01T01:00:00Z",
        "start_commit": "a" * 40, "result_commit": "b" * 40, "outcome": "completed",
        "inputs": {
            "task": {"path": "tasks/T-001.md", "sha256": "0" * 64},
            "requirements": [], "factory_config_sha256": "0" * 64,
        },
        "implementation": {
            "changed_files": ["src/x.py"],
            "patch": {"sha256": "0" * 64, "size": 0, "media_type": "application/json"},
        },
        "dependencies": [], "validation": [], "reviews": [], "decisions": [],
        "publication": {"state": "local", "errors": []},
    }
    (tmp_path / "evidence" / "runs" / "RUN-001.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )

    run_dir = tmp_path / "coverage-reviews" / "FEAT-001-unreg-capped"
    verdict_dir = run_dir / "verdicts"
    verdict_dir.mkdir(parents=True)
    (verdict_dir / "SR-999.json").write_text(json.dumps(_verdict("SR-999")), encoding="utf-8")

    calls: list[str] = []

    class _Backend:
        def __init__(self, *a: object, **k: object) -> None:
            pass

        def run(self, role: object, prompt: str) -> AgentResult:
            calls.append(prompt)
            return AgentResult(ok=True, output=_verdict("SR-999"), raw="", session_id="s")

    monkeypatch.setattr("coherence.audit.runner.PiAgentBackend", _Backend)

    rc = run(
        tmp_path, "FEAT-001", run_id="unreg-capped", no_gates=True, max_workers=2,
        policy_bound=True, max_reruns=0,
    )

    assert rc in (0, 1, 2)
    assert calls == []
    audit = json.loads((run_dir / "audit.json").read_text(encoding="utf-8"))
    assert audit["skipped_by_max_reruns"] == ["SR-999"]
    status = json.loads((run_dir / "status.json").read_text(encoding="utf-8"))
    assert status["srs"]["SR-999"]["state"] == "stale_capped"


def test_worker_completion_updates_live_status_progress(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Finding 3: the coordinator's `for future in as_completed(futures):`
    loop runs on the coordinator thread, so it may safely write a
    progress-only status update per completed worker -- proving live
    per-SR status.json progress survived Task 3's parallelisation, instead
    of every in-flight SR showing "running" for the whole batch duration.
    A fast SR must reach a distinguishing "worker_done" marker in a status
    write while a slower sibling is still genuinely in flight.

    Spies on ``_write_status`` (recording a deep copy of each payload)
    rather than polling status.json off disk: reading a file mid-``os.
    replace()`` from another thread is a real sharing-violation race on
    Windows, not just a synchronization nicety, so this asserts on the
    in-memory call sequence instead -- still exercising the real write
    path via ``call through``."""
    _feat_scope(tmp_path, ["SR-001", "SR-002"])
    fast_done = threading.Event()
    release_slow = threading.Event()

    class _Backend:
        def __init__(self, *a: object, **k: object) -> None:
            pass

        def run(self, role: object, prompt: str) -> AgentResult:
            if "auditing SR-SR-001" in prompt:
                result = AgentResult(ok=True, output=_verdict("SR-001"), raw="", session_id="s")
                fast_done.set()
                return result
            # SR-002: block until the test has observed SR-001's live
            # progress marker.
            release_slow.wait(timeout=5)
            return AgentResult(ok=True, output=_verdict("SR-002"), raw="", session_id="s")

    monkeypatch.setattr("coherence.audit.runner.PiAgentBackend", _Backend)

    import coherence.audit.runner as runner_mod

    original_write_status = runner_mod._write_status
    writes_lock = threading.Lock()
    writes: list[dict] = []

    def _spy_write_status(path: Path, payload: dict) -> None:
        with writes_lock:
            writes.append(json.loads(json.dumps(payload)))
        original_write_status(path, payload)

    monkeypatch.setattr("coherence.audit.runner._write_status", _spy_write_status)

    run_dir = tmp_path / "coverage-reviews" / "FEAT-001-live"
    result: dict[str, int] = {}

    def _run_it() -> None:
        result["rc"] = run(
            tmp_path, "FEAT-001", run_id="live", no_gates=True, max_workers=2,
        )

    thread = threading.Thread(target=_run_it)
    thread.start()
    try:
        assert fast_done.wait(timeout=5)
        deadline = time.time() + 5
        observed_payload: dict | None = None
        while time.time() < deadline:
            with writes_lock:
                for payload in reversed(writes):
                    if payload.get("srs", {}).get("SR-001", {}).get("state") == "worker_done":
                        observed_payload = payload
                        break
            if observed_payload is not None:
                break
            time.sleep(0.005)
        assert observed_payload is not None, (
            "expected SR-001 to reach 'worker_done' before the batch finished"
        )
        # SR-002 must still be genuinely in flight in that same snapshot --
        # proves this was a mid-batch write, not the final post-batch status.
        assert observed_payload["srs"]["SR-002"]["state"] == "running"
    finally:
        release_slow.set()
        thread.join(timeout=10)

    assert result["rc"] == 0
    final_status = json.loads((run_dir / "status.json").read_text(encoding="utf-8"))
    assert final_status["srs"]["SR-001"]["state"] == "done"
    assert final_status["srs"]["SR-002"]["state"] == "done"


def test_max_reruns_caps_resubmission_and_reports_the_uncapped_remainder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The resubmission set (verdict exists, obligation unsatisfied) is
    sorted by SR id and capped at max_reruns; the remainder keep their stale
    verdict for this run and are recorded, not silently dropped."""
    _feat_scope(tmp_path, ["SR-001", "SR-002", "SR-003"])
    run_dir = tmp_path / "coverage-reviews" / "FEAT-001-capped"
    verdict_dir = run_dir / "verdicts"
    verdict_dir.mkdir(parents=True)
    for sr_id in ("SR-001", "SR-002", "SR-003"):
        (verdict_dir / f"{sr_id}.json").write_text(
            json.dumps(_verdict(sr_id)), encoding="utf-8"
        )

    _CallTrackingBackend.calls = []
    monkeypatch.setattr("coherence.audit.runner.PiAgentBackend", _CallTrackingBackend)

    rc = run(
        tmp_path, "FEAT-001", run_id="capped", no_gates=True, max_workers=2,
        policy_bound=True, max_reruns=1,
    )

    assert rc == 0
    # Only the lexicographically-first candidate is resubmitted.
    assert _audited_srs(_CallTrackingBackend.calls) == {"SR-001"}
    audit = json.loads((run_dir / "audit.json").read_text(encoding="utf-8"))
    assert audit["skipped_by_max_reruns"] == ["SR-002", "SR-003"]
    # Distinct from a genuinely fresh "done" verdict (Finding 2): status.json
    # must not let a capped SR look indistinguishable from a real pass.
    status = json.loads((run_dir / "status.json").read_text(encoding="utf-8"))
    assert status["srs"]["SR-002"]["state"] == "stale_capped"
    assert status["srs"]["SR-003"]["state"] == "stale_capped"

    report = json.loads((run_dir / "report.json").read_text(encoding="utf-8"))
    assert report["skipped_by_max_reruns"] == ["SR-002", "SR-003"]
    from coherence.audit.report import render_human_summary

    summary = render_human_summary(report)
    assert "SR-002" in summary and "SR-003" in summary
    assert "--max-reruns cap" in summary


def test_max_reruns_zero_disables_resubmission_but_still_submits_missing_verdicts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """--max-reruns 0 disables policy-bound resubmission entirely, but an SR
    with no verdict file at all is always (re)submitted regardless -- the
    fail-open-avoidance rule this task must not violate."""
    _feat_scope(tmp_path, ["SR-001", "SR-002"])
    run_dir = tmp_path / "coverage-reviews" / "FEAT-001-zero"
    verdict_dir = run_dir / "verdicts"
    verdict_dir.mkdir(parents=True)
    # SR-001 has a stale existing verdict; SR-002 has none at all.
    (verdict_dir / "SR-001.json").write_text(json.dumps(_verdict("SR-001")), encoding="utf-8")

    _CallTrackingBackend.calls = []
    monkeypatch.setattr("coherence.audit.runner.PiAgentBackend", _CallTrackingBackend)

    rc = run(
        tmp_path, "FEAT-001", run_id="zero", no_gates=True, max_workers=2,
        policy_bound=True, max_reruns=0,
    )

    assert rc == 0
    # SR-001 is a resubmission candidate but capped away; SR-002 has no
    # verdict file, so it is always submitted, cap or no cap.
    assert _audited_srs(_CallTrackingBackend.calls) == {"SR-002"}
    audit = json.loads((run_dir / "audit.json").read_text(encoding="utf-8"))
    assert audit["skipped_by_max_reruns"] == ["SR-001"]
    status = json.loads((run_dir / "status.json").read_text(encoding="utf-8"))
    assert status["srs"]["SR-001"]["state"] == "stale_capped"
    assert status["srs"]["SR-002"]["state"] == "done"


@pytest.mark.parametrize("bad_value", ["-1"])
def test_cli_max_reruns_negative_fails_argument_validation(
    bad_value: str, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as exc_info:
        cli_main(["run", "FEAT-001", "--max-reruns", bad_value])
    assert exc_info.value.code == 2


def test_cli_max_reruns_zero_is_a_valid_value(monkeypatch: pytest.MonkeyPatch) -> None:
    """Unlike --max-workers, 0 must be ACCEPTED by argument parsing -- it is
    the explicit way to disable policy-bound resubmission, not a rejected
    non-positive value."""
    captured: dict[str, object] = {}

    def _fake_cmd_run(root: object, feat: object, **kwargs: object) -> int:
        captured.update(kwargs)
        return 0

    monkeypatch.setattr("coherence.audit.cli.cmd_run", _fake_cmd_run)
    rc = cli_main(["run", "FEAT-001", "--policy-bound", "--max-reruns", "0"])
    assert rc == 0
    assert captured["max_reruns"] == 0
    assert captured["policy_bound"] is True


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
