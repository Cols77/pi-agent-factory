# Coherence Increment 7: Unified Long-Run Surface Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Present factory runs, audits, measurements, simulations, and experiments through one status protocol and mission-control surface while preserving every native durable store and raw artifact reference.

**Architecture:** coherence.runs adapts existing checkpoint, journal, audit, simulation, and measurement records into a source-discriminated RunStatus pointing to ObservationEnvelope/artifact references. It never merges or overwrites source stores. coherence.status and the extension consume the same service. Notifications are extension-owned and deduplicated by immutable producer/run/terminal-observation identity, not timestamp.

**Tech Stack:** Python 3.11+, dataclasses, JSONL/JSON readers, substrate observations, TypeScript Pi extension, pytest, npm test.

---

## Execution Coordination

- Prerequisites: Increment 4 domain observation adapters and Increment 6 decision/inbox status.
- Parallel after RunStatus freezes: factory/audit/measurement/simulation adapter units; TypeScript renderer after the contract; source-specific fixtures can be built independently.
- Serial: runs service/status integration after all adapters; completion notification is last because it depends on stable terminal identities.

## File Structure

**Create:** src/coherence/runs/{__init__,model,store,service,transport,factory_adapter,audit_adapter,measurement_adapter,simulation_adapter,experiment_adapter}.py, tests/unit/coherence/test_runs.py, tests/unit/coherence/test_run_adapters.py, pi-ext/factory-watch/test/coherence-mission-control.test.ts.

**Modify:** src/coherence/status.py, factory/orchestrator/{execution,journal,run_cli,run_state,status}.py readers only as needed, coherence/{audit,measurement,simulation} adapters, pi-ext/factory-watch/src/{mission-control-dashboard,status-format,index}.ts, related existing tests.

### Task 1: Freeze source-discriminated RunStatus

- [ ] **Step 1: Write model fixtures.**

Define:

    RunStatus(
      producer="factory" | "audit" | "measurement" | "simulation" | "experiment",
      run_id="...",
      state="running" | "interrupted" | "passed" | "failed" | "unknown",
      observation_ref="obs:...",
      artifacts=(ArtifactRef(...),),
      resume_cmd="...",
      updated_at="...",
    )

Reject missing producer/run_id/ref, state outside enum, duplicate artifact refs, and a terminal run lacking an observation reference. Assert sorting is producer/run-id deterministic.

- [ ] **Step 2: Implement model and pure store protocol.**

Create frozen RunStatus plus a RunSource Protocol returning status rows. No writer API is exposed. Add tests proving the model does not inspect mtimes or modify an artifact.

- [ ] **Step 3: Verify and commit.**

Run:

    rtk proxy uv run python -m pytest tests/unit/coherence/test_runs.py -q
    git add src/coherence/runs tests/unit/coherence/test_runs.py
    git commit -m "feat(coherence): define unified run status"

### Task 2: Implement independent source adapters

- [ ] **Step 1: Write one fixture per durable source.**

Cover factory session checkpoint/JSONL, coverage report, measurement report, simulation registry run, and experiment observation. Each asserts native identifier/outcome/artifact refs/resume command are retained and malformed source produces unknown with diagnostic, not a pass.

- [ ] **Step 2: Implement adapters.**

Implement factory_run_status, audit_run_status, measurement_run_status, simulation_run_status, and experiment_run_status. Read only existing locations such as sessions/.factory-runs/by-session, coverage-reviews, validation reports, and simulation registry/evidence. Attach existing observation refs; do not synthesize raw artifacts or centralise data.

- [ ] **Step 3: Verify and commit adapter streams.**

Run:

    rtk proxy uv run python -m pytest tests/unit/coherence/test_run_adapters.py tests/unit/orchestrator/test_execution.py tests/unit/orchestrator/test_journal.py tests/unit/orchestrator/test_run_cli.py tests/unit/simulation/test_sim_registry.py tests/unit/validation/test_report.py tests/unit/coverage/test_cli.py -q
    git add src/coherence/runs tests/unit/coherence/test_run_adapters.py
    git commit -m "feat(coherence): adapt durable run sources"

### Task 3: Integrate status, dashboard, and deduplicated notification

- [ ] **Step 1: Write service and UI tests.**

Assert list_run_statuses aggregates/sorts sources, status displays the same primary condition, and the dashboard renders source-specific rows. Test terminal notification writes a session-local dedupe key:

    (producer, run_id, terminal_observation_id)

and fires once across polls even if source mtime changes; a later terminal observation may notify once.

- [ ] **Step 2: Implement service and extension integration.**

coherence.runs.service aggregates RunSource implementations. coherence.status reads it. Update mission-control dashboard/status-format/index to discriminate producers rather than assuming pipeline rows. Persist notification keys under sessions only; ctx.ui.notify is invoked only after a new immutable terminal tuple.

- [ ] **Step 3: Verify and commit.**

Run:

    rtk proxy uv run python -m pytest tests/unit/coherence/test_runs.py tests/unit/coherence/test_run_adapters.py -q
    rtk proxy npm test --prefix pi-ext/factory-watch -- mission-control-dashboard status-format coherence-mission-control
    git add src/coherence/status.py src/coherence/runs pi-ext/factory-watch tests/unit/coherence
    git commit -m "feat(coherence): unify long-run mission control"

### Task 4: Verify Increment 7

- [ ] **Step 1: Run complete source and static checks.**

Run:

    rtk proxy uv run python -m pytest tests/unit/coherence tests/unit/orchestrator tests/unit/simulation tests/unit/validation tests/unit/coverage -q
    rtk proxy npm test --prefix pi-ext/factory-watch
    rtk proxy uv run ruff check src tests
    rtk proxy uv run pyright

Expected: one status protocol and dashboard reach every source; raw artifacts remain reachable through refs.

## Plan Self-review

- Preserves existing stores and adds only projections/adapters, meeting the unified long-run requirement without a new event database.

## Review Amendments

RunStatus additionally has diagnostics: tuple[RunDiagnostic, ...] and terminal_observation_id: str | None; malformed source records return state unknown plus a diagnostic and no fabricated terminal identity. Per-producer adapters are the exact separate modules listed above and may run in parallel; service.py is the sole integration registry owner. coherence reads substrate/coherence artifacts only: factory exposes its checkpoint/journal data through the existing substrate-compatible read adapter introduced in Increment 1B, never through a coherence import of factory.

## Addendum (2026-08-22): progressive assurance — profile-controlled rerun and resolve-command display

See `docs/superpowers/specs/2026-08-22-coherence-progressive-assurance-design.md` (section 10 disposition row for Increment 7). Requires this plan's Tasks 1-4, Increment 4's addendum (`verification_result`, policy-bound `--policy-bound`/`--max-reruns` auto-rerun), and Increment 6's `human_review` addendum merged first. Increment 6 is required because Task 5 consumes `human_review` obligations in the same status assembly path.

### Task 5: `RunStatus.blocking_obligation` and honest `resume_cmd` display

#### Internal requirement-ID carrier contract

The source-adapter boundary uses one frozen, internal `RunStatusInput` carrier before
service assembly constructs the public `RunStatus`:

    RunStatusInput(
      producer, run_id, state, observation_ref, artifacts, resume_cmd, updated_at,
      diagnostics=(), terminal_observation_id=None,
      requirement_ids=(),
    )

`requirement_ids` is an immutable `tuple[str, ...]` of the native requirement IDs. The
simulation adapter MUST copy `coherence.simulation.registry.Run.requirements` into that
field verbatim (including no added `sr:` prefix); adapters whose native records expose
no requirement list pass an empty tuple. Adapters return `RunStatusInput`, never a
partially assembled `RunStatus`. `service.py` is the only owner that reads
`requirement_ids`, computes the three obligation fields, and constructs the frozen
`RunStatus`; `requirement_ids` is internal carrier data and is not a `RunStatus` field or
serialized JSON key. The service sorts IDs only for deterministic obligation selection
and never mutates the native `Run` or the carrier.

#### Concrete carrier and adapter-rewiring contract

The following is the file-level contract for this addendum; an adapter must not construct
the public status object as an intermediate step:

- `src/coherence/runs/model.py` defines the frozen `RunStatusInput` shown above and keeps
  `RunStatus` as the public, obligation-enriched type. `RunStatusInput` has no
  `blocking_obligation`, `blocking_obligation_resolve_cmd`, or `rerun_allowed` fields.
- `src/coherence/runs/store.py` changes `RunSource` to expose
  `iter_status_inputs() -> Iterable[RunStatusInput]`. It does not expose a writer and does
  not perform service assembly.
- `src/coherence/runs/{factory_adapter,audit_adapter,measurement_adapter,simulation_adapter,experiment_adapter}.py`
  keep the existing per-source function names (`factory_run_status`, `audit_run_status`,
  `measurement_run_status`, `simulation_run_status`, and `experiment_run_status`) but
  change each return annotation and return value to `RunStatusInput`. The simulation
  adapter is the only one that currently populates `requirement_ids`; the other four
  return `requirement_ids=()`.
- `src/coherence/runs/service.py` is the only file that converts an input: its private
  assembly helper accepts one `RunStatusInput` and returns one frozen `RunStatus`, and
  `list_run_statuses()` applies that helper after collecting every source's inputs. No
  adapter imports or calls the assembly helper.
- `tests/unit/coherence/test_run_adapters.py` asserts the five adapters return carrier
  instances and preserve native fields; `tests/unit/coherence/test_runs.py` owns the
  input-to-public-status and obligation-selection assertions.

#### Canonical serializer/transport contract

Create `src/coherence/runs/transport.py` with the sole public JSON entrypoint
`serialize_run_statuses(statuses: Iterable[RunStatus]) -> dict[str, object]`. It returns
`{"runs": [...]}` in service sort order. Each row includes the public fields, including
`blocking_obligation`, `blocking_obligation_resolve_cmd`, `rerun_allowed`, and
`resume_cmd`; a Python `None` `resume_cmd` is always emitted as JSON `null`, never omitted.
The structured `Obligation.resolve_cmd` tuple is preserved as a JSON array (or `null`),
and the internal `requirement_ids` carrier is omitted. `coherence.status --json` calls
this entrypoint, and the extension test fixture consumes its payload shape; no second
serializer may be maintained in the extension.

When a source has no resume command, the cross-layer fixture in
`pi-ext/factory-watch/test/coherence-mission-control.test.ts` must start from a row with
`resume_cmd: null`, retain a non-null `blocking_obligation_resolve_cmd` array, and render
the obligation/resolve-command UI while rendering no resume-command label, control,
`undefined`, empty command, or stale resume value. The fixture must first render a row
with a resume command and then rerender the `null` row, so stale state is covered. The
dashboard renders each array item as a separate command item; it does not join the tuple
into a shell string or execute it. This is a transport/display projection only and does
not decide command portability.

- [ ] **Step 1: Write the failing test.**

Add to `tests/unit/coherence/test_runs.py`: construct a `RunStatus` for a `failed` simulation run
whose native record (`coherence.simulation.registry.Run.requirements: list[str]`) names
`["SR-DOGFOOD-001"]` (a seeded SR with a `high_assurance` profile override), and assert
`service.py`'s status assembly attaches `blocking_obligation` naming the open `verification_result`
obligation id (Increment 4's addendum) when one exists for that scope, and `None` when every
requirement resolves to a `prototype` profile with nothing blocking. Seed a second run whose
`requirements` names two SRs, only one of which has an open blocking obligation, and assert
`blocking_obligation` deterministically names that one (Step 2 below fixes the ambiguous
one-run-many-SRs mapping this field had). Assert `rerun_allowed` is `True` only when the attached
obligation's `resolve_cmd` is exposed as the same `blocking_obligation_resolve_cmd`, and that field
is `None` when no blocking obligation exists. Assert the attached obligation's
`kind == "verification_result"` — never for a `kind == "human_review"` blocking
obligation, which needs a human decision, not an automatic rerun (Increment 4's `--policy-bound`
mechanism only ever reruns `verification_result`-backed harness validation; it does not and cannot
rerun a human review). Assert constructing two different `RunStatus` instances from the same
adapter data via `service.py` never raises `dataclasses.FrozenInstanceError`.

The positive `rerun_allowed` assertion must also seed every runtime prerequisite: policy-bound
mode is enabled, the winning SR's `run_dir/verdicts/<sr_id>.json` exists, the evidence recipe is
classified as `ResolutionClass.repeatable_policy`, and the remaining `max_reruns` budget is
positive (`reruns_used < max_reruns`). Add separate negative assertions for each missing
prerequisite, including `--max-reruns 0` and an exhausted budget. A `human_review` winner must
remain `rerun_allowed == False` even when all of those prerequisites and a non-empty resolve
command are present.

Run:

    rtk proxy uv run python -m pytest tests/unit/coherence/test_runs.py -k blocking_obligation -v

Expected: FAIL (`TypeError: RunStatus() got an unexpected keyword argument 'blocking_obligation'`).

The adapter/service/serialization contract is also required: seed a simulation `Run` whose
native `requirements` are `["SR-B", "SR-A"]`, assert the simulation adapter returns a
`RunStatusInput.requirement_ids` value of `("SR-B", "SR-A")`, assert service assembly uses
that carrier to select the deterministic obligation, and serialize the resulting status.
The JSON must contain `blocking_obligation`, `blocking_obligation_resolve_cmd`,
`rerun_allowed`, and `resume_cmd` with their public values, must omit the internal
`requirement_ids` carrier, and must round-trip the absent `resume_cmd` as JSON `null`.
The resolve-command JSON value is an array because the source contract is
`tuple[str, ...] | None`; the test must not flatten it into a string.
Add an end-to-end status/JSON/UI contract test using that same fixture: status assembly
and its JSON output must expose the same obligation ID, resolve command, rerun boolean,
and `resume_cmd: null`, while the dashboard renders the obligation and resolve command
and does not render a missing resume command as `undefined`, an empty command, or a stale
value. This test crosses the service serializer and the TypeScript dashboard fixture;
it is not satisfied by separate model-only assertions.

- [ ] **Step 2: Implement.**

Add three fields to `RunStatus` (`src/coherence/runs/model.py`), all with defaults so every
existing constructor call in the adapters keeps working unchanged:
`blocking_obligation: str | None = None`,
`blocking_obligation_resolve_cmd: tuple[str, ...] | None = None`,
`rerun_allowed: bool = False`. `blocking_obligation_resolve_cmd` is the winning obligation's
structured `Obligation.resolve_cmd` with the same tuple type; it is distinct from `resume_cmd`,
which resumes the native run. `RunStatus` is frozen
(Task 1) — the helper below computes all three values BEFORE constructing each `RunStatus`
and passes them into the constructor directly (the safer, more local fix over
`dataclasses.replace` on an already-built instance, since `service.py` already builds each row
from adapter data in one place rather than mutating a finished object).

In `service.py`'s status assembly (the sole integration registry owner per the Review Amendments
above), for each row being assembled, resolve the run's OWN requirement ids -- not a single
`sr:<id>` scope, since `coherence.simulation.registry.Run.requirements` (the only native store that
exposes this today) is a `list[str]`, not one SR id:

The service supplies the rerun inputs from the owning audit context, not from the display command:
`policy_bound` is the active `--policy-bound` mode; `verdict_files[req_id]` is the expected
`run_dir/verdicts/<req_id>.json`; `repeatable_policy[req_id]` is true only when the evidence
recipe has `ResolutionClass.repeatable_policy`; and `max_reruns`/`reruns_used` are the coordinator's
configured cap and already-admitted policy-bound reruns. Missing context is false/absent and must
never make `rerun_allowed` true.

```python
def _blocking_obligation(
    root: Path,
    requirement_ids: tuple[str, ...],
    *,
    policy_bound: bool,
    verdict_files: Mapping[str, Path],
    repeatable_policy: Mapping[str, bool],
    max_reruns: int,
    reruns_used: int,
) -> tuple[str | None, tuple[str, ...] | None, bool]:
    """Deterministic run -> obligation mapping: a run's native record may name
    several requirements (Run.requirements: list[str]); this compiles
    obligations for every one, sorted by (scope_ref, obligation id), and
    surfaces the FIRST blocking, unsatisfied verification_result/human_review
    obligation found, returning both its id and resolve_cmd -- a single scalar
    field can only name one. This is a
    deterministic "first, sorted" pick, not the full blocking set; a future
    increment can widen the field to a list if one id proves insufficient.
    Only verification_result and human_review are considered -- NOT
    ci_verification, a project-level obligation this per-run field must not
    surface (every run in a repo would otherwise show the same
    project-wide blocking id, which is not what a reviewer is asking this
    field for).
    """
    from coherence.policy.compiler import compile_obligations

    candidates = []
    for req_id in sorted(requirement_ids):
        for ob in compile_obligations(root, f"sr:{req_id}"):
            if (
                ob.kind in ("verification_result", "human_review")
                and ob.requiredness == "blocking"
                and ob.state != "satisfied"
            ):
                candidates.append((req_id, ob))
    if not candidates:
        return None, None, False
    candidates.sort(key=lambda item: (item[1].scope_ref, item[1].id))
    req_id, winner = candidates[0]
    # This is an eligibility projection, not permission to execute a command. Every
    # prerequisite is required: policy-bound mode is enabled; the distinct durable
    # verdict file exists; the evidence recipe is repeatable_policy; and the bounded
    # rerun budget is not exhausted. human_review is excluded by kind even when its
    # resolve_cmd is non-empty.
    rerun_allowed = (
        winner.kind == "verification_result"
        and policy_bound
        and verdict_files.get(req_id) is not None
        and verdict_files[req_id].is_file()
        and repeatable_policy.get(req_id, False)
        and max_reruns > 0
        and reruns_used < max_reruns
        and bool(winner.resolve_cmd)
    )
    return winner.id, winner.resolve_cmd, rerun_allowed
```

A run whose native record exposes no requirement-id list at all (factory/audit/measurement/
experiment runs today -- only the simulation adapter's `Run.requirements` provides one) passes an
empty tuple and gets `(None, None, False)`, i.e. all three fields stay at their default -- this addendum
changes nothing for a project that has not adopted `high_assurance` anywhere, and nothing for a
producer this mapping does not (yet) cover.

Extend `pi-ext/factory-watch/src/mission-control-dashboard.ts` (already touched by this plan's
Task 3) to extend the RunStatus view type with
`blocking_obligation_resolve_cmd: readonly string[] | null`. Render each resolve-command item
beside the resume command when both are present; when `resume_cmd` is `null`, omit only the
resume UI and retain the obligation/resolve-command UI.
Label it plainly as the resolve command, not a cost estimate -- `substrate.policy.obligation.
Obligation` has no cost field (time, dollar, or otherwise) to display; a prior draft of this step
called this a "cost note," which this addendum retracts as unsupported by the actual contract. If
a real rerun-cost-bound field is ever added (Increment 4's addendum considered and declined this,
citing the same absence -- see its Step 3), this label can be revisited then.

- [ ] **Step 3: Run the tests.**

Run:

    rtk proxy uv run python -m pytest tests/unit/coherence/test_runs.py tests/unit/coherence/test_run_adapters.py -q
    rtk proxy npm test --prefix pi-ext/factory-watch

Expected: PASS.

- [ ] **Step 4: Commit.**

    git add src/coherence/runs pi-ext/factory-watch/src/mission-control-dashboard.ts tests/unit/coherence/test_runs.py
    git commit -m "feat(runs): profile-controlled blocking_obligation and honest resolve-command display"

### Approval-dependent decisions left open

This resolution round does not decide whether `test_marker` or course-trace obligations belong
in the shared progressive-assurance taxonomy, whether a future `RunStatus` needs a `reviewer`
field (or its ownership/serialization), or whether `Obligation.resolve_cmd` is portable enough
to display or execute across shells and platforms. Those remain explicit approval-dependent
decisions for the relevant future increment. This plan only carries the structured command tuple,
serializes it without flattening, and displays it without execution.
