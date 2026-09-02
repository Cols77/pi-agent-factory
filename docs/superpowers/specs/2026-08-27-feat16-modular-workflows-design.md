# FEAT-16 — Modular Workflows (MODULAR-WORKFLOWS)

_Status: **design dossier** (2026-08-27). Owner: Python factory orchestrator (the authority) + a
thin declarative workflow interpreter. This is the missing abstraction that lets gates (FEAT-14) and
the governed driver (FEAT-13) compose against, and that FEAT-15 (POLISH) and FEAT-17 (PLANNING)
plug into as pre-defined templates. Planning/design only.

_Parent: `docs/superpowers/specs/2026-08-26-coherence-inc9-programme-session-capture.md` (FEAT-16
proposal). Companion: FEAT-13 (GOVERNED-EXECUTION-DRIVER), FEAT-14 (VALIDATION-GATES), FEAT-15
(POLISH-FLOW), FEAT-17 (PLANNING-BOOTSTRAP)._

---

## 1. Purpose

Let a project (or a product) declare **what a "run" means** — which ordered nodes execute, which
gates run at each node, and how negatives drive retry/escalation — as an **inspectable, composable
workflow**, instead of the current hard-coded node sequence. This directly answers the program
requirement that *"depending on the deterministic workflow executions, various gates could be
required"* and the roadmap ask for *"modular workflow constructions … with pre-defined workflows."*

Today the order lives **implicitly inside `src/factory/orchestrator/runner.py`**, and there is no
workflow type, no per-project/no-workflow gate selection, and no library of named workflows. A user
who wants a "safe refactor" (context → dev → unit → agentic review only) or a "coverage audit" or an
"experiment" run has **no way to express it**; every run is the one standard sequence.

---

## 2. Built-already vs genuinely-new (honest delta)

### Already built (the nodes, the gates, the host seam — NO rewrite needed)
- **Node functions are discrete and reusable:** `src/factory/orchestrator/nodes.py` exports
  `run_context_gatherer`, `run_dev`, `run_validation`, `run_review`, `run_session_review`.
- **Roles/outcomes are typed:** `src/factory/orchestrator/types.py` — `AgentRole
  {CONTEXT_GATHERER, DEV, VALIDATION, REVIEW, SESSION_REVIEW, SYNTHESIS, COVERAGE_AUDIT}`;
  `NodeOutcome {PASS, FAIL, REJECT, CHANGES_REQUESTED, ESCALATE, ALREADY_DONE}`; `NodeEvent`.
- **Gates are already named + skippable:** `src/factory/orchestrator/backends.py` `ConfigGateRunner`
  (`unit`/`sim`/`integration`/`full`; undeclared → `GATE_NOT_APPLICABLE=-1`, "skip and pass"; pytest
  exit 5 normalized). Gates already vary by project config (`factory.yaml`).
- **Host seam exists:** `AgentBackend` protocol (`run(role, prompt, on_snippet, on_session_id)`).
- **A runner already assembles them** in `runner.py` (fixed order) + `execution.py` (`RunExecution`),
  `join` via `TaskResult`, `HumanReviewGate`/`GrillGate`, KB-select, evidence finalize, git_ops.

### The real gap (the delta)
- **The node ORDER is hard-coded** in `runner.py` — not data.
- **No `Workflow` type / config** — you cannot declare a different sequence or per-node gates.
- **No pre-defined workflow library** — nothing to pick from.

So FEAT-16 is a **re-cast, not a rewrite**: it lifts the existing node functions + gate runner into
a **declarative interpreter** whose default (`standard`) reproduces today's behavior byte-for-byte,
and adds named templates reusing the same functions. It adds **no new enforcement logic, no new node
types** — it formalizes what already runs.

---

## 3. Proposed design

### 3a. The `Workflow` type (`src/factory/workflow/model.py`)
A workflow is a pure, serializable, declarative value (survives the filesystem-first treaty: the
WORKFLOW is a YAML file = canonical; the interpreter is derived):

```python
@dataclass(frozen=True)
class NodeSpec:
    node: str                 # "context-gather" | "dev" | "validation" | "review" | "session-review" | "synthesis"
    gates: tuple[str, ...]    # gate names to run after this node (FEAT-14 kinds)
    on_pass: ...              # next-node selection (default: next in order)
    on_fail: ...              # "retry" | "escalate" | "next" | "stop"
    on_reject: ...
    max_attempts: int = 1     # node-level retry budget (defaults from today's nodes)

@dataclass(frozen=True)
class Workflow:
    name: str                 # "standard" | "polish" | "coverage-audit" | "safe-refactor" | "experiment"
    steps: tuple[NodeSpec, ...]
    entry_node: str = "context-gather"
```

- Declared in `.factory/factory.yaml` under `workflows:` (YAML = the canonical file; derived index
  after). If absent, `coherence run` falls back to the **`standard` template** — so **zero behavior
  change** for every existing project.
- Gate naming reuses the **existing** `ConfigGateRunner` names (`unit`, `sim`, `integration`, `full`)
  **plus** the FEAT-14 taxonomy kinds (`agentic_review`, `human_review`, `sim_human_visualization`).
  An undeclared gate **skips** (preserves the configurable-gates rule: a webapp with no `sim` does not
  fail).

### 3b. The interpreter (`src/factory/workflow/interpreter.py`)
Rewrite `runner.py`'s fixed switch into a **data-driven interpreter** over a `Workflow`:

```
for step in workflow.steps:
    outcome, event = run_step(step.node, ...)   # calls the SAME node fn as today
    for gate in step.gates:                     # FEAT-14 gate contract
        r = gates.run_detail(gate)              # exists today
        handle r.returncode (0/applicable/skip) # exists today
    advance = decide(step, outcome)             # on_pass/on_fail/on_reject table
```

- Each `run_step` delegates to the existing `run_context_gatherer` / `run_dev` / `run_review` / …,
  unchanged — so all the retry/KB-select/evidence/freshness behavior is inherited, not re-specified.
- The **`standard` template = today's exact order + today's gate set**, so `coherence run` on the
  health-resolution tasks (T-1..T-6) diff-tests green against the `main` baseline. That's the
  regression gate for the whole FEAT.

### 3c. Pre-defined templates (the "library")
Built-in under `coherence workflows` (CLI: `coherence workflows --list`, `--show <name>`):

| Workflow | Steps (order) | Gates | Notes |
|---|---|---|---|
| **standard** | context → dev → validation → review → session-review (+human-review + grill) | unit, sim(incl. human-vis), integration, agentic_review | the current fixed pipeline (byte-identical) |
| **polish** | finding → isolate-worktree → dev → re-gate → human-playground-confirm | unit, agentic_review, **sim_human_visualization** | FEAT-15's loop; human confirms genuinely-works |
| **coverage-audit** | coverage-audit (read-only, per-SR verdict) → synthesis | none/audit | per-SR semantic audit |
| **safe-refactor** | context → dev → unit → agentic_review | unit, agentic_review | NO sim/human; for low-risk refactors |
| **experiment** | context → dev → sim_regression → validation → review | sim_regression, unit | for experiment/measurement runs |

Each is a **declared YAML workflow** reusing node fns; none needs a new node type. A project may
**override** any template or define bespoke ones in `factory.yaml`.

---

## 4. Scope — ONE tracer-bullet through every layer

Vertical: substrate (workflow model) → factory (interpreter + runner re-cast) → coherence (gate
taxonomy binding FEAT-14) → host (CLI `coherence workflows`) → console association (FEAT-10 shows the
active workflow/step).

### Task W-01 — `Workflow` model + YAML parse
- Add `src/factory/workflow/model.py` + loader (parses `workflows:` from `factory.yaml`).
- **Verify:** `coherence workflows --list` prints the built-ins; a minimal custom YAML workflow loads.
- **Acceptance:** a `Workflow` value-round-trips through YAML; absent config → `standard`.

### Task W-02 — Re-cast the runner to interpret `standard`
- Rewrite `runner.py`'s node sequence into the interpreter; `standard` == today's order + gates.
- **Verify:** run a health-resolution task (e.g. T-1: `coherence navigate health --json`) — result
  identical to `main`'s behavior; full regression suite green (the lock/pdf/config pre-existing
  failures are NOT regressions).
- **Acceptance:** zero behavior change when no custom workflow is declared; diff-test confirms.

### Task W-03 — Gate binding per workflow (FEAT-14 contract)
- A `NodeSpec.gates` selects which gates run; a different workflow has a different gate set.
- **Verify:** YAML where `safe-refactor` declares only `[unit, agentic_review]` runs **no** `sim`; a
  webapp (no `sim` declared) has that gate **skipped, not failed**.
- **Acceptance:** "varies per workflow" is expressible + enforced; undeclared-gate-skip preserved.

### Task W-04 — Templates library + CLI polish
- Ship `standard/polish/coverage-audit/safe-refactor/experiment` as declared YAML; `coherence
  workflows --show <name>` prints the steps+gates.
- **Verify:** `--list` shows 5; `--show safe-refactor` shows its exact 4 steps/2 gates.
- **Acceptance:** a user can inspect and pick a workflow before a governed run (FEAT-13).

### Task W-05 — FEAT-13/FEAT-15/FEAT-10 integration smoke
- The governed driver (FEAT-13) accepts `--workflow <name>`; polish (FEAT-15) runs via the `polish`
  template; the console (FEAT-10) shows the active workflow + current step.
- **Verify:** `coherence run-governed --workflow safe-refactor` on a task only runs that workflow's
  gates; a polish run streams its template steps on the console.
- **Acceptance:** the workflow is the shared contract the driver, polish, and console all consume.

---

## 5. Files likely to change (planned)

- **New:** `src/factory/workflow/model.py`, `src/factory/workflow/interpreter.py`,
  `src/factory/workflow/templates/standard.yaml` (+ `polish`, `coverage-audit`, `safe-refactor`,
  `experiment`), `src/coherence/workflows/cli.py` (`coherence workflows`), tests.
- **Modify (re-cast, no logic change):** `src/factory/orchestrator/runner.py` (interpret a Workflow
  instead of the hard-coded switch), `src/factory/config.py` (load `workflows:`).
- **Reuse (read-only):** `nodes.py`, `backends.py`, `types.py`, `execution.py`.
- **Consumers (FEAT-13/15/10):** `run-governed --workflow`, polish template, console step display.

## 6. Risks & open questions

- **Backward-compat is the #1 risk** — the `standard` template must reproduce today's run
  byte-for-byte or every existing plan/workflow shifts. Mitigate: W-02's diff-test against `main`
  before any other change; keep `standard` literal.
- **Enforcement lives in Python** — the interpreter must NOT offload gate decisions to the host; it
  stays in `factory.workflow`. No new authority.
- **Parallelism** — today's pipeline is linear; if a workflow fans out (e.g. two reviews in parallel)
  that's a DAG extension. Scope W-* to **linear** first; document fan-out as a follow-on (FEAT-13's
  swarm already achieves review-parallelism at the driver level, not the node level).
- **Overlap watch** — FEAT-16 is the *shape*; FEAT-11 is *enforcement*; FEAT-13 is the *driver*;
  FEAT-14 is the *gate taxonomy*. Keep clear boundaries so none draws the others' scope.
- **Filesystem treaty** — workflows are canonical YAML; the interpreter is derived. No graph/DB.

## 7. Feature completion / acceptance (NOT a task DoD)

> Note on levels: "Definition of done" is **task-scoped** — `dod_met` is a field on
> `TaskResult` (`src/factory/orchestrator/types.py`), the gate a *task* passes. A feature is an
> aggregate: it is complete only when the tasks satisfying its SRs each pass their own DoD and the
> feature's SR/invariants are satisfied + gated. The completion criterion below is that feature-level
> aggregate.

### Feature completion criteria

A workflow is a declarative, inspectable, composable `Workflow` (YAML-canonical, from `factory.yaml`),
with pre-defined templates (`standard` == today's behavior exactly, plus `polish`, `coverage-audit`,
`safe-refactor`, `experiment`), where each workflow selects which gates run per node (FEAT-14) and
the governed driver + polish + console all read the same workflow contract (FEAT-13/15/10). The
interpreter enforces in Python; no regression on `standard`.

**Verdict: YES, a distinct FEAT** — it is the missing abstraction that the gate taxonomy (14), the
polish loop (15), and the governed driver (13) all compose against, and it delivers the "modular +
pre-defined workflows" roadmap ask without rebuilding the node pipeline.
