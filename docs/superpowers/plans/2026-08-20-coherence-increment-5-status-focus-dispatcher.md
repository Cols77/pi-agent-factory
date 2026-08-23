# Coherence Increment 5: Status, Focus, Dispatcher, and TUI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Provide a deterministic coherence status, session focus, explanation, Pi status widget, and honest intent-routing interface.

**Architecture:** Python owns concurrent read-only probes, precedence, focus storage, and vocabulary explanation. The extension renders structured JSON and a deterministic zero-argument menu. Argument classification has an explicit host-capability gate because the installed Pi API exposes newSession/sendUserMessage, not a direct enum-constrained completion.

**Tech Stack:** Python 3.11+, atomic JSON, argparse, TypeScript, Pi extension, pytest, npm test.

---

## Execution Coordination

- Prerequisites: Increments 3 and 4.
- Parallel after StatusLine is frozen: Python status/focus/explain; TypeScript widget/menu; factory-selfcheck compatibility alias.
- Serial: extension command registration has one owner; argument classifier wiring follows verified Pi API capability.

## File Structure

**Create:** src/coherence/status.py, src/coherence/focus.py, src/coherence/explain.py, .pi/skills/using-coherence/SKILL.md, pi-ext/factory-watch/src/coherence-command.ts, pi-ext/factory-watch/src/coherence-status.ts, tests/unit/coherence/test_status.py, tests/unit/coherence/test_focus.py, tests/unit/coherence/test_explain.py, pi-ext/factory-watch/test/coherence-command.test.ts, pi-ext/factory-watch/test/coherence-status.test.ts.

**Modify:** src/coherence/cli.py, pi-ext/factory-watch/src/index.ts, status-format.ts, mission-control-dashboard.ts, factory-skills.ts, factory-init-command.ts, and their existing tests.

### Task 1: Add a pure status contract

- [ ] **Step 1: Write failing precedence tests.**

Define `StatusLine(source, outcome, summary, produced_by, resolve_cmd: tuple[str, ...] | None,
observation_ref)` and `StatusSnapshot(lines, primary, exit_code)`. Resolver commands use the 2B
ordered tuple contract: each item is one fully substituted command, and order/duplicates are
preserved end-to-end; a semicolon-delimited string is invalid. Use fake probe results to assert:

    interrupted_run > failing_gate > stale_audit > proposed_backlog > nothing_pending

Every line names the producer and resolver command tuple. A stale snapshot must render stale with
its resolver and never current.

- [ ] **Step 2: Implement concurrent probes.**

Implement status_snapshot(project_root) to concurrently run trace check, register check, current run checkpoint, newest audit age, and membership --gate. Each probe returns one StatusLine even on a tool error. Add coherence status and coherence status --json to the group dispatcher.

- [ ] **Step 3: Verify and commit.**

Run:

    rtk proxy uv run python -m pytest tests/unit/coherence/test_status.py tests/unit/system/test_cli.py tests/unit/orchestrator/test_run_cli.py tests/unit/orchestrator/test_status.py -q
    git add src/coherence/status.py src/coherence/cli.py tests/unit/coherence/test_status.py
    git commit -m "feat(coherence): aggregate truthful status"

### Task 2: Add focus and explain

- [ ] **Step 1: Write failing atomic focus tests.**

Test set_focus(session_root, "feat:FEAT-NAV-017"), get_focus, and clear_focus. Invalid refs create no file. Assert the atomic JSON location is sessions/.coherence-focus.json and no repository-tracked file changes. Test explain delegates current vocabulary and rejects unknown values.

- [ ] **Step 2: Implement and wire CLI.**

Add coherence focus <scope-ref>, coherence focus --none, and coherence explain <term-or-id>. Explicit command scopes override session focus. The explain implementation reads the existing vocabulary data only.

- [ ] **Step 3: Verify and commit.**

Run:

    rtk proxy uv run python -m pytest tests/unit/coherence/test_focus.py tests/unit/coherence/test_explain.py -q
    git add src/coherence/focus.py src/coherence/explain.py src/coherence/cli.py tests/unit/coherence
    git commit -m "feat(coherence): add session focus and explain"

### Task 3: Add deterministic extension status and menu

- [ ] **Step 1: Write TypeScript fixtures.**

Mock coherence status JSON and assert coherence-status renders primary and resolve command. Mock no-argument probes and assert coherence-command renders the ranked menu, offers “not that? pick from the menu”, and sends no model message.

- [ ] **Step 2: Implement the bridge.**

coherence-status.ts invokes coherence status --json. coherence-command.ts implements the zero-argument menu only. Register /using-coherence in index.ts, add the widget beside the factory widget, and write the skill routing table without write authority.

- [ ] **Step 3: Verify and commit.**

Run:

    rtk proxy npm test --prefix pi-ext/factory-watch -- coherence-command coherence-status status-format factory-skills skill-prompt
    git add .pi/skills/using-coherence pi-ext/factory-watch/src pi-ext/factory-watch/test
    git commit -m "feat(pi): add coherence status and deterministic menu"

### Task 4: Resolve the direct-classifier capability gate truthfully

- [ ] **Step 1: Verify host support.**

Add an extension test for a direct structured completion accepting the enum:

    UNDERSTAND, VERIFY_CLAIM, CLOSE_GAPS, AUTHOR_REQUIREMENTS,
    BUILD, RECOVER, TRIAGE, TEACH

The test must distinguish this capability from session creation. On the present API it demonstrates absence.

- [ ] **Step 2: Implement the only supported outcome.**

If the test finds a verified direct structured-completion API, implement classify_intent(text) returning intent and optional scope ref, print the classification and menu escape hatch, then dispatch.

If it does not, /using-coherence with an argument returns exit 2 and:

    argument routing requires a Pi structured-completion capability; use the no-argument menu

Do not create a session and describe it as one constrained classification call.

- [ ] **Step 3: Verify and commit.**

Run:

    rtk proxy npm test --prefix pi-ext/factory-watch -- coherence-command
    git add pi-ext/factory-watch/src pi-ext/factory-watch/test .pi/skills/using-coherence
    git commit -m "feat(pi): gate coherence intent classification on host capability"

### Task 5: Rename factory diagnostics and verify Increment 5

- [ ] **Step 1: Update alias tests.**

Test /factory-selfcheck performs current bootstrap diagnostics. Test /factory-doctor prints one deprecation line and forwards. Test factory.orchestrator.run_cli doctor remains run-recovery only.

- [ ] **Step 2: Implement aliases and run final checks.**

Rename the registration in factory-init-command.ts while retaining the old forwarder. Then run:

    rtk proxy uv run python -m pytest tests/unit/coherence tests/unit/system tests/unit/orchestrator -q
    rtk proxy npm test --prefix pi-ext/factory-watch
    rtk proxy uv run ruff check src tests
    rtk proxy uv run pyright

Expected: deterministic work lands regardless of classifier capability; classification is never falsely claimed.

## Plan Self-review

- Covers status, focus, explain, TUI, using-coherence, and doctor renaming.
- Records the current Pi capability limitation as a testable implementation gate rather than inventing an unavailable API.

## Review Amendments

### Approved deterministic-router amendment

This amendment supersedes Task 4 and all direct-Pi-classifier wording above. Create
src/coherence/router.py with Intent, RouteMatch(intent, scope_ref, score), and
route_text(text). Its versioned phrase-to-intent table has threshold 3: extract a valid
scope ref, sum normalised phrase weights, and return a route only for one unique maximum
at least 3. A tie, no match, or below-threshold score returns None.

Add tests/unit/coherence/test_router.py covering each of the eight intents, scope extraction,
normalised case/whitespace, a tie, no matching phrase, and a below-threshold score. Each None
case must open the deterministic menu. coherence-command.ts prints a successful classification
with its menu escape hatch and never calls newSession or any model API for routing.

Run:

    rtk proxy uv run python -m pytest tests/unit/coherence/test_router.py -q
    rtk proxy npm test --prefix pi-ext/factory-watch -- coherence-command

This removes the host-capability blocker: Increment 5 is complete when every input visibly
routes or opens the menu without a model dependency.

Focus is stored atomically in .pi/factory/session-context.json under a coherence_focus key, matching the existing session-policy owner; tests assert it is ignored/untracked. The classifier capability probe is a version-pinned integration fixture against the real Pi SDK export, not the local structural pi-types.ts subset.

Until that fixture proves a direct schema-constrained one-response API, the original exact-one-intent acceptance criterion is externally blocked and Increment 5 cannot be marked complete. Deterministic no-argument routing, status, focus, explanation, and aliases remain independently shippable; argument routing returns the documented refusal.

## Addendum (2026-08-22): progressive assurance — health as a vector

See `docs/superpowers/specs/2026-08-22-coherence-progressive-assurance-design.md` (§6, §10 disposition row for Increment 5, and §13 amendment row 2). Requires this plan's Tasks 1-5, Increment 2B and Increment 4's addendum (`verification_result`) merged first. `coherence.navigate.health.query_health` currently returns one scalar (`health.percent`) beside separately-computed `vcycle_findings` and `freshness_findings` lists the browser must reassemble itself (spec §1 gap 5) -- this addendum adds an eleven-dimension `dimensions` list, each with its own `satisfied`/`expected`/`exempt` counts. Per spec §13's amendment (narrowing §6's original claim to what is actually built): only dimensions 4/5 (`verification_strategy`/`executed_evidence`, backed by `verification_result`) and 11 (`human_review`) are genuinely obligation-backed, each built only from obligations compiled `required`/`blocking` for that scope; dimensions 1, 2, 9 and 10 (`requirement_quality`, `decomposition_allocation`, `nonconformance_closure`, `deferrals_waivers`) are direct queries over existing recorded state (register, trace, `NC-*`, gap data), not obligation-backed. Dimensions 3 and 7 (`implementation_trace`, `evidence_freshness`) reclassify existing `vcycle_findings`/`freshness_health` findings; dimension 8 (`suspect_relationships`) is partial until Increment 6. `human_review` (dimension 11) correctly reports `expected: 0` today -- no `human_review` obligation kind compiles until Increment 6's addendum -- that is the honest answer, not a stub to fill in later.

### Task 6: `compile_health_dimensions` and its `dimensions` key on `query_health`

**Dimension 8 acceptance boundary:** this dimension is explicitly partial after Increment 6 unless
`compile_health_dimensions` concretely consumes `coherence.trace.suspect.edge_validity` and an
integration test proves that its states affect the returned health count. Increment 6's standalone
`edge_validity` classifier and unit tests do not make this health dimension complete.

**Open decision — dimension-8 integration:** the eventual health consumer, prior-state input, and
the integration test that may replace the current proxy remain undecided. This addendum does not
claim dimension 8 is complete or choose that integration boundary.

- [ ] **Step 1: Write the failing tests.**

Add `tests/unit/coherence/test_health_dimensions.py`. Seed a repo with: one SR whose
`compile_obligations(root, "sr:<id>")` produces a required `verification_result` obligation
with a passing recorded validation, one SR with a required `verification_result` obligation
whose validation is missing, one high-assurance SR whose `verification_result` is blocking,
one feature containing one of those SRs, one feature containing none, and one `NC-*` record with
`status: open`. Assert `compile_health_dimensions(root)` returns exactly 11
`DimensionCount(name=..., satisfied=..., expected=..., exempt=...)` entries in the fixed order
`requirement_quality, decomposition_allocation, implementation_trace, verification_strategy,
executed_evidence, validation_scenarios, evidence_freshness, suspect_relationships,
nonconformance_closure, deferrals_waivers, human_review`.

For dimensions 4 and 5, assert the obligation universe is exactly the compiled
`verification_result` obligations whose `requiredness` is `required` or `blocking`: advisory and
`not_applicable` obligations are excluded from both `expected` and `satisfied`. A waived
obligation in that universe is reported through `exempt` and is excluded from both dimension 4/5
numerators as well as the denominator; it must not count as a satisfied strategy or executed
result. Assert `verification_strategy` counts active obligations with a nonblank ordered `resolve_cmd`
tuple (inspect its command items, never call string methods on the tuple),
and `executed_evidence` counts active obligations with `state == "satisfied"`; both use the same
active obligation denominator, not `len(sr_nodes)`. A project-scope `ci_verification` obligation is CI-special: it
remains consumed by the CI gate, but is excluded from dimensions 4/5 because it is not a
per-SR `verification_result` obligation; a passing CI gate must not substitute for per-SR
verification evidence. Assert `nonconformance_closure` reports `expected=1, satisfied=0` for the
one open `NC-*` record; assert `human_review` reports `expected=0` (no `human_review` obligation
kind compiles yet, Increment 6's addendum adds it). Assert `query_health(root)["dimensions"]` is
that same list, JSON-shaped (`[{"name": ..., "satisfied": ..., "expected": ..., "exempt": ...},
...]`), and that `query_health(root)["health"]["percent"]` is still present (not removed, only
demoted).

Add a second fixture repo for `evidence_freshness` (dimension 7): one simulation run whose recorded fingerprints are current (fresh, no finding) and one whose fingerprints no longer match its sources (`EVIDENCE_STALE`), no explainers/diagrams. Assert `compile_health_dimensions` reports `evidence_freshness` as `satisfied=1, expected=2` -- the universe is the two trackable runs, not a bare-SR-id intersection (SR ids never appear as a freshness finding's `subject`; see Step 2's fix below).

Add a third fixture repo, reusing `tests/unit/coherence/`'s conventions (the real directory this new test file lives in -- `tests/unit/coherence/navigate` is not a real path in this repo), to prove the call-count regression this addendum must not reintroduce: reuse (or extend) `tests/unit/system/test_health.py::test_query_health_loads_trace_nodes_once_for_a_multi_member_bundle`'s `monkeypatch.setattr(health.trace_model, "load_nodes", counted_load_nodes)` pattern against a repo with 3+ SRs, and assert `calls == 1` still holds after `compile_health_dimensions` is wired into `query_health` (Step 2 must not reload the graph once per SR).

Run:

    rtk proxy uv run python -m pytest tests/unit/coherence/test_health_dimensions.py -v

Expected: FAIL (ImportError: cannot import name compile_health_dimensions).

- [ ] **Step 2: Implement `compile_health_dimensions` in `src/coherence/navigate/health.py`.**

```python
@dataclass(frozen=True)
class DimensionCount:
    name: str
    satisfied: int
    expected: int
    exempt: int


_DIMENSION_ORDER = (
    "requirement_quality", "decomposition_allocation", "implementation_trace",
    "verification_strategy", "executed_evidence", "validation_scenarios",
    "evidence_freshness", "suspect_relationships", "nonconformance_closure",
    "deferrals_waivers", "human_review",
)

_FRESHNESS_STALE_CODES = ("EVIDENCE_STALE", "EXPLAINER_STALE", "DIAGRAM_STALE")


def compile_health_dimensions(
    root: Path, *, nodes=None, edges=None, validation=None, degraded: list[str] | None = None,
) -> list["DimensionCount"]:
    """Eleven independently-applicable dimensions (spec section 6, narrowed by
    spec section 13 amendment row 2 to match what is actually built): only
    dimensions 4 (verification_strategy), 5 (executed_evidence) and 11
    (human_review) are genuinely obligation-backed. Dimensions 1
    (requirement_quality), 2 (decomposition_allocation), 9
    (nonconformance_closure) and 10 (deferrals_waivers) are direct queries
    over existing recorded state -- register, trace, NC-*, gap data -- not
    obligation-backed; this function does not pretend otherwise. Dimensions 3
    (implementation_trace) and 7 (evidence_freshness) reclassify the existing
    vcycle_health/freshness_health findings -- they are not recomputed here.
    Dimension 8 (suspect_relationships) remains partial after Increment 6
    unless this function concretely consumes coherence.trace.suspect.edge_validity
    with integration tests proving the resulting health count; Increment 6's
    standalone classifier is not sufficient. Until then it reuses REQ_STALE as
    a proxy. Dimension 11 (human_review) correctly
    reports 0/0 until Increment 6 compiles that obligation kind.

    `degraded`, when passed (`query_health` passes its own already-built
    list), receives one message if the human_review computation cannot
    resolve a scope's profile -- it never raises past this function.
    """
    from coherence.policy.compiler import compile_obligations
    from coherence.trace.validation_status import load_validation as _load_validation
    from factory.memory.nonconformance import load_nonconformances
    from substrate.policy.vocabulary import UncompiledPresetError

    if nodes is None:
        nodes = trace_model.load_nodes(root)
    if edges is None:
        edges = trace_model.extract_edges(root, nodes)
    if validation is None:
        validation = _load_validation(root)
    if degraded is None:
        degraded = []
    vcycle = vcycle_health(root, nodes=nodes, edges=edges, validation=validation)
    fresh = freshness_health(root, nodes=nodes, edges=edges)
    gaps = gaps_module.find_gaps(nodes, edges, validation)

    sr_nodes = [n for n in nodes if n.kind == "sr"]
    feat_nodes = [n for n in nodes if n.kind == "feat"]
    task_nodes = [n for n in nodes if n.kind == "task"]
    register = register_module.load_register(root / "requirements")
    register_by_id = {r.id: r for r in register}

    # Dimension 1 (requirement_quality) is a deliberately honest placeholder,
    # not a silently-implied quality gate: `statement`/`domain` are already
    # schema-required non-blank strings (enforced at load time, not here),
    # and this repo has no further recorded content-quality signal for an SR
    # today (fixtures repo-wide use one-letter placeholder statements/domains
    # by convention, so a length/placeholder heuristic here would trivially
    # fail nearly every existing fixture and much real content without
    # measuring anything meaningful). A real criterion needs either a schema
    # field or a project-level convention neither exists yet -- future work,
    # not this addendum's.
    req_quality_ok = len(sr_nodes)
    decomposition_ok = sum(
        1 for f in feat_nodes if any(e.kind == "contains" and e.src == f.id for e in edges)
    )
    impl_no_req = {f.subject for f in vcycle if f.code == "IMPL_NO_REQ"}
    # Dimensions 4/5 share one obligation-derived universe. Only required and
    # blocking verification_result obligations participate; advisory and
    # not_applicable obligations are not denominator slots. The project-scope
    # ci_verification obligation is deliberately excluded: CI proves the
    # project gate, not an individual SR's verification result.
    # Waived obligations are counted only in `exempt`; they are removed before
    # both dimension numerators and the shared denominator are computed.
    verification_candidates = [
        o
        for n in sr_nodes
        for o in compile_obligations(root, f"sr:{n.id}", nodes=nodes, edges=edges)
        if o.kind == "verification_result"
        and o.requiredness in ("required", "blocking")
    ]
    verification_exempt = sum(1 for o in verification_candidates if o.state == "waived")
    verification_obligations = [
        o for o in verification_candidates if o.state != "waived"
    ]
    verification_expected = len(verification_obligations)
    verification_strategy_ok = sum(
        1
        for o in verification_obligations
        if any(command.strip() for command in (o.resolve_cmd or ()))
    )
    executed_evidence_ok = sum(
        1 for o in verification_obligations if o.state == "satisfied"
    )

    # Dimension 6 (validation_scenarios): a genuinely different signal from
    # dimension 5 (executed_evidence, harness pass/fail) -- guide section 5.3
    # keeps verification/validation/freshness distinct, never one boolean.
    # Count SRs referenced by at least one goal whose lifecycle has reached a
    # terminal, recorded evaluation (REACHED/NOT_REACHED), via the goal
    # registry already imported at module level (coherence.goals.registry).
    from coherence.goals.lifecycle import TERMINAL_GOAL_STATES

    goals = load_goals(root)
    validated_by_goal: set[str] = set()
    for goal in goals.values():
        if goal.state in TERMINAL_GOAL_STATES:
            validated_by_goal.update(goal.requirements)
    validation_scenarios_ok = sum(1 for n in sr_nodes if n.id in validated_by_goal)

    # Dimension 7 (evidence_freshness): freshness_health's findings are NEVER
    # subject-keyed by a bare SR id (only run:/explainer:/diag:/code:/feat:
    # prefixes) and only ever appear for a NON-fresh artifact -- a fresh
    # artifact has no finding at all. So the universe cannot be read off the
    # finding list alone; it is reconstructed the same way freshness_health
    # builds it internally (runs + explainers + diag nodes), the same three
    # enumerable collections its EVIDENCE_STALE/EXPLAINER_STALE/DIAGRAM_STALE
    # findings are drawn from. IMPL_STALE's subject is a code: ref from a
    # separate, non-enumerable domain (semantically-invalidated code, derived
    # per-SR-change, not a fixed count of trackable artifacts) -- it is
    # tracked by dimension 3 (implementation_trace)/vcycle instead and
    # deliberately excluded from this dimension's denominator, narrowing the
    # four staleness codes to the three whose universe is actually countable.
    freshness_universe: set[str] = set()
    for run in sim_registry.load_runs(_evidence_dir(root)):
        freshness_universe.add(f"run:{run.run_id}")
    for explainer in _load_explainers(root):
        freshness_universe.add(f"explainer:{explainer.id}")
    for node in nodes:
        if node.kind == "diag":
            freshness_universe.add(f"diag:{node.id}")
    freshness_stale = {
        f.subject for f in fresh if f.code in _FRESHNESS_STALE_CODES
    } & freshness_universe
    evidence_freshness_ok = len(freshness_universe) - len(freshness_stale)

    suspect_proxy = {f.subject for f in vcycle if f.code == "REQ_STALE"}
    try:
        nonconformances = load_nonconformances(root)
    except Exception:
        nonconformances = {}
    nc_closed = sum(1 for r in nonconformances.values() if r.status in ("corrected", "waived"))
    # `waived` is the canonical state wording. Raw `deferred`/`exempt` gap
    # dispositions are counted as waiver evidence; no source or authority is selected here.
    waived_gaps = sum(1 for g in gaps if g.disposition in ("deferred", "exempt"))

    # Dimension 11 (human_review): obligation-backed. Reuse the already-loaded
    # nodes/edges via compile_obligations'/resolve_profile's nodes=/edges=
    # passthrough (Increment 2B) so this loop never reloads the trace graph
    # per SR -- required to keep query_health's existing "load_nodes called
    # once" contract (tests/unit/system/test_health.py). `not_applicable`
    # obligations (every sr: scope under prototype, per Increment 6's
    # addendum) are excluded from both satisfied and expected -- shown
    # elsewhere, never counted here (spec section 6). A repo whose profile
    # cannot yet be compiled (UncompiledPresetError, e.g. an
    # exploration/product-profiled scope) degrades this dimension to 0/0
    # instead of crashing the whole health page.
    human_review_obligations: list = []
    try:
        human_review_obligations = [
            o
            for n in sr_nodes
            for o in compile_obligations(root, f"sr:{n.id}", nodes=nodes, edges=edges)
            if o.kind == "human_review"
        ]
    except UncompiledPresetError as exc:
        degraded.append(f"human_review dimension unresolved: {exc}")
    human_review_obligations = [
        o for o in human_review_obligations if o.requiredness in ("required", "blocking")
    ]
    human_review_exempt = sum(1 for o in human_review_obligations if o.state == "waived")
    human_review_obligations = [o for o in human_review_obligations if o.state != "waived"]

    return [
        DimensionCount("requirement_quality", req_quality_ok, len(sr_nodes), 0),
        DimensionCount("decomposition_allocation", decomposition_ok, len(feat_nodes), 0),
        DimensionCount(
            "implementation_trace", len(task_nodes) - len(impl_no_req), len(task_nodes), 0
        ),
        DimensionCount(
            "verification_strategy", verification_strategy_ok, verification_expected, verification_exempt
        ),
        DimensionCount(
            "executed_evidence", executed_evidence_ok, verification_expected, verification_exempt
        ),
        DimensionCount("validation_scenarios", validation_scenarios_ok, len(sr_nodes), 0),
        DimensionCount("evidence_freshness", evidence_freshness_ok, len(freshness_universe), 0),
        DimensionCount(
            "suspect_relationships", len(sr_nodes) - len(suspect_proxy), len(sr_nodes), 0
        ),
        DimensionCount("nonconformance_closure", nc_closed, len(nonconformances), 0),
        DimensionCount("deferrals_waivers", waived_gaps, len(gaps), 0),
        DimensionCount(
            "human_review",
            sum(1 for o in human_review_obligations if o.state == "satisfied"),
            len(human_review_obligations),
            human_review_exempt,
        ),
    ]
```

Wire it into `query_health`'s return dict (`src/coherence/navigate/health.py::query_health`, already-shipped Increment 3 function): add `"dimensions": [asdict(d) for d in compile_health_dimensions(root, nodes=nodes, edges=edges, validation=validation, degraded=degraded)]` alongside the existing keys -- `query_health` already builds a `degraded: list[str] = []` local before its return dict (used today for `ordering_available`); pass that same list through so a human_review resolution failure lands in the one place readers already look for degraded state. Do not remove `health.percent` -- it stays present for existing readers; only `_render_health`'s first line (Task 7) stops leading with it.

- [ ] **Step 3: Run the tests.**

Run:

    rtk proxy uv run python -m pytest tests/unit/coherence/test_health_dimensions.py tests/unit/system/test_health.py tests/unit/system/test_vcycle_health.py tests/unit/system/test_freshness_health.py tests/unit/system/test_cli.py -q

Expected: PASS; every pre-existing `query_health`/`cmd_health` test still passes (this step is additive-only to the returned dict), including `test_health.py::test_query_health_loads_trace_nodes_once_for_a_multi_member_bundle`'s `calls == 1` assertion (`tests/unit/coherence/navigate` is not a real directory in this repo -- the health test suite actually lives under `tests/unit/coherence/` directly and `tests/unit/system/`; every regression command in this addendum has been corrected to name those real paths).

- [ ] **Step 4: Commit.**

    git add src/coherence/navigate/health.py tests/unit/coherence/test_health_dimensions.py
    git commit -m "feat(health): compile_health_dimensions, the 11-dimension health vector"

### Task 7: Render the worst dimension as the one-line summary

- [ ] **Step 1: Write the failing test.**

`_render_health` is exercised today by `tests/unit/system/test_cli.py::test_health_without_json_flag_prints_human_readable_text` (not a `tests/unit/coherence/navigate` file, which does not exist). Add a new test beside it: seed a repo where one dimension has `satisfied < expected` and every other dimension is fully satisfied, and assert the FIRST line of `_render_health(query_health(root))` names that dimension, not an average across all eleven -- averaging five greens and one red back into a number is exactly the scalar item 5 retires (spec section 6). Add a second test asserting the pre-existing behaviour survives for a payload with no `dimensions` key at all (an older/fixture `query_health`-shaped dict): `_render_health` must fall back to the original percent-based headline, not raise `KeyError`.

- [ ] **Step 2: Implement.**

In `src/coherence/navigate/cli.py::_render_health`, this is a MINIMAL diff: only the headline construction branches on whether `dimensions` is present, and the existing `for cls in h["classes"]:` loop and everything after it (bundles, unbundled, degraded) is untouched, not deleted:

```python
def _worst_dimension(dimensions: list[dict]) -> dict | None:
    shortfalls = [d for d in dimensions if d["expected"] > d["satisfied"]]
    if not shortfalls:
        return None
    return min(shortfalls, key=lambda d: d["satisfied"] / d["expected"] if d["expected"] else 0)


def _render_health(result: dict) -> str:
    h = result["health"]
    dimensions = result.get("dimensions")
    if dimensions:
        worst = _worst_dimension(dimensions)
        if worst is None:
            headline = "health: every dimension fully satisfied"
        else:
            headline = (
                f"health: worst dimension {worst['name']} "
                f"({worst['satisfied']}/{worst['expected']})"
            )
        lines = [headline]
        for dim in dimensions:
            lines.append(f"  {dim['name']}: {dim['satisfied']}/{dim['expected']}")
    else:
        # No dimensions key (older/fixture query_health payload) -- degrade to
        # the original percent-based line rather than raising KeyError.
        lines = [
            f"health: {h['satisfied']}/{h['expected']} SR ({h['percent']}%) "
            f"[dangling {h['dangling']}, deferred {h['deferred']}, proposed {h['proposed']}]"
        ]
    for cls in h["classes"]:
        suffix = f" (exempt {cls['exempt']})" if cls["exempt"] else ""
        lines.append(f"  {cls['name']}: {cls['satisfied']}/{cls['expected']}{suffix}")
    lines.append(f"bundles: {len(result['bundles'])}")
    for b in result["bundles"]:
        counts = b["readiness_counts"]
        lines.append(
            f"  {b['id']}: {b['readiness']} "
            f"({counts['sr_total']} SR, {counts['bound']} bound)"
        )
    unbundled_total = sum(len(v) for v in result["unbundled"].values())
    if unbundled_total:
        lines.append(f"unbundled ({unbundled_total}):")
        for refs in result["unbundled"].values():
            lines.extend(f"  - {ref}" for ref in refs)
    for reason in result["degraded"]:
        lines.append(f"  ! degraded: {reason}")
    return "\n".join(lines)
```

Everything from the `for cls in h["classes"]:` loop onward is copied unchanged from the current implementation -- this task only replaces the headline-construction lines above it.

- [ ] **Step 3: Run the tests.**

Run:

    rtk proxy uv run python -m pytest tests/unit/system/test_cli.py tests/unit/coherence/test_health_dimensions.py -q

Expected: PASS.

- [ ] **Step 4: Commit.**

    git add src/coherence/navigate/cli.py tests/unit/system/test_cli.py
    git commit -m "feat(health): render the worst dimension, not an averaged percent"
