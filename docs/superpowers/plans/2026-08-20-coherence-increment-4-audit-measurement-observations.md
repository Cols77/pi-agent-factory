# Coherence Increment 4: Audit, Measurement, and Observation Adapters Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move coverage assurance and measurement harnesses to coherence, emit validated domain observations, parallelise independent SR reviews deterministically, and consume codemap import-edge overlap.

**Architecture:** Preserve the native HarnessResult/TrialResult and coverage report formats, adapting them to typed ObservationEnvelope payloads rather than flattening them into command text. Audit and measurement move in parallel after their input contracts land; a shared adapter/projection test validates their agreement. Per-SR review dispatch becomes bounded parallel work with the coordinator as the only report/status writer. Audit replaces its private import walker with substrate.codemap and reports missing/renamed test selection separately.

**Tech Stack:** Python 3.11+, concurrent.futures, dataclasses, existing validation harnesses, substrate observations/projections/codemap, pytest, Ruff, Pyright.

---

## Execution Coordination

- **Prerequisites:** Increment 1C codemap/KB APIs, Increment 2 trace/register, and Increment 3 simulation/navigation canonical paths.
- **Parallel:** audit transfer/codemap fixtures, measurement harness transfer, and simulation observation fixtures can run in separate worktrees.
- **Serial:** bounded SR concurrency follows audit runner transfer; shared adapter registry, coherence CLI dispatch, report compatibility, and final gate verification are one integration lane.
- **Shared file rule:** only the integration worker edits coherence.cli, adapter registration, pyproject entry points, and compatibility-test matrix.

## File Structure

**Create:**

- src/coherence/audit/ canonical coverage modules plus observations.py
- src/coherence/measurement/ canonical harness modules plus observations.py
- src/coherence/simulation/observations.py
- tests/unit/coherence/test_observation_adapters.py
- tests/unit/coherence/test_audit_parallel.py

**Modify:**

- src/factory/coverage/{scope,imports,audit,gate,report,runner,cli,__main__}.py
- src/factory/validation/{harness,sim_harness,playwright_harness,pipeline,report,scorer_registry,assertions,cli,__main__}.py
- src/coherence/{cli,__main__}.py
- tests/unit/coverage/* and tests/unit/validation/*

### Task 1: Move audit and cut over to codemap overlap

- [ ] **Step 1: Write old/new audit parity and selection tests.**

For existing feature fixtures compare audit JSON, consolidate states, gate outcome, and human report from factory.coverage and coherence.audit. Add a binding-test path that no longer exists and require:

    {"ok": false, "reason": "binding test selection missing", ...}

which is distinct from an existing test with zero overlap. Re-run every current Python import fixture and assert substrate.codemap.compute_overlap has the same truth values as the old private walker.

- [ ] **Step 2: Move audit modules and add a compatibility wrapper.**

Move coverage scope/audit/gate/report/runner/cli to coherence.audit. Replace factory.coverage with warning forwarding modules. In coherence.audit import OverlapResult/compute_overlap only from substrate.codemap; factory.coverage.imports remains a legacy shim but no audit code imports it.

- [ ] **Step 3: Verify codemap audit cutover.**

Run: rtk proxy uv run python -m pytest tests/unit/coverage/test_scope.py tests/unit/coverage/test_imports.py tests/unit/coverage/test_audit.py tests/unit/coverage/test_cli.py -q

Expected: unchanged existing results plus explicit missing-selection findings.

- [ ] **Step 4: Commit.**

    git add src/coherence/audit src/factory/coverage tests/unit/coverage
    git commit -m "refactor(coherence): migrate audit to codemap overlap"

### Task 2: Move measurement harnesses and add native observation payloads

- [ ] **Step 1: Write contract fixtures.**

For a passing, failing, interrupted, and invalid harness result assert:

    envelope = measurement_observation(result, inputs, artifacts)
    assert envelope.facts["schema"] == "measurement/v1"
    assert envelope.outcome == expected

Assert typed facts preserve metric_value, passed, trials, artifacts, and raw references without embedding raw output. Machine and agent_compact projections must have identical outcome, diagnostic codes, and artifact refs; invalid/unknown cannot project to pass.

- [ ] **Step 2: Move harness modules.**

Move harness, sim_harness, playwright_harness, pipeline, report, scorer_registry, assertions, cli, and __main__ to coherence.measurement. Retarget pipeline configuration to substrate.config and register calls to coherence.register. Keep factory.validation document validators in substrate/factory adapters from Increment 1B; do not move them again.

- [ ] **Step 3: Implement adapters.**

Implement coherence.measurement.observations and coherence.simulation.observations using the Increment 1 PayloadRegistry. Register named schemas measurement/v1 and simulation-run/v1. Persist or reference raw output through ArtifactRef only; adapters never decide policy from a compact projection.

- [ ] **Step 4: Verify harness and adapter suites.**

Run:

    rtk proxy uv run python -m pytest tests/unit/validation tests/unit/simulation tests/unit/coherence/test_observation_adapters.py -q
    rtk proxy uv run pyright

Expected: old/new harness results agree and every adapter validates its native facts.

- [ ] **Step 5: Commit.**

    git add src/coherence/measurement src/coherence/simulation/observations.py src/factory/validation tests/unit/validation tests/unit/coherence/test_observation_adapters.py
    git commit -m "refactor(coherence): migrate measurement observations"

### Task 3: Add audit observations and bounded deterministic per-SR review

- [ ] **Step 1: Write controlled concurrency tests.**

Use a fake backend with a barrier and active-worker counter. For three independent SRs assert max active workers is greater than one and no greater than --max-workers; require nonpositive values to fail argument validation. Assert pre-existing verdicts launch no worker, one worker failure yields the current degraded semantics, and two runs with differing completion order produce byte-identical sorted audit/report JSON.

- [ ] **Step 2: Implement serial coordinator plus bounded workers.**

Add --max-workers to coherence audit run, defaulting from an explicit configuration policy. Phase 0 scope/overlap, resume checks, consolidation, and gate remain serial. Submit only missing SR verdicts to a bounded executor; each worker constructs its own PiAgentBackend and atomically writes verdicts/<SR>.json. The coordinator collects futures, sorts SR IDs, appends deterministic tool failures, and is the sole writer of status/report artifacts.

- [ ] **Step 3: Emit audit observations.**

Adapt completed audit reports and per-SR verdicts to audit/v1 envelopes with feature/SR/snapshot refs, typed states, diagnostics, and report ArtifactRefs. A workflow failure produces fail/unknown according to the existing gate state, never a synthetic pass.

- [ ] **Step 4: Run audit suite.**

Run:

    rtk proxy uv run python -m pytest tests/unit/coverage/test_runner.py tests/unit/coverage/test_gate.py tests/unit/coverage/test_cli.py tests/unit/coherence/test_audit_parallel.py tests/unit/coherence/test_observation_adapters.py -q

Expected: concurrency is bounded, resume works, and report ordering is deterministic.

- [ ] **Step 5: Commit.**

    git add src/coherence/audit tests/unit/coverage tests/unit/coherence/test_audit_parallel.py tests/unit/coherence/test_observation_adapters.py
    git commit -m "feat(audit): parallelise deterministic SR review"

### Task 4: Expose canonical coherence groups and verify envelopes

- [ ] **Step 1: Add console group tests.**

Add audit and measurement to coherence.cli GROUPS. Test python -m coherence audit audit FEAT-001 and python -m coherence measurement check with fixture argv, plus old factory module invocations warning and forwarding.

- [ ] **Step 2: Run full Increment 4 verification.**

Run:

    rtk proxy uv run python -m pytest tests/unit/coverage tests/unit/validation tests/unit/simulation tests/unit/coherence -q
    rtk proxy uv run python -m pytest -m unit -q
    rtk proxy uv run ruff check src tests
    rtk proxy uv run pyright

Expected: audit/measurement behaviour is compatible; envelope and compact projection facts agree; complete unit suite passes.

- [ ] **Step 3: Commit.**

    git add src/coherence src/factory tests
    git commit -m "feat(coherence): expose audit and measurement groups"

## Plan Self-review

- Covers TN-09 parallel SR auditing, TN-13 codemap overlap, and remaining audit naming while retaining test/simulation domain semantics.
- Limits parallel execution to independently owned workers and keeps all durable audit report assembly serial and deterministic.

## Review Amendments

Process execution stays factory-owned: factory validation gate runners execute pytest/Playwright and return native results; coherence.measurement owns HarnessResult/TrialResult schemas, readers, reports, and adapters only. Add test-run/v1, experiment/v1, and gate-run/v1 adapters beside measurement/v1, simulation-run/v1, and audit/v1; each content-hashes raw output artifacts.

The audit worker policy is config key audit.max_workers with default 4 and CLI --max-workers override. write_verdict_atomically(run_dir, sr_id, verdict) is the only worker write; coordinator alone writes audit.json, report.json, status transitions, and ordered tool_failures. The adapter registry and test_observation_adapters.py are integration-owned. Increment 4 production work follows Increment 3.

## Addendum (2026-08-22): progressive assurance — profile-aware verification-contract validation

See `docs/superpowers/specs/2026-08-22-coherence-progressive-assurance-design.md` (§10 disposition
row for Increment 4, and §13's `{python}`-substitution correction) and
`docs/superpowers/plans/2026-08-22-coherence-increment-2b-progressive-assurance-foundation.md`
(the `Obligation` contract and `coherence.policy.compiler.compile_obligations` this addendum
extends). Requires this plan's Tasks 1-4, Increment 2B, and Increment 3B's canonical obligation
views merged first. Increment 2B remains the compiler/contract prerequisite; Increment 3B is
required because the audit surface consumes its canonical obligation-view projection. Increment
6B's dogfood slice consumes the `verification_result` kind this addendum adds.

**Unresolved review-contract decisions (not closed by this addendum):** the human-review
identity field remains undecided (`reviewer` versus `reviewed_by`), and it is also undecided
whether that evidence belongs inside `verification_result`, inside `human_review`, or in a
shared contract. This addendum must not hard-code either field name or invent a second,
independent review contract. The verification helper below therefore owns only the recorded
validation result and declared harness; the review-identity cases remain pending until those
decisions are made.

**Note on the real CLI this addendum wires into:** as of this addendum, audit still lives at
`src/factory/coverage/cli.py` (Increment 4's Tasks 1-3, which move it to `coherence.audit`, land
in this same plan before Task 5 below runs). Its `run` subcommand's real flags are `feat`
(positional), `--provider`, `--model`, `--run-id`, `--no-gates` — there is no `--full-sweep` flag
on `run` anywhere in this codebase (`--full-sweep` is `validate_task_requirements`'s *keyword*
argument, a different layer entirely — Increment 2B Task 1). Step 3 below is written against these
real flags, once Tasks 1-3 have renamed the module to `coherence.audit`.

### Task 5: Compile `verification_result` and gate auto-rerun on it

- [ ] **Step 1: Write the failing obligation test.**

Add to `tests/unit/coherence/policy/test_compiler.py` (created by Increment 2B): seed an SR with a
binding (`harness` set, non-null) and no recorded validation, compile obligations for `sr:<id>`
under `profile: high_assurance`, and assert a `verification_result` obligation comes back
`requiredness == "blocking"` and `state == "open"`. Seed a second SR under `profile: prototype`
whose `coherence.trace.validation_status.load_validation` entry is `state="passed", stale=False`,
and assert its `verification_result` obligation is `state == "satisfied"` (prototype's contract is
pass/fail only — no extra fields). Seed a third SR under `profile: high_assurance` with the same
 passing, non-stale validation entry but without a declared harness, and assert its
`verification_result` obligation is still `state == "open"` with a reason naming the missing
harness. Do not add a reviewer-identity test until the unresolved review-contract decisions above
select the field and obligation ownership.
Assert the same scope under `profile: prototype` is `requiredness == "required"`, never `blocking`
(D16: only `high_assurance` blocks on this kind).

Run:

    rtk proxy uv run python -m pytest tests/unit/coherence/policy/test_compiler.py -k verification_result -v

Expected: FAIL (`StopIteration` — no `verification_result` obligation is emitted for `sr:*` scopes
yet).

- [ ] **Step 2: Extend `compile_obligations`.**

In `src/coherence/policy/compiler.py`, add an `elif scope_ref.startswith("sr:")` branch alongside
the existing `task:` branch. For a non-project scope, `compile_obligations` must ensure `nodes`
and `edges` are loaded at most once when the caller did not provide them, pass those same objects
to `resolve_profile`, and pass them unchanged to every obligation helper. The branch must call
`_verification_result_obligation(root, scope_ref, profile, nodes=nodes, edges=edges)` with the
same preloaded graph objects; helpers must not reload the trace graph. The helper reads
`coherence.trace.validation_status.load_validation(root)`, looks up the SR id via
`coherence.register.register.load_register`, and computes `state`/`reason` from more than pass/fail
once `profile == "high_assurance"`:

```python
def _sr_node_path(sr_id: str, *, nodes) -> Path | None:
    """Resolve an SR's actual file from preloaded trace nodes.

    Match by node kind and frontmatter id; never guess ``requirements/<sr_id>.md``.
    The caller owns graph loading; this helper never reloads nodes.
    """
    node = next((n for n in nodes if n.kind == "sr" and n.id == sr_id), None)
    return node.path if node is not None else None


def _verification_result_obligation(
    root: Path, scope_ref: str, profile: str, *, nodes, edges,
) -> Obligation:
    from coherence.register import register as register_module
    from coherence.trace.validation_status import load_validation

    sr_id = scope_ref.partition(":")[2]
    sr_path = _sr_node_path(sr_id, nodes=nodes)
    status = load_validation(root).get(sr_id)
    passed = status is not None and status.state == "passed" and not status.stale
    reason_extra = None
    if passed and profile == "high_assurance":
        # guide §5.3: this addendum checks only a declared harness. Whether
        # human-review identity is part of this obligation or human_review is
        # intentionally unresolved; do not read either proposed field name.
        register = {r.id: r for r in register_module.load_register(root / "requirements")}
        req = register.get(sr_id)
        if req is None or req.binding is None or req.binding.harness is None:
            passed, reason_extra = False, "binding declares no harness"
    requiredness = "blocking" if profile == "high_assurance" else "required"
    reason = reason_extra or (
        "harness-validated result recorded" if passed
        else "no passing, non-stale validation result recorded"
    )
    return Obligation(
        id=f"ob:verification_result:{scope_ref}",
        scope_ref=scope_ref,
        kind="verification_result",
        requiredness=requiredness,
        reason=f"{profile} requires {reason} for {sr_id}",
        source_policy=profile,
        state="satisfied" if passed else "open",
        resolve_cmd=(
            (f"coherence register bind ...; rerun validation for {sr_path.name}",)
            if sr_path is not None
            else ("coherence register bind ...; rerun validation (SR trace node not found)",)
        ),
    )
```

`edges` is accepted even though this SR-local helper does not traverse relationships; accepting it
and forwarding the same object from `compile_obligations` preserves the shared preloaded-graph
contract and prevents a future caller from adding a second graph load. Mirror the
`_task_justification_obligation` helper's constructor keyword set exactly, so Increment 3B's
canonical `coherence.navigate.obligations` view renders it identically to every other kind with no
special-casing. The review-identity field and whether it is evaluated here or by `human_review`
remain open decisions; do not implement either choice in this addendum.

- [ ] **Step 3: Policy-bound, bounded auto-rerun.**

`coherence audit run` (real flags: `feat --provider --model --run-id --no-gates`, per this
addendum's header note) gains two flags: `--policy-bound` and `--max-reruns <N>` (default `10`).
Without `--policy-bound`, both flags are inert and behaviour is byte-identical to before this
addendum (an SR with an already-recorded verdict is always skipped — Task 3 Step 2's existing
resume semantics).

With `--policy-bound` set: for each SR whose verdict is **already recorded**
(`run_dir/verdicts/<sr_id>.json` exists), check `coherence.policy.compiler.compile_obligations(root,
f"sr:{sr_id}")` for its `verification_result` obligation. An SR is skipped (not resubmitted) only
when **both** (a) that obligation reports `state == "satisfied"` **and** (b) its verdict file
exists — checking the compiled obligation's `state` alone is not enough, because
`verification_result.state` is derived from `coherence.trace.validation_status.load_validation`
(harness-validation results), a store distinct from `run_dir/verdicts/<sr_id>.json` (the
coverage-audit AI-verdict worker's own durable state, this plan's Task 2/3). An SR can pass harness
validation while never having had an audit verdict recorded at all; checking `state` alone would
silently skip resubmitting it, a fail-open path against invariant-kernel rule 1 ("missing evidence
is `unknown`, never treated as passing"). Requiring the verdict file to *also* exist closes that
path: an SR with no verdict file is always (re)submitted regardless of harness-validation state.

An SR with a *missing* verdict file was already going to be submitted by Task 3 Step 2's existing
"submit only missing SR verdicts" logic, with or without `--policy-bound` — this flag only changes
whether an SR with a recorded verdict gets **resubmitted**.

`--max-reruns <N>` bounds the *policy-bound resubmission* set specifically (guide §9.4:
"automatic executable reruns obey profile time, cost and side-effect limits"; §4.2's
`automation.rerun_max_seconds`/`rerun_max_cost_class` concept, which this repo has no concrete
runtime-cost model to enforce yet — `substrate.freshness.recipes.ResolutionClass.repeatable_policy`
is the real marker this rerun already runs under, but it is a fingerprint-authority tag today, not
a carrier of time/cost fields, so this addendum does not invent config keys nothing else reads).
After computing the resubmission set (verdict exists, obligation not satisfied), sort SR ids and
cap the set at the first `N`; the remainder are left with their existing (stale) verdict for this
run and reported as `skipped_by_max_reruns` in the coordinator's audit report, not silently
dropped. `--max-reruns 0` disables policy-bound resubmission entirely (equivalent to omitting
`--policy-bound`, but explicit). SRs with no verdict file at all are never subject to this cap —
they are always submitted, as they always were.

- [ ] **Step 4: Run the tests.**

Run:

    rtk proxy uv run python -m pytest tests/unit/coherence/policy/test_compiler.py tests/unit/coherence/test_audit_parallel.py -v

Expected: PASS; the pre-existing (non-`--policy-bound`) audit-run behaviour from this plan's Task
3 is unchanged.

- [ ] **Step 5: Commit.**

    git add src/coherence/policy/compiler.py src/coherence/audit tests/unit/coherence/policy/test_compiler.py tests/unit/coherence/test_audit_parallel.py
    git commit -m "feat(audit): verification_result obligation and --policy-bound auto-rerun"
