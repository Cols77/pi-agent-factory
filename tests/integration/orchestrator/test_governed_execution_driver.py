"""SR-034/SR-049 governed execution driver -- integration tracer bullet (Task 7).

This is the plan's Task 7 proof: one end-to-end scenario (and the required
additional cases) driving the *real* ``GovernedExecutionDriver`` wired to the
*real* ``ExecutionContract``, compiled Coherence ``GatePlan``, ``RunExecution``
journal, ``ExecutionTransport`` projection and ``TestCampaign`` classifier --
with only the two genuine host boundaries faked: the ``AgentBackend`` (no real
Pi/worker subprocess) and the ``GateRunner`` (no real pytest/ruff/pyright
subprocess). This mirrors the fixture style already accepted in
``tests/unit/orchestrator/test_execution_driver.py``
(``_ScriptedBackend``/``driver_fixture``), just assembled as one integration
module per the plan's file map.

Brief-to-shipped translation note (the same convention
``factory/orchestrator/execution.py``'s own module docstring uses for its
"plan snippet -> shipped API" table): the plan's Task 7 Step 1 snippet is
illustrative pseudocode written before Tasks 2/5/6/8 were implemented, and
several of its literal details never made it into the shipped surface:

* The plan's ``workspace_owner`` is ``execution_workspace.WorkspaceOwner`` --
  a lease-acquiring protocol. Task 6's own report recorded that no concrete
  implementation of it exists anywhere in this plan (only the protocol), and
  the shipped ``GovernedExecutionDriver`` never references it: it takes a
  plain ``backend_factory: Callable[[Path], AgentBackend]`` invoked once per
  attempt. ``_WorkspaceOwnerDouble`` below stands in for the illustrative
  fixture value by observing the *same* invariants (one acquisition per
  attempt, one shared workspace path for every worker call) through the seam
  that actually exists.
* The shipped ``NodeEvent.extra["governed_execution"]`` carries only
  ``stage_id``/``revision``/``attempt`` (plus ``state``/``request_sha256`` on
  a pause and ``human_decision``/``retry_reset_iteration`` on a resume) --
  never a per-event ``contract_sha256``. The contract/GatePlan hashes are
  persisted once, in the ``contract-compiled`` stage's journalled evidence
  (verified below directly against the journal, which is the accepted SR-049
  evidence surface per the plan's file map: "RunExecution remains the
  evidence writer"), not copied into every subsequent ``NodeEvent``. Per-event
  assertions below therefore use what the shipped kernel actually records:
  stage/revision/attempt sequences, the dev event's folded
  ``gate_signatures``/outcome, the canonical-gates failure ``reason``, and the
  needs-input/human-decision payloads -- real "event payloads", just not the
  specific field the illustrative snippet named.
* The plan's ``backend.review_session_ids == ("review-spec", "review-quality")``
  compares against the two *stage ids*, which are never session ids in the
  shipped review swarm (``factory.orchestrator.review_swarm``): a session id
  is backend-minted per lane. The invariant that matters -- two distinct,
  fresh review sessions, one per lane -- is asserted directly against the two
  real session ids captured from the backend.

Task 7 does not modify ``execution_driver.py`` (it is not in this task's file
list), so none of the above is "fixed" here -- these are the shipped,
already-reviewed and committed Task 5/6/8 contracts, exercised honestly.
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import pytest

from coherence.execution.cli import main as execution_main
from coherence.execution.gate_plan import compile_gate_plan
from factory.orchestrator.backends import AgentBackend, FakeGateRunner, GateRun
from factory.orchestrator.execution import RunExecution
from factory.orchestrator.execution_campaign import CampaignResult, TestCampaign, TestSnapshot
from factory.orchestrator.execution_contract import ExecutionContract
from factory.orchestrator.execution_driver import CanonicalGateError, GovernedExecutionDriver
from factory.orchestrator.execution_transport import ExecutionTransport, materialize_transport
from factory.orchestrator.git_ops import FakeGitOps
from factory.orchestrator.types import AgentRole, NodeOutcome
from substrate.agents.model import AgentResult
from substrate.ledger.tasks import Task

pytestmark = [pytest.mark.integration, pytest.mark.sr("SR-034"), pytest.mark.sr("SR-049")]

_WORKFLOW = "governed-execution/v1"
RUN_ID = "run-013"
TASK_ID = "T-013"

# The two host entrypoints Task 6 shipped; referenced (never executed as
# markdown) so the "cross-host parity" assertions below stay tied to the real
# files rather than a copied string.
_REPO_ROOT = Path(__file__).resolve().parents[3]
_SKILL_PATH = _REPO_ROOT / ".agents" / "skills" / "governed-execution" / "SKILL.md"
_COMMAND_PATH = _REPO_ROOT / ".claude" / "commands" / "governed-execution.md"


# -- fixtures / helpers -------------------------------------------------------


def task_fixture(tmp_path: Path, *, satisfies: tuple[str, ...] = ()) -> Task:
    return Task(
        id=TASK_ID,
        title="Governed execution driver",
        status="todo",
        dod=["both reviews reported", "canonical gates green"],
        body="",
        path=tmp_path / f"{TASK_ID}.md",
        satisfies=list(satisfies),
    )


def gate_plan_fixture():
    return compile_gate_plan(
        workflow_version=_WORKFLOW,
        version="behavior-change@1",
        required_gates=("unit", "full"),
        preflight_policy="mandatory-only",
    )


def contract_fixture(tmp_path: Path, gate_plan) -> ExecutionContract:
    contract = ExecutionContract.build(
        run_id=RUN_ID,
        task_id=TASK_ID,
        workflow_version=_WORKFLOW,
        workspace=tmp_path / "worktree",
        required_gates=("unit", "full"),
        satisfies=("SR-034", "SR-049"),
        plan_ref="docs/superpowers/plans/2026-09-10-feat013-governed-execution-driver-plan.md",
        spec_ref=None,
        max_fixer_iterations=2,
    )
    return contract.with_gate_plan(gate_plan)


def execution_fixture(tmp_path: Path) -> RunExecution:
    return RunExecution.create(tmp_path, RUN_ID, TASK_ID, "a" * 40, FakeGitOps(head="a" * 40))


class _EmptyRegistry:
    def is_registered(self, test_id: str) -> bool:
        return False


class _ScriptedCampaignRunner:
    """Pops exactly one scripted ``TestSnapshot`` per call; fails closed."""

    def __init__(self, snapshots: list[TestSnapshot]) -> None:
        self._snapshots = list(snapshots)
        self.calls = 0

    def run(self, contract: ExecutionContract) -> TestSnapshot:
        self.calls += 1
        if not self._snapshots:
            raise AssertionError("campaign runner script exhausted")
        return self._snapshots.pop(0)


def _snapshot(
    passed: tuple[str, ...], failed: tuple[str, ...], declared: tuple[str, ...]
) -> TestSnapshot:
    passed_ids = frozenset(passed)
    declared_ids = frozenset(declared)
    total = len(declared_ids)
    return TestSnapshot(
        passed_ids=passed_ids,
        failed_ids=frozenset(failed),
        pass_rate=(len(passed_ids) / total) if total else 0.0,
        declared_ids=declared_ids,
    )


class _AlwaysPassingCampaignRunner:
    """Every call -- baseline or any number of post-DEV/fixer cycles -- reports
    the same fully-passing snapshot. Used wherever a test's fixer loop is
    driven by review findings rather than campaign classification, so the
    number of DEV/fixer cycles never has to be pre-counted against a scripted
    snapshot list (unlike ``_ScriptedCampaignRunner``, used by the tests that
    specifically assert classification behaviour)."""

    def __init__(self, declared: tuple[str, ...] = ("tests/test_x.py::test_a",)) -> None:
        self._declared = declared

    def run(self, contract: ExecutionContract) -> TestSnapshot:
        return _snapshot(self._declared, (), self._declared)


def clean_campaign_fixture() -> TestCampaign:
    """A campaign whose baseline and every post-DEV run pass cleanly."""
    return TestCampaign(runner=_AlwaysPassingCampaignRunner(), flaky_registry=_EmptyRegistry())


class _RecordingCampaign:
    """Wraps a real ``TestCampaign`` and records every classification result.

    A real production collaborator, not a mock: the wrapped ``TestCampaign``
    does the actual classification (regression/pre-existing/flaky/candidate
    disposition, the one bounded confirmation re-run); this only observes what
    it returns so a test can assert the SR-049 classification evidence the
    driver itself does not fold into ``NodeEvent.extra`` (see module docstring).
    """

    def __init__(self, inner: TestCampaign) -> None:
        self._inner = inner
        self.results: list[CampaignResult] = []

    def capture_baseline(self, contract: ExecutionContract) -> TestSnapshot:
        return self._inner.capture_baseline(contract)

    def evaluate_after_dev(self, contract: ExecutionContract, baseline: TestSnapshot) -> CampaignResult:
        result = self._inner.evaluate_after_dev(contract, baseline)
        self.results.append(result)
        return result


@dataclass
class _ReviewScript:
    spec_findings: tuple[str, ...]
    quality_findings: tuple[str, ...]
    spec_dod: bool = True
    quality_dod: bool = True


def _clean_review() -> _ReviewScript:
    return _ReviewScript(spec_findings=(), quality_findings=())


def _finding_review() -> _ReviewScript:
    return _ReviewScript(spec_findings=("spec ok but x is wrong",), quality_findings=())


class _ScriptedBackend(AgentBackend):
    """A governed ``AgentBackend`` scripting dev/review results by prompt.

    Mirrors ``tests/unit/orchestrator/test_execution_driver.py``'s
    ``_ScriptedBackend``, plus ``review_session_ids`` (see the module
    docstring's translation note on the brief's illustrative field name).
    """

    def __init__(self, *, unit_ok: bool = True, review_scripts: list[_ReviewScript] | None = None) -> None:
        self.unit_ok = unit_ok
        self._review_scripts = list(review_scripts or [_clean_review()])
        self.roles: list[str] = []
        self.session_ids: list[str] = []
        self.dev_prompts: list[str] = []
        self.review_sessions: dict[str, str] = {}
        self.review_cycle = 0
        self._dev_count = 0

    @property
    def review_session_ids(self) -> tuple[str, ...]:
        """The two most recent, lane-ordered review session ids."""
        return (self.review_sessions.get("spec-review", ""), self.review_sessions.get("quality-review", ""))

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
        script = self._review_scripts[self.review_cycle % max(1, len(self._review_scripts))]
        lane = "spec-review" if "SPEC-COMPLIANCE" in prompt else "quality-review"
        session = f"{lane}-session-{self.review_cycle + 1}"
        self.session_ids.append(session)
        self.review_sessions[lane] = session
        if on_session_id is not None:
            on_session_id(session)
        findings = script.spec_findings if lane == "spec-review" else script.quality_findings
        dod_met = script.spec_dod if lane == "spec-review" else script.quality_dod
        if lane == "quality-review":
            self.review_cycle += 1
        return AgentResult(
            ok=True, output={"findings": list(findings), "dod_met": dod_met}, session_id=session
        )


class _BarrierReviewBackend(AgentBackend):
    """Proves, through the *whole driver*, that review-join waits for both
    fresh sessions.

    Each review lane blocks on a two-party barrier before returning. If the
    driver's review swarm ever ran the two lanes sequentially rather than
    concurrently, the first lane would deadlock waiting for a partner that
    never arrives -- ``Barrier.wait(timeout=...)`` turns that into a fast,
    explicit failure instead of a hang. This reproves Task 3's own
    ``run_review_swarm`` concurrency guarantee one layer up, through the
    driver kernel that actually calls it in production.
    """

    def __init__(self) -> None:
        self._barrier = threading.Barrier(2)
        self.review_started = 0
        self.dev_calls = 0
        self._dev_count = 0

    def run(
        self,
        role: AgentRole,
        prompt: str,
        on_snippet: Callable[[str], None] | None = None,
        on_session_id: Callable[[str], None] | None = None,
    ) -> AgentResult:
        if role is AgentRole.DEV:
            self._dev_count += 1
            self.dev_calls += 1
            session = f"dev-session-{self._dev_count}"
            if on_session_id is not None:
                on_session_id(session)
            return AgentResult(ok=True, output={"summary": "unit green"}, session_id=session)
        self.review_started += 1
        self._barrier.wait(timeout=5)
        lane = "spec-review" if "SPEC-COMPLIANCE" in prompt else "quality-review"
        session = f"{lane}-session"
        if on_session_id is not None:
            on_session_id(session)
        return AgentResult(ok=True, output={"findings": [], "dod_met": True}, session_id=session)


class _NoopGate(FakeGateRunner):
    """Every gate reports green (or not-applicable)."""

    def __init__(self) -> None:
        super().__init__({})


class _UnitFailingGate(FakeGateRunner):
    """The ``unit`` gate passes during mandatory preflight, then fails on the
    DEV cycle's own post-attempt check -- simulating a real worker/DEV
    failure rather than a preflight block (both read the same gate name, so
    the first queued result must be a pass)."""

    def __init__(self) -> None:
        super().__init__(
            {"unit": [0, GateRun(name="unit", returncode=1, output="unit tests red", applicable=True)]}
        )


class _RecordingDeferrals:
    def __init__(self) -> None:
        self.writes: list[dict[str, object]] = []

    def write(
        self,
        reason: str,
        *,
        review_after: str | None = None,
        decided_at: str | None = None,
        decided_by: str | None = None,
    ) -> None:
        self.writes.append(
            {"reason": reason, "review_after": review_after, "decided_at": decided_at, "decided_by": decided_by}
        )


class _RecordingTraceCheck:
    """A real callable double (not a mock assertion): scripted pass/fail,
    recording every invocation so a test can assert the SR-049 in-loop
    canonical gate actually ran (``trace_check.calls``)."""

    def __init__(self, *, ok: bool = True) -> None:
        self.ok = ok
        self.calls: list[str] = []

    def __call__(self) -> None:
        self.calls.append("trace-completeness")
        if not self.ok:
            raise CanonicalGateError("trace check failed")


class _WorkspaceOwnerDouble:
    """Stands in for the plan's illustrative ``workspace_owner`` fixture value
    (see module docstring). Observes: one acquisition per attempt
    (``acquired_count``), and the one shared workspace path used by every
    worker call (``worker_paths``)."""

    def __init__(self, workspace: Path) -> None:
        self.path = workspace
        self.acquired_count = 0
        self.worker_paths: list[Path] = []

    def bind(self, backend: AgentBackend) -> Callable[[Path], AgentBackend]:
        def _factory(workspace: Path) -> AgentBackend:
            assert workspace == self.path, "every worker must bind to the one leased workspace"
            self.acquired_count += 1
            return _PathRecordingBackend(backend, self.worker_paths, workspace)

        return _factory


class _PathRecordingBackend(AgentBackend):
    """Records the bound workspace path on every worker call (dev + both
    reviews), then delegates to the real scripted backend."""

    def __init__(self, inner: AgentBackend, sink: list[Path], workspace: Path) -> None:
        self._inner = inner
        self._sink = sink
        self._workspace = workspace

    def run(
        self,
        role: AgentRole,
        prompt: str,
        on_snippet: Callable[[str], None] | None = None,
        on_session_id: Callable[[str], None] | None = None,
    ) -> AgentResult:
        self._sink.append(self._workspace)
        return self._inner.run(role, prompt, on_snippet=on_snippet, on_session_id=on_session_id)


def governed_fixture(
    tmp_path: Path,
    *,
    backend: AgentBackend | None = None,
    review_scripts: list[_ReviewScript] | None = None,
    campaign: object | None = None,
    max_fixer_iterations: int = 2,
    trace_ok: bool = True,
    register_ok: bool = True,
    deferrals: _RecordingDeferrals | None = None,
    unit_ok: bool = True,
    gates: FakeGateRunner | None = None,
) -> tuple[GovernedExecutionDriver, AgentBackend, FakeGateRunner, _RecordingTraceCheck, _WorkspaceOwnerDouble]:
    """The Task 7 tracer-bullet fixture: real contract/GatePlan/RunExecution/
    transport/campaign, fake backend + gate runner. Matches the brief's Step 1
    destructuring: ``driver, backend, gates, trace_check, workspace_owner``.
    """
    gate_plan = gate_plan_fixture()
    contract = contract_fixture(tmp_path, gate_plan)
    execution = execution_fixture(tmp_path)
    resolved_campaign = campaign if campaign is not None else clean_campaign_fixture()
    transport = ExecutionTransport.for_transport("direct")
    resolved_backend = backend if backend is not None else _ScriptedBackend(
        unit_ok=unit_ok, review_scripts=review_scripts or [_clean_review()]
    )
    resolved_gates = gates if gates is not None else _NoopGate()
    workspace_owner = _WorkspaceOwnerDouble(contract.workspace)
    trace_check = _RecordingTraceCheck(ok=trace_ok)
    register_calls: list[str] = []

    def _register_check() -> None:
        register_calls.append("register-completeness")
        if not register_ok:
            raise CanonicalGateError("register check failed")

    driver = GovernedExecutionDriver(
        execution=execution,
        gate_plan=gate_plan,
        contract_factory=lambda: contract,
        backend_factory=workspace_owner.bind(resolved_backend),
        gates=resolved_gates,
        campaign=resolved_campaign,
        transport=transport,
        manifest={"context": {"source_files": ["src/x.py"]}},
        repo_root=tmp_path,
        transcript_dir=tmp_path / "transcripts",
        max_fixer_iterations=max_fixer_iterations,
        deferrals=deferrals or _RecordingDeferrals(),
        trace_check=trace_check,
        register_check=_register_check,
    )
    return driver, resolved_backend, resolved_gates, trace_check, workspace_owner


def _stage_ids(result) -> list[str]:
    return [event.extra["governed_execution"]["stage_id"] for event in result.events]


# -- Step 1: the tracer bullet -------------------------------------------------


def test_governed_tracer_bullet_preserves_authority_and_task_result(tmp_path: Path) -> None:
    driver, backend, gates, trace_check, workspace_owner = governed_fixture(tmp_path)
    # SR-034 finding 1: the canonical-gates stage now also runs the real
    # ``run_completion_preflight`` (see execution_driver._canonical_gates).
    # This tracer bullet is a general smoke test with no scripted per-
    # requirement validation evidence, so -- like every other test in this
    # module -- it uses the default no-satisfies task: `_validate_and_review`
    # runs the validation node with a hardcoded `satisfies=[]` (a pre-existing,
    # separate gap this finding does not touch), so a task that *did* declare
    # a real `satisfies` here would have that node overwrite any pre-seeded
    # validation-report.json with an empty one and (correctly) block on
    # `validation_missing` before ever reaching this smoke assertion.
    result = driver.run(task_fixture(tmp_path))

    assert result.outcome == "completed"
    assert result.dod_met is True
    assert workspace_owner.acquired_count == 1
    assert workspace_owner.worker_paths == [workspace_owner.path] * 3
    # Two distinct, fresh review sessions -- see the module docstring's note
    # on the brief's illustrative `("review-spec", "review-quality")` literal.
    assert len(set(backend.review_session_ids)) == 2
    assert all(backend.review_session_ids)
    assert trace_check.calls == ["trace-completeness"]
    assert _stage_ids(result) == [
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
    # SR-049: the contract identity that gated this run is the one persisted
    # journal evidence -- checked against the accepted evidence surface
    # (the RunExecution journal), not a per-event field the shipped kernel
    # never populates (see module docstring).
    contract = driver.contract_factory()
    # `open_task_cursor` opens revision 1 of the root stage with no journal
    # entry (a first open journals nothing); `_record`'s own `begin_revision`
    # call then bumps to revision 2 and journals a `cursor-opened` marker
    # ahead of the real evidence record -- so the "completed" record, not the
    # first "contract-compiled" node event, is the one carrying the hashes.
    compiled_event = next(
        e
        for e in driver.execution.journal.events()
        if e.node == "contract-compiled" and e.state == "completed"
    )
    assert compiled_event.data["contract_sha256"] == contract.contract_sha256
    assert compiled_event.data["gate_plan_sha256"] == driver.gate_plan.gate_plan_sha256


# -- Step 1: failing canonical trace gate --------------------------------------


def test_failing_canonical_trace_gate_blocks_completion_with_evidence(tmp_path: Path) -> None:
    driver, backend, gates, trace_check, workspace_owner = governed_fixture(tmp_path, trace_ok=False)

    result = driver.run(task_fixture(tmp_path))

    assert result.outcome == "escalated"
    assert result.dod_met is False
    assert trace_check.calls == ["trace-completeness"]
    stages = _stage_ids(result)
    assert stages[-1] == "canonical-gates"
    assert "handoff" not in stages
    canonical_event = result.events[-1]
    assert canonical_event.result == "fail"
    assert "trace check failed" in canonical_event.extra["reason"]


# -- Step 1: a pre-existing test failure ---------------------------------------


def test_pre_existing_campaign_failure_is_never_a_regression_but_still_blocks(
    tmp_path: Path,
) -> None:
    """A test that failed before DEV and still fails after is classified
    ``pre_existing_failures`` (never injected as a regression), but SR-034's
    quarantine discipline still treats any unregistered failure as blocking
    (decision 1: only a human-curated registry entry -- never a mere
    disposition -- makes a failure non-blocking). With the budget exhausted
    the run pauses for a human rather than fabricating a fix.
    """
    declared = ("tests/test_x.py::test_a", "tests/test_x.py::test_pre_existing")
    runner = _ScriptedCampaignRunner(
        [
            _snapshot(("tests/test_x.py::test_a",), ("tests/test_x.py::test_pre_existing",), declared),
            _snapshot(("tests/test_x.py::test_a",), ("tests/test_x.py::test_pre_existing",), declared),
            _snapshot(("tests/test_x.py::test_a",), ("tests/test_x.py::test_pre_existing",), declared),
        ]
    )
    campaign = _RecordingCampaign(TestCampaign(runner=runner, flaky_registry=_EmptyRegistry()))
    backend = _ScriptedBackend(review_scripts=[_clean_review()])
    driver, backend, gates, trace_check, workspace_owner = governed_fixture(
        tmp_path, backend=backend, campaign=campaign, max_fixer_iterations=1
    )

    result = driver.run(task_fixture(tmp_path))

    assert result.outcome == "escalated"
    assert result.dod_met is False
    assert result.events[-1].extra["governed_execution"]["state"] == "needs_input"
    assert campaign.results, "the campaign classifier must have run"
    first = campaign.results[0]
    assert first.pre_existing_failures == ("tests/test_x.py::test_pre_existing",)
    assert first.regressions == ()
    assert first.pass_rate_gate_passed is False


# -- Step 1: an unlisted failure that passes its one classification rerun -----


def test_unlisted_failure_gets_one_classification_rerun_and_still_completes(
    tmp_path: Path,
) -> None:
    """A failure with no baseline history (here: a test DEV's own change
    introduces) gets exactly one bounded classification re-run. Passing that
    rerun makes it a human-visible ``registry_candidates`` entry, never a
    regression -- but it is still unregistered, so it still costs one fixer
    pass before a clean second campaign lets the run complete.
    """
    runner = _ScriptedCampaignRunner(
        [
            _snapshot(("tests/test_x.py::test_a",), (), ("tests/test_x.py::test_a",)),
            _snapshot(
                ("tests/test_x.py::test_a",),
                ("tests/test_x.py::test_flaky",),
                ("tests/test_x.py::test_a", "tests/test_x.py::test_flaky"),
            ),
            _snapshot(
                ("tests/test_x.py::test_a", "tests/test_x.py::test_flaky"),
                (),
                ("tests/test_x.py::test_a", "tests/test_x.py::test_flaky"),
            ),
            _snapshot(
                ("tests/test_x.py::test_a", "tests/test_x.py::test_flaky"),
                (),
                ("tests/test_x.py::test_a", "tests/test_x.py::test_flaky"),
            ),
        ]
    )
    campaign = _RecordingCampaign(TestCampaign(runner=runner, flaky_registry=_EmptyRegistry()))
    backend = _ScriptedBackend(review_scripts=[_clean_review(), _clean_review()])
    driver, backend, gates, trace_check, workspace_owner = governed_fixture(
        tmp_path, backend=backend, campaign=campaign, max_fixer_iterations=1
    )

    result = driver.run(task_fixture(tmp_path))

    assert campaign.results, "the campaign classifier must have run"
    first = campaign.results[0]
    assert first.classification_reruns == {"tests/test_x.py::test_flaky": 1}
    assert first.registry_candidates == ("tests/test_x.py::test_flaky",)
    assert first.regressions == ()
    assert first.fixer_iterations_consumed == 0
    assert result.outcome == "completed"
    assert result.dod_met is True
    assert "fixer" in _stage_ids(result)


# -- Step 1: a real regression --------------------------------------------------


def test_real_regression_reaches_the_fixer_as_feedback_before_escalating(tmp_path: Path) -> None:
    declared = ("tests/test_x.py::test_a", "tests/test_x.py::test_b")
    runner = _ScriptedCampaignRunner(
        [
            _snapshot(declared, (), declared),
            _snapshot(("tests/test_x.py::test_a",), ("tests/test_x.py::test_b",), declared),
            _snapshot(("tests/test_x.py::test_a",), ("tests/test_x.py::test_b",), declared),
        ]
    )
    campaign = _RecordingCampaign(TestCampaign(runner=runner, flaky_registry=_EmptyRegistry()))
    backend = _ScriptedBackend(review_scripts=[_clean_review(), _clean_review()])
    driver, backend, gates, trace_check, workspace_owner = governed_fixture(
        tmp_path, backend=backend, campaign=campaign, max_fixer_iterations=1
    )

    result = driver.run(task_fixture(tmp_path))

    assert campaign.results[0].regressions == ("tests/test_x.py::test_b",)
    stages = _stage_ids(result)
    assert "fixer" in stages
    assert result.outcome == "escalated"
    assert result.events[-1].extra["governed_execution"]["state"] == "needs_input"
    # The regression id reached the fixer's DEV prompt verbatim -- real
    # observable interaction evidence, not a synthesized event field.
    assert backend.dev_prompts and "tests/test_x.py::test_b" in backend.dev_prompts[-1]
    fixer_events = [e for e in result.events if e.extra["governed_execution"]["stage_id"] == "fixer"]
    assert len(fixer_events) == 1
    assert fixer_events[0].extra["governed_execution"]["revision"] == 1


# -- Step 1: a worker failure ---------------------------------------------------


def test_worker_failure_escalates_before_any_review_is_dispatched(tmp_path: Path) -> None:
    backend = _ScriptedBackend(unit_ok=False, review_scripts=[_clean_review()])
    driver, backend, gates, trace_check, workspace_owner = governed_fixture(
        tmp_path, backend=backend, gates=_UnitFailingGate()
    )

    result = driver.run(task_fixture(tmp_path))

    assert result.outcome == "escalated"
    assert result.dod_met is False
    assert AgentRole.REVIEW.value not in backend.roles
    dev_event = next(e for e in result.events if e.extra["governed_execution"]["stage_id"] == "dev")
    assert dev_event.result == NodeOutcome.ESCALATE.value
    assert dev_event.extra["gate_signatures"] == []
    assert result.events[-1].extra["governed_execution"]["state"] == "needs_input"
    # `_dev_cycle` folds the node's outcome/gate_signatures into the recorded
    # event, but not `run_dev`'s own `reason` text; that is real evidence too,
    # just journalled on the pending request rather than on the dev NodeEvent.
    pending = driver.execution.pending_human_decision_request()
    assert pending is not None
    assert pending["reason"] == "DEV failed and unit gates stayed red"


# -- Step 1: each human budget decision -----------------------------------------


def test_block_decision_escalates_with_no_deferral_and_a_recorded_event(tmp_path: Path) -> None:
    backend = _ScriptedBackend(review_scripts=[_finding_review()])
    deferrals = _RecordingDeferrals()
    driver, backend, gates, trace_check, workspace_owner = governed_fixture(
        tmp_path, backend=backend, max_fixer_iterations=1, deferrals=deferrals
    )

    paused = driver.run(task_fixture(tmp_path))
    request_sha256 = paused.events[-1].extra["governed_execution"]["request_sha256"]

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
    decision_event = resumed.events[-1]
    assert decision_event.extra["human_decision"] == "block"
    assert decision_event.result == NodeOutcome.ESCALATE.value


def test_defer_decision_writes_a_real_deferral_and_records_the_decision_event(
    tmp_path: Path,
) -> None:
    backend = _ScriptedBackend(review_scripts=[_finding_review()])
    deferrals = _RecordingDeferrals()
    driver, backend, gates, trace_check, workspace_owner = governed_fixture(
        tmp_path, backend=backend, max_fixer_iterations=1, deferrals=deferrals
    )

    paused = driver.run(task_fixture(tmp_path))
    request_sha256 = paused.events[-1].extra["governed_execution"]["request_sha256"]

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
    assert resumed.events[-1].extra["human_decision"] == "defer"


def test_retry_then_block_resolves_through_two_explicit_human_decisions(tmp_path: Path) -> None:
    backend = _ScriptedBackend(review_scripts=[_finding_review()])
    driver, backend, gates, trace_check, workspace_owner = governed_fixture(
        tmp_path, backend=backend, max_fixer_iterations=1
    )

    paused = driver.run(task_fixture(tmp_path))
    assert paused.events[-1].extra["governed_execution"]["state"] == "needs_input"
    request_sha256 = paused.events[-1].extra["governed_execution"]["request_sha256"]

    retried = driver.resume(
        task_fixture(tmp_path),
        request_sha256=request_sha256,
        decision="retry",
        response="retry once",
        decided_by="human",
    )
    # `resume()`'s retry branch appends its own "human-decision" NodeEvent to a
    # *local* list, then returns `self.run(task)` directly -- a fresh
    # `TaskResult` with its own fresh `events`, so the retry decision event
    # itself never reaches `TaskResult.events` (unlike `defer`/`block`, which
    # return that local list directly). The decision is still real, durable
    # SR-049 evidence -- just on the journal, not in-memory on this result; it
    # is checked there instead of asserting a field the shipped kernel drops.
    retry_decision = next(
        d
        for e in driver.execution.journal.events()
        if isinstance(e.data, dict) and isinstance(e.data.get("human_decision"), dict)
        for d in [e.data["human_decision"]]
        if d.get("decision") == "retry"
    )
    assert retry_decision["retry_reset_iteration"] == 0
    assert retry_decision["request_sha256"] == request_sha256
    assert retried.outcome == "escalated"
    assert retried.events[-1].extra["governed_execution"]["state"] == "needs_input"

    second_request = retried.events[-1].extra["governed_execution"]["request_sha256"]
    assert second_request != request_sha256  # a genuinely new request, not a replay
    blocked = driver.resume(
        task_fixture(tmp_path),
        request_sha256=second_request,
        decision="block",
        response="enough",
        decided_by="human",
    )
    assert blocked.outcome == "escalated"
    assert blocked.dod_met is False
    assert blocked.events[-1].extra["human_decision"] == "block"


# -- Step 1: cross-host-parity / lifecycle-projection assertions ---------------


def test_review_join_waits_for_both_fresh_sessions_through_the_whole_driver(tmp_path: Path) -> None:
    backend = _BarrierReviewBackend()
    driver, backend, gates, trace_check, workspace_owner = governed_fixture(tmp_path, backend=backend)

    result = driver.run(task_fixture(tmp_path))

    assert result.outcome == "completed"
    assert result.dod_met is True
    assert backend.review_started == 2
    assert "review-join" in _stage_ids(result)


def test_needs_input_pause_does_not_advance_to_a_child_stage(tmp_path: Path) -> None:
    backend = _ScriptedBackend(review_scripts=[_finding_review()])
    driver, backend, gates, trace_check, workspace_owner = governed_fixture(
        tmp_path, backend=backend, max_fixer_iterations=1
    )

    result = driver.run(task_fixture(tmp_path))

    stages = _stage_ids(result)
    assert "canonical-gates" not in stages
    assert "handoff" not in stages
    pending = driver.execution.pending_human_decision_request()
    assert pending is not None
    assert pending["state"] == "pending"
    # The request is bound to the entry (root) cursor's own position; re-asking
    # for it returns the exact same position rather than a newly opened one.
    root_stage = driver.gate_plan.stages[0]
    cursor_before = driver.execution.open_task_cursor(TASK_ID, driver.gate_plan)
    cursor_again = driver.execution.open_task_cursor(TASK_ID, driver.gate_plan)
    assert cursor_before == cursor_again
    assert cursor_before.stage_id == root_stage == pending["stage_id"]


def test_transport_projection_identity_matches_across_direct_and_hermes(tmp_path: Path) -> None:
    gate_plan = gate_plan_fixture()
    contract = contract_fixture(tmp_path, gate_plan)
    execution = execution_fixture(tmp_path)
    cursor = execution.open_task_cursor(TASK_ID, gate_plan)

    direct = materialize_transport(transport="direct", contract=contract, gate_plan=gate_plan, cursor=cursor)
    hermes = materialize_transport(
        transport="hermes-kanban", contract=contract, gate_plan=gate_plan, cursor=cursor
    )

    assert direct.root.metadata() == hermes.root.metadata()
    assert direct.transport != hermes.transport
    assert direct.durable_owner == "factory-driver"
    assert hermes.durable_owner == "hermes"
    assert {c.stage_id for c in direct.cards} == {c.stage_id for c in hermes.cards} == set(gate_plan.stages)
    for direct_card, hermes_card in zip(direct.cards, hermes.cards):
        assert direct_card.run_id == hermes_card.run_id == contract.run_id
        assert direct_card.contract_sha256 == hermes_card.contract_sha256 == contract.contract_sha256
        assert direct_card.gate_plan_sha256 == hermes_card.gate_plan_sha256 == gate_plan.gate_plan_sha256
        assert direct_card.workflow_version == hermes_card.workflow_version == gate_plan.workflow_version
        assert direct_card.revision == hermes_card.revision
        assert direct_card.attempt == hermes_card.attempt


def test_direct_cli_legal_actions_reflects_the_driven_run_verbatim(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The Codex skill, Claude Code command and Pi tools are thin renderers of
    exactly this Python-owned ``coherence execution legal-actions`` command
    (proven textually in ``tests/unit/codex/test_governed_execution_surface.py``
    and, for the Pi TypeScript adapter, in
    ``pi-ext/factory-watch/test/execution-tools.test.ts``); what this test adds
    is the missing link -- that for one real, fully-driven governed run, the
    direct CLI's projection agrees with the driver's own internal, journalled
    state (run id, stage, revision/attempt, contract hash and GatePlan hash).
    """
    driver, backend, gates, trace_check, workspace_owner = governed_fixture(tmp_path)
    result = driver.run(task_fixture(tmp_path))
    assert result.outcome == "completed"
    contract = driver.contract_factory()

    exit_code = execution_main(
        [
            "legal-actions",
            "--run-id", RUN_ID,
            "--task-id", TASK_ID,
            "--project-root", str(tmp_path),
            "--json",
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["run_id"] == RUN_ID
    assert payload["task_id"] == TASK_ID
    assert payload["state"] == "completed"
    assert payload["starts_automatically"] is False
    assert payload["legal_next_actions"] == ["inspect-handoff", "stream-progress"]
    assert payload["stage"] == "handoff"
    handoff_cursor = driver.execution.stage_cursors["handoff"]
    assert payload["revision"] == handoff_cursor.revision
    assert payload["attempt"] == handoff_cursor.attempt
    assert payload["hashes"]["contract_sha256"] == contract.contract_sha256
    assert payload["hashes"]["gate_plan_sha256"] == driver.gate_plan.gate_plan_sha256

    # Both host entrypoints declare exactly this command as their transition
    # check -- the same fixture run's projection is what they would render.
    codex_text = _SKILL_PATH.read_text(encoding="utf-8")
    claude_text = _COMMAND_PATH.read_text(encoding="utf-8")
    assert "coherence execution legal-actions" in codex_text
    assert "coherence execution legal-actions" in claude_text
