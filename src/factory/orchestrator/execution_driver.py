"""SR-034/SR-049 bounded single-task governed execution driver.

Task 5's transition kernel. It wraps the *existing* nodes (``run_dev``,
``run_validation``), gates (``GateRunner``) and the SR-034/SR-049
infrastructure -- the immutable ``ExecutionContract``, the compiled Coherence
``GatePlan`` and its transport projection, the ``TestCampaign`` baseline and
regression classifier, the fresh-context parallel review swarm, and the
journal-backed ``RunExecution`` stage cursor -- into one bounded
DEV -> parallel-review -> fixer-until-clean orchestration.

The driver is deliberately *not* a scheduler, supervisor, retry engine or
allocator. It drives one selected ``Task`` through the fixed canonical stage
graph (:data:`~coherence.execution.gate_plan.CANONICAL_EXECUTION_STAGES`),
records each stage as a :class:`NodeEvent` carrying a
``governed_execution.stage_id`` (SR-049 evidence), and returns the existing
:class:`TaskResult` shape. No gate is ever bypassed: the SR-049 in-loop
canonical trace/register/obligation check runs *before*
``TaskResult.dod_met`` can be ``True``.

The fixer budget is project-wide (SR-034 decision 3, 2026-09-11): at most
``max_fixer_iterations`` fresh fixer passes are spent automatically. When the
budget is exhausted and the work is still not clean, the driver pauses on a
durable ``needs_input`` request and returns an escalated ``TaskResult``; a human
must explicitly ``retry`` (one more attempt), ``defer`` (write a ``Deferral``)
or ``block`` (keep it escalated). No branch auto-accepts a review finding, and
no retry is automatic -- every iteration past the budget is human-issued.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol

from coherence.execution.gate_plan import GatePlan
from factory.orchestrator.backends import GATE_NOT_APPLICABLE, AgentBackend, GateRunner
from factory.orchestrator.execution import RunExecution
from factory.orchestrator.execution_campaign import TestCampaign
from factory.orchestrator.execution_contract import ExecutionContract
from factory.orchestrator.execution_transport import ExecutionTransport, validate_binding
from factory.orchestrator.nodes import run_dev, run_validation
from factory.orchestrator.review_swarm import ReviewSwarmResult, run_review_swarm
from factory.orchestrator.types import NodeEvent, NodeOutcome, TaskResult
from factory.preflight.checks import run_completion_preflight
from substrate.ledger.tasks import Task


class DriverBackendFactory(Protocol):
    """Produces one ``AgentBackend`` bound to a shared absolute workspace path.

    Distinct from, and NOT interchangeable with, ``execution_workspace.BackendFactory``
    (which ``.bind(lease, contract) -> BoundExecution``s a workspace-owned backend);
    the two protocols share no contract despite the historical name collision --
    see SR-034's final-review Finding 2/3. Reconciling them is out of scope here.
    """

    def __call__(self, workspace: Path) -> AgentBackend: ...


class ContractFactory(Protocol):
    """Builds the one immutable, GatePlan-bound ``ExecutionContract``."""

    def __call__(self) -> ExecutionContract: ...


class DeferralWriter(Protocol):
    """Persists one deliberate human deferral (the ``defer`` decision)."""

    def write(
        self,
        reason: str,
        *,
        review_after: str | None = None,
        decided_at: str | None = None,
        decided_by: str | None = None,
    ) -> None: ...


class CanonicalGateError(RuntimeError):
    """The in-loop SR-049 canonical trace/register/obligation gate failed."""


# The closed human-decision vocabulary the driver may request (never widened).
ALLOWED_DECISIONS: tuple[str, ...] = ("retry", "defer", "block")


class _NullDeferralWriter:
    """Fail-closed stand-in when no :class:`DeferralWriter` was injected."""

    def write(self, reason: str, **_: object) -> None:
        raise RuntimeError(
            "no DeferralWriter injected: a defer decision cannot be honoured"
        )


def _review_feedback(swarm: ReviewSwarmResult) -> str:
    """The joint reviewer finding text passed through ``run_dev(feedback=...)``."""
    lines: list[str] = []
    for review in swarm.reviews:
        if review.findings:
            lines.append(f"{review.lane}:")
            lines.extend(f"- {finding}" for finding in review.findings)
    return "\n".join(lines) if lines else ""


def _swarm_clean(swarm: ReviewSwarmResult) -> bool:
    """True only when every lane reported no findings and met its own dod."""
    return all(not review.findings and review.dod_met for review in swarm.reviews)


class GovernedExecutionDriver:
    """Bounded single-task governed driver around the existing nodes and gates.

    Every collaborator is injected through the keyword-only constructor so the
    kernel is testable with fakes and no undeclared collaborator is referenced at
    runtime. The driver drives one ``Task`` through the canonical stage graph and
    returns the existing :class:`TaskResult`.
    """

    def __init__(
        self,
        *,
        execution: RunExecution,
        gate_plan: GatePlan,
        contract_factory: ContractFactory,
        backend_factory: DriverBackendFactory,
        gates: GateRunner,
        campaign: TestCampaign,
        transport: ExecutionTransport,
        manifest: dict,
        repo_root: Path,
        transcript_dir: Path,
        max_fixer_iterations: int = 2,
        deferrals: DeferralWriter | None = None,
        trace_check: Callable[[], None] | None = None,
        register_check: Callable[[], None] | None = None,
        run_dev_seam: Callable[..., tuple[NodeOutcome, NodeEvent]] = run_dev,
    ) -> None:
        if max_fixer_iterations < 1:
            raise ValueError("max_fixer_iterations must be >= 1")
        self.execution = execution
        self.gate_plan = gate_plan
        self.contract_factory = contract_factory
        self.backend_factory = backend_factory
        self.gates = gates
        self.campaign = campaign
        self.transport = transport
        self.manifest = manifest
        self.repo_root = repo_root
        self.transcript_dir = transcript_dir
        self.max_fixer_iterations = max_fixer_iterations
        self.deferrals = deferrals if deferrals is not None else _NullDeferralWriter()
        self.trace_check = trace_check if trace_check is not None else (lambda: None)
        self.register_check = (
            register_check if register_check is not None else (lambda: None)
        )
        self._run_dev = run_dev_seam

    # -- evidence helpers -----------------------------------------------------

    def _record(
        self,
        events: list[NodeEvent],
        stage_id: str,
        *,
        state: str = "completed",
        data: dict[str, Any] | None = None,
        result: str = "pass",
    ) -> None:
        """Record one stage's governed evidence and append its ``NodeEvent``.

        The stage cursor is a first open (``begin_revision``) when the stage has
        not been visited yet, and the live cursor otherwise, so a fixer cycle can
        re-drive the prefix without re-bumping an already-recorded revision.

        Args:
            events: the run's accumulated ``NodeEvent`` list; appended in place.
            stage_id: a canonical stage id.
            state: the journaled stage record state (default ``completed``).
            data: the journaled stage-record payload.
            result: the ``NodeEvent.result`` string (default ``pass``).
        """
        cursor = self.execution.begin_revision(stage_id)
        advanced = self.execution.record_stage(
            cursor, state=state, data={**(data or {}), "stage": stage_id}
        )
        events.append(
            NodeEvent(
                stage_id,
                result,
                1,
                {
                    "governed_execution": {
                        "stage_id": stage_id,
                        "revision": advanced.revision,
                        "attempt": advanced.attempt,
                    }
                },
            )
        )

    def _result(
        self, events: list[NodeEvent], task: Task, outcome: str, *, dod_met: bool
    ) -> TaskResult:
        return TaskResult(
            task.id,
            task.title,
            outcome,
            len(events),
            events,
            dod_met,
            manifest=self.manifest,
        )

    def _request_human_decision(
        self,
        task: Task,
        events: list[NodeEvent],
        *,
        reason: str,
        finding_universe_sha256: str | None = None,
    ) -> TaskResult:
        """Pause on a durable ``needs_input`` request and return an escalated result."""
        cursor = self.execution.open_task_cursor(task.id, self.gate_plan)
        advanced, request = self.execution.open_human_decision_request(
            cursor,
            reason=reason,
            finding_universe_sha256=finding_universe_sha256,
            allowed_decisions=ALLOWED_DECISIONS,
        )
        events.append(
            NodeEvent(
                "needs-input",
                NodeOutcome.ESCALATE.value,
                1,
                {
                    "governed_execution": {
                        "stage_id": advanced.stage_id,
                        "revision": advanced.revision,
                        "attempt": advanced.attempt,
                        "state": "needs_input",
                        "request_sha256": request["request_sha256"],
                    }
                },
            )
        )
        return self._result(events, task, "escalated", dod_met=False)

    # -- sub-transitions ------------------------------------------------------

    def _run_preflight_cycle(self, events: list[NodeEvent], task: Task) -> TaskResult | None:
        """Compile + preflight + transport materialisation.

        Returns an escalated ``needs_input`` result on a mandatory-gate failure,
        or ``None`` to proceed.
        """
        contract = self.contract_factory()
        validate_binding(contract=contract, gate_plan=self.gate_plan)
        self.execution.open_task_cursor(task.id, self.gate_plan)
        self._record(
            events,
            "contract-compiled",
            data={
                "contract_sha256": contract.contract_sha256,
                "gate_plan_sha256": self.gate_plan.gate_plan_sha256,
                "workflow_version": contract.workflow_version,
            },
        )
        for gate in self.gate_plan.required_gates:
            if self.gates.run(gate) not in (0, GATE_NOT_APPLICABLE):
                return self._request_human_decision(
                    task, events, reason=f"mandatory preflight gate {gate!r} failed"
                )
        self._record(events, "preflight", data={"policy": self.gate_plan.preflight_policy})
        projection = self.transport.project(
            contract=contract, gate_plan=self.gate_plan, cursor=self.execution.open_task_cursor(
                task.id, self.gate_plan
            )
        )
        self._record(
            events,
            "transport-materialized",
            data={
                "transport": self.transport.name,
                "projection_sha256": projection.projection_sha256,
            },
        )
        return None

    def _dev_cycle(
        self,
        events: list[NodeEvent],
        task: Task,
        backend: AgentBackend,
        *,
        feedback: str | None,
    ) -> NodeOutcome:
        """Run exactly one bounded DEV pass; return its outcome."""
        self._record(events, "dev")
        d_outcome, d_ev = self._run_dev(
            backend,
            self.gates,
            task,
            self.manifest,
            [],
            self.repo_root,
            1,  # bounded: the driver owns the fixer loop, not an inner retry loop
            feedback=feedback,
            transcript_dir=self.transcript_dir,
        )
        # Fold the node's actual outcome and gate signatures into the recorded
        # dev event's extra so the trace reflects what really happened.
        dev_event = events[-1]
        dev_event.result = d_ev.result
        dev_event.extra["gate_signatures"] = list(d_ev.extra.get("gate_signatures", ()))
        return d_outcome

    def _validate_and_review(
        self,
        events: list[NodeEvent],
        task: Task,
        contract: ExecutionContract,
    ) -> tuple[str, ReviewSwarmResult | None, str]:
        """Validation + campaign classification + parallel review.

        Returns ``(action, swarm, feedback)`` where ``action`` is one of
        ``"clean"`` (no fixer, no human pause), ``"needs_input"`` (a
        pre-existing validation failure that is surfaced to the human, never
        auto-fixed) or ``"fixer"`` (regressions, a failed pass-rate gate or an
        unclean review), and ``feedback`` is the reviewer/regression text.
        """
        # validation
        self._record(events, "validation")
        v_outcome, v_ev = run_validation(
            self.gates,
            task.id,
            repo_root=self.repo_root,
            satisfies=[],
            transcript_dir=self.transcript_dir,
        )
        # Fold the node's actual outcome into the recorded validation event so
        # the trace reflects what really happened, matching the dev fold in
        # ``_dev_cycle``: a pre-existing validation failure must not leave a
        # ``pass`` event on a task that escalates (SR-049 evidence integrity).
        validation_event = events[-1]
        validation_event.result = v_ev.result
        if v_outcome == NodeOutcome.FAIL:
            # A pre-existing validation failure (requirement/sim/integration gate
            # red with no regression to fix yet) is surfaced to the human, never
            # injected as fixer feedback.
            return "needs_input", None, ""

        # campaign classification
        self._record(events, "campaign-classification")
        campaign = self.campaign.evaluate_after_dev(contract, self._baseline)
        # review swarm
        self._record(events, "review-spec")
        self._record(events, "review-quality")
        swarm = run_review_swarm(
            backend=self._backend,
            task=task,
            contract=contract,
            manifest=self.manifest,
            events=events,
        )
        self._record(events, "review-join")
        regressions = bool(campaign.regressions) or not campaign.pass_rate_gate_passed
        review_clean = _swarm_clean(swarm)
        if regressions or not review_clean:
            feedback_parts: list[str] = []
            if campaign.regressions:
                feedback_parts.append(
                    "campaign regressions: " + ", ".join(campaign.regressions)
                )
            if not review_clean:
                review_text = _review_feedback(swarm)
                if review_text:
                    feedback_parts.append(review_text)
            return "fixer", swarm, "\n".join(feedback_parts)
        return "clean", swarm, ""

    def _canonical_gates(self, events: list[NodeEvent], task: Task) -> bool:
        """Run the SR-049 canonical trace/register gates, then the SR-050/
        completion-evidence preflight (per-requirement validation freshness,
        unresolved must-fix human-review annotations, and the relation-
        maintenance obligation) inside the same ``canonical-gates`` stage
        envelope. Neither check may be skipped before ``dod_met`` is True --
        this is the same completion evidence the legacy ``run_task`` path
        enforces via ``run_completion_preflight`` (runner.py).
        """
        from factory.orchestrator.nodes import run_canonical_gates

        outcome, ev = run_canonical_gates(self.trace_check, self.register_check)
        if outcome == NodeOutcome.ESCALATE:
            self._record(events, "canonical-gates", state="failed", result="fail")
            events[-1].extra["reason"] = ev.extra.get("reason", "SR-049 gate failed")
            return False
        # The governed driver has no interactive HumanReviewGate/artifact_store
        # (that concept belongs to the legacy interactive path); its own
        # human-in-the-loop surface is the retry/defer/block decision request,
        # so completion never *requires* a persisted human review here --
        # require_review=False. A must-fix annotation left over from a real
        # persisted review is still blocking below, same as the legacy path.
        completion = run_completion_preflight(
            self.repo_root, task, self.transcript_dir, require_review=False
        )
        if not completion.ok:
            self._record(events, "canonical-gates", state="failed", result="fail")
            events[-1].extra["reason"] = "; ".join(
                f"{issue.code}: {issue.detail}" for issue in completion.issues
            )
            return False
        self._record(events, "canonical-gates")
        return True

    # -- public kernel --------------------------------------------------------

    def run(self, task: Task) -> TaskResult:
        """Drive one governed task to completion, escalation, or a human pause."""
        events: list[NodeEvent] = []
        escalated = self._run_preflight_cycle(events, task)
        if escalated is not None:
            return escalated
        contract = self.contract_factory()
        self._backend = self.backend_factory(contract.workspace)

        # Baseline must be captured before DEV so the campaign can compare.
        self._record(events, "baseline")
        self._baseline = self.campaign.capture_baseline(contract)

        fixer_passes_used = 0
        feedback: str | None = None
        while True:
            d_outcome = self._dev_cycle(events, task, self._backend, feedback=feedback)
            if d_outcome == NodeOutcome.ESCALATE:
                return self._request_human_decision(
                    task, events, reason="DEV failed and unit gates stayed red"
                )

            action, _swarm, cycle_feedback = self._validate_and_review(
                events, task, contract
            )
            if action == "clean":
                if not self._canonical_gates(events, task):
                    return self._result(events, task, "escalated", dod_met=False)
                self._record(events, "handoff")
                return self._result(events, task, "completed", dod_met=True)
            if action == "needs_input":
                return self._request_human_decision(
                    task, events, reason="validation failed (pre-existing or no regression)"
                )

            # Work is not clean: spend a fixer pass, bounded by the project budget.
            if fixer_passes_used >= self.max_fixer_iterations:
                return self._request_human_decision(
                    task,
                    events,
                    reason=(
                        "review findings remain after the project fixer budget "
                        f"({self.max_fixer_iterations}) was exhausted"
                    ),
                )
            self._record(events, "fixer", data={"iteration": fixer_passes_used + 1})
            feedback = cycle_feedback or "review requested changes"
            fixer_passes_used += 1

    def resume(
        self,
        task: Task,
        *,
        request_sha256: str,
        decision: str,
        response: str,
        decided_by: str,
    ) -> TaskResult:
        """Resolve a durable ``needs_input`` request with an explicit human decision."""
        events: list[NodeEvent] = []
        cursor = self.execution.consume_human_decision(
            task.id,
            request_sha256=request_sha256,
            decision=decision,
            response=response,
            decided_by=decided_by,
        )
        events.append(
            NodeEvent(
                "human-decision",
                "pass" if decision == "retry" else NodeOutcome.ESCALATE.value,
                1,
                {"human_decision": decision, "response": response},
            )
        )
        if decision == "defer":
            self.deferrals.write(reason=response, decided_by=decided_by)
            return self._result(events, task, "escalated", dod_met=False)
        if decision == "block":
            return self._result(events, task, "escalated", dod_met=False)
        # retry: a real human issued one more attempt of the named stage.
        self.execution.begin_attempt(cursor.stage_id)
        return self.run(task)


__all__ = [
    "ALLOWED_DECISIONS",
    "CanonicalGateError",
    "ContractFactory",
    "DeferralWriter",
    "DriverBackendFactory",
    "GovernedExecutionDriver",
]