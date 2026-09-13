---
id: PLAN-FEAT-013-GOVERNED-EXECUTION-DRIVER
title: "FEAT-013 Governed Execution Driver Implementation Plan"
lifecycle_state: draft
status: draft
feature: FEAT-013
spec_ref: docs/superpowers/specs/2026-09-08-feat013-governed-execution-driver-design.md
requirements:
  - SR-034
  - SR-049
---

# FEAT-013 Governed Execution Driver Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Drive one already-selected factory task through a backend-bound DEV, two fresh parallel reviews, bounded fixer passes, canonical gates, and human decisions while preserving the existing `TaskResult` contract and one execution-owned worktree.

**Architecture:** Add a host-neutral `GovernedExecutionDriver` around the existing `AgentBackend`, `GateRunner`, `run_dev`, `run_validation`, `RunExecution`, and `TaskResult` surfaces. The driver consumes a Coherence-compiled immutable execution contract and workflow-specific `GatePlan`; a selected transport may project that plan into operational records, but cannot redefine stages or assurance. Inject one execution workspace owner (created by Task 2 — no lease owner exists in the orchestrator today) and a backend factory so the driver observes one shared worktree without allocating worktrees or creating a scheduler. Keep Coherence authoritative for gates, traceability, deferrals, and human decisions; expose Python-owned execution commands through the existing Pi host-registration seam rather than creating another MCP server (the FEAT-9 MCP adapter does not exist yet and is out of scope). Add thin Codex and Claude Code entrypoints that call this same command surface, so both hosts share the exact lifecycle and cannot create a parallel state machine.

**Tech Stack:** Python 3.12, frozen dataclasses and `typing.Protocol`, JSON/JSONL run evidence, pytest, Ruff, Pyright, existing factory gates and Coherence CLI, TypeScript Pi extension adapters.

---

## Status, scope, and decision gates

**The six plan-stage open questions were decided by the human on 2026-09-11** (FEAT-013 plan review; `coherence plan append` is closed for this run — it returns `capture is terminal` — so the decisions are recorded here and take effect through this plan revision):

1. **Flaky-test registry accepted** — `Deferral`-shaped record, human-only write verb, plus the quarantine discipline in Task 4 (owner + `review_after`; fix-or-delete at expiry; never covering a deterministic failure introduced by the change; count kept visible).
2. **Out-of-worktree writes are prevented by the harness, never a task failure.** Every worker lane is launched with a write policy rooted at the lease path plus a declared allowlist; a denied write is recorded as evidence and the run continues — no `NodeOutcome.REJECT`, no human escalation (Tasks 2 and 5).
3. **Fixer-iteration budget is `2`**, project-wide, written to `.factory/factory.yaml` (Task 5, Step 4). The key must be present and valid; a governed dispatch fails closed otherwise — absence is not a default.
4. **No new `AgentRole`.** The two reviews stay prompt-distinguished, and evidence distinguishes them by the canonical stage ids `review-spec`/`review-quality` and the closed review lane (`spec-review`/`quality-review`); the stage-vs-lane vocabulary mapping must be documented rather than conflated.
5. **Narrow preflight stays in SR-034 as `mandatory-only`**; the AC-8 obligation/health variant is supplied later by FEAT-018 and remains gated behind `ac8_decision_ref`.
6. **Resolved by decision 2** — there is no separate out-of-worktree *policy* to choose: the harness denies out-of-root writes automatically. The evidence-only detector named in the invariants is enforcement tooling for a lane that cannot enforce, not an alternative policy outcome.

A seventh decision belongs to the FEAT-017 planning-gate register, not to SR-034, and is recorded here only for traceability: planning-gate findings must be scoped to the artifacts of the run under review (`PLAN_TASK_PARITY` compared by `source_plan`; the FEAT-017 closure reference inputs included only for a FEAT-017 run), because `tasks/` is a multi-plan ledger and a repo-wide scan reports other features' artifacts as this run's findings.

Both gates have since been recorded (2026-09-11): the reviewed spec is `status: accepted`, and `SR-034` consent is written to `gate-decisions/sr-SR-034.json`. What remains gated is *adoption*: no step may write project state that represents `SR-034` as implemented, adopted, or claimed in `requirements/index.json` before the implementation and its evidence exist.

## Captured intent coverage

This plan carries every captured answer into executable work: `a2` is covered by
the in-loop trace gate in Task 5; `a3` by fresh worker prompts and session
checks in Tasks 2 and 3; `a4` by the baseline/campaign contract in Task 4; `a5`
and `a6` by reuse of the existing backend and gate authority; `a7` by the one
lease contract in Task 2; `a8` by explicit retry/defer/block handling in Task
5; `a9` by the no-blind-retry classifier in Task 4; `a10` by surfaced worker,
flaky, regression, and infrastructure outcomes in Tasks 4–6; and `a11` by the
known-flaky-first classification sequence in Task 4.

## File map

- `src/factory/orchestrator/execution_contract.py` — immutable execution contract and worker-assignment values shared by the driver and host adapters.
- `src/factory/orchestrator/execution_workspace.py` — injected workspace-owner and backend-factory protocols; it observes ownership but does not allocate worktrees.
- `src/factory/orchestrator/review_swarm.py` — two prompt-distinguished, fresh-session `REVIEW` invocations and their deterministic ordering contract.
- `src/factory/orchestrator/execution_campaign.py` — baseline snapshots, complete campaign results, pass-rate comparison, and regression/flaky classification.
- `src/coherence/execution/gate_plan.py` — Coherence-owned immutable `GatePlan` compiler and canonical execution-stage validation.
- `src/factory/orchestrator/execution_transport.py` — immutable direct/Hermes transport projection of a Coherence-compiled `GatePlan`; no lifecycle or scheduling implementation.
- `src/coherence/execution/flaky_registry.py` — human-curated known-flaky registry reader/writer using the approved decision shape.
- `src/factory/orchestrator/execution_driver.py` — the bounded single-task driver that returns the existing `TaskResult` and records `NodeEvent` evidence.
- `src/factory/config.py` and `.factory/factory.yaml` — parse and declare the project-wide fixer budget after the human supplies its numeric value.
- `src/coherence/execution/cli.py` and `src/coherence/cli.py` — Python-owned dispatch/report/progress and human-only flaky-registration commands.
- `pi-ext/factory-watch/src/execution-tools.ts` and `pi-ext/factory-watch/src/index.ts` — thin host registrations that call the Python command surface.
- `.agents/skills/governed-execution/SKILL.md` — Codex skill entrypoint for the governed execution lifecycle.
- `.claude/commands/governed-execution.md` — Claude Code slash-command entrypoint for the same lifecycle.
- `tests/unit/codex/test_governed_execution_surface.py` — shared contract tests for both host entrypoints.
- `tests/unit/orchestrator/test_execution_{contract,workspace,review_swarm,campaign,driver}.py` — deterministic factory unit coverage.
- `tests/unit/coherence/test_execution_gate_plan.py` — canonical GatePlan, preflight-policy, and stage-order coverage.
- `tests/unit/coherence/test_flaky_registry.py` and `tests/unit/coherence/test_execution_cli.py` — strict registry and CLI contract coverage.
- `pi-ext/factory-watch/test/execution-tools.test.ts` — adapter request/response and tool-catalog coverage.
- `tests/integration/orchestrator/test_governed_execution_driver.py` — one fake-backend end-to-end tracer bullet covering ordering, gates, trace evidence, workspace identity, and `TaskResult` output.

## Execution invariants

The implementation must preserve these invariants in every task:

- The driver consumes the existing `AgentBackend` protocol and returns the existing `TaskResult`; it does not add a competing result or acceptance type.
- `AgentRole.REVIEW` is invoked twice with distinct prompts and independently captured session ids. The fixer is not dispatched until both reviews have returned.
- The only repetition budget for the DEV/review/fixer cycle is the configured project-wide fixer budget. The one confirmation rerun for an unlisted failed test is classification-only and never consumes that budget.
- A required gate, obligation, trace check, or human-review interrupt is authoritative. A host adapter can report it or request it; it cannot override it.
- The driver receives a validated `GatePlan` and records its hash/version with the contract; a transport projection may materialize root/stage records but never changes the plan, gate set, or completion authority.
- One workspace lease is acquired for the execution and the same path is included in every worker assignment. The driver never allocates a lease per worker.
- An out-of-worktree write is *prevented*, not detected: every worker lane is launched with a write policy rooted at the lease path plus an explicitly declared allowlist (session temp dir, tool caches, the shared `.git` objects, the transcript dir). A denied write is recorded as `denied_write` evidence and the run continues — never a task failure, never a human escalation. A detector remains only as an evidence-only fallback for a lane that cannot enforce the policy, and the deny count is surfaced in the handoff.
- The recorded decisions above (budget value `2`, `mandatory-only` preflight, no new `AgentRole`, harness-enforced write policy, accepted flaky registry) and the two recorded gates (spec `status: accepted`, `SR-034` consent decision) are facts, not inferences; what no step may do is write project state that represents `SR-034` as implemented or adopted before the implementation and its evidence exist.

## Deterministic execution lifecycle and host mapping

FEAT-013 uses the same separation as the mature FEAT-017 planning workflow: Coherence owns
the lifecycle contract, stage ordering, hashes, evidence, gates, and human decisions;
transport owns only durable operational projection; and host surfaces provide conversation,
invocation, and presentation. The runtime stage graph is fixed and must not be reordered:

```text
execution-run
  -> contract-compiled
  -> preflight
  -> transport-materialized
  -> baseline
  -> dev
  -> validation
  -> campaign-classification
  -> review-spec  +  review-quality        (parallel, fresh sessions)
  -> review-join
  -> canonical-gates
  -> handoff
```

The canonical `GatePlan.stages` tuple is exactly
`("contract-compiled", "preflight", "transport-materialized", "baseline", "dev",
"validation", "campaign-classification", "review-spec", "review-quality", "review-join",
"fixer", "canonical-gates", "handoff")`. `execution-run` is the transport root, not a
stage in that tuple. `needs_input` is a paused state on the current stage, not an additional
stage, and therefore cannot be used to bypass the tuple.

`GatePlan` is compiled and validated only by `src/coherence/execution/gate_plan.py`; the factory
transport imports the frozen value and may only project it. `preflight_policy` is part of the
GatePlan version/hash and has two closed values: `mandatory-only` (safe identifiers, config,
contract/GatePlan consistency, and required capability checks) and
`ac8-obligation-health` (the additional proposed AC-8 obligation/health checks). `GatePlan`
also carries a nullable `ac8_decision_ref` that participates in the same canonical hash, so
`compile_gate_plan()` can reject `ac8-obligation-health` when that reference is null or does not
match the current human decision record; the reference is the field the compiler validates, not
an implicit lookup. Because AC-8 is
unconfirmed in this run, the driver may use only `mandatory-only`; it must record that policy in
the preflight stage and refuse an `ac8-obligation-health` plan until the human decision is
recorded. The stage is therefore real and deterministic, not a silent no-op, while the
unconfirmed acceptance criterion is not implemented by inference.

Each `RunExecution` governed event embeds one canonical `stage_record` under its existing
namespaced evidence payload. The record schema is:

```json
{
  "schema": 1,
  "run_id": "FEAT-013",
  "task_id": "T-013",
  "stage_id": "dev",
  "revision": 1,
  "attempt": 1,
  "lineage_key": "feat013/FEAT-013/dev/v1",
  "attempt_key": "feat013/FEAT-013/dev/r1/a1/v1",
  "parent_event_sha256": "<previous stage-record hash or null>",
  "contract_sha256": "<execution contract hash>",
  "gate_plan_sha256": "<compiled GatePlan hash>",
  "workflow_version": "governed-execution/v1",
  "input_sha256": "<canonical input-manifest hash>",
  "output_sha256": "<canonical output/evidence hash>",
  "state": "completed",
  "event_sequence": 1,
  "record_sha256": "<sha256 of this record without record_sha256>"
}
```

Hashes use sorted-key compact JSON and SHA-256. `stage_record` is appended to the existing
`RunExecution` journal/checkpoint through `record_stage()`; old records are immutable. The
cursor accepts `running` only from the current predecessor, `completed` only with a matching
output hash, `needs_input` only with a pending request, and `invalidated` only as a new
descendant-invalidation record. It rejects skipped/repeated stages, a reused `attempt_key`, a
non-increasing revision/attempt, or a parent hash that is not the current journal tail. Stage-id
uniqueness is scoped to one `(revision, attempt)` key: a new attempt re-runs and re-records the
fixed prefix (`contract-compiled`, `preflight`, `transport-materialized`, `baseline`) under its
new attempt key, and a fixer revision re-records `dev` onward under its new revision, while a
repeat inside the same attempt/revision is still rejected. The single exception is the same-attempt reclaim recovery append described below, which is tagged recovery evidence rather than a stage transition. A
same-attempt Hermes reclaim appends recovery evidence with the same attempt key and fencing
lineage; a retry increments `attempt`; a scoped fixer increments `revision`, starts its own
`fixer` stage, and invalidates all descendant current pointers without mutating prior records.

The durable `needs_input` request is an append-only `human-decision-requested` record with
`record_schema: 2` — deliberately *not* a `stage_record`, because a request is not a stage
transition: it carries no `lineage_key`/`attempt_key`/`output_sha256`/`event_sequence`, and its
`state` is the request state rather than the stage state — with `request_id`, `request_sha256`,
`run_id`, `task_id`, `stage_id`, `revision`, `attempt`,
`finding_universe_sha256`, `input_sha256`, `allowed_decisions` (closed to `retry|defer|block`),
`created_event_sha256`, and `state="pending"`. The enclosing `RunExecution` governed event keeps
the stage-level `state="needs_input"` on the current stage and embeds the request under
`extra["governed_execution"]["request"]`; the two literals are fields on two different objects
and must not be conflated. `resolve-human` must supply a safe
`decision_id`, the exact `request_sha256`, decision, response, `decided_by="human"`, and current
artifact/input hashes. It appends one `human-decision-recorded` record whose hash binds those
fields and the request hash. Restart reconstruction reads the journal tail and releases no
stage unless the request is current; an identical decision-id/request/hash replay is an
idempotent read, while a conflicting, stale, already-consumed, or hash-mismatched decision is
rejected. A valid retry appends `attempt_started` for the next attempt, revalidates the unchanged
contract/GatePlan/preflight prefix and workspace identity, and resumes at `dev`; it never reruns
or overwrites the prior attempt's records.

The implementation order is independent of source task numbering and is mandatory:

```text
Task 1 -> Task 2 -> Task 3 -> Task 4 -> Task 8 -> Task 5 -> Task 6 -> Task 7
```

Task 8 remains physically after Task 7 only because generated task ids are append-only. No
Task 7 integration/full-gate work may begin until Task 8's Coherence GatePlan compiler,
transport projection, cursor metadata, and tamper tests are complete.

The conditional loop is part of that graph, not a second scheduler:

```text
campaign-classification/review findings
  -> fixer (if budget remains)
  -> review-spec + review-quality

budget exhausted, required gate failure, worker/infrastructure failure, or human-review interrupt
  -> needs_input
  -> resolve-human(retry) -> dev       (only after a recorded human retry; next attempt, resets fixer budget)
  -> resolve-human(defer|block) -> handoff/escalated
```

Every stage transition is admitted only by the preceding current stage evidence and required
Coherence gate. `RunExecution` remains the evidence writer; its journal/checkpoints carry the
stable `run_id`, stage id, revision, attempt, contract hash, GatePlan hash/version, workspace
identity, parent evidence, and gate result. The `RunExecution` cursor this plan adds (Task 5, Step 5 — today `RunExecution.record()` is a flat keyword-only evidence writer with no cursor and no parent-hash chaining) allocates
monotonic stage identities from its journal/checkpoint tail: a fixer is a new revision that
invalidates the affected stage and descendants, a human retry is the next attempt and never
overwrites prior evidence, and a transport reclaim resumes the same attempt under its fencing
rules. Parallel review results join by canonical reviewer/stage order rather than arrival time.
The terminal result is the existing `TaskResult`; `completed` requires canonical gates,
trace/register/preflight evidence, and `dod_met=True`, while escalated or blocked paths remain
non-completed.

The host mapping is deliberately one-to-many at the adapter boundary and one-to-one at the
authority boundary:

| Host surface | Entry action | Authority and lifecycle rule |
| --- | --- | --- |
| Codex | `.agents/skills/governed-execution/SKILL.md` | Validate safe `run_id`/`task_id`, query Python legal actions, invoke the Python command, and render returned evidence. It never advances a stage from prose or model output. |
| Claude Code | `.claude/commands/governed-execution.md` | Same argv-level command contract and legal-action projection as Codex; no Claude-local journal, retry loop, gate, or consent writer. |
| Pi/FEAT-9 | Pi registration seam (`registerTraceTools` pattern in `pi-ext/factory-watch/src/index.ts`); the `execution-tools.ts` family is created by Task 6 | Same Python command surface and JSON response; host forwards results without interpreting pass/fail or human decisions. The FEAT-9 MCP adapter does not exist yet and is not created by this plan. |
| Direct/Hermes transport | `materialize_transport(...)` | Projects the same compiled GatePlan and stage metadata. Hermes may own durable attempts/heartbeats/reclaim when selected, but cannot alter Coherence stage order or assurance. |

The host entrypoints must support only explicit `legal-actions`, `dispatch`, `progress`, and
`resolve-human` requests against a named run/task. They must refuse missing or unsafe identifiers,
surface `needs_input` unchanged, and report `starts_automatically: false` for handoff. They must
not execute generated implementation tasks, adopt requirements, or launch downstream workflows.

### Task 1: Define the immutable execution contract and worker assignment

**Files:**
- Create: `src/factory/orchestrator/execution_contract.py`
- Create: `tests/unit/orchestrator/test_execution_contract.py`

**Interfaces:**
- Produces: SR-034 backend-neutral contract for one selected task, one workflow version, one workspace, and the configured fixer budget.
- Produces: SR-049 traceable contract hash that can be included in existing `NodeEvent.extra` and run evidence.

- [ ] **Step 1: Write RED tests for canonical hashing and immutability**

```python
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from factory.orchestrator.execution_contract import ExecutionContract, WorkerAssignment
from factory.orchestrator.types import AgentRole


def test_contract_hash_is_stable_and_binds_all_execution_inputs(tmp_path: Path) -> None:
    contract = ExecutionContract.build(
        run_id="run-013",
        task_id="T-013",
        workflow_version="governed-execution/v1",
        workspace=tmp_path / "worktree",
        required_gates=("unit", "full"),
        satisfies=("SR-034", "SR-049"),
        plan_ref="docs/superpowers/plans/plan.md",
        spec_ref="docs/superpowers/specs/spec.md",
        max_fixer_iterations=2,
    )

    assert len(contract.contract_sha256) == 64
    assert contract.contract_sha256 == contract.rebuild_hash()
    assert contract.to_dict()["workspace"] == (tmp_path / "worktree").as_posix()


def test_contract_and_worker_assignment_are_frozen(tmp_path: Path) -> None:
    contract = ExecutionContract.build(
        run_id="run-013",
        task_id="T-013",
        workflow_version="v1",
        workspace=tmp_path,
        required_gates=("unit",),
        satisfies=(),
        plan_ref=None,
        spec_ref=None,
        max_fixer_iterations=1,
    )
    assignment = WorkerAssignment("spec-review", AgentRole.REVIEW, "prompt", tmp_path)

    with pytest.raises(FrozenInstanceError):
        contract.max_fixer_iterations = 2  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        assignment.workspace = Path("other")  # type: ignore[misc]
```

- [ ] **Step 2: Run the RED test**

Run: `rtk uv run pytest tests/unit/orchestrator/test_execution_contract.py -q -o addopts=''`

Expected: collection fails because `factory.orchestrator.execution_contract` does not exist.

- [ ] **Step 3: Implement the exact contract surface**

Add frozen `ExecutionContract` and `WorkerAssignment` dataclasses. `ExecutionContract.build()` must reject blank ids, non-positive `max_fixer_iterations`, duplicate gates or SR ids, and non-absolute workspace paths. Canonicalize a sorted JSON payload with compact separators and hash it with SHA-256. `to_dict()` includes `schema: 1`, `run_id`, `task_id`, `workflow_version`, `workspace`, sorted `required_gates`, sorted `satisfies`, `plan_ref`, `spec_ref`, `max_fixer_iterations`, and `contract_sha256`. `rebuild_hash()` hashes the same payload without trusting the stored digest. `WorkerAssignment` accepts only the four lanes `dev`, `spec-review`, `quality-review`, and `fixer`; it stores the existing `AgentRole`, prompt, and the shared absolute workspace path. Declare the closed lane vocabulary once as `Lane = Literal["dev", "spec-review", "quality-review", "fixer"]` and use it in every signature that takes a lane. `WorkerAssignment.for_lane(contract, lane, workspace)` is the single constructor used by the driver and every host, so the lane→role→prompt mapping exists in exactly one place; the same module documents the stage-id ↔ review-lane mapping (`review-spec` ↔ `spec-review`, `review-quality` ↔ `quality-review`) required by decision 4.

```python
@dataclass(frozen=True)
class ExecutionContract:
    run_id: str
    task_id: str
    workflow_version: str
    workspace: Path
    required_gates: tuple[str, ...]
    satisfies: tuple[str, ...]
    plan_ref: str | None
    spec_ref: str | None
    max_fixer_iterations: int
    contract_sha256: str

    @classmethod
    def build(cls, **values: object) -> "ExecutionContract":
        # Validate and normalize all values before computing the digest.
        normalized = _normalize_contract_values(values)
        digest = _sha256_canonical(normalized)
        return cls(**normalized, contract_sha256=digest)

    def rebuild_hash(self) -> str:
        return _sha256_canonical(_payload_without_hash(self))
```

- [ ] **Step 4: Run focused verification**

Run: `rtk uv run pytest tests/unit/orchestrator/test_execution_contract.py -q -o addopts=''`

Run: `rtk uv run ruff check src/factory/orchestrator/execution_contract.py tests/unit/orchestrator/test_execution_contract.py`

Run: `rtk uv run pyright src/factory/orchestrator/execution_contract.py`

Expected: all commands exit zero.

- [ ] **Step 5: Commit the contract slice**

```bash
git add src/factory/orchestrator/execution_contract.py tests/unit/orchestrator/test_execution_contract.py
git commit -m "feat(orchestrator): define governed execution contract"
```

### Task 2: Bind every worker to one injected execution workspace

**Files:**
- Create: `src/factory/orchestrator/execution_workspace.py`
- Create: `tests/unit/orchestrator/test_execution_workspace.py`
- Modify: `src/factory/orchestrator/pi_backend.py`
- Modify: `tests/unit/orchestrator/test_pi_backend.py`

**Interfaces:**
- Produces: SR-034 host seam for free/Hermes/Pi backends without a second scheduler or allocator.
- Produces: SR-049 workspace identity in worker and checkpoint evidence.
- Produces: the harness-enforced `WritePolicy` (denied roots + declared allowlist) carried by the lease into every backend binding, with deny events as evidence rather than failures (decision 2, 2026-09-11).

- [ ] **Step 1: Write RED tests for one acquire/release and one backend binding**

```python
import tempfile
from pathlib import Path


def test_driver_dependencies_can_bind_all_worker_roles_to_one_lease(tmp_path: Path) -> None:
    owner = RecordingWorkspaceOwner(tmp_path / "execution-worktree")
    factory = RecordingBackendFactory()
    contract = contract_fixture(tmp_path / "execution-worktree")

    with owner.acquire(contract) as lease:
        bound = factory.bind(lease, contract)
        assignments = [
            bound.assignment("dev"),
            bound.assignment("spec-review"),
            bound.assignment("quality-review"),
            bound.assignment("fixer"),
        ]

    assert owner.acquired == ["run-013"]
    assert owner.released == ["run-013"]
    assert {item.workspace for item in assignments} == {lease.path}
    assert factory.bound_paths == [lease.path]
    assert lease.policy.deny_outside_roots == (lease.path.resolve(),)
    assert Path(tempfile.gettempdir()).resolve() in lease.policy.allowed_roots
    assert factory.bound_policies == [lease.policy]
    assert lease.policy.on_denied == "deny-and-evidence"
```

- [ ] **Step 2: Run the RED test**

Run: `rtk uv run pytest tests/unit/orchestrator/test_execution_workspace.py -q -o addopts=''`

Expected: collection fails because the workspace-owner protocol and lease type do not exist.

- [ ] **Step 3: Implement owner and backend-factory protocols without allocation logic**

Define frozen `WorkspaceLease(execution_id, path, policy)`, `WritePolicy(deny_outside_roots, allowed_roots, on_denied)`, `WorkspaceOwner.acquire(contract) -> ContextManager[WorkspaceLease]`, and `BackendFactory.bind(lease, contract) -> BoundExecution` (the frozen wrapper shown below, carrying the unchanged `AgentBackend` as `.backend`). `WritePolicy.on_denied` has exactly one legal value, `"deny-and-evidence"`: the harness refuses the write and the refusal is recorded as evidence; there is deliberately no `"fail-task"` mode (decision 2, 2026-09-11). `deny_outside_roots` is the leased worktree root and `allowed_roots` is the declared carve-out list (session temp dir, tool cache roots, the shared `.git` objects, the transcript dir), so a deny is a rule decision rather than an ad-hoc check. Add `workspace_prompt_suffix(workspace, contract)` so every prompt carries the same absolute path and contract hash. Do not add `create_worktree`, retry, scheduling, or per-role ownership methods. Add `PiBackendFactory(repo_root, extension_path, provider, model)` that constructs a `PiAgentBackend` bound to the supplied workspace path and write policy; retain the existing role-to-scope translation and subprocess behavior in `substrate.agents.backend`. `bind(lease, contract)` returns the frozen `BoundExecution` wrapper: the driver hands `bound.backend` to the existing node seams (`run_dev`, `run_validation`, the review swarm — the unchanged `AgentBackend` protocol) and builds the DEV/fixer prompt through `bound.assignment(lane)`; the review swarm composes its own two lane prompts from the contract and manifest, and the host adapters use the same `assignment` seam, so the lane→role→prompt mapping still has one construction path. No method is added to `AgentBackend` itself.

```python
class WorkspaceOwner(Protocol):
    def acquire(self, contract: ExecutionContract) -> ContextManager[WorkspaceLease]: ...


class BackendFactory(Protocol):
    def bind(self, lease: WorkspaceLease, contract: ExecutionContract) -> BoundExecution: ...


@dataclass(frozen=True)
class BoundExecution:
    """One backend bound to one leased workspace and its write policy."""

    backend: AgentBackend
    contract: ExecutionContract
    workspace: Path
    policy: WritePolicy

    def assignment(self, lane: Lane) -> WorkerAssignment:
        """The only way the driver and hosts build a worker assignment."""
        return WorkerAssignment.for_lane(self.contract, lane, self.workspace)


@dataclass(frozen=True)
class WorkspaceLease:
    execution_id: str
    path: Path
    policy: WritePolicy


def workspace_prompt_suffix(workspace: Path, contract: ExecutionContract) -> str:
    return (
        f"\n\nEXECUTION CONTRACT: {contract.contract_sha256}\n"
        f"SHARED WORKSPACE: {workspace.resolve().as_posix()}\n"
        "All assigned work must stay in this workspace."
    )
```

- [ ] **Step 4: Add backend-binding tests and preserve existing Pi behavior**

Add a fake `WorkspaceOwner` that records acquire/release calls and a fake factory that records every bind path and the `WritePolicy` it was bound with (`bound_paths`, `bound_policies`). Extend `test_pi_backend.py` to assert the factory passes the supplied workspace to `PiAgentBackend`, while existing `AgentRole` and callback tests remain unchanged. Use the existing backend's `session_id` callback as the sole session identity source; do not add a host-generated session id.

- [ ] **Step 5: Verify and commit**

Run: `rtk uv run pytest tests/unit/orchestrator/test_execution_workspace.py tests/unit/orchestrator/test_pi_backend.py -q -o addopts=''`

Run: `rtk uv run ruff check src/factory/orchestrator/execution_workspace.py src/factory/orchestrator/pi_backend.py tests/unit/orchestrator/test_execution_workspace.py tests/unit/orchestrator/test_pi_backend.py`

Expected: all tests pass and the existing Pi backend contract remains green.

```bash
git add src/factory/orchestrator/execution_workspace.py src/factory/orchestrator/pi_backend.py tests/unit/orchestrator/test_execution_workspace.py tests/unit/orchestrator/test_pi_backend.py
git commit -m "feat(orchestrator): bind governed workers to one workspace"
```

### Task 3: Add the fresh-context parallel review swarm

**Files:**
- Create: `src/factory/orchestrator/review_swarm.py`
- Create: `tests/unit/orchestrator/test_execution_review_swarm.py`

**Interfaces:**
- Produces: SR-034 independent spec-compliance and code-quality review invocations using the existing `AgentRole.REVIEW`.
- Produces: SR-049 review session ids and findings as ordinary `NodeEvent` evidence inputs.

- [ ] **Step 1: Write RED tests for concurrency, prompt separation, and session separation**

```python
def test_review_swarm_waits_for_both_fresh_review_sessions() -> None:
    backend = BarrierBackend(
        results=[agent_result("review-spec", "review-session-1"), agent_result("review-quality", "review-session-2")]
    )

    result = run_review_swarm(
        backend=backend,
        task=task_fixture(),
        contract=contract_fixture(),
        manifest={},
        events=[],
    )

    assert {review.lane for review in result.reviews} == {"spec-review", "quality-review"}
    assert {review.session_id for review in result.reviews} == {"review-session-1", "review-session-2"}
    assert result.completed_at > backend.first_started_at
    assert all("prior review output" not in prompt for _, prompt in backend.calls)
```

Add negative tests for a missing session id and duplicate session ids; both must raise a typed `ReviewProtocolError` before the driver can dispatch a fixer.

- [ ] **Step 2: Run the RED test**

Run: `rtk uv run pytest tests/unit/orchestrator/test_execution_review_swarm.py -q -o addopts=''`

Expected: collection fails because `run_review_swarm` and `ReviewProtocolError` do not exist.

- [ ] **Step 3: Implement two independent `AgentRole.REVIEW` calls**

Define frozen `ReviewResult(lane, result, session_id, findings, dod_met)` and `ReviewSwarmResult(reviews, completed_at)`. Give `ReviewSwarmResult.review_for(lane)` a closed-lane lookup that rejects missing or duplicate lanes. Use `ThreadPoolExecutor(max_workers=2)` with one future per lane. Each worker builds its own prompt from the task, manifest, contract, and lane-specific instructions; it receives no other review output and no shared mutable prompt/context object. Convert the incoming event history to an immutable tuple before submitting either worker; review workers may read that snapshot but must not append to the caller's event list. Capture `AgentResult.session_id` through the existing callback and require it to be non-empty. Sort the returned results by the stable lane order `spec-review`, `quality-review`, then reject duplicate session ids. Do not add a new `AgentRole`: decision 4 (2026-09-11) settled this — the two reviews stay prompt-distinguished and are separated in evidence by the `spec-review`/`quality-review` lanes and the canonical stage ids `review-spec`/`review-quality`, with that mapping documented in `execution_contract`.

```python
def run_review_swarm(
    *, backend: AgentBackend, task: Task, contract: ExecutionContract,
    manifest: dict, events: Sequence[NodeEvent],
) -> ReviewSwarmResult:
    event_snapshot = tuple(events)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = {
            lane: pool.submit(
                _run_one_review, backend, lane, task, contract, manifest, event_snapshot
            )
            for lane in ("spec-review", "quality-review")
        }
        reviews = [futures[lane].result() for lane in ("spec-review", "quality-review")]
    session_ids = [review.session_id for review in reviews]
    if len(set(session_ids)) != 2:
        raise ReviewProtocolError("reviewer sessions must be distinct")
    return ReviewSwarmResult(tuple(reviews), datetime.now(timezone.utc))
```

- [ ] **Step 4: Verify no fixer can be called from the swarm**

Keep `run_review_swarm()` limited to review calls and result normalization. The driver in Task 5 owns the next transition. Assert in the test double that no `AgentRole.DEV` call occurs while either review future is unresolved, and that the caller's event list is unchanged until both review futures have returned; append normalized review evidence only in the driver thread after the join.

- [ ] **Step 5: Verify and commit**

Run: `rtk uv run pytest tests/unit/orchestrator/test_execution_review_swarm.py -q -o addopts=''`

Run: `rtk uv run ruff check src/factory/orchestrator/review_swarm.py tests/unit/orchestrator/test_execution_review_swarm.py`

Expected: all review protocol tests pass.

```bash
git add src/factory/orchestrator/review_swarm.py tests/unit/orchestrator/test_execution_review_swarm.py
git commit -m "feat(orchestrator): run fresh parallel review swarm"
```

### Task 4: Implement baseline, campaign, and flaky/regression classification

**Files:**
- Create: `src/factory/orchestrator/execution_campaign.py`
- Create: `tests/unit/orchestrator/test_execution_campaign.py`
- Create: `src/coherence/execution/__init__.py`
- Create: `src/coherence/execution/flaky_registry.py`
- Create: `tests/unit/coherence/test_flaky_registry.py`

**Interfaces:**
- Produces: SR-034 complete required-test campaign, baseline comparison, and regression injection data.
- Produces: SR-034 human-only known-flaky registry read path and one bounded classification rerun.
- Produces: the quarantine discipline (decision 1, 2026-09-11) — every entry carries its curating human (`decided_by`) and `review_after`; at expiry the default action is fix-or-delete, never silent renewal; a deterministic failure introduced by the current change is a regression regardless of any entry; quarantined tests keep running non-blocking with their results recorded and the count surfaced; and genuinely nondeterministic-by-design tests (timing/perf, live services, browser smoke) move to a non-blocking suite instead of being registered.
- Produces: SR-049 persisted classification evidence that distinguishes a gate result from a human registry decision.

- [ ] **Step 1: Write RED tests for baseline and pass-rate comparison**

```python
def test_passing_baseline_and_new_failure_are_classified_as_regression() -> None:
    runner = ScriptedCampaignRunner(
        [snapshot("a", "b"), snapshot("a", "c")]
    )
    campaign = TestCampaign(runner, flaky_registry=EmptyFlakyRegistry())

    baseline = campaign.capture_baseline(contract_fixture())
    outcome = campaign.evaluate_after_dev(contract_fixture(), baseline)

    assert outcome.failed_ids == frozenset({"c"})
    assert outcome.regressions == ("b",)
    assert outcome.pass_rate_gate_passed is False


def test_pre_existing_failure_is_not_injected_as_a_regression() -> None:
    runner = ScriptedCampaignRunner([snapshot("a", "pre-existing"), snapshot("a", "pre-existing")])
    campaign = TestCampaign(runner, flaky_registry=EmptyFlakyRegistry())

    baseline = campaign.capture_baseline(contract_fixture())
    outcome = campaign.evaluate_after_dev(contract_fixture(), baseline)

    assert outcome.regressions == ()
    assert outcome.pre_existing_failures == ("pre-existing",)
```

- [ ] **Step 2: Write RED tests for the known-flaky decision path**

```python
def test_unlisted_failure_gets_one_classification_rerun_and_never_a_fix_retry() -> None:
    runner = ScriptedCampaignRunner([snapshot("a"), snapshot("flaky"), snapshot("a")])
    campaign = TestCampaign(runner, flaky_registry=EmptyFlakyRegistry())

    baseline = campaign.capture_baseline(contract_fixture())
    outcome = campaign.evaluate_after_dev(contract_fixture(), baseline)

    assert outcome.classification_reruns == {"flaky": 1}
    assert outcome.registry_candidates == ("flaky",)
    assert outcome.regressions == ()
    assert outcome.fixer_iterations_consumed == 0
```

- [ ] **Step 3: Implement strict campaign types and no-blind-retry rules**

Define frozen `TestSnapshot(passed_ids, failed_ids, pass_rate)`, `CampaignResult`, and `TestCampaignRunner`. Require the campaign result to contain the full declared test id set and a pass rate in `[0.0, 1.0]`. `TestCampaign.capture_baseline()` calls the runner once before DEV. `TestCampaign` is production code under `src/`, so set `__test__ = False` on it (or name it `ExecutionCampaign`); otherwise pytest emits a `PytestCollectionWarning` for a class whose name starts with `Test` and defines `__init__`, and the driver tests import it directly. `evaluate_after_dev()` compares `baseline.passed_ids - current.passed_ids`, classifies listed ids immediately, and gives each unlisted failed id exactly one bounded classification re-run (the known-flaky-first mechanism dispositioned in `challenge-a10-tradeoff` — **not** `repeatable_policy`/`max_reruns`, which the `challenge-a9-tradeoff` disposition scopes to non-deterministic verification obligations and explicitly rules out of this cycle). A confirmation pass becomes a human-visible registry candidate; a repeated failure becomes a regression. The confirmation run is never sent to DEV as a fix attempt and never increments the fixer budget. Use stable pytest node ids, not test display names.

```python
@dataclass(frozen=True)
class CampaignResult:
    snapshot: TestSnapshot
    regressions: tuple[str, ...]
    pre_existing_failures: tuple[str, ...]
    flaky_ids: tuple[str, ...]
    registry_candidates: tuple[str, ...]
    classification_reruns: dict[str, int]
    pass_rate_gate_passed: bool
    fixer_iterations_consumed: int = 0
```

- [ ] **Step 4: Add the registry tests before implementing the registry**

```python
def test_registry_round_trip_and_human_only_fields(tmp_path: Path) -> None:
    record = register_flaky(
        tmp_path, "tests/test_feature.py::test_eventually_consistent",
        reason="external service is nondeterministic", decided_by="human",
        decided_at="2026-09-10T00:00:00Z", review_after=None,
    )
    assert read_flaky(tmp_path, record.test_id) == record
    assert record.schema == 1


def test_registry_rejects_non_human_or_malformed_records(tmp_path: Path) -> None:
    path = flaky_path(tmp_path, "tests/test_feature.py::test_x")
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"schema": 1, "test_id": "x", "decided_by": "agent"}), encoding="utf-8")

    with pytest.raises(FlakyRegistryError, match="decided_by"):
        read_flaky(tmp_path, "tests/test_feature.py::test_x")
```

- [ ] **Step 5: Implement the accepted registry exactly as decided**

Decision 1 (2026-09-11) accepted this registry, so implement the one-file-per-test path `flaky-tests/<safe-test-id>.json` with schema `1`, `test_id`, `reason`, `decided_by`, `decided_at`, and nullable `review_after`. No separate `owner` key is added: the quarantine entry's owner *is* `decided_by` (the human who curated it) together with `review_after` (its expiry), which is how the discipline in this task's interfaces maps onto the reused `Deferral` shape. Reuse the strict ISO validation and human-decision conventions of `coherence.deferrals.Deferral`. `read_flaky()` is the driver path; `register_flaky()` rejects every `decided_by` other than `human`, validates the safe slug and exact test id, and atomically writes. No driver path calls the writer. If a later human decision changes the path or CLI name, update this task's interfaces and tests before implementation; do not retain both shapes.

- [ ] **Step 6: Verify campaign and registry behavior**

Run: `rtk uv run pytest tests/unit/orchestrator/test_execution_campaign.py tests/unit/coherence/test_flaky_registry.py -q -o addopts=''`

Run: `rtk uv run ruff check src/factory/orchestrator/execution_campaign.py src/coherence/execution/flaky_registry.py tests/unit/orchestrator/test_execution_campaign.py tests/unit/coherence/test_flaky_registry.py`

Expected: baseline, pre-existing failure, single classification rerun, human candidate, and strict registry tests pass.

```bash
git add src/factory/orchestrator/execution_campaign.py src/coherence/execution src/coherence/execution/flaky_registry.py tests/unit/orchestrator/test_execution_campaign.py tests/unit/coherence/test_flaky_registry.py
git commit -m "feat(execution): classify campaigns and known flaky tests"
```

### Task 5: Build the bounded governed driver around existing nodes and gates

Implementation order is `Task 1 -> Task 2 -> Task 3 -> Task 4 -> Task 8 -> Task 5 -> Task 6 -> Task 7`. Task 8 keeps source task number 8 because the generated decomposition is append-only, but its GatePlan/transport contract must be implemented and reviewed before this driver wiring.

**Files:**
- Create: `src/factory/orchestrator/execution_driver.py`
- Create: `tests/unit/orchestrator/test_execution_driver.py`
- Modify: `src/factory/orchestrator/nodes.py`
- Modify: `src/factory/orchestrator/runner.py`
- Modify: `src/factory/orchestrator/execution.py`
- Modify: `src/factory/config.py`
- Modify: `.factory/factory.yaml` — write the decided `governed_execution.max_fixer_iterations: 2` (decision 3)

**Interfaces:**
- Produces: SR-034 single-task DEV -> parallel-review -> fixer-until-clean orchestration using existing nodes and `TaskResult`.
- Produces: SR-034 project-wide fixer budget with explicit retry/defer/block human resolution.
- Produces: SR-049 in-loop canonical trace/register/obligation gate before `TaskResult.dod_met` can be true.
- Produces: a journal-backed `GovernedStageCursor` and `HumanDecisionRequest`/decision-record
  contract for deterministic stage transitions, revision/attempt identity, durable `needs_input`
  pause, and explicit resume.

- [ ] **Step 1: Write RED tests for the happy path and ordering**

```python
def test_driver_returns_existing_task_result_after_clean_fresh_review_cycle(tmp_path: Path) -> None:
    backend = ScriptedGovernedBackend(
        dev=[agent_result("dev-session")],
        reviews=[clean_review("review-spec"), clean_review("review-quality")],
    )
    driver = driver_fixture(tmp_path, backend=backend)

    result = driver.run(task_fixture())

    assert isinstance(result, TaskResult)
    assert result.outcome == "completed"
    assert result.dod_met is True
    assert [event.extra["governed_execution"]["stage_id"] for event in result.events] == [
        "contract-compiled", "preflight", "transport-materialized", "baseline", "dev",
        "validation", "campaign-classification", "review-spec", "review-quality", "review-join",
        "canonical-gates", "handoff",
    ]
    # `fixer` appears only inside a revision after a finding; the happy path has none.
    assert backend.roles == [AgentRole.DEV, AgentRole.REVIEW, AgentRole.REVIEW]
    assert len({sid for sid in backend.session_ids}) == 3
```

Add a test with one finding and a clean fixer cycle; assert the fixer is called only after both initial reviews have returned, and assert the next DEV prompt contains the exact reviewer finding passed through `_run_dev_once(..., feedback=...)` to the existing `run_dev(..., feedback=...)` argument. Add a test where the trace-completeness gate fails; assert `outcome == "escalated"`, `dod_met is False`, and no completed result is emitted. Add a campaign test where `pass_rate_gate_passed=False` and `regressions` is non-empty; assert regression feedback reaches the fixer instead of immediate human escalation. Add a pre-existing validation-failure test with no regression; assert it is surfaced to the human and is not injected as fixer feedback.

- [ ] **Step 2: Write RED tests for budget exhaustion and human decisions**

```python
@pytest.mark.parametrize("decisions", [["defer"], ["block"], ["retry", "block"]])
def test_budget_exhaustion_requires_the_explicit_human_decision(
    tmp_path: Path, decisions: list[str]
) -> None:
    driver = driver_fixture(
        tmp_path,
        backend=always_finding_backend(),
        max_fixer_iterations=1,
        human_decisions=decisions,
    )

    result = driver.run(task_fixture())
    for decision in decisions:
        assert result.outcome == "escalated"
        assert result.events[-1].extra["governed_execution"]["state"] == "needs_input"
        request_hash = result.events[-1].extra["governed_execution"]["request_sha256"]
        result = driver.resume(
            task_fixture(),
            request_sha256=request_hash,
            decision=decision,
            response=f"human decision: {decision}",
            decided_by="human",
        )

    assert result.outcome == "escalated"
    assert result.events[-1].result == NodeOutcome.ESCALATE.value
    decision_events = [event for event in result.events if "human_decision" in event.extra]
    assert decision_events[-1].extra["human_decision"] == decisions[-1]
    if "retry" in decisions:
        retry_event = next(
            event for event in decision_events if event.extra["human_decision"] == "retry"
        )
        assert retry_event.extra["retry_reset_iteration"] == 0
```

For `retry`, assert the decision record resets the budget only after a real human decision; use a finite decision sequence in the test (`retry` followed by `block`) so the fixture cannot loop indefinitely. A human may explicitly issue another retry in a real run, but no retry is automatic. For `defer`, assert a real `Deferral(reason, review_after, decided_at, decided_by)` reaches the injected `DeferralWriter`, whose production adapter delegates to the existing `coherence.register.write.write_deferral` (there is no orchestrator deferral writer today); for `block`, assert no deferral is synthesized. No branch may auto-accept a review finding.

- [ ] **Step 3: Implement the driver transition kernel**

Add `GovernedExecutionDriver` with injected `WorkspaceOwner`, `BackendFactory`, `ExecutionContractFactory`, `GateRunner`, `TestCampaign`, `TransportSelector`, `DeferralWriter`, `HumanReviewGate`, `RunExecution`, the task `manifest`, `repo_root`, `transcript_dir`, canonical `trace_check` and `register_check` callables, and the existing `run_dev`, `run_validation`, `run_completion_preflight` seams. The constructor is keyword-only and binds exactly the attributes the transition kernel below uses — `self.workspace_owner`, `self.backend_factory`, `self.contract_factory`, `self.gates`, `self.campaign`, `self.transport` (the injected `TransportSelector`), `self.deferrals`, `self.human_review`, `self.execution`, `self.manifest`, `self.repo_root`, `self.transcript_dir` — plus the validated `GatePlan` as `self.gate_plan`, and the node seams as `self.run_validation` and `self.run_completion_preflight` (the DEV seam is wrapped by `self._run_dev_once`); no kernel line may reference an undeclared collaborator, and the private `_run_*`, `_record_*`, `_request_human_decision`, `_failure_result`, and `_complete_after_canonical_gates` helpers are methods of this class. Add a frozen `GovernedStageCursor` with `stage_id`, `revision`, `attempt`, `parent_event_sha256`, and `attempt_key`; load its monotonic tail from `RunExecution` before starting and persist every transition through `RunExecution.record()`. The cursor permits only the canonical stage tuple, rejects a skipped or repeated stage *within one `(revision, attempt)` key* while allowing the fixed prefix and the dev→review sequence to repeat under a new attempt or revision key, advances a fixer to a new revision with descendant invalidation and a recorded `fixer` stage, advances a human retry to the next attempt, and keeps a transport reclaim on the same attempt. Compile the contract, run mandatory preflight, materialize the selected transport, acquire one lease, bind one backend to its path, record a baseline, invoke `run_dev(..., max_iters=1)`, run the existing validation node, run the complete campaign, invoke `run_review_swarm`, and only then decide whether a fresh `AgentRole.DEV` fixer is needed. Append every transition as a `NodeEvent` with the stage cursor and canonical gate details. Keep `TaskResult` construction in one return helper so all failure branches set `dod_met=False`.

```python
class GovernedExecutionDriver:
    def __init__(
        self, *, workspace_owner: WorkspaceOwner, backend_factory: BackendFactory,
        contract_factory: ExecutionContractFactory, gates: GateRunner, campaign: TestCampaign,
        transport: TransportSelector, deferrals: DeferralWriter, human_review: HumanReviewGate,
        execution: RunExecution, manifest: dict, repo_root: Path, transcript_dir: Path,
        gate_plan: GatePlan, trace_check: Callable[..., object],
        register_check: Callable[..., object],
    ) -> None:
        ...  # exactly one attribute per parameter, including self.gate_plan

    def run(self, task: Task) -> TaskResult:
        cursor = self.execution.open_cursor(task.id, self.gate_plan)
        return self._run_attempt(task, cursor, attempt_kind="initial")

    def resume(
        self, task: Task, *, request_sha256: str, decision: str,
        response: str, decided_by: str,
    ) -> TaskResult:
        cursor = self.execution.consume_human_decision(
            task.id, request_sha256=request_sha256, decision=decision,
            response=response, decided_by=decided_by,
        )
        events: list[NodeEvent] = []
        self._record_human_decision(decision, cursor, request_sha256, response, events)
        if decision == "retry":
            cursor = self.execution.begin_attempt(cursor, reason="human retry")
            later = self._run_attempt(task, cursor, attempt_kind="human-retry")
            return replace(later, events=events + later.events)
        if decision == "defer":
            self.deferrals.write_from_human_decision(task.id, cursor, response)
        return self._failure_result(task, events, f"human decision: {decision}")

    def _run_attempt(self, task: Task, cursor: GovernedStageCursor, *, attempt_kind: str) -> TaskResult:
        events: list[NodeEvent] = []
        contract = self.contract_factory.for_task(task, cursor=cursor)
        self._record_stage("contract-compiled", cursor, contract, events)
        if not self._run_preflight(task, contract, cursor, events):
            return self._failure_result(task, events, "preflight blocked")
        projection = materialize_transport(
            transport=self.transport.name, contract=contract,
            gate_plan=self.gate_plan, cursor=cursor,
        )
        self._record_stage("transport-materialized", cursor, projection, events)
        with self.workspace_owner.acquire(contract) as lease:
            bound = self.backend_factory.bind(lease, contract)
            baseline = self.campaign.capture_baseline(contract)
            self._record_stage("baseline", cursor, baseline, events)
            fixer_iteration = 0
            feedback: str | None = None
            while True:
                _dev_outcome, dev_event = self._run_dev_once(
                    task, contract, bound, events, fixer_iteration, feedback=feedback
                )
                self._record_stage("dev", cursor, dev_event, events)
                validation_outcome, validation_event = self.run_validation(
                    self.gates, task.id, repo_root=self.repo_root,
                    satisfies=list(task.satisfies), transcript_dir=self.transcript_dir,
                )
                self._record_stage("validation", cursor, validation_event, events)
                campaign = self.campaign.evaluate_after_dev(contract, baseline)
                self._record_stage("campaign-classification", cursor, campaign, events)
                if campaign.flaky_ids or campaign.registry_candidates:
                    self.human_review.surface_campaign_candidates(campaign)
                if campaign.regressions:
                    feedback = format_regressions(campaign.regressions)
                elif not campaign.pass_rate_gate_passed:
                    self.human_review.surface_campaign_block(campaign)
                    return self._request_human_decision(
                        task, contract, cursor, events,
                        "required campaign pass-rate gate failed",
                    )
                elif validation_outcome is not NodeOutcome.PASS:
                    self.human_review.surface_validation_failure(validation_event)
                    return self._request_human_decision(
                        task, contract, cursor, events,
                        "required validation gate failed",
                    )
                else:
                    reviews = run_review_swarm(
                        backend=bound.backend, task=task, contract=contract,
                        manifest=self.manifest, events=events,
                    )
                    self._record_stage(
                        "review-spec", cursor, reviews.review_for("spec-review"), events
                    )
                    self._record_stage(
                        "review-quality", cursor, reviews.review_for("quality-review"), events
                    )
                    self._record_stage("review-join", cursor, reviews, events)
                    feedback = format_findings(reviews)
                if not feedback:
                    result, gate_events = self._complete_after_canonical_gates(
                        task, contract, cursor, events
                    )
                    self._record_stage("canonical-gates", cursor, result.manifest, events)
                    events.extend(gate_events)
                    if result.dod_met:
                        self._record_stage("handoff", cursor, result.manifest, events)
                    return result
                if fixer_iteration == contract.max_fixer_iterations:
                    return self._request_human_decision(
                        task, contract, cursor, events, feedback,
                    )
                self._record_fix_feedback(feedback, events)
                self._record_stage("fixer", cursor, fixer_event(cursor, feedback), events)
                cursor = self.execution.begin_revision(
                    cursor, stage_id="fixer", reason="review or campaign regression"
                )
                projection = materialize_transport(
                    transport=self.transport.name, contract=contract,
                    gate_plan=self.gate_plan, cursor=cursor,
                )
                self._record_stage("transport-materialized", cursor, projection, events)
                fixer_iteration += 1
```

The concrete implementation must keep the above transition ordering, but use the existing node helpers for prompt composition, gate execution, status callbacks, transcripts, and context-limit handling. `validation_outcome` and `campaign.pass_rate_gate_passed` are both required before review or completion. A failed pass-rate gate with identified regressions becomes fixer feedback; a failed pass-rate gate with no regression to inject enters the durable `needs_input` state. A failing required gate returns a non-completed `NodeEvent`; the driver never changes it to pass. `_request_human_decision()` appends an `ESCALATE`/`needs_input` event containing a deterministic `request_sha256`, current stage/revision/attempt, allowed decisions, current input hashes, and the full pending-request record declared in the lifecycle section, embedded under `extra["governed_execution"]["request"]` with its own `record_schema: 2` and `state="pending"`, while the event itself carries `state="needs_input"` for the current stage; it does not synchronously choose or consume a decision. `resume()` accepts only a matching append-only human decision with `decided_by=human` and appends one `human-decision-recorded` `NodeEvent` carrying `extra["human_decision"]` (and `extra["retry_reset_iteration"] == 0` on a recorded retry) before returning; `retry` starts the next attempt and resets the fixer budget, `defer` writes the existing `Deferral`, and `block` writes no deferral. `defer` and `block` return non-completed results that still carry their decision event — no branch returns a result with an empty `events` list. Out-of-worktree writes never enter this kernel as a failure: the lease's `WritePolicy` is handed to every backend binding, the harness denies the attempt, and the denial is recorded as `denied_write` evidence on the current stage. The driver does not synthesize `NodeOutcome.REJECT` for it, does not consume fixer budget, and does not escalate; the deny count is surfaced in the handoff.

`_run_dev_once(task, contract, bound, events, fixer_iteration, *, feedback)` is the kernel's single DEV/fixer entry point: it builds that worker's assignment through `bound.assignment("dev" if fixer_iteration == 0 else "fixer")`, calls the existing `run_dev(bound.backend, ...)` with `feedback` forwarded to `run_dev`'s `feedback=` argument, and returns `(outcome, NodeEvent)`. The kernel itself never composes a prompt or fabricates a session id.

`_complete_after_canonical_gates()` must run the configured project gate names from the fixed `unit`/`integration`/`full` vocabulary through `GateRunner.run_detail()`, then call the existing Python-owned `coherence.trace.cli.cmd_check()` and `coherence.register.cli.cmd_check()` entrypoints (including the SR-049 claim/marker checks exposed by the register review command), and finally call `run_completion_preflight(repo_root, task, transcript_dir, require_review=...)` — its real signature requires those positionals plus the keyword-only `require_review` — for obligation and completion evidence. Record each result as a `NodeEvent` inside the single `canonical-gates` stage envelope with `gate_name="trace-completeness"` for the SR-049 transition; any non-zero canonical check or blocking preflight issue returns `NodeOutcome.ESCALATE`/`dod_met=False`. These are injected Python callables in tests, not host-side reimplementations or a new `trace` gate name.

- [ ] **Step 4: Add config parsing and record the decided budget value**

Add a typed `GovernedExecutionConfig(max_fixer_iterations: int | None)` to `FactoryConfig`. Parse `governed_execution.max_fixer_iterations`; reject zero, negative, boolean, and non-integer values. The human recorded the value as `2` on 2026-09-11 (Status, decision 3), so write `2` into `.factory/factory.yaml` and add a config test proving it is project-wide, not task-local. A governed dispatch must still fail closed with a clear configuration diagnostic whenever the key is absent or invalid — the decided value does not make an unset or malformed config acceptable.

```yaml
governed_execution:
  max_fixer_iterations: 2
```

The value `2` is the human decision of 2026-09-11 (Status, decision 3) and is the value to write into `.factory/factory.yaml`; the earlier illustrative `3` is superseded. The config test must still prove the setting is project-wide rather than task-local, and a governed dispatch must continue to fail closed while the value is unset.

- [ ] **Step 5: Preserve the existing runner as a compatibility path**

Add narrow `run_governed_task(...)` and `resume_governed_task(...)` entrypoints in `runner.py` that construct `GovernedExecutionDriver` from already-created dependencies and leave `run_task`/`run_next` behavior unchanged unless the caller explicitly selects the governed path. Extend `RunExecution` with `open_cursor()`, `record_stage()`, `begin_revision()`, `begin_attempt()`, and `consume_human_decision()` over namespaced `governed_execution` journal/checkpoint data. These methods must enforce the canonical stage tuple, monotonic revision/attempt rules, exact parent-event hashes, and append-only human request/decision matching while remaining compatible with existing checkpoint readers. Do not add a scheduler, retry engine, per-role allocator, or alternate gate implementation.

- [ ] **Step 6: Verify the driver and existing orchestrator suite**

Run: `rtk uv run pytest tests/unit/orchestrator/test_execution_driver.py tests/unit/orchestrator/test_execution.py tests/unit/orchestrator/test_nodes_context_dev.py tests/unit/orchestrator/test_nodes_val_review.py tests/unit/orchestrator/test_runner.py -q -o addopts=''`

Run: `rtk uv run ruff check src/factory/orchestrator/execution_driver.py src/factory/orchestrator/nodes.py src/factory/orchestrator/runner.py src/factory/orchestrator/execution.py src/factory/config.py tests/unit/orchestrator/test_execution_driver.py`

Run: `rtk uv run pyright src/factory/orchestrator/execution_driver.py src/factory/orchestrator/execution_contract.py src/factory/orchestrator/execution_workspace.py`

Expected: all focused and compatibility tests pass; no existing runner test changes its outcome.

```bash
git add src/factory/orchestrator/execution_driver.py src/factory/orchestrator/nodes.py src/factory/orchestrator/runner.py src/factory/orchestrator/execution.py src/factory/config.py tests/unit/orchestrator/test_execution_driver.py
git commit -m "feat(orchestrator): add bounded governed execution driver"
```

### Task 6: Expose Python-owned execution verbs through the existing host adapter

**Files:**
- Create: `src/coherence/execution/cli.py`
- Create: `tests/unit/coherence/test_execution_cli.py`
- Modify: `src/coherence/cli.py`
- Create: `pi-ext/factory-watch/src/execution-tools.ts`
- Create: `pi-ext/factory-watch/test/execution-tools.test.ts`
- Modify: `pi-ext/factory-watch/src/index.ts`
- Modify: `pi-ext/factory-watch/src/tool-catalog.ts`
- Create: `.agents/skills/governed-execution/SKILL.md`
- Create: `.claude/commands/governed-execution.md`
- Create: `tests/unit/codex/test_governed_execution_surface.py`

**Interfaces:**
- Produces: SR-034 `dispatch_task`, `report_worker_result`, and `stream_progress` verbs through the existing FEAT-9/Pi host registration seam.
- Produces: SR-034 human-only flaky registration command; the driver has no registry write capability.
- Produces: SR-049 JSON event/evidence forwarding without host-side gate or trace interpretation.
- Produces: one shared host contract for Codex's `governed-execution` skill and Claude Code's `/governed-execution` command; both call the Python-owned CLI and consume its legal-action/state projection.
- Produces: schema-1 `ExecutionProjection`/handoff payloads with `starts_automatically: Literal[False]`; direct CLI, Pi, Codex, and Claude must consume this same JSON contract.

- [ ] **Step 1: Write RED tests for Python CLI argument validation**

```python
def test_execution_dispatch_requires_safe_run_and_task_ids(capsys: pytest.CaptureFixture[str]) -> None:
    assert execution_main(["dispatch-task", "../escape", "--run-id", "run-013"]) == 2
    assert "safe" in capsys.readouterr().err.lower()


def test_execution_progress_returns_driver_events_verbatim(tmp_path: Path, capsys) -> None:
    result = execution_main(["stream-progress", "run-013", "--project-root", str(tmp_path), "--json"])

    assert result == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["run_id"] == "run-013"
    assert payload["events"] == fake_run_events()


def test_execution_legal_actions_is_the_only_host_transition_projection(capsys) -> None:
    assert execution_main([
        "legal-actions", "--run-id", "run-013", "--task-id", "T-013", "--json",
    ]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["schema"] == 1
    assert payload["run_id"] == "run-013"
    assert payload["task_id"] == "T-013"
    assert payload["starts_automatically"] is False
    assert payload["state"] in {"ready", "needs_input", "completed", "escalated", "blocked"}
    assert isinstance(payload["legal_next_actions"], list)


def test_completed_execution_handoff_cannot_auto_start_downstream_work(capsys) -> None:
    assert execution_main([
        "dispatch-task", "T-013", "--run-id", "run-013", "--project-root", ".", "--json",
    ]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["handoff"]["starts_automatically"] is False
```

- [ ] **Step 2: Implement the Python command surface**

Add an `execution` group to `coherence.cli.GROUPS`. Define frozen schema-1 `ExecutionProjection` and `ExecutionHandoff` serializers whose `starts_automatically` field is typed and emitted as the literal JSON boolean `false`; every execution command uses these serializers. `coherence execution legal-actions --run-id ... --task-id ... --json` is the only host transition projection: it reads the current `RunExecution`/GatePlan evidence, returns the fixed stage state, legal next actions, current hashes, and—when `state=needs_input`—the exact pending request hash and allowed decisions. It never mutates state. `coherence execution dispatch-task` validates the run/task ids, resolves the task, invokes the explicit `run_governed_task` entrypoint, and emits the driver's structured result plus an `ExecutionHandoff` on completion; the handoff always has `starts_automatically=false`. `coherence execution resolve-human --run-id ... --task-id ... --request-sha256 ... --decision-id ... --decision retry|defer|block --response ... --decided-by human --json` validates the current request hash, decision id, current artifact/input hashes, and human actor, appends exactly one decision event, and invokes `resume_governed_task` only for `retry`; `defer` writes the existing `Deferral`, and `block` remains escalated. A repeated identical decision id returns the original decision without appending; a conflicting, stale, or already-consumed decision is rejected. `report-worker-result` accepts one validated worker event, appends it through the existing run-evidence writer, and never marks a task complete. `stream-progress` reads the canonical run journal and emits events in sequence order. Add the accepted `flaky-register <test-id> --reason ... --decided-by human ...` command (decision 1, 2026-09-11); reject all non-human writers and route to `register_flaky()`. Return exit code 0 for a valid payload, 1 for a canonical blocked/escalated result, and 2 for invalid CLI input. Every execution projection and handoff also carries `denied_write_count`, read from the run evidence: it is visibility only and never blocks a transition (decision 2, 2026-09-11).

```python
GROUPS = {
    # existing groups remain unchanged
    "execution": execution_main,
}
```

- [ ] **Step 3: Write RED tests for the Codex skill and Claude Code command contract**

Add text-level contract tests that both entrypoints require a named safe run/task, call
`coherence execution legal-actions` before `dispatch-task`, pass arguments as separate argv
values, render `needs_input` without answering it, and stop when `starts_automatically` is
`false`. The tests must reject host-local retry loops, direct worker process invocation, gate
interpretation, and any second journal/state path, and must require both entrypoints to state that consent, requirement adoption, and downstream handoff are human-only (which is why the literal `consent` assertion below is required rather than forbidden). The Codex skill is
the project-local `.agents/skills/governed-execution/SKILL.md`; the Claude Code entrypoint is
`.claude/commands/governed-execution.md`. Both must state that Python/Coherence is authoritative
and that a human must explicitly authorize retry, defer, block, or downstream handoff.

```python
def test_codex_and_claude_entrypoints_share_the_same_authority_contract() -> None:
    codex = Path(".agents/skills/governed-execution/SKILL.md").read_text()
    claude = Path(".claude/commands/governed-execution.md").read_text()
    for text in (codex, claude):
        assert "coherence execution legal-actions" in text
        assert "starts_automatically: false" in text
        assert "never" in text.lower()
        assert "consent" in text.lower()
```

Text presence is necessary but not sufficient, and the parity test needs a real right-hand side.
The Python test runs `coherence execution legal-actions --run-id <fixture> --task-id <fixture>
--json` through `execution_main`, writes that JSON to a fixture file, and asserts it is
byte-identical to the checked-in expectation; the TypeScript parity test builds the Pi tool with a
runner that executes the **real** Python command (`uv run coherence execution legal-actions …`)
rather than the stub used in Step 5, and asserts the adapter's forwarded text parses to the same
JSON after key sorting. Until that test exists, the "byte-equivalent projection" claim in Step 7 is
an expectation, not a verified property.

- [ ] **Step 4: Implement the Codex and Claude Code entrypoints**

Write the Codex skill as a deterministic host procedure and the Claude Code file as its
slash-command equivalent. Both accept `/governed-execution <run-id> <task-id>`-style input,
validate identifiers, call `coherence execution legal-actions` first, and permit only the
backend-returned action. When the result is `needs_input`, they display the exact request hash
and allowed `retry|defer|block` choices and call `coherence execution resolve-human` only after
the human selects one; they never answer the request themselves. They may call `dispatch-task`,
`stream-progress`, or `resolve-human`; they must not reproduce the driver loop in markdown,
shell, TypeScript, or model instructions. They forward structured JSON and exact blocking
reasons, create no host-local lifecycle state, never infer a transition from a Kanban `done`
card or model response, and never start implementation or downstream workflows automatically.

- [ ] **Step 5: Write RED tests for the thin Pi tools**

```typescript
it("dispatches governed execution through the Python CLI", async () => {
  const calls: string[][] = [];
  const tool = buildExecutionTools({ run: (argv) => { calls.push(argv); return '{"outcome":"escalated"}'; } })
    .find((entry) => entry.name === "execution_dispatch_task");

  const result = await tool!.execute("call-1", { task_id: "T-013", run_id: "run-013" }, undefined, undefined, { cwd: "." });

  expect(calls[0]).toEqual(expect.arrayContaining(["execution", "dispatch-task", "T-013", "--run-id", "run-013"]));
  expect(result.content[0]).toEqual({ type: "text", text: '{"outcome":"escalated"}' });
});

it("forwards the read-only legal-action projection through the Python CLI", async () => {
  const calls: string[][] = [];
  const tool = buildExecutionTools({ run: (argv) => {
    calls.push(argv);
    return '{"state":"needs_input","starts_automatically":false}';
  }}).find((entry) => entry.name === "execution_legal_actions");

  const result = await tool!.execute("call-2", { task_id: "T-013", run_id: "run-013" }, undefined, undefined, { cwd: "." });

  expect(calls[0]).toEqual(expect.arrayContaining(["execution", "legal-actions", "--run-id", "run-013", "--task-id", "T-013"]));
  expect(result.content[0]).toEqual({ type: "text", text: '{"state":"needs_input","starts_automatically":false}' });
});
```

- [ ] **Step 6: Implement and register the host adapter**

Follow `trace-tools.ts`'s `Type.Object` parameter schema and `{content, details}` result shape. Add exactly four execution tools: read-only legal-actions, dispatch, worker-result reporting, and progress streaming. Each tool passes `ctx.cwd`, validated arguments, and the Python command output through unchanged; it never decides pass/fail, writes a flaky record, or fabricates a human decision. Register the tools in `index.ts` and derive their names in `tool-catalog.ts`. The human `resolve-human` operation remains a Python command invoked by the Codex/Claude procedure or an explicit Pi UI action, never an automatic tool transition. The FEAT-9 MCP adapter consumes the same Python-owned command seam; no second MCP server or host-local execution state is created. The Pi tools, Codex skill, Claude Code command, and direct CLI must all produce equivalent legal-action and event projections for the same run/task input.

- [ ] **Step 7: Verify Python and TypeScript adapter contracts**

Run: `rtk uv run pytest tests/unit/coherence/test_execution_cli.py -q -o addopts=''`

Run: `rtk uv run pytest tests/unit/codex/test_governed_execution_surface.py -q -o addopts=''`

Run: `rtk npm test -- --runInBand pi-ext/factory-watch/test/execution-tools.test.ts`

Run: `rtk npm run typecheck --workspace pi-ext/factory-watch`

Expected: invalid arguments are rejected, canonical JSON is forwarded unchanged, the Python
`ExecutionProjection` and `ExecutionHandoff` serializers always emit
`starts_automatically: false`, the direct CLI and Pi legal-actions responses are byte-equivalent
for the same fixture input, and the extension type-checks without introducing a new server.

```bash
git add src/coherence/execution/cli.py src/coherence/cli.py src/coherence/execution/flaky_registry.py tests/unit/coherence/test_execution_cli.py pi-ext/factory-watch/src/execution-tools.ts pi-ext/factory-watch/src/index.ts pi-ext/factory-watch/src/tool-catalog.ts pi-ext/factory-watch/test/execution-tools.test.ts .agents/skills/governed-execution/SKILL.md .claude/commands/governed-execution.md tests/unit/codex/test_governed_execution_surface.py
git commit -m "feat(execution): expose governed driver through host tools"
```

### Task 7: Prove the tracer bullet and run the Coherence gates

**Files:**
- Create: `tests/integration/orchestrator/test_governed_execution_driver.py`
- Modify: `tests/unit/codex/test_coherence_plan_contract.py` only if the plan parser needs a contract fixture update
- Modify: `docs/features/FEAT-013.md` only to link the accepted implementation plan after human adoption

**Interfaces:**
- Produces: SR-034 end-to-end evidence for backend seam, fresh review ordering, fixer bounds, one workspace, explicit human decisions, and host verbs.
- Produces: SR-049 real trace/register/obligation/test-marker gate evidence before a completed `TaskResult`.

- [ ] **Step 1: Write the integration scenario before implementation is declared complete**

```python
def test_governed_tracer_bullet_preserves_authority_and_task_result(tmp_path: Path) -> None:
    driver, backend, gates, trace_check, workspace_owner = governed_fixture(tmp_path)

    result = driver.run(task_fixture(satisfies=("SR-049",)))

    assert result.outcome == "completed"
    assert result.dod_met is True
    assert workspace_owner.acquired_count == 1
    assert workspace_owner.worker_paths == [workspace_owner.path] * 3
    assert backend.review_session_ids == ("review-spec", "review-quality")
    assert trace_check.calls == ["trace-completeness"]
    assert all(
        event.extra["governed_execution"]["contract_sha256"] == result.manifest["contract_sha256"]
        for event in result.events
    )
```

Add separate integration cases for: a failing canonical trace gate, a pre-existing test failure, an unlisted failure that passes its one classification rerun, a real regression, a worker failure, and each human budget decision. The tests must assert the emitted event payloads rather than just final booleans.

Also assert the fixed lifecycle projection: the same `run_id`, stage ids, revision/attempt,
contract hash, GatePlan hash/version, and workspace identity are present across direct and
Hermes projections; review completion joins only after both fresh sessions return; `needs_input`
does not advance to a child; and the Codex skill, Claude Code command, Pi tools, and direct CLI
produce equivalent legal-action responses for one fixture run.

- [ ] **Step 2: Run the tracer bullet with canonical project tooling**

Run: `rtk uv run pytest tests/integration/orchestrator/test_governed_execution_driver.py -q -o addopts=''`

Expected: all integration cases pass with fake workers and no network or real Pi process.

- [ ] **Step 3: Run the feature-scoped Coherence checks**

Run: `rtk uv run coherence trace check --project-root .`

Run: `rtk uv run coherence register check --project-root .`

Run: `rtk uv run coherence register review --all --check-claims --no-ingest --project-root .`

Run: `rtk uv run coherence plan check --run-id FEAT-013 --project-root . --intent .intent/intent.json --spec docs/superpowers/specs/2026-09-08-feat013-governed-execution-driver-design.md --plan docs/superpowers/plans/2026-09-10-feat013-governed-execution-driver-plan.md`

Expected: the plan parser reports task/file/`Produces:` parity; trace and register output is evaluated as canonical evidence. A failed canonical check blocks completion and is reported with its actual diagnostic. Findings whose subject is an artifact outside this run's selected plan and authority spec — for example another plan's tasks under `tasks/`, which is a multi-plan ledger — are not this plan's findings: report them as out of scope under the recorded planning-gate scoping decision (Status, seventh note), rather than treating them as FEAT-013 blockers.

- [ ] **Step 4: Run the full required gate set**

Run: `rtk uv run python -m factory.orchestrator list --repo . --json`

Run: `rtk uv run python -m pytest -q`

Run: `rtk uv run ruff check src tests`

Run: `rtk uv run pyright src`

Expected: commands exit zero, or the handoff records the exact failing gate and remains non-completed. Do not mark SR-034 adopted or modify its requirement record to make a gate pass.

- [ ] **Step 5: Prepare review evidence and stop for human handoff**

Record the plan/spec references, contract hash, event sequence, test-campaign baseline, review session ids, gate details, and any human deferral/decision records in the existing run evidence format. Dispatch a fresh independent plan reviewer and resolve only valid findings. After the plan reviewer is clean, present the exact projection and wait for the human to decide whether to adopt the plan and select a downstream implementation workflow.

```bash
git status --short
git diff --check
```

Expected: only the FEAT-013 plan/spec and explicitly scoped implementation changes are present; no downstream task execution, requirement adoption, consent, merge, or push occurs in this planning run.

### Task 8: Preserve the compiled GatePlan through direct and Kanban transports

This task is a prerequisite for Task 5's driver wiring. Its source task number remains 8 because the generated decomposition is append-only; the implementation order is declared before Task 5 above. GatePlan compilation and validation remain Coherence-owned; this task only carries the already-compiled value through a transport projection.

**Files:**
- Create: `src/coherence/execution/gate_plan.py`
- Create: `tests/unit/coherence/test_execution_gate_plan.py`
- Create: `src/factory/orchestrator/execution_transport.py`
- Create: `tests/unit/orchestrator/test_execution_transport.py`
- Modify: `src/factory/orchestrator/execution_contract.py`
- Modify: `tests/unit/orchestrator/test_execution_contract.py`
- Modify: `src/factory/orchestrator/execution.py` and `tests/unit/orchestrator/test_execution.py` — the `RunExecution` cursor extensions (`open_cursor`, `record_stage`, `begin_revision`, `begin_attempt`) that the projection and tamper tests construct.

Task 8 does **not** touch `src/factory/orchestrator/execution_driver.py`: under the mandated order `Task 8 -> Task 5` that file does not exist yet. The driver-side binding in Step 4 is the contract Task 5's kernel must satisfy; Task 8 covers it with tests against `materialize_transport` and the `RunExecution` cursor.

**Interfaces:**
- Produces: SR-034 Coherence-owned immutable compilation and validation of the canonical workflow-specific `GatePlan`.
- Produces: SR-034 host-neutral transport projection of one already-compiled workflow-specific `GatePlan`; the transport cannot compile or alter it.
- Produces: SR-049 card/event metadata carrying the run id, contract hash, GatePlan hash/version, workflow version, stage id, and attempt.

- [ ] **Step 1: Write RED tests for immutable GatePlan identity and projection metadata**

```python
def test_transport_projection_carries_contract_and_gate_plan_identity(tmp_path: Path) -> None:
    contract = contract_fixture(tmp_path)
    gate_plan = compile_gate_plan(
        workflow_version=contract.workflow_version,
        version="behavior-change@1",
        required_gates=("unit", "full"),
        preflight_policy="mandatory-only",
    )

    bound = contract.with_gate_plan(gate_plan)  # new frozen contract; digest recomputed, never mutated
    cursor = GovernedStageCursor(
        stage_id="transport-materialized", revision=1, attempt=1,
        parent_event_sha256=None,
        attempt_key="feat013/FEAT-013/transport-materialized/r1/a1/v1",
    )
    projection = materialize_transport(
        transport="hermes-kanban", contract=bound, gate_plan=gate_plan, cursor=cursor,
    )

    assert all(card.revision == 1 and card.attempt == 1 for card in projection.cards)

    assert projection.root.run_id == bound.run_id
    assert all(card.contract_sha256 == bound.contract_sha256 for card in projection.cards)
    assert all(card.gate_plan_sha256 == gate_plan.gate_plan_sha256 for card in projection.cards)
    assert all(card.workflow_version == contract.workflow_version for card in projection.cards)
    assert [card.stage_id for card in projection.cards] == [
        "contract-compiled", "preflight", "transport-materialized", "baseline", "dev",
        "validation", "campaign-classification", "review-spec", "review-quality",
        "review-join", "fixer", "canonical-gates", "handoff",
    ]


def test_transport_is_a_projection_not_a_scheduler_or_allocator() -> None:
    assert not hasattr(ExecutionTransport, "schedule")
    assert not hasattr(ExecutionTransport, "retry")
    assert not hasattr(ExecutionTransport, "allocate_worktree")
```

- [ ] **Step 2: Run the RED test**

Run: `rtk uv run pytest tests/unit/orchestrator/test_execution_transport.py -q -o addopts=''`

Expected: collection fails because the Coherence GatePlan compiler, transport projection, and `materialize_transport` do not exist.

- [ ] **Step 3: Implement the transport contract without operational lifecycle**

In `src/coherence/execution/gate_plan.py`, add frozen `GatePlan` plus `compile_gate_plan()`. The compiler canonicalizes the workflow version, the exact `CANONICAL_EXECUTION_STAGES` tuple, the fixed gate names (`unit`, `integration`, `full`), and `preflight_policy` into a SHA-256 identity; reject any missing, extra, duplicated, or reordered stage and reject `ac8-obligation-health` unless its `ac8_decision_ref` is current. In `src/factory/orchestrator/execution_transport.py`, add frozen `TransportCard` and `TransportProjection` values only. `materialize_transport()` accepts a validated GatePlan and returns a deterministic root plus stage-card projection for `direct` and `hermes-kanban`; every card carries `run_id`, `contract_sha256`, `gate_plan_sha256`, `workflow_version`, `stage_id`, `revision`, and the current `attempt`, never a hard-coded attempt. A retry materializes a new immutable projection for the next attempt; a reclaim resumes the same attempt under its fencing rules. The transport imports the Coherence GatePlan and has no compiler, dispatch, durable lifecycle, retry, heartbeat, workspace allocation, or completion-status authority; Hermes remains the operational owner when the selected transport is Hermes Kanban. `ExecutionContract.with_gate_plan(gate_plan)` is the only way a contract learns a GatePlan: it returns a new frozen contract with `gate_plan_sha256`/`workflow_version` bound and `contract_sha256` recomputed by `rebuild_hash()` — the stored digest is never mutated in place, and tests compare cards against the bound contract's digest.

- [ ] **Step 4: Bind the driver to the projection and verify tamper resistance**

Require the driver (Task 5's kernel) to receive the validated Coherence GatePlan before acquiring workers, to materialize the selected transport projection once per revision/attempt — Task 5's kernel re-materializes after `begin_revision` and after `begin_attempt` — and to include that projection's identity in the first `NodeEvent`/`RunExecution.record()` payload of the revision/attempt. Reject a plan/contract hash mismatch before `DEV`; reject a stale/replayed stage cursor, non-monotonic revision/attempt, or mismatched parent-event hash; do not let a transport card or Kanban state alter `GateRunner`, trace, obligation, human-review, or `TaskResult` decisions. Add tests proving direct and Hermes projections have identical canonical stage metadata, a human retry emits `attempt=2` without overwriting `attempt=1`, a fixer emits a new revision with descendant invalidation, and a changed stage/gate list or preflight policy produces a different GatePlan hash.

- [ ] **Step 5: Run focused verification**

Run: `rtk uv run pytest tests/unit/coherence/test_execution_gate_plan.py tests/unit/orchestrator/test_execution_transport.py tests/unit/orchestrator/test_execution_contract.py tests/unit/orchestrator/test_execution.py -q -o addopts=''`

Run: `rtk uv run ruff check src/coherence/execution/gate_plan.py src/factory/orchestrator/execution_transport.py src/factory/orchestrator/execution_contract.py src/factory/orchestrator/execution.py tests/unit/coherence/test_execution_gate_plan.py tests/unit/orchestrator/test_execution_transport.py tests/unit/orchestrator/test_execution_contract.py tests/unit/orchestrator/test_execution.py`

Expected: projection identity, contract binding, tamper rejection, and the existing `RunExecution` behavior pass without adding scheduler or worktree-owner behavior.

```bash
git add src/coherence/execution/gate_plan.py src/factory/orchestrator/execution_transport.py src/factory/orchestrator/execution_contract.py src/factory/orchestrator/execution.py tests/unit/coherence/test_execution_gate_plan.py tests/unit/orchestrator/test_execution_transport.py tests/unit/orchestrator/test_execution_contract.py tests/unit/orchestrator/test_execution.py
git commit -m "feat(orchestrator): preserve gate plans through transports"
```

### Task 9: Add a Hermes-side governed-execution skill

Added by the spec addendum of 2026-09-13 (`docs/superpowers/specs/2026-09-08-feat013-governed-execution-driver-design.md`
§11, AC-10) after implementation was already in progress. Closes the gap the addendum
describes: Hermes was in scope as a worker backend (§1/§2) and as the `hermes-kanban`
transport (Task 8), but had no equivalent to Codex's skill or Claude Code's command for a
human working from a Hermes session to inspect state or issue a `retry`/`defer`/`block`
decision. Depends on Task 6 (the Python CLI this plugin calls) being landed and committed
first; runs after it in execution order, not folded into it.

**Files:**
- Create: `.hermes/plugins/governed-execution/plugin.yaml`
- Create: `.hermes/plugins/governed-execution/plugin.py`
- Create: `.hermes/plugins/governed-execution/__init__.py`
- Create: `.hermes/plugins/governed-execution/README.md`
- Create: `tests/unit/hermes/test_governed_execution_plugin.py`
- Modify: `tests/unit/codex/test_governed_execution_surface.py` — extend the cross-host parity
  assertion (Task 6, Step 3) to include the Hermes plugin's rendered output as a fourth surface.

**Interfaces:**
- Produces: SR-034 AC-10 Hermes host exposure — a Hermes plugin invoking the same
  Python-owned execution command surface as the Codex skill and Claude Code command, with
  the same dispatch/resolve-human capability (not the purely-read-only shape of
  `.hermes/plugins/coherence-plan/` — see the corrected Step 2 note below).
- Produces: one shared host contract extended to four surfaces (direct CLI, Pi, Codex, Claude
  Code, Hermes) all consuming the same `ExecutionProjection`/handoff JSON.

- [ ] **Step 1: Write RED tests for the Hermes plugin**

Follow `.hermes/plugins/coherence-plan/`'s existing test pattern (find its test file under
`tests/unit/hermes/` or wherever the coherence-plan plugin's own tests live — mirror that
location for `test_governed_execution_plugin.py`). Cover: a safe run-id/task-id is required
before any command runs; the plugin calls `coherence execution legal-actions` before
`dispatch-task`; `needs_input` is rendered unchanged, never answered; `resolve-human` is only
invoked after an explicit decision is supplied to the plugin's own entrypoint (never inferred
from a Hermes Kanban `done` card or a model response); and a missing checkout, an unreadable
CLI, or a non-zero CLI exit renders as a blocked message rather than raising into the Hermes
host.

- [ ] **Step 2: Implement the plugin**

Unlike `.hermes/plugins/coherence-plan/plugin.py` (which loads a stdlib-only adapter module by
file path to avoid a heavy package-level import chain in `coherence.planning`), this plugin
invokes the Python CLI by subprocess (`uv run coherence execution legal-actions|dispatch-task|
resolve-human|stream-progress ...`, matching how Task 6's Pi/TypeScript adapter already calls
it) — `coherence.execution`'s package `__init__.py` carries no heavy import chain to route
around, and subprocessing through `uv run` gets the right interpreter/dependencies for a Hermes
install that lives outside this checkout for free, the same guarantee `coherence-plan`'s plugin
earns via its file-path trick. Resolve the project root the same way `coherence-plan`'s plugin
does (`COHERENCE_PROJECT_ROOT`/cwd/deployment-marker fallback) so a Hermes install outside the
checkout still targets the right project. Register one namespaced command
(`governed-execution`) via `ctx.register_command`, following `coherence-plan`'s
`register(ctx)` shape exactly. Unlike `coherence-plan`'s plugin (purely read-only — it only
ever calls a read projection), this plugin has dispatch/resolve-human parity with the Codex
skill and Claude Code command, so `plugin.yaml`'s `tags` must not carry `read-only`; pick
tags that reflect what it actually does (e.g. `execution`, `governed-execution`).

- [ ] **Step 3: Extend the cross-host parity test**

Add the Hermes plugin's rendered `legal-actions` output to the existing fixture-run comparison
in `tests/unit/codex/test_governed_execution_surface.py` (Task 6, Step 3) so all four surfaces
— direct CLI, Pi tools, Codex skill, Claude Code command, Hermes plugin — are asserted
byte-equivalent (after key sorting) for the same fixture run, not just the three Task 6 built.

- [ ] **Step 4: Verify**

Run: `rtk uv run pytest tests/unit/hermes/test_governed_execution_plugin.py tests/unit/codex/test_governed_execution_surface.py -q -o addopts=''`

Expected: the plugin rejects unsafe identifiers, forwards canonical JSON unchanged, never
answers `needs_input` itself, and produces a legal-action projection byte-equivalent to the
other three host surfaces for the same fixture input.

```bash
git add .hermes/plugins/governed-execution/ tests/unit/hermes/test_governed_execution_plugin.py tests/unit/codex/test_governed_execution_surface.py
git commit -m "feat(hermes): add the governed-execution plugin (AC-10)"
```

## Self-review against the reviewed spec

- Boundary and backend seam: Tasks 2, 5, and 6 use existing backend/node/gate surfaces and explicitly exclude scheduler, supervisor, retry engine, allocator, and second MCP server.
- Contract and transport identity: Task 8 compiles and validates GatePlan only in Coherence, then carries that precompiled value through direct/Hermes projections without giving the transport lifecycle or acceptance authority.
- Role mapping and fresh ordering: Task 3 preserves `AgentRole.REVIEW` twice, requires distinct sessions, and Task 5 dispatches the fixer only after both reviews return.
- Existing `TaskResult` shape: Task 1 defines contract values only, and Task 5 returns the existing `TaskResult` type using `NodeEvent` for new evidence.
- No gate bypass and in-loop SR-049 check: Tasks 5 and 7 run canonical gates and fail closed.
- Baseline, pass rate, regressions, and no blind retry: Task 4 plus the Task 5 campaign transition covers every AC-5 branch.
- One execution workspace: Task 2 defines ownership injection and Task 7 asserts one lease and one path.
- Project-wide fixer budget and human retry/defer/block: Tasks 5 and 7 cover all three explicit decisions; the value is the recorded human decision `2` (Status, decision 3).
- AC-1 host verbs: Task 6 adds one Python-owned command surface plus thin Pi, Codex-skill, and Claude-Code adapters; no host interprets gates or creates a second lifecycle state machine, and the plan does not claim that an absent external FEAT-9 server has been modified.
- Deterministic lifecycle: the fixed execution stage graph, canonical GatePlan validation, journal-backed revision/attempt evidence, explicit pending-decision replay rules, parallel-review join, human `needs_input` barrier with `resolve-human`, and `starts_automatically: false` handoff are explicit and are shared by every host and transport.
- Proposed AC-8: not implemented by this plan — SR-034 ships `mandatory-only` preflight, and the obligation/health variant waits on the FEAT-018 supply confirmed by decision 5; the plan does not silently adopt AC-8.
- Known-flaky registry: accepted by decision 1 — Task 4 implements the human-only registry with the quarantine discipline (owner + `review_after`, fix-or-delete at expiry), and nondeterministic-by-design tests move out of the blocking suite rather than being registered.
- Out-of-worktree policy and subroles: decided (decisions 2 and 4) — the harness denies out-of-root writes and records the denial as evidence (never a task failure), and the two reviews stay prompt-distinguished with stage-id/lane evidence; no new `AgentRole` is added.
- AC-10 Hermes host exposure (added 2026-09-13): Task 9 extends Task 6's host-adapter pattern to a fourth surface, a Hermes plugin with the same dispatch/resolve-human parity as the Codex skill and Claude Code command, without changing AC-1's original text or reopening the already-recorded SR-034 consent.

The placeholder scan is clean: the plan contains no `TBD`, `TODO`, or deferred implementation placeholder. The budget value is the recorded decision `2`, and the two items that gate implementation — confirmation of the reviewed spec and consent for `SR-034` — have both been recorded (spec `status: accepted`; `gate-decisions/sr-SR-034.json`), so nothing in this plan is waiting on an unstated assumption.
