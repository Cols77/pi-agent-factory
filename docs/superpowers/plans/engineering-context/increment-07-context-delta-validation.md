# Increment 7 — Context Delta + Freshness Reconciliation (Implementation Plan)

**Status:** Draft for written review. Assumes locked D1–D9 (SCC browser sole human surface; no Obsidian; freshness as a maintained property).
**Source phase:** Engineering Context spec §37 **Phase 7 — Context Delta**, spec §28–§31, and HLR-09 (freshness).
**Landing repo:** pi-agent-factory (+ optional index) + cool_physical_ai_project (checkpoints).
**Sub-agents:** dev=`pi -p prompts/increment-07-dev.md`, review=`pi -p prompts/increment-07-review.md`.

## Goal

Close the human mental-model gap while making **artifact freshness a maintained engineering property**.

Increment 7 SHALL deliver:

1. deterministic `/catchup <feature>` — what changed since the developer's last checkpoint;
2. goal-aware requirement status;
3. dependency-driven change-impact resolution;
4. transitive invalidation of dependent engineering artifacts;
5. authority-aware refresh policy;
6. automatic restoration of safe derived/generated artifacts;
7. automatic validation rerun where allowed and practical;
8. routing of semantic implementation repairs through the existing DEV workflow;
9. deterministic freshness reconciliation;
10. feature-level **freshness closure** reporting.

This increment implements HLR-09 using the existing trace, fingerprint, evidence and system-query
substrates. It MUST NOT build an independent staleness framework.

### SP-B boundary

SCC SP-B is an active upstream implementation dependency.

This increment MUST NOT modify SP-B-owned implementation before SP-B lands.
Browser/UI work defined here is performed only on the landed SP-B + Inc 6 substrate.
The domain/freshness architecture is independent of SP-B implementation details.

## Reuse (do not rebuild)

- **Freshness/stale detection:** `factory.freshness` + `factory.evidence.reconcile` already
  fingerprint code and flag stale evidence — this is the change-impact engine's core.
- **Goal-aware status:** Inc 2 Task 7 derived `requirement_validation`.
- **Change history / commits:** `factory.system.feature.recent_changes` (Inc 1) + `git_ops`.
- **Run/sim evidence:** Inc 3.
- **Human views:** Inc 6 views; `/catchup` output is a rendered **"Catch me up"** view in the
  SCC browser (a new additive tab/view), presented at REVIEW.

## Global constraints (Program §6 + D3)

- Additive; existing verbs untouched. `/catchup` and a `catchup` subcommand are new.
- Developer checkpoints are recorded, never inferred (spec §31 `developer_checkpoint.commit`).
- "Changed since" is computed from recorded checkpoints + git history + goals/history — never from
  an LLM summarizing the past. The delta is deterministic.
- Introduce a derived index NOW only if `query_goal_history`/`recent_changes` prove slow on the
  real repo; otherwise keep on-demand (spec §33 SQLite optional). If built, it must be rebuildable
  from canonical artifacts (AC-10).

## File structure (additive)

| File | Responsibility |
|---|---|
| `src/factory/commands/catchup.py` | `/catchup` handler + `factory catchup` CLI. |
| `src/factory/delta/__init__.py` `compute.py` `checkpoint.py` | delta computation + checkpoint store read/write. |
| `pi-ext/factory-watch/src/system-catchup-view.ts` | **"Catch me up"** view in `/system` (additive tab). |
| `pi-ext/factory-watch/test/system-catchup-view.test.ts` | render tests. |
| `src/factory/trace/validation_status.py` (extend additive) | `VALIDATED/VERIFICATION_STALE/REGRESSED` derivation. |
| `src/factory/system/queries.py` (extend additive) | `query_catchup`. |
| `src/factory/system/cli.py` (extend additive) | `catchup` subcommand; optional `index` build. |
| `tests/unit/delta/test_compute.py` `test_checkpoint.py` `tests/unit/commands/test_catchup.py` | tests. |

## Task 1: Developer checkpoints

**Interfaces:**
```python
@dataclass(frozen=True) class Checkpoint: feature: str; commit: str; reviewed_at: str
def save_checkpoint(pi_dir: Path, cp: Checkpoint) -> None
def load_checkpoint(pi_dir: Path, feature: str) -> Checkpoint | None   # missing = no review yet
```
- [x] **Step 1: Failing tests** — write→read round-trip (`.pi/checkpoints.json`); missing feature
  returns `None` (legitimate, not an error); malformed file degrades rather than crashes.
- [x] **Step 2: Implement** minimal JSON store under `.pi/` (canonical-only, not evidence).
- [x] **Step 3:** full suite + lint + commit.

## Task 2: Delta computation

**Interfaces:**
```python
@dataclass(frozen=True) class ContextDelta:
    feature: str; since_commit: str
    prs_merged: list[str]; requirements_changed: list[str]
    adrs_added: list[str]; scenarios_added: list[str]
    goals_reached: list[str]; goals_regressed: list[str]
    metric_changes: list[dict]      # [{metric, from, to, regression?}]
    new_open_items: list[str]
def compute_delta(root, feature, since_commit) -> ContextDelta
```
- [x] **Step 1: Failing tests** — from a seeded git history + goals/history + sim runs, produce the
  spec §31 / §9.4 delta (`2 PRs merged, goal reached, metric 87%→95%, new concern false-reacquisition↑`).
  Assert metric regression is flagged.
- [x] **Step 2: Implement** — compose:
```python
def compute_delta(root, feature, since_commit):
    return ContextDelta(
      prs_merged=git_ops.prs_since(root, since_commit, paths=feature_files),
      requirements_changed=git_diff_requirements(root, since_commit),
      adrs_added=[a for a in load_adrs(root) if authored_after(a, since_commit)],
      scenarios_added=simulation.new_scenarios_since(root, since_commit),
      goals_reached=goals_transitioned(root, "REACHED", since_commit),
      goals_regressed=goals_transitioned(root, "REGRESSED", since_commit),
      metric_changes=metric_deltas(metric_history, since_commit),
      new_open_items=open_questions_since(root, since_commit),
    )
```
- [x] **Step 3:** full suite + lint + commit.

## Task 3: `/catchup` + `query_catchup`

- [x] **Step 1:** `/catchup FEAT-NAV-017` loads the checkpoint, computes `compute_delta`, upgrades
  the checkpoint to HEAD, and (at REVIEW) presents via Inc 5/Inc 6 surfaces. Deterministic text block
  matching spec §31 wording.
- [x] **Step 2:** `query_catchup` exposes it in the claim/freshness plumbing for agent (Inc 4) use.
- [x] **Step 3:** render the delta as an additive **"Catch me up"** view in the SCC browser
  (system-page.ts, on top of SP-B/Inc 6), emulating the spec §31 / §9.4 block:

```
Since your last review:
Requirements       +1 changed
Design decisions   +1
Implementation     3 PRs merged
Goals              1 reached
Regressions        1
Metrics            reacquisition_rate 82% -> 91%
```

  It renders *computed* `ContextDelta` fields only (never an LLM summary of the past), via the
  existing claim/freshness render helpers. `system-page.ts` is edited additively, after Inc 6.
- [x] **Step 4:** TS vitest + `uv run python -m pytest -q` + lint green; commit.
- [ ] **Step 3:** full suite + lint + commit.

## Task 4: Goal-aware requirement status (additive, spec §28–§30)

- [ ] **Step 1:** extend Inc 2 `requirement_validation` to emit:
  - `VALIDATED` — all goals REACHED and code unchanged since latest evidence;
  - `VERIFICATION_STALE` — code affecting the requirement changed since latest evidence
    (reuse `freshness`/`reconcile` fingerprint);
  - `REGRESSED` — a formerly-REACHED goal is now below target;
  - `VERIFICATION_PENDING` — goals exist, none reached;
  - and keep v1 behaviour when the requirement has no goals.
- [ ] **Step 2: Failing tests** — a goal goes REACHED→REGRESSED and the requirement status follows
  (spec §29 "validated requirement whose goal regressed"); a code change after validation marks
  `VERIFICATION_STALE` (spec §30 example, `A→C`).
- [ ] **Step 3:** full v1 suite green (the new states are additive, reported through the derived
  status only); commit.

## Task 5: Derived impaction probe + v-cycle health report (spec §29)

- [ ] **Step 1: Failing tests** — detect `requirement without test`, `requirement without
  implementation`, `implementation without traceable requirement`, `goal without metric source`,
  `metric without experiment`, `simulation without commit`, stale evidence (already covered by Task 4),
  feature with failing verification.
- [ ] **Step 2: Implement** `factory.system/health.py` `vcycle_health(root) -> list[Finding]` as a
  pure query (reusing trace gaps + goals + simulation), exposed via a `health` subcommand and the Inc 6 surfaces.
- [ ] **Step 3:** full suite + lint + commit.

## Task 5b: Comprehension hook + delta diagram (D8 / D7)

**Files:** `src/factory/commands/catchup.py` (extend), `src/factory/system/queries.py`
(`query_catchup` renders `diag:` delta if present), `pi-ext/factory-watch` Catch-me-up view (extend).

- [ ] **Step 1: Failing tests** — `/catchup FEAT-NAV-017` returns its deterministic `ContextDelta`
  (Task 2) unchanged, and additionally offers an **optional** "Verify my understanding" entry that
  invokes the installed `grill-understanding` + `visual-explainer` skills on the changed feature
  (D8). The delta itself stays deterministic — the comprehension step is an explicit, optional,
  risk-triggered side action, never auto-run and never a stored score.
- [ ] **Step 2: Implement** — a `--verify-understanding` flag on `/catchup` (and a Catch-me-up
  view button) that starts the comprehension skill on the feature; where a `diag:` diagram of the
  feature exists (D7), the Catch-me-up / delta view embeds it so the delta is read against a
  picture (e.g. the changed V-cycle slice or the goal chart). Reuse `query_diagram` (Inc 1) +
  rendering from Inc 6.
- [ ] **Step 3:** full suite + lint + commit.

## Task 5c: General artifact dependency provenance

### Goal

Generalise freshness from isolated code/evidence checks into explicit artifact dependencies that can
be traversed transitively.

Reuse:

- `factory.trace`;
- `factory.freshness`;
- existing artifact fingerprints;
- evidence reconciliation;
- feature/bundle scope.

Do not create a second graph.

### Required model

An artifact whose authority depends on another artifact must expose sufficient provenance to evaluate
that dependency.

Conceptual interface:

```python
@dataclass(frozen=True)
class ArtifactDependency:
    source_ref: str
    dependent_ref: str
    fingerprint: str | None
    dependency_kind: str

@dataclass(frozen=True)
class ArtifactFreshness:
    artifact_ref: str
    state: FreshnessState
    reasons: tuple[str, ...]
```

Exact model names are implementation choices.

### Dependency types

At minimum, the implementation must support dependencies involving:

- requirement → implementation;
- implementation → validation evidence;
- requirement → validation evidence;
- metric definition → evidence;
- validation/scenario/harness → evidence;
- requirement/implementation/ADR → generated explainer;
- feature/requirement/goal → diagram;
- canonical artifact → derived projection.

Only declared or deterministically authoritative relations may drive freshness.

### Failing tests

Cover:

1. SR changes → linked downstream artifact stale.
2. Implementation changes → SR stays fresh; evidence and implementation-dependent explainer stale.
3. Metric definition changes → old evidence stale.
4. Validation harness changes → old evidence stale.
5. Generator changes → generated artifact stale even if engineering inputs did not change.
6. Missing dependency fingerprint → state degrades/unknown; never assumed fresh.
7. Unrelated repository change → no false invalidation.
8. Dependency propagation does not rely on LLM inference.

---

## Task 5d: Transitive impact resolver

### Goal

Compute the affected dependency closure after a repository/canonical-artifact change.

Conceptual interface:

```python
@dataclass(frozen=True)
class Impact:
    changed: tuple[str, ...]
    directly_affected: tuple[str, ...]
    transitively_affected: tuple[str, ...]

def compute_impact(root: Path, changed_refs: Sequence[str]) -> Impact:
    ...
```

### Required behaviour

Given:

```text
SR-017
  ↓
code:navigation/preemption.py
  ↓
evidence:EXP-004
  ↓
diag:DIAG-NAV-009
  ↓
explainer:NAV-PREEMPTION
```

a change to `SR-017` must discover every reachable dependent artifact unless an explicit dependency
boundary applies.

### Failing tests

- direct dependency;
- two-hop dependency;
- multi-hop dependency;
- fan-out;
- fan-in;
- cycle protection;
- deleted artifact;
- renamed artifact with changed identity;
- no impact across unrelated feature;
- deterministic ordering.

---

## Task 5e: Authority-aware refresh policy

### Goal

Separate "this is stale" from "what should the factory do about it."

Conceptual interface:

```python
class RefreshAction(Enum):
    RECOMPUTE = "recompute"
    REGENERATE = "regenerate"
    RERUN_VALIDATION = "rerun-validation"
    ROUTE_TO_DEV = "route-to-dev"
    REQUEST_HUMAN_ACTION = "request-human-action"
    SUPERSEDE = "supersede"

@dataclass(frozen=True)
class RefreshDecision:
    artifact_ref: str
    action: RefreshAction
    reason: str
```

### Default policy

|Artifact authority class|Default action|
|---|---|
|authoritative BR/SR/ADR/goal/metric contract|preserve; request explicit workflow if it itself must change|
|implementation|`ROUTE_TO_DEV` when semantically invalidated by upstream intent|
|validation evidence|`RERUN_VALIDATION` where executable/safe, else explicit refresh required|
|generated explainer/diagram/summary|`REGENERATE`|
|derived query/view/index|`RECOMPUTE`|

The policy must be deterministic.

An LLM may perform a regeneration or implementation task after the action is selected, but it must not
decide whether the source artifact is stale.

### Resource/safety boundary

Automatic work may be suppressed by configured execution policy, cost budget, unavailable hardware,
unsafe external effects or missing environment.

In such cases the state must remain explicit:

```text
REFRESH_REQUIRED
or
BLOCKED
```

Never silently `FRESH`.

---

## Task 5f: Automatic generated-artifact regeneration

### Goal

Safe generated engineering knowledge SHALL be refreshed automatically when its dependencies become
stale and the generator is available.

Initial required types:

- traced visual explainers;
- canonical diagrams where a deterministic/registered authoring route exists;
- derived summaries/views.

### Important supersession

This task **supersedes** the earlier statement in this plan that explainer regeneration is always
on-demand and "never auto-run."

New rule:

> Staleness detection is automatic. Safe regeneration is also automatic when the refresh policy
> selects `REGENERATE` and the required generator is available.

Manual regeneration remains a fallback, not the default architecture.

### Explainer freshness

Explainer freshness must account for the dependencies it explains, including where applicable:

- linked SR content;
- linked implementation;
- linked ADR/design state;
- diagram asset;
- generator version/fingerprint.

It is insufficient for a code-dependent explainer to fingerprint only the SR text.

### Failing tests

1. linked SR changes → explainer stale → regeneration requested/executed;
2. linked code changes → explainer stale even when SR unchanged;
3. unrelated code change → explainer remains fresh;
4. regeneration success → new dependency fingerprints → fresh;
5. regeneration failure → stale/blocked remains visible;
6. generator fingerprint changes → explainer refreshed;
7. historical explainer provenance remains attributable to old state.

---

## Task 5g: Automatic evidence refresh

### Goal

Where validation is executable, bounded and safe, stale evidence should be regenerated automatically.

Examples:

- pytest-backed acceptance;
- simulation harness;
- deterministic metric extraction;
- configured bounded experiment.

### Required behaviour

```text
implementation changes
→ affected evidence stale
→ refresh policy = RERUN_VALIDATION
→ harness executes
→ evidence persisted with new provenance
→ goals/status re-evaluated
```

If validation requires unavailable hardware, expensive cloud resources, human action or unsafe
physical execution:

```text
evidence = REFRESH_REQUIRED / BLOCKED
```

The requirement must NOT remain validated from old evidence.

### Acceptance

A stale evidence record remains in history but is excluded from current validation authority.

---

## Task 5h: Semantic implementation invalidation

### Goal

An upstream intent change may make implementation semantically stale even when the code itself did not
change.

Example:

```text
SR-017 semantics changed
→ implementation previously satisfying old SR cannot be assumed current
```

The factory SHALL NOT automatically rewrite such implementation as though it were a generated document.

Instead:

```text
upstream semantic change
→ implementation impact detected
→ ROUTE_TO_DEV
→ controlled implementation workflow
→ validation
→ reconciliation
```

The resulting work item must retain the upstream cause.

This is distinct from evidence staleness and must remain visible until repaired or explicitly accepted.

---

## Task 5i: Freshness reconciliation

### Goal

After refresh actions execute, recompute the dependency graph and current authority.

Conceptual interface:

```python
@dataclass(frozen=True)
class FreshnessReconciliation:
    refreshed: tuple[str, ...]
    still_stale: tuple[str, ...]
    blocked: tuple[str, ...]
    superseded: tuple[str, ...]
    closure_reached: bool
```

The reconciler must not trust the fact that a refresh command ran.

It verifies current fingerprints/provenance after the action completes.

### Required invariant

```text
refresh action executed
≠
artifact is fresh
```

Freshness is established only after reconciliation against current dependencies.

---

## Task 5j: Feature freshness closure

### Goal

Expose whether the complete impacted feature slice is coherent again.

```python
def freshness_closure(root: Path, feature: str) -> FreshnessClosure:
    ...
```

A feature reaches closure if every impacted reachable artifact is:

- fresh;
- explicitly superseded; or
- intentionally unresolved with a visible reason/action.

The system must distinguish:

```text
closure_reached = True
```

from:

```text
closure_reached = False
remaining:
  code:...      ROUTE_TO_DEV
  evidence:...  BLOCKED: hardware unavailable
```

"Explicitly unresolved" does not mean healthy; it means there is no hidden stale state.

---

## Task 5k: `/catchup` freshness integration

Extend `ContextDelta` to expose engineering invalidation and repair, not only repository changes.

Conceptually add:

```python
invalidated: list[str]
auto_refreshed: list[str]
refresh_required: list[str]
blocked_refreshes: list[str]
freshness_closure_reached: bool
```

Example human output:

```text
Since your last review:

Requirements
  SR-017 changed

Implementation
  navigation/preemption.py updated

Automatically invalidated
  2 validation runs
  1 diagram
  2 visual explainers

Automatically refreshed
  validation runs
  diagram
  visual explainers

Remaining stale
  none

Metric
  reacquisition_rate 0.93 -> 0.96

Freshness closure
  REACHED
```

The state fields are deterministic.

Narrative explanation may be generated separately but may not contradict them.

---

## Task 5l: Change-impact integration with V-cycle health

Extend `vcycle_health` findings to include:

- stale implementation relative to changed upstream intent;
- stale validation;
- stale generated explainer;
- stale diagram;
- missing provenance;
- blocked refresh;
- failed regeneration;
- refresh loop detected;
- unresolved freshness closure.

The SCC/browser surface may render these findings only after SP-B + Inc 6 have landed.

The Python/domain representation does not depend on browser implementation details.

---

## Task 5m: Refresh loop protection

Automatic regeneration creates a new class of failure: refresh loops.

The system must detect and stop pathological chains such as:

```text
generator writes artifact
→ write appears as input change
→ generator runs again
→ ...
```

Required protections:

- dependency direction is explicit;
- generated output is not implicitly considered its own source;
- generator writes are attributable to refresh operations;
- repeated identical refresh attempts are bounded;
- reconciliation compares meaningful dependency fingerprints;
- blocked/failed refresh becomes visible rather than retrying forever.

Add deterministic tests for self-cycle and two-generator cycles.

---

## Task 5n: Historical preservation

Refreshing current engineering knowledge must not erase evidence of prior states.

At minimum:

- old validation retains original commit/configuration provenance;
- superseded generated artifacts remain attributable where history storage exists;
- `/catchup` may distinguish invalidated historical evidence from current evidence;
- failure records and rejected hypotheses remain immutable historical knowledge.

Inc 8 consumes this provenance for durable engineering memory.

---

## Task 5o: Thin-slice freshness acceptance — Physical Agentic AI Drone

Use one navigation/pre-emption feature as the reference test.

### Test A — requirement semantic change

Initial:

```text
requirement      FRESH
implementation   FRESH
validation       FRESH
diagram          FRESH
explainer        FRESH
feature closure  REACHED
```

Change requirement semantics.

Assert:

```text
requirement      FRESH
implementation   REFRESH_REQUIRED / ROUTE_TO_DEV
validation       STALE
diagram          STALE then regenerated
explainer        STALE then regenerated
feature closure  NOT REACHED
```

Complete DEV repair.

Assert:

```text
implementation   FRESH
validation       automatically rerun where configured
goal             re-evaluated
diagram          reconciled fresh
explainer        reconciled fresh
feature closure  REACHED
```

Historical pre-change evidence must still exist but must not validate current state.

### Test B — implementation-only change

Change the implementation without changing the SR.

Assert:

```text
requirement      remains FRESH
implementation   current
old validation   STALE
dependent explainer / diagram stale
validation reruns
generated knowledge refreshes
requirement/goal status re-evaluates
closure eventually REACHED
```

This test is mandatory: it proves invalidation is dependency-driven rather than special-cased around
SR changes.

## Task 6: Optional rebuildable index

- [ ] **Step 1:** measure. If `query_catchup`/`query_goal_history` on the real repo exceed a
  threshold, add a SQLite index under `.pi/` built by `factory index build` from canonical artifacts;
  deleting it and rebuilding reconstructs the same graph (AC-10). If fast enough, skip (record the decision).
- [ ] **Step 2:** if built: `--rebuild` deterministic, indexed only for read queries; commit.

## Task 7: Review handoff

- [ ] **Step 1:** reviewer sub-agent — compliance vs spec §28–§31, §9.4, AC-10 rebuildability,
  AC-07 regression, D3 additive rule; deterministic-delta rule (no LLM over the past).
- [ ] **Step 2:** fix findings; update checkboxes.

## Acceptance for Increment 7

Increment 7 is complete only when all of the following hold:

- `/catchup FEAT-NAV-017` returns a deterministic, correct "since your last review" delta.
- Requirement state correctly reflects goal/evidence freshness.
- `vcycle_health` surfaces missing and inconsistent V-cycle relationships.
- Artifact dependencies can be traversed transitively for freshness impact.
- A requirement change invalidates all declared downstream dependent artifacts.
- An implementation-only change invalidates evidence/generated knowledge without invalidating the
  authoritative SR.
- Stale evidence cannot validate current implementation.
- Safe generated artifacts are automatically regenerated.
- Safe executable validation is automatically rerun when configured.
- Semantic implementation repair is routed through DEV rather than silently rewritten.
- Refresh success is verified by reconciliation, not assumed.
- Feature freshness closure is computed and exposed.
- Missing provenance is degraded/unknown/stale, never silently fresh.
- Refresh loops are bounded/detected.
- Historical evidence remains preserved.
- `/catchup` reports changed, invalidated, auto-refreshed, blocked and remaining stale artifacts.
- Optional comprehension intervention remains distinct from deterministic freshness state.
- SP-B implementation has not been modified by this increment before it lands.
- v1 suite remains green and all new behaviour is additive to existing public contracts unless an
  explicit compatibility decision says otherwise.

---

## Additional requirements — grill node + traced explainer staleness (added 2026-08-12)

Folded in from the grill design (`docs/superpowers/specs/2026-08-12-grill-understanding-node-design.md`) after re-grounding against **current main**. These ADD to the locked scope; the existing tasks above are unchanged. **Dependency note:** the SR↔code staleness engine already exists on main — `factory.freshness` fingerprints files/trees/values (sha256), and `factory.evidence.reconcile` reports `ReconcileKind.STALE_VALIDATION`. New work REUSES it; it does not build a parallel checksum.

### A. Grill as an orchestrator node (additive)

Unlike Task 5b's *optional, on-demand* `/catchup --verify-understanding`, this makes the grill a **blocking, human-in-the-loop node** that fires for every interactive run:

- In `run_task` (`src/factory/orchestrator/{nodes,runner}.py`), **after `context-gather`, before `dev`**; skipped in `--auto` (no `HumanReviewGate`), mirroring the `human-review` gate (`FileHumanReviewGate`, which now archives diffs and takes `repo_root`).
- `GrillGate` polls `<transcript_dir>/grill-result.json`; verdicts `agreed` / `not-agreed` / `skipped` — **never a hard block**; `not-agreed`/abandoned flags the human-review banner (pairing suggestion).
- Extension (`pi-ext/factory-watch`): watcher flags `grill:blocked`; mission-control raises `[Grill now] / [Skip]`; the grill is hosted in an interactive `pi --session` terminal window seeded by hard-loading the skill + task content (`findSkillFile`, which gains a global fallback).
- Skills: `grill-understanding` + `visual-explainer` + `diagram-design` installed globally under `~/.agents/skills/` (siblings, preserving `visual-explainer/../diagram-design` and `scripts/open_in_obsidian.py`).

### B. Explainer as a traced, SR-linked artifact (additive)

- New `explainer` node kind in `src/factory/trace/` (loaded from `docs/visual-explain/*.md`), with an `explains:` edge (SR-ID linked) — respecting the trace rule “declared edges only; never infer an edge.”
- Explainer staleness couples the **declared engineering dependencies that make the explanation
  authoritative**, including SR content and the relevant implementation where applicable. Reuse
  `fingerprint_file` / `fingerprint_value` / `fingerprint_git_tree`; do not create a parallel checksum.
- Explainer invalidation participates in the general HLR-09 dependency graph.
- When refresh policy selects `REGENERATE`, regeneration is automatic where the registered generator
  is available and execution is safe. Manual regeneration is a fallback.
- Successful generation does not itself imply freshness; the regenerated artifact must be reconciled
  against current dependencies.
- Historical generated knowledge is retained where history/provenance storage supports it.
- Resolution via **on-edit refresh** (no persistent daemon); surfaced through the existing widget/report, and reflected in the derived index (AC-10 rebuildable if built).

### C. Open decision — surface conflict (RESOLVED 2026-08-12)

The generic-skill + **Obsidian** path (visual-explainer) chosen for the grill conflicts with this program’s locked D1–D6 (“SCC browser sole human surface; **no Obsidian**”). **Resolution: SCC / `diagram-design` is canonical and automated; Obsidian is a personal, manual view of the same artifacts.** The factory/extension never auto-opens Obsidian — the `docs/visual-explain/<slug>.md` files stay Obsidian-compatible (frontmatter + relative SVG links) so the human may open them in their own registered vault at will, but the deterministic surface is the SCC browser / file paths. §B authoring therefore targets `diagram-design`-style explainers under `docs/visual-explain/`; no automated `open_in_obsidian.py` step.
