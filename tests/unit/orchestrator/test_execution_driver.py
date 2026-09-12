"""SR-034/SR-049 governed execution driver tests (RED first).

The driver wraps the *existing* nodes (``run_dev``/``run_validation``) and the
SR-034/SR-049 infrastructure (contract, GatePlan, transport, campaign, review
swarm, governed stage cursor) into one bounded single-task orchestration. These
tests script a governed ``AgentBackend``, a campaign runner and the gates, and
assert the honest driver behaviour: happy-path staging, the fixer loop bound by
the project budget, the SR-049 canonical gate before ``dod_met`` can be true,
and the explicit retry/defer/block human resolution.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import pytest

from coherence.execution.gate_plan import compile_gate_plan
from factory.orchestrator.backends import AgentBackend, FakeGateRunner, GateRun
from factory.orchestrator.execution import RunExecution
from factory.orchestrator.execution_campaign import TestCampaign, TestSnapshot
from factory.orchestrator.execution_contract import ExecutionContract
from factory.orchestrator.execution_driver import CanonicalGateError, GovernedExecutionDriver
from factory.orchestrator.execution_transport import ExecutionTransport
from factory.orchestrator.git_ops import FakeGitOps
from factory.orchestrator.types import AgentRole, NodeOutcome
from substrate.agents.model import AgentResult
from substrate.ledger.tasks import Task

pytestmark = pytest.mark.unit

_WORKFLOW = "governed-execution/v1"


# -- fixtures / helpers -------------------------------------------------------


def task_fixture(tmp_path: Path) -> Task:
    return Task(
        id="T-013",
        title="Governed execution driver",
        status="todo",
        dod=["both reviews reported", "canonical gates green"],
        body="",
        path=tmp_path / "T-013.md",
    )


def gate_plan_fixture() -> Any:
    return compile_gate_plan(
        workflow_version=_WORKFLOW,
        version="behavior-change@1",
        required_gates=("unit", "full"),
        preflight_policy="mandatory-only",
    )


def contract_fixture(tmp_path: Path, gate_plan: Any) -> ExecutionContract:
    contract = ExecutionContract.build(
        run_id="run-013",
        task_id="T-013",
        workflow_version=_WORKFLOW,
        workspace=tmp_path / "worktree",
        required_gates=("unit", "full"),
        satisfies=("SR-034", "SR-049"),
        plan_ref="docs/superpowers/plans/plan.md",
        spec_ref=None,
        max_fixer_iterations=2,
    )
    return contract.with_gate_plan(gate_plan)


def execution_fixture(tmp_path: Path) -> RunExecution:
    return RunExecution.create(
        tmp_path,
        "run-013",
        "T-013",
        "a" * 40,
        FakeGitOps(head="a" * 40),
    )


class ScriptedCampaignRunner:
    """Returns scripted snapshots for baseline, after-dev and confirmation runs."""

    def __init__(self, baseline: TestSnapshot, after_dev: TestSnapshot) -> None:
        self._baseline = baseline
        self._after = after_dev
        self.runs: list[TestSnapshot] = []

    def run(self, contract: ExecutionContract) -> TestSnapshot:
        if not self.runs:
            self.runs.append(self._baseline)
            return self._baseline
        self.runs.append(self._after)
        return self._after


class _EmptyRegistry:
    def is_registered(self, test_id: str) -> bool:
        return False


def campaign_fixture(
    baseline_passed: tuple[str, ...] = ("tests/test_x.py::test_a",),
    after_failed: tuple[str, ...] = (),
) -> tuple[TestCampaign, ScriptedCampaignRunner]:
    baseline_declared = frozenset(baseline_passed)
    after_declared = baseline_declared | frozenset(after_failed)
    declared = after_declared
    baseline = TestSnapshot(
        passed_ids=baseline_declared,
        failed_ids=frozenset(),
        pass_rate=len(baseline_declared) / len(declared) if declared else 0.0,
        declared_ids=declared,
    )
    after = TestSnapshot(
        passed_ids=frozenset(declared - set(after_failed)),
        failed_ids=frozenset(after_failed),
        pass_rate=(len(declared) - len(after_failed)) / len(declared),
        declared_ids=declared,
    )
    runner = ScriptedCampaignRunner(baseline, after)
    return TestCampaign(runner=runner, flaky_registry=_EmptyRegistry()), runner


@dataclass
class _ReviewScript:
    """One scripted review cycle: findings per lane and whether it passed."""

    spec_findings: tuple[str, ...]
    quality_findings: tuple[str, ...]
    spec_dod: bool = True
    quality_dod: bool = True


class _ScriptedBackend(AgentBackend):
    """A governed ``AgentBackend`` that scripts dev/review results by prompt.

    DEV invocations get ``unit_ok``; review lanes get a scripted
    ``_ReviewScript`` per review cycle. Records every role and session id so a
    test can assert ordering and fresh sessions.
    """

    def __init__(
        self,
        *,
        unit_ok: bool = True,
        review_scripts: list[_ReviewScript] | None = None,
    ) -> None:
        self.unit_ok = unit_ok
        self._review_scripts = list(review_scripts or [])
        self.roles: list[str] = []
        self.session_ids: list[str] = []
        self.dev_prompts: list[str] = []
        self.review_cycle = 0
        self._dev_count = 0

    def run(
        self,
        role: AgentRole,
        prompt: str,
        on_snippet: Callable[[str], None] | None = None,
        on_session_id: Callable[[str], None] | None = None,
    ) -> AgentResult:
        self.roles.append(role.value)
        if role is AgentRole.DEV:
            self._dev_count += 1
            session = f"dev-session-{self._dev_count}"
            self.session_ids.append(session)
            self.dev_prompts.append(prompt)
            if on_session_id is not None:
                on_session_id(session)
            return AgentResult(
                ok=True,
                output={"summary": "changed files; unit green" if self.unit_ok else "red"},
                session_id=session,
            )
        # REVIEW lane
        script = self._review_scripts[self.review_cycle % max(1, len(self._review_scripts))]
        lane = "spec-review" if "SPEC-COMPLIANCE" in prompt else "quality-review"
        session = f"{lane}-session-{self.review_cycle + 1}"
        self.session_ids.append(session)
        if on_session_id is not None:
            on_session_id(session)
        findings = script.spec_findings if lane == "spec-review" else script.quality_findings
        dod_met = script.spec_dod if lane == "spec-review" else script.quality_dod
        if lane == "quality-review":
            self.review_cycle += 1
        return AgentResult(
            ok=True, output={"findings": list(findings), "dod_met": dod_met}, session_id=session
        )


class _NoopGate(FakeGateRunner):
    """A GateRunner that reports every gate green (used by the driver fixture)."""

    def __init__(self) -> None:
        super().__init__({})


class _ValidationFailingGate(FakeGateRunner):
    """A GateRunner that fails the validation ``sim`` gate so validation blocks."""

    def __init__(self) -> None:
        super().__init__(
            {
                "sim": [GateRun(name="sim", returncode=1, output="boom", applicable=True)],
            }
        )


class _RecordingDeferrals:
    def __init__(self) -> None:
        self.writes: list[dict[str, Any]] = []

    def write(
        self,
        reason: str,
        *,
        review_after: str | None = None,
        decided_at: str | None = None,
        decided_by: str | None = None,
    ) -> None:
        self.writes.append(
            {
                "reason": reason,
                "review_after": review_after,
                "decided_at": decided_at,
                "decided_by": decided_by,
            }
        )


def driver_fixture(
    tmp_path: Path,
    *,
    backend: _ScriptedBackend,
    review_scripts: list[_ReviewScript] | None = None,
    campaign=None,
    max_fixer_iterations: int = 2,
    trace_ok: bool = True,
    register_ok: bool = True,
    deferrals: _RecordingDeferrals | None = None,
    unit_ok: bool = True,
) -> GovernedExecutionDriver:
    gate_plan = gate_plan_fixture()
    contract = contract_fixture(tmp_path, gate_plan)
    execution = execution_fixture(tmp_path)
    if campaign is None:
        campaign, _ = campaign_fixture()
    transport = ExecutionTransport.for_transport("direct")
    if backend is None:  # type: ignore[arg-type]
        backend = _ScriptedBackend(
            unit_ok=unit_ok, review_scripts=review_scripts or []
        )

    def _make_backend(workspace: Path):  # noqa: ANN001
        return backend

    manifest = {"context": {"source_files": ["src/x.py"]}}

    def _trace() -> None:
        if not trace_ok:
            raise CanonicalGateError("trace check failed")

    def _register() -> None:
        if not register_ok:
            raise CanonicalGateError("register check failed")

    return GovernedExecutionDriver(
        execution=execution,
        gate_plan=gate_plan,
        contract_factory=lambda: contract,
        backend_factory=_make_backend,
        gates=_NoopGate(),
        campaign=campaign,
        transport=transport,
        manifest=manifest,
        repo_root=tmp_path,
        transcript_dir=tmp_path / "transcripts",
        max_fixer_iterations=max_fixer_iterations,
        deferrals=deferrals or _RecordingDeferrals(),
        trace_check=_trace,
        register_check=_register,
    )


def _clean_review() -> _ReviewScript:
    return _ReviewScript(spec_findings=(), quality_findings=())


def _finding_review() -> _ReviewScript:
    return _ReviewScript(spec_findings=("spec ok but x is wrong",), quality_findings=())


# -- tests --------------------------------------------------------------------


def test_happy_path_records_the_canonical_stages_and_completes(tmp_path: Path) -> None:
    backend = _ScriptedBackend(review_scripts=[_clean_review()])
    driver = driver_fixture(tmp_path, backend=backend)

    result = driver.run(task_fixture(tmp_path))

    assert result.outcome == "completed"
    assert result.dod_met is True
    assert [event.extra["governed_execution"]["stage_id"] for event in result.events] == [
        "contract-compiled",
        "preflight",
        "transport-materialized",
        "baseline",
        "dev",
        "validation",
        "campaign-classification",
        "review-spec",
        "review-quality",
        "review-join",
        "canonical-gates",
        "handoff",
    ]
    assert backend.roles == [AgentRole.DEV.value, AgentRole.REVIEW.value, AgentRole.REVIEW.value]
    assert len({sid for sid in backend.session_ids}) == 3


def test_fixer_runs_only_after_both_reviews_and_receives_finding_feedback(
    tmp_path: Path,
) -> None:
    backend = _ScriptedBackend(
        review_scripts=[_finding_review(), _clean_review(), _clean_review()]
    )
    driver = driver_fixture(tmp_path, backend=backend, max_fixer_iterations=2)

    result = driver.run(task_fixture(tmp_path))

    assert result.outcome == "completed"
    assert result.dod_met is True
    stages = [event.extra["governed_execution"]["stage_id"] for event in result.events]
    assert "fixer" in stages
    # The fixer DEV pass must carry the reviewer finding verbatim.
    dev_prompts = backend.dev_prompts
    assert dev_prompts and "spec ok but x is wrong" in dev_prompts[-1]
    # Both reviews ran before the fixer DEV was issued.
    assert backend.roles.count(AgentRole.REVIEW.value) == 4


def test_trace_gate_failure_escalates_without_dod_met(tmp_path: Path) -> None:
    backend = _ScriptedBackend(review_scripts=[_clean_review()])
    driver = driver_fixture(tmp_path, backend=backend, trace_ok=False)

    result = driver.run(task_fixture(tmp_path))

    assert result.outcome == "escalated"
    assert result.dod_met is False
    stages = [event.extra["governed_execution"]["stage_id"] for event in result.events]
    assert "handoff" not in stages
    assert "canonical-gates" in stages


def test_campaign_regression_feedback_reaches_the_fixer(tmp_path: Path) -> None:
    # A deterministic regression (test_b passed in the baseline, fails after DEV)
    # must drive a fixer pass -- it is not silently escalated on the first
    # finding. The fixer's DEV prompt carries the regression id as feedback.
    campaign, _ = campaign_fixture(
        baseline_passed=("tests/test_x.py::test_a", "tests/test_x.py::test_b"),
        after_failed=("tests/test_x.py::test_b",),
    )
    backend = _ScriptedBackend(review_scripts=[_clean_review(), _clean_review()])
    driver = driver_fixture(
        tmp_path, backend=backend, campaign=campaign, max_fixer_iterations=2
    )

    result = driver.run(task_fixture(tmp_path))

    # A sustained regression legally exhausts the budget and escalates AFTER the
    # fixer got the feedback -- it must not escalate before the fixer ran.
    stages = [event.extra["governed_execution"]["stage_id"] for event in result.events]
    assert "fixer" in stages
    assert result.outcome == "escalated"
    assert result.events[-1].extra["governed_execution"]["state"] == "needs_input"
    # The regression feedback reached the fixer DEV prompt verbatim.
    assert backend.dev_prompts and "tests/test_x.py::test_b" in "\n".join(
        backend.dev_prompts
    )


def test_budget_exhaustion_pauses_on_needs_input(tmp_path: Path) -> None:
    backend = _ScriptedBackend(review_scripts=[_finding_review()])
    driver = driver_fixture(tmp_path, backend=backend, max_fixer_iterations=1)

    result = driver.run(task_fixture(tmp_path))

    assert result.outcome == "escalated"
    assert result.dod_met is False
    assert result.events[-1].extra["governed_execution"]["state"] == "needs_input"
    assert len(result.events[-1].extra["governed_execution"]["request_sha256"]) == 64


def test_block_decision_keeps_escalated_and_writes_no_deferral(tmp_path: Path) -> None:
    backend = _ScriptedBackend(review_scripts=[_finding_review()])
    deferrals = _RecordingDeferrals()
    driver = driver_fixture(
        tmp_path, backend=backend, max_fixer_iterations=1, deferrals=deferrals
    )

    result = driver.run(task_fixture(tmp_path))
    request_sha256 = result.events[-1].extra["governed_execution"]["request_sha256"]

    resumed = driver.resume(
        task_fixture(tmp_path),
        request_sha256=request_sha256,
        decision="block",
        response="human block",
        decided_by="human",
    )

    assert resumed.outcome == "escalated"
    assert resumed.dod_met is False
    assert deferrals.writes == []


def test_defer_decision_writes_a_real_deferral(tmp_path: Path) -> None:
    backend = _ScriptedBackend(review_scripts=[_finding_review()])
    deferrals = _RecordingDeferrals()
    driver = driver_fixture(
        tmp_path, backend=backend, max_fixer_iterations=1, deferrals=deferrals
    )

    result = driver.run(task_fixture(tmp_path))
    request_sha256 = result.events[-1].extra["governed_execution"]["request_sha256"]

    resumed = driver.resume(
        task_fixture(tmp_path),
        request_sha256=request_sha256,
        decision="defer",
        response="defer to next cycle",
        decided_by="human",
    )

    assert resumed.outcome == "escalated"
    assert resumed.dod_met is False
    assert deferrals.writes and deferrals.writes[-1]["reason"] == "defer to next cycle"
    assert deferrals.writes[-1]["decided_by"] == "human"


def test_retry_then_block_resolves_through_human_decisions(tmp_path: Path) -> None:
    backend = _ScriptedBackend(review_scripts=[_finding_review()])
    driver = driver_fixture(tmp_path, backend=backend, max_fixer_iterations=1)

    result = driver.run(task_fixture(tmp_path))
    assert result.events[-1].extra["governed_execution"]["state"] == "needs_input"
    request_sha256 = result.events[-1].extra["governed_execution"]["request_sha256"]

    # A real human issues one retry: the driver runs again and, still unable to
    # catch a clean cycle under the fixed budget, pauses again for a decision.
    result = driver.resume(
        task_fixture(tmp_path),
        request_sha256=request_sha256,
        decision="retry",
        response="retry once",
        decided_by="human",
    )
    assert result.outcome == "escalated"
    assert result.events[-1].extra["governed_execution"]["state"] == "needs_input"

    request_sha256 = result.events[-1].extra["governed_execution"]["request_sha256"]
    result = driver.resume(
        task_fixture(tmp_path),
        request_sha256=request_sha256,
        decision="block",
        response="enough",
        decided_by="human",
    )
    assert result.outcome == "escalated"
    assert result.dod_met is False


def test_pre_existing_validation_failure_records_a_failing_validation_event(
    tmp_path: Path,
) -> None:
    # SR-049 evidence-integrity: when run_validation returns NodeOutcome.FAIL,
    # the journaled validation stage and its recorded NodeEvent must reflect the
    # real fail -- not a spurious pass -- even though the task then escalates to
    # the human. This mirrors _dev_cycle folding d_ev.result into the dev event.
    backend = _ScriptedBackend(review_scripts=[_finding_review()])
    gate_plan = gate_plan_fixture()
    contract = contract_fixture(tmp_path, gate_plan)
    execution = execution_fixture(tmp_path)
    campaign, _ = campaign_fixture()

    driver = GovernedExecutionDriver(
        execution=execution,
        gate_plan=gate_plan,
        contract_factory=lambda: contract,
        backend_factory=lambda workspace: backend,  # noqa: ANN001
        gates=_ValidationFailingGate(),
        campaign=campaign,
        transport=ExecutionTransport.for_transport("direct"),
        manifest={"context": {"source_files": []}},
        repo_root=tmp_path,
        transcript_dir=tmp_path / "transcripts",
        max_fixer_iterations=2,
    )

    result = driver.run(task_fixture(tmp_path))

    assert result.outcome == "escalated"
    validation_event = next(
        e for e in result.events if e.node == "validation"
    )
    # The recorded validation event must carry the failing gate's outcome
    # ("fail"), not the unconditional pass the stage was journaled with -- the
    # dev-pattern fold the driver already applies to its own dev event.
    assert validation_event.result == "fail"


def test_pre_existing_validation_failure_is_surfaced_not_auto_fixed(
    tmp_path: Path,
) -> None:
    backend = _ScriptedBackend(review_scripts=[_finding_review()])
    gate_plan = gate_plan_fixture()
    contract = contract_fixture(tmp_path, gate_plan)
    execution = execution_fixture(tmp_path)
    campaign, _ = campaign_fixture()
    deferrals = _RecordingDeferrals()

    driver = GovernedExecutionDriver(
        execution=execution,
        gate_plan=gate_plan,
        contract_factory=lambda: contract,
        backend_factory=lambda workspace: backend,  # noqa: ANN001
        gates=_ValidationFailingGate(),
        campaign=campaign,
        transport=ExecutionTransport.for_transport("direct"),
        manifest={"context": {"source_files": []}},
        repo_root=tmp_path,
        transcript_dir=tmp_path / "transcripts",
        max_fixer_iterations=2,
        deferrals=deferrals,
    )

    result = driver.run(task_fixture(tmp_path))

    # A pre-existing validation failure pauses for a human; it is never auto-fixed
    # as if it were a regression introduced by the change.
    assert result.outcome == "escalated"
    assert result.dod_met is False
    assert result.events[-1].extra["governed_execution"]["state"] == "needs_input"
    # No DEV pass followed the validation failure.
    assert backend._dev_count == 1

# -- nodes/runner integration seams (Task 5 Modifies) --------------------------


def test_run_canonical_gates_passes_when_both_checks_are_green() -> None:
    from factory.orchestrator.nodes import run_canonical_gates

    def _ok() -> None:
        return None

    outcome, ev = run_canonical_gates(_ok, _ok)
    assert outcome == NodeOutcome.PASS
    assert ev.node == "canonical-gates"
    assert ev.result == "pass"


def test_run_canonical_gates_fails_closed_on_a_trace_failure() -> None:
    from factory.orchestrator.execution_driver import CanonicalGateError
    from factory.orchestrator.nodes import run_canonical_gates

    def _bad() -> None:
        raise CanonicalGateError("trace is broken")

    outcome, ev = run_canonical_gates(_bad, lambda: None)
    assert outcome == NodeOutcome.ESCALATE
    assert ev.result == "fail"
    assert "trace is broken" in ev.extra["reason"]


def test_run_governed_task_resolves_budget_and_fails_closed_without_factory(
    tmp_path: Path,
) -> None:
    from factory.config import FactoryConfig
    from factory.orchestrator.runner import run_governed_task

    cfg = FactoryConfig(
        playgrounds={}, harnesses={}, gates={},
    )
    cfg.governed_execution = type(cfg.governed_execution)(max_fixer_iterations=2)  # type: ignore[Assignment]

    # No driver factory -> fail closed (the facade needs the wiring closure).
    with pytest.raises(ValueError, match="driver_factory"):
        run_governed_task(
            task_fixture(tmp_path),
            _ScriptedBackend(review_scripts=[_clean_review()]),  # type: ignore[arg-type]
            _NoopGate(),
            tmp_path,
            cfg=cfg,
        )


def test_run_governed_task_invokes_the_wired_driver(tmp_path: Path) -> None:
    from factory.config import FactoryConfig, GovernedExecutionConfig
    from factory.orchestrator.runner import run_governed_task

    cfg = FactoryConfig(playgrounds={}, harnesses={}, gates={})
    cfg.governed_execution = GovernedExecutionConfig(max_fixer_iterations=2)
    budget_used: list[int] = []

    def _factory(**kw):  # noqa: ANN001
        budget_used.append(kw["max_fixer_iterations"])
        return driver_fixture(tmp_path, backend=kw["backend"]).run(kw["task"])

    result = run_governed_task(
        task_fixture(tmp_path),
        _ScriptedBackend(review_scripts=[_clean_review()]),
        _NoopGate(),
        tmp_path,
        cfg=cfg,
        driver_factory=_factory,
    )

    assert budget_used == [2]
    assert result.outcome == "completed"
    assert result.dod_met is True
