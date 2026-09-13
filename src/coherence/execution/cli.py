"""SR-034/SR-049 Python-owned governed-execution host commands.

This module is the *only* host seam for governed execution. Codex's
``governed-execution`` skill, Claude Code's ``/governed-execution`` command, the
Pi ``execution_*`` tools and a human at a terminal all invoke these commands and
consume the same schema-1 JSON. No host owns a second journal, lifecycle,
retry loop, gate interpretation or consent writer; a host may render what these
commands return and nothing else.

Two frozen serializers carry that contract:

* :class:`ExecutionProjection` -- the read-only transition projection behind
  ``legal-actions`` (and attached to every mutating command's response). It
  reports the current stage state, the closed set of legal next actions, the
  current hashes, the pending human-decision request when one exists, and the
  visibility-only ``denied_write_count``.
* :class:`ExecutionHandoff` -- the completion handoff.

Both always emit ``starts_automatically`` as the literal JSON ``false``; the
field is typed ``Literal[False]`` and a truthy value raises at construction, so
no code path can hand a host a payload that authorises downstream work.

Authority boundaries this module keeps:

* ``legal-actions`` and ``stream-progress`` never write. They read the canonical
  run journal and project it.
* ``dispatch-task`` resolves the task and calls the explicit
  :func:`factory.orchestrator.runner.run_governed_task` entrypoint; it never
  drives a stage itself, and it refuses to run over a pending human decision.
* ``resolve-human`` validates the pending request hash, the decision id, the
  closed ``retry|defer|block`` vocabulary and ``decided_by=human``, then appends
  exactly one decision -- through ``RunExecution.consume_human_decision``, which
  owns the replay/conflict/superseded rules. Only ``retry`` re-drives the run,
  via :func:`factory.orchestrator.runner.resume_governed_task`.
* ``report-worker-result`` appends one validated worker event through the
  existing run-evidence writer and can never mark a task complete.
* ``flaky-register`` is human-only and routes to
  :func:`coherence.execution.flaky_registry.register_flaky`; the driver has no
  registry write capability at all.

Driver wiring (fail-closed): ``run_governed_task``/``resume_governed_task``
require a ``driver_factory`` closure that binds every driver collaborator
(contract factory, workspace-bound backend factory, campaign runner, transport,
stage cursors) to this repo and run. SR-034 has no concrete
``TestCampaignRunner``/``WorkspaceOwner`` implementation yet, so this CLI passes
the caller-supplied factory straight through and, when none exists, returns a
blocked ``EXECUTION_WIRING_UNAVAILABLE`` projection instead of fabricating a
result. A ``retry`` that cannot run therefore leaves the human's request pending
rather than consuming it.

Exit codes (the host contract): ``0`` for a valid payload, ``1`` for a canonical
blocked/escalated result, ``2`` for invalid CLI input.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Literal

from coherence.execution.flaky_registry import FlakyRegistryError, register_flaky
from coherence.planning.paths import safe_root

SCHEMA = 1

#: Where :class:`factory.orchestrator.execution.RunExecution` keeps a run.
RUN_DIR_PARTS = ("sessions", ".factory-runs", "by-session")

#: The one key a denied out-of-worktree write is counted from. It is visibility
#: only (decision 2, 2026-09-11): it is surfaced on every projection and handoff
#: and never blocks a transition.
DENIED_WRITE_COUNT_KEY = "denied_write_count"

#: The namespaced journal payload key one reported worker event is recorded under.
WORKER_RESULT_KEY = "worker_result"

#: The closed worker-result vocabulary. Deliberately excludes anything that
#: could read as completion: a worker reports, the driver decides.
WORKER_RESULTS = ("pass", "fail", "error")

#: The closed human-decision vocabulary (never widened here; the journal's own
#: ``ALLOWED_HUMAN_DECISIONS`` is the authority).
DECISIONS = ("retry", "defer", "block")

#: The closed projected states.
STATES = ("ready", "needs_input", "completed", "escalated", "blocked")

#: The closed action vocabulary a host may be told about. A host may render
#: these and invoke the named command; it may never invent or translate one.
LEGAL_ACTION_IDS = (
    "dispatch-task",
    "resolve-human",
    "report-worker-result",
    "stream-progress",
    "inspect-handoff",
    "inspect-evidence",
)

_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class ExecutionCliError(ValueError):
    """A command argument is unsafe, malformed, or outside a closed vocabulary."""


# -- serializers --------------------------------------------------------------


@dataclass(frozen=True)
class ExecutionProjection:
    """The schema-1 read-only host transition projection for one run/task."""

    run_id: str
    task_id: str
    state: str
    legal_next_actions: tuple[str, ...] = ()
    blocked: bool = False
    reason: str | None = None
    detail: str | None = None
    stage: str | None = None
    revision: int | None = None
    attempt: int | None = None
    contract_sha256: str | None = None
    gate_plan_sha256: str | None = None
    pending_request: dict[str, Any] | None = None
    denied_write_count: int = 0
    starts_automatically: Literal[False] = False

    def __post_init__(self) -> None:
        _require_literal_false(self.starts_automatically)
        if self.state not in STATES:
            raise ExecutionCliError(f"unknown execution state {self.state!r}; allowed {STATES}")
        unknown = [a for a in self.legal_next_actions if a not in LEGAL_ACTION_IDS]
        if unknown:
            raise ExecutionCliError(f"unknown legal next actions: {unknown}")
        if not isinstance(self.denied_write_count, int) or self.denied_write_count < 0:
            raise ExecutionCliError("denied_write_count must be a non-negative integer")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": SCHEMA,
            "run_id": self.run_id,
            "task_id": self.task_id,
            "state": self.state,
            "blocked": self.blocked,
            "reason": self.reason,
            "detail": self.detail,
            "legal_next_actions": list(self.legal_next_actions),
            "stage": self.stage,
            "revision": self.revision,
            "attempt": self.attempt,
            "hashes": {
                "contract_sha256": self.contract_sha256,
                "gate_plan_sha256": self.gate_plan_sha256,
            },
            "pending_request": self.pending_request,
            "denied_write_count": self.denied_write_count,
            "starts_automatically": self.starts_automatically,
        }


@dataclass(frozen=True)
class ExecutionHandoff:
    """The schema-1 completion handoff. It hands over; it never starts work."""

    run_id: str
    task_id: str
    outcome: str
    dod_met: bool
    summary: str
    denied_write_count: int = 0
    legal_next_actions: tuple[str, ...] = ("inspect-handoff",)
    starts_automatically: Literal[False] = False

    def __post_init__(self) -> None:
        _require_literal_false(self.starts_automatically)
        unknown = [a for a in self.legal_next_actions if a not in LEGAL_ACTION_IDS]
        if unknown:
            raise ExecutionCliError(f"unknown legal next actions: {unknown}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": SCHEMA,
            "run_id": self.run_id,
            "task_id": self.task_id,
            "outcome": self.outcome,
            "dod_met": self.dod_met,
            "summary": self.summary,
            "legal_next_actions": list(self.legal_next_actions),
            "denied_write_count": self.denied_write_count,
            "starts_automatically": self.starts_automatically,
        }


def _require_literal_false(value: object) -> None:
    """``starts_automatically`` is a hard invariant, not a default."""
    if value is not False:
        raise ExecutionCliError(
            "starts_automatically is Literal[False]: a governed execution payload "
            "can never authorise downstream work"
        )


# -- run state ----------------------------------------------------------------


@dataclass(frozen=True)
class _RunState:
    """Everything the projections read, derived from the canonical run journal."""

    events: list[dict[str, Any]] = field(default_factory=list)
    task_ids: frozenset[str] = frozenset()
    pending_request: dict[str, Any] | None = None
    decisions: list[dict[str, Any]] = field(default_factory=list)
    handoff_recorded: bool = False
    stage: str | None = None
    revision: int | None = None
    attempt: int | None = None
    contract_sha256: str | None = None
    gate_plan_sha256: str | None = None
    denied_write_count: int = 0


def _run_dir(root: Path, run_id: str) -> Path:
    return root.joinpath(*RUN_DIR_PARTS, run_id)


def read_run_state(root: Path, run_id: str) -> _RunState:
    """Read the canonical run journal. Never writes, never repairs."""
    from factory.orchestrator.execution import HUMAN_DECISION_KEY, HUMAN_DECISION_REQUEST_KEY
    from factory.orchestrator.journal import RunJournal

    events = sorted(RunJournal(_run_dir(root, run_id)).events(), key=lambda e: e.sequence)
    requests: list[dict[str, Any]] = []
    decisions: list[dict[str, Any]] = []
    task_ids: set[str] = set()
    handoff = False
    stage = revision = attempt = None
    contract_sha256 = gate_plan_sha256 = None
    denied = 0

    for event in events:
        task_ids.add(event.task_id)
        data = event.data if isinstance(event.data, dict) else {}
        request = data.get(HUMAN_DECISION_REQUEST_KEY)
        if isinstance(request, dict):
            requests.append(request)
        decision = data.get(HUMAN_DECISION_KEY)
        if isinstance(decision, dict):
            decisions.append(decision)
        cursor = data.get("stage_cursor")
        if isinstance(cursor, dict):
            stage = cursor.get("stage_id", stage)
            revision = cursor.get("revision", revision)
            attempt = cursor.get("attempt", attempt)
        contract_sha256 = data.get("contract_sha256", contract_sha256)
        gate_plan_sha256 = data.get("gate_plan_sha256", gate_plan_sha256)
        count = data.get(DENIED_WRITE_COUNT_KEY)
        if isinstance(count, int) and not isinstance(count, bool) and count > 0:
            denied += count
        if event.node == "handoff" and event.state == "completed":
            handoff = True

    consumed = {
        decision.get("request_sha256")
        for decision in decisions
        if isinstance(decision.get("request_sha256"), str)
    }
    pending = next(
        (
            request
            for request in reversed(requests)
            if request.get("request_sha256") not in consumed
        ),
        None,
    )
    return _RunState(
        events=[_event_dict(event) for event in events],
        task_ids=frozenset(task_ids),
        pending_request=pending,
        decisions=decisions,
        handoff_recorded=handoff,
        stage=stage,
        revision=revision,
        attempt=attempt,
        contract_sha256=contract_sha256,
        gate_plan_sha256=gate_plan_sha256,
        denied_write_count=denied,
    )


def _event_dict(event: object) -> dict[str, Any]:
    from dataclasses import asdict

    return asdict(event)  # type: ignore[arg-type]


def project(run_id: str, task_id: str, state: _RunState) -> ExecutionProjection:
    """Derive the fixed stage state and the legal next actions from evidence.

    The order is the lifecycle order and is not negotiable: a pending human
    decision outranks everything (nothing may advance while a human is being
    asked), then a recorded ``block``, then a recorded ``handoff``, then a
    recorded ``defer``, and only an otherwise-quiet run is ``ready``.
    """
    pending = state.pending_request
    common: dict[str, Any] = {
        "run_id": run_id,
        "task_id": task_id,
        "stage": state.stage,
        "revision": state.revision,
        "attempt": state.attempt,
        "contract_sha256": state.contract_sha256,
        "gate_plan_sha256": state.gate_plan_sha256,
        "denied_write_count": state.denied_write_count,
    }
    if pending is not None:
        allowed = pending.get("allowed_decisions")
        return ExecutionProjection(
            state="needs_input",
            legal_next_actions=("resolve-human", "stream-progress"),
            pending_request={
                "request_id": pending.get("request_id"),
                "request_sha256": pending.get("request_sha256"),
                "reason": pending.get("reason"),
                "stage_id": pending.get("stage_id"),
                "revision": pending.get("revision"),
                "attempt": pending.get("attempt"),
                "allowed_decisions": list(allowed) if isinstance(allowed, (list, tuple)) else [],
                "input_sha256": pending.get("input_sha256"),
                "finding_universe_sha256": pending.get("finding_universe_sha256"),
            },
            **common,
        )
    last_decision = state.decisions[-1].get("decision") if state.decisions else None
    if last_decision == "block":
        return ExecutionProjection(
            state="blocked",
            blocked=True,
            reason="HUMAN_BLOCK",
            detail="a human blocked this run; only a human can reopen it",
            legal_next_actions=("inspect-evidence", "stream-progress"),
            **common,
        )
    if state.handoff_recorded:
        return ExecutionProjection(
            state="completed",
            legal_next_actions=("inspect-handoff", "stream-progress"),
            **common,
        )
    if last_decision == "defer":
        return ExecutionProjection(
            state="escalated",
            reason="HUMAN_DEFER",
            detail="a human deferred this run; the Deferral is the record",
            legal_next_actions=("inspect-evidence", "stream-progress"),
            **common,
        )
    return ExecutionProjection(
        state="ready",
        legal_next_actions=("dispatch-task", "report-worker-result", "stream-progress"),
        **common,
    )


def _blocked(run_id: str, task_id: str, reason: str, detail: str) -> ExecutionProjection:
    return ExecutionProjection(
        run_id=run_id,
        task_id=task_id,
        state="blocked",
        blocked=True,
        reason=reason,
        detail=detail,
        legal_next_actions=("inspect-evidence",),
    )


# -- validation ---------------------------------------------------------------


def _safe_id(kind: str, value: object) -> str:
    if not isinstance(value, str) or not _SAFE_ID.match(value):
        raise ExecutionCliError(
            f"{kind} {value!r} is not a safe identifier "
            "(expected [A-Za-z0-9][A-Za-z0-9._-]*)"
        )
    return value


def _safe_project_root(value: object) -> Path:
    if not isinstance(value, Path):
        raise ExecutionCliError("project root must be a path")
    root = None
    try:
        root = safe_root(value)
    except (OSError, RuntimeError, ValueError):
        root = None
    if root is None:
        raise ExecutionCliError(f"project root {str(value)!r} is not a safe path")
    return root


def _safe_text(kind: str, value: object, *, max_length: int = 4000) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ExecutionCliError(f"{kind} must be a non-blank string")
    if len(value) > max_length:
        raise ExecutionCliError(f"{kind} exceeds {max_length} characters")
    if any(ord(char) < 32 and char not in "\n\t" for char in value):
        raise ExecutionCliError(f"{kind} contains control characters")
    return value


def _safe_sha256(kind: str, value: object) -> str:
    if not isinstance(value, str) or not _SHA256.match(value):
        raise ExecutionCliError(f"{kind} must be a canonical lowercase sha256 digest")
    return value


def _require_human(decided_by: object) -> str:
    if decided_by != "human":
        raise ExecutionCliError(
            f"decided_by must be 'human', got {decided_by!r}: only a human may decide"
        )
    return "human"


# -- output -------------------------------------------------------------------


def _emit(payload: dict[str, Any], *, as_json: bool, summary: str) -> None:
    if as_json:
        print(json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False))
    else:
        print(summary)


def _exit_code(projection: ExecutionProjection) -> int:
    """0 for a valid payload, 1 for a canonical blocked/escalated result."""
    return 1 if projection.blocked or projection.state in {"blocked", "escalated"} else 0


def _result_dict(result: object) -> dict[str, Any]:
    from dataclasses import asdict

    payload = asdict(result)  # type: ignore[arg-type]
    payload.pop("manifest", None)  # host evidence, not a context dump
    return payload


# -- commands -----------------------------------------------------------------


def _cmd_legal_actions(args: argparse.Namespace) -> int:
    root = _safe_project_root(args.project_root)
    run_id = _safe_id("run id", args.run_id)
    task_id = _safe_id("task id", args.task_id)

    state = read_run_state(root, run_id)
    if state.task_ids and task_id not in state.task_ids:
        projection = _blocked(
            run_id,
            task_id,
            "TASK_MISMATCH",
            f"run {run_id!r} holds evidence for {sorted(state.task_ids)}, not {task_id!r}",
        )
    else:
        projection = project(run_id, task_id, state)
    payload = projection.to_dict()
    _emit(
        payload,
        as_json=args.json,
        summary=f"{run_id}/{task_id}: {projection.state} "
        f"-> {', '.join(projection.legal_next_actions) or 'none'}",
    )
    return _exit_code(projection)


def _cmd_stream_progress(args: argparse.Namespace) -> int:
    root = _safe_project_root(args.project_root)
    run_id = _safe_id("run id", args.run_id)
    state = read_run_state(root, run_id)
    payload = {
        "schema": SCHEMA,
        "run_id": run_id,
        "events": state.events,
        "denied_write_count": state.denied_write_count,
        "starts_automatically": False,
    }
    _emit(
        payload,
        as_json=args.json,
        summary="\n".join(
            f"{event['sequence']:>4}  {event['node']}  {event['state']}"
            for event in state.events
        )
        or f"{run_id}: no recorded events",
    )
    return 0


def _cmd_dispatch_task(args: argparse.Namespace, driver_factory) -> int:
    from factory.orchestrator.runner import run_governed_task

    root = _safe_project_root(args.project_root)
    run_id = _safe_id("run id", args.run_id)
    task_id = _safe_id("task id", args.task_id)

    state = read_run_state(root, run_id)
    if state.task_ids and task_id not in state.task_ids:
        return _fail(args, _blocked(run_id, task_id, "TASK_MISMATCH", "run holds another task"))
    if state.pending_request is not None:
        return _fail(
            args,
            _blocked(
                run_id,
                task_id,
                "NEEDS_INPUT",
                "a human decision is pending; resolve it with `resolve-human` first",
            ),
        )
    task = _resolve_task(root, task_id)
    if task is None:
        return _fail(
            args, _blocked(run_id, task_id, "TASK_NOT_FOUND", f"no task {task_id!r} in the ledger")
        )
    if driver_factory is None:
        return _fail(args, _wiring_unavailable(run_id, task_id))

    try:
        backend, gates, transcript_dir = _wire_run(root, run_id)
    except Exception as exc:  # noqa: BLE001 - an unconfigured project never dispatches
        return _fail(args, _blocked(run_id, task_id, "PROJECT_NOT_CONFIGURED", str(exc)))
    try:
        result = run_governed_task(
            task,
            backend,
            gates,
            root,
            session_id=run_id,
            transcript_dir=transcript_dir,
            driver_factory=driver_factory,
        )
    except ValueError as exc:  # fail-closed facade (no wiring closure)
        return _fail(args, _wiring_unavailable(run_id, task_id, str(exc)))

    return _emit_run_result(args, root, run_id, task_id, result, action="dispatch-task")


def _cmd_resolve_human(args: argparse.Namespace, driver_factory, git_ops) -> int:
    root = _safe_project_root(args.project_root)
    run_id = _safe_id("run id", args.run_id)
    task_id = _safe_id("task id", args.task_id)
    request_sha256 = _safe_sha256("request_sha256", args.request_sha256)
    decision_id = _safe_text("decision id", args.decision_id, max_length=400)
    decision = args.decision
    response = _safe_text("response", args.response)
    decided_by = _require_human(args.decided_by)
    if decision not in DECISIONS:
        raise ExecutionCliError(f"unknown decision {decision!r}; allowed {DECISIONS}")

    state = read_run_state(root, run_id)
    if state.task_ids and task_id not in state.task_ids:
        return _fail(args, _blocked(run_id, task_id, "TASK_MISMATCH", "run holds another task"))

    replay = _identical_replay(state, request_sha256, decision_id, decision, response, decided_by)
    if replay is not None:
        projection = project(run_id, task_id, state)
        payload = {
            "schema": SCHEMA,
            "run_id": run_id,
            "task_id": task_id,
            "action": "resolve-human",
            "decision": decision,
            "decision_id": replay.get("decision_id"),
            "request_sha256": request_sha256,
            "replayed": True,
            "result": None,
            "handoff": None,
            "projection": projection.to_dict(),
            "starts_automatically": False,
        }
        _emit(payload, as_json=args.json, summary=f"{decision} already recorded (replay)")
        return _exit_code(projection)

    rejection = _decision_rejection(state, request_sha256, decision, decision_id)
    if rejection is not None:
        return _fail(args, _blocked(run_id, task_id, rejection[0], rejection[1]))

    if decision == "retry":
        return _resume_retry(
            args, root, run_id, task_id, request_sha256, response, decided_by, driver_factory
        )

    # defer / block: the decision is the whole transition. It is appended by the
    # journal's own consume_human_decision (the authority on replay, conflict
    # and superseded requests), and a defer additionally writes the existing
    # Deferral onto the task node.
    if decision == "defer" and _resolve_task(root, task_id) is None:
        # Checked BEFORE the decision is appended: a Deferral with nowhere to be
        # written must not leave a consumed request behind it.
        return _fail(
            args, _blocked(run_id, task_id, "TASK_NOT_FOUND", f"no task {task_id!r} in the ledger")
        )
    try:
        execution = _open_execution(root, run_id, task_id, git_ops)
        execution.consume_human_decision(
            task_id,
            request_sha256=request_sha256,
            decision=decision,
            response=response,
            decided_by=decided_by,
        )
        if decision == "defer":
            _write_deferral(root, task_id, response, args.review_after)
    except Exception as exc:  # noqa: BLE001 - every failure is a refusal, never a pass
        return _fail(args, _blocked(run_id, task_id, "DECISION_REJECTED", str(exc)))

    projection = project(run_id, task_id, read_run_state(root, run_id))
    payload = {
        "schema": SCHEMA,
        "run_id": run_id,
        "task_id": task_id,
        "action": "resolve-human",
        "decision": decision,
        "decision_id": decision_id,
        "request_sha256": request_sha256,
        "replayed": False,
        "result": None,
        "handoff": None,
        "projection": projection.to_dict(),
        "starts_automatically": False,
    }
    _emit(payload, as_json=args.json, summary=f"recorded {decision} for {run_id}/{task_id}")
    return _exit_code(projection)


def _resume_retry(
    args: argparse.Namespace,
    root: Path,
    run_id: str,
    task_id: str,
    request_sha256: str,
    response: str,
    decided_by: str,
    driver_factory,
) -> int:
    from factory.orchestrator.runner import resume_governed_task

    task = _resolve_task(root, task_id)
    if task is None:
        return _fail(
            args, _blocked(run_id, task_id, "TASK_NOT_FOUND", f"no task {task_id!r} in the ledger")
        )
    if driver_factory is None:
        # Fail closed *before* the decision is consumed: an unrunnable retry
        # must leave the human's request pending, not spend it.
        return _fail(args, _wiring_unavailable(run_id, task_id))

    try:
        backend, gates, transcript_dir = _wire_run(root, run_id)
    except Exception as exc:  # noqa: BLE001 - an unconfigured project never resumes
        return _fail(args, _blocked(run_id, task_id, "PROJECT_NOT_CONFIGURED", str(exc)))
    try:
        result = resume_governed_task(
            task,
            backend,
            gates,
            root,
            request_sha256=request_sha256,
            decision="retry",
            response=response,
            decided_by=decided_by,
            session_id=run_id,
            transcript_dir=transcript_dir,
            driver_factory=driver_factory,
        )
    except ValueError as exc:
        return _fail(args, _wiring_unavailable(run_id, task_id, str(exc)))

    return _emit_run_result(
        args,
        root,
        run_id,
        task_id,
        result,
        action="resolve-human",
        extra={"decision": "retry", "request_sha256": request_sha256, "replayed": False},
    )


def _cmd_report_worker_result(args: argparse.Namespace, git_ops) -> int:
    root = _safe_project_root(args.project_root)
    run_id = _safe_id("run id", args.run_id)
    task_id = _safe_id("task id", args.task_id)
    lane = _safe_id("lane", args.lane)
    detail = _safe_text("detail", args.detail)
    if args.result not in WORKER_RESULTS:
        raise ExecutionCliError(
            f"unknown worker result {args.result!r}; allowed {WORKER_RESULTS} "
            "(a worker reports; it never completes a task)"
        )
    denied = args.denied_writes
    if not isinstance(denied, int) or denied < 0:
        raise ExecutionCliError("--denied-writes must be a non-negative integer")

    state = read_run_state(root, run_id)
    if state.task_ids and task_id not in state.task_ids:
        return _fail(args, _blocked(run_id, task_id, "TASK_MISMATCH", "run holds another task"))

    record = {
        "schema": SCHEMA,
        "lane": lane,
        "result": args.result,
        "detail": detail,
        "reported_at": _now(),
    }
    try:
        execution = _open_execution(root, run_id, task_id, git_ops)
        # The worker event never moves the run: it is appended at whatever
        # position the checkpoint already holds, so no resume reads it as a
        # transition, and `state` is "reported" -- never "completed".
        next_node, remaining = _current_position(root, run_id)
        execution.record(
            node="worker-result",
            state="reported",
            attempt=1,
            next_node=next_node,
            remaining=remaining,
            data={WORKER_RESULT_KEY: record, DENIED_WRITE_COUNT_KEY: denied},
        )
    except Exception as exc:  # noqa: BLE001
        return _fail(args, _blocked(run_id, task_id, "WORKER_RESULT_REJECTED", str(exc)))

    projection = project(run_id, task_id, read_run_state(root, run_id))
    payload = {
        "schema": SCHEMA,
        "run_id": run_id,
        "task_id": task_id,
        "action": "report-worker-result",
        "recorded": record,
        "projection": projection.to_dict(),
        "starts_automatically": False,
    }
    _emit(payload, as_json=args.json, summary=f"recorded {lane} {args.result} for {run_id}")
    return _exit_code(projection)


def _cmd_flaky_register(args: argparse.Namespace) -> int:
    root = _safe_project_root(args.project_root)
    decided_by = _require_human(args.decided_by)
    reason = _safe_text("reason", args.reason)
    try:
        record = register_flaky(
            root,
            args.test_id,
            reason=reason,
            decided_by=decided_by,
            decided_at=_now(),
            review_after=args.review_after,
        )
    except FlakyRegistryError as exc:
        raise ExecutionCliError(str(exc)) from exc
    payload = {
        "schema": SCHEMA,
        "action": "flaky-register",
        "record": {
            "schema": record.schema,
            "test_id": record.test_id,
            "reason": record.reason,
            "decided_by": record.decided_by,
            "decided_at": record.decided_at,
            "review_after": record.review_after,
        },
        "starts_automatically": False,
    }
    _emit(payload, as_json=args.json, summary=f"registered known-flaky {record.test_id}")
    return 0


# -- shared command helpers ---------------------------------------------------


def _fail(args: argparse.Namespace, projection: ExecutionProjection) -> int:
    payload = projection.to_dict()
    _emit(payload, as_json=args.json, summary=f"blocked: {projection.reason} — {projection.detail}")
    return 1


def _wiring_unavailable(run_id: str, task_id: str, detail: str | None = None) -> ExecutionProjection:
    return _blocked(
        run_id,
        task_id,
        "EXECUTION_WIRING_UNAVAILABLE",
        detail
        or (
            "no driver_factory wired this run's GovernedExecutionDriver "
            "collaborators; refusing to fabricate a result"
        ),
    )


def _emit_run_result(
    args: argparse.Namespace,
    root: Path,
    run_id: str,
    task_id: str,
    result: object,
    *,
    action: str,
    extra: dict[str, Any] | None = None,
) -> int:
    state = read_run_state(root, run_id)
    projection = project(run_id, task_id, state)
    outcome = getattr(result, "outcome", "escalated")
    dod_met = bool(getattr(result, "dod_met", False))
    handoff = (
        ExecutionHandoff(
            run_id=run_id,
            task_id=task_id,
            outcome=outcome,
            dod_met=dod_met,
            summary=(
                f"{task_id} completed under run {run_id}; a human decides what happens next"
            ),
            denied_write_count=state.denied_write_count,
        ).to_dict()
        if outcome == "completed" and dod_met
        else None
    )
    payload = {
        "schema": SCHEMA,
        "run_id": run_id,
        "task_id": task_id,
        "action": action,
        **(extra or {}),
        "result": _result_dict(result),
        "handoff": handoff,
        "projection": projection.to_dict(),
        "starts_automatically": False,
    }
    _emit(payload, as_json=args.json, summary=f"{run_id}/{task_id}: {outcome} (dod_met={dod_met})")
    # Only a completed run that actually met its dod is a valid payload; every
    # other terminal shape is the canonical blocked/escalated exit.
    return 0 if outcome == "completed" and dod_met else 1


def _resolve_task(root: Path, task_id: str):
    from substrate.ledger.tasks import get_task, load_tasks

    tasks_dir = root / "tasks"
    if not tasks_dir.is_dir():
        return None
    try:
        return get_task(load_tasks(tasks_dir), task_id)
    except (OSError, ValueError):
        return None


def _open_execution(root: Path, run_id: str, task_id: str, git_ops):
    """Open the existing run-evidence writer for an existing or fresh run."""
    from factory.orchestrator.execution import RunExecution
    from factory.orchestrator.git_ops import SubprocessGitOps
    from factory.orchestrator.journal import RunJournal

    ops = git_ops if git_ops is not None else SubprocessGitOps()
    checkpoint = RunJournal(_run_dir(root, run_id)).latest()
    start_commit = checkpoint.start_commit if checkpoint is not None else ops.head_commit(root)
    return RunExecution.create(root, run_id, task_id, start_commit, ops)


def _current_position(root: Path, run_id: str) -> tuple[str, dict[str, int]]:
    """The run's current checkpoint position, so an appended event never moves it."""
    from factory.orchestrator.execution import STAGE_CHECKPOINT_NODE_PREFIX
    from factory.orchestrator.journal import RunJournal

    checkpoint = RunJournal(_run_dir(root, run_id)).latest()
    if checkpoint is None:
        return f"{STAGE_CHECKPOINT_NODE_PREFIX}worker-result", {}
    return checkpoint.node, dict(checkpoint.remaining)


def _identical_replay(
    state: _RunState,
    request_sha256: str,
    decision_id: str,
    decision: str,
    response: str,
    decided_by: str,
) -> dict[str, Any] | None:
    """The already-journalled decision when this call repeats it exactly."""
    for record in state.decisions:
        if record.get("request_sha256") != request_sha256:
            continue
        if (
            record.get("decision_id") == decision_id
            and record.get("decision") == decision
            and record.get("response") == response
            and record.get("decided_by") == decided_by
        ):
            return record
    return None


def _decision_rejection(
    state: _RunState, request_sha256: str, decision: str, decision_id: str
) -> tuple[str, str] | None:
    """Reject a conflicting, stale or mis-identified decision before any write."""
    for record in state.decisions:
        if record.get("request_sha256") == request_sha256:
            return (
                "DECISION_REJECTED",
                f"request {request_sha256} was already decided "
                f"{record.get('decision')!r} by {record.get('decided_by')!r}",
            )
    pending = state.pending_request
    if pending is None:
        return ("DECISION_REJECTED", "no pending human decision request for this run to consume")
    if pending.get("request_sha256") != request_sha256:
        return (
            "DECISION_REJECTED",
            f"the pending request is {pending.get('request_sha256')!r}, not {request_sha256!r}",
        )
    allowed = pending.get("allowed_decisions")
    if isinstance(allowed, (list, tuple)) and decision not in allowed:
        return ("DECISION_REJECTED", f"the pending request allows {list(allowed)}, not {decision!r}")
    expected = f"{pending.get('request_id')}/{decision}"
    if decision_id != expected:
        return (
            "DECISION_ID_MISMATCH",
            f"decision id {decision_id!r} does not identify this request's "
            f"{decision!r} decision ({expected!r})",
        )
    return None


def _write_deferral(root: Path, task_id: str, reason: str, review_after: str | None) -> None:
    from coherence.trace.write import set_deferred

    set_deferred(root, task_id, reason, review_after=review_after)


def _wire_run(root: Path, run_id: str):
    """Build the run's backend, gates and transcript dir for the driver facade.

    These are the collaborators the *facade* takes; every driver-internal
    collaborator is the injected ``driver_factory``'s business.
    """
    from factory.config import load_config, require_gates
    from factory.orchestrator.backends import ConfigGateRunner
    from factory.orchestrator.pi_backend import PiAgentBackend
    from substrate.paths import scope_guard_extension

    transcript_dir = root / "sessions" / ".factory-transcripts" / run_id
    gates = ConfigGateRunner(
        root, require_gates(load_config(root), root), log_dir=transcript_dir
    )
    backend = PiAgentBackend(repo_root=root, extension_path=scope_guard_extension())
    return backend, gates, transcript_dir


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")


# -- parser -------------------------------------------------------------------


def _add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--project-root", default=Path("."), type=Path)
    parser.add_argument("--json", action="store_true")


def _parser(prog: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog=prog)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_legal = sub.add_parser("legal-actions")
    p_legal.add_argument("--run-id", required=True)
    p_legal.add_argument("--task-id", required=True)
    _add_common(p_legal)

    p_dispatch = sub.add_parser("dispatch-task")
    p_dispatch.add_argument("task_id")
    p_dispatch.add_argument("--run-id", required=True)
    _add_common(p_dispatch)

    p_resolve = sub.add_parser("resolve-human")
    p_resolve.add_argument("--run-id", required=True)
    p_resolve.add_argument("--task-id", required=True)
    p_resolve.add_argument("--request-sha256", required=True)
    p_resolve.add_argument("--decision-id", required=True)
    p_resolve.add_argument("--decision", required=True)
    p_resolve.add_argument("--response", required=True)
    p_resolve.add_argument("--decided-by", required=True)
    p_resolve.add_argument("--review-after", default=None)
    _add_common(p_resolve)

    p_worker = sub.add_parser("report-worker-result")
    p_worker.add_argument("--run-id", required=True)
    p_worker.add_argument("--task-id", required=True)
    p_worker.add_argument("--lane", required=True)
    p_worker.add_argument("--result", required=True)
    p_worker.add_argument("--detail", required=True)
    p_worker.add_argument("--denied-writes", type=int, default=0)
    _add_common(p_worker)

    p_progress = sub.add_parser("stream-progress")
    p_progress.add_argument("run_id")
    _add_common(p_progress)

    p_flaky = sub.add_parser("flaky-register")
    p_flaky.add_argument("test_id")
    p_flaky.add_argument("--reason", required=True)
    p_flaky.add_argument("--decided-by", required=True)
    p_flaky.add_argument("--review-after", default=None)
    _add_common(p_flaky)

    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    prog: str = "coherence-execution",
    driver_factory: Callable[..., Any] | None = None,
    git_ops: Any | None = None,
) -> int:
    """Run one governed-execution command.

    Args:
        argv: the command argv (without the ``execution`` group name).
        prog: the program name used in usage errors.
        driver_factory: the wiring closure ``run_governed_task`` /
            ``resume_governed_task`` need. ``None`` (the default) makes every
            driving command fail closed rather than fabricate a result.
        git_ops: the ``GitOps`` the run-evidence writer uses; defaults to
            ``SubprocessGitOps``.

    Returns:
        ``0`` for a valid payload, ``1`` for a canonical blocked/escalated
        result, ``2`` for invalid CLI input.
    """
    parser = _parser(prog)
    try:
        args = parser.parse_args(list(argv) if argv is not None else None)
    except SystemExit as exc:  # argparse already reported the usage error
        return exc.code if isinstance(exc.code, int) else 2

    try:
        if args.cmd == "legal-actions":
            return _cmd_legal_actions(args)
        if args.cmd == "stream-progress":
            return _cmd_stream_progress(args)
        if args.cmd == "dispatch-task":
            return _cmd_dispatch_task(args, driver_factory)
        if args.cmd == "resolve-human":
            return _cmd_resolve_human(args, driver_factory, git_ops)
        if args.cmd == "report-worker-result":
            return _cmd_report_worker_result(args, git_ops)
        if args.cmd == "flaky-register":
            return _cmd_flaky_register(args)
    except ExecutionCliError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(f"error: unknown command {args.cmd!r}", file=sys.stderr)
    return 2


__all__ = [
    "DECISIONS",
    "DENIED_WRITE_COUNT_KEY",
    "LEGAL_ACTION_IDS",
    "SCHEMA",
    "STATES",
    "WORKER_RESULTS",
    "ExecutionCliError",
    "ExecutionHandoff",
    "ExecutionProjection",
    "main",
    "project",
    "read_run_state",
]
