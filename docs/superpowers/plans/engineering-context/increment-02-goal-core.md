# Increment 2 — `/goal` + Goals Core (Implementation Plan)

**Status:** Draft for written review. Assumes locked **D3 (additive, keep v1 working),
D4 (both), D5 (spec vocabulary)**. D1 (pi-ext)/D2 (Obsidian+browser) do not affect this
increment's Python core.
**Source phase:** Engineering Context spec §37 **Phase 2 — `/goal`.**
**Landing repo:** pi-agent-factory (Python core) + cool_physical_ai_project (declared goal values).
**Sub-agents:** dev=`pi -p prompts/increment-02-dev.md`, review=`pi -p prompts/increment-02-review.md`.

## Goal

A first-class **Goal** with the spec §13 lifecycle, deterministic metric evaluation,
evidence persistence, goal-reached notification and regression detection. Demonstrate
one drone requirement progressing `NOT_REACHED → REACHED → REGRESSED` (spec §37 Phase 2
exit demo). The `/goal` Pi command (agent UX) is Inc 2's command shim over the Python
`factory.goals` core; evaluation auto-wiring from real runs arrives in Inc 3.

## Reuse (do not rebuild)

- **Artifact/model:** `factory.trace.model` load_nodes + `goals/GOAL-*.md` glob (Inc 1).
- **Deterministic claims/freshness:** `factory.system._claims`, `factory.freshness`.
- **Requirement status:** `factory.trace.validation_status` (extended goal-aware, additive).
- **Run/evidence store:** `factory.evidence.manifests` (evidence identity for a goal in Inc 3).
- **Notifications:** reuse the cockpit's existing notification plumbing; no new surface.

## Global constraints (from Program §6 + D3)

- **Additive and non-breaking.** Existing CLI verbs/commands/schemas are untouched.
  The new `factory.goals` package and `goal` subcommand are added; nothing existing is re-written.
- Deterministic evaluation: no LLM to mark REACHED (spec §14). Semantic metrics may use
  LLM-as-Judge later and MUST produce an inspectable evidence artifact — out of scope here (deterministic only).
- Lifecycle transitions are recorded to the goal file + an append-only transition log;
  never inferred from git history.
- Full v1 suite stays green at every commit.

## File structure (all additive in pi-agent-factory)

| File | Responsibility |
|---|---|
| `src/factory/goals/__init__.py` `__main__.py` `cli.py` | `factory goals` CLI (subcommands: `list`, `show`, `create`, `set-state`, `evaluate`, `history`). |
| `src/factory/goals/schema.py` | Goal frontmatter loader/validator (reuses `goal.schema.json` from Inc 1, extended with lifecycle). |
| `src/factory/goals/lifecycle.py` | State machine + allowed transitions (`TransitionError`). |
| `src/factory/goals/evaluator.py` | Deterministic metric comparison → result; evidence bundle. |
| `src/factory/goals/registry.py` | Load all goals, keyed by id; resolve feature/requirement/metric refs. |
| `src/factory/schemas/goal.schema.json` | Extended: `state`, `metric`, `target`, `evidence`, `history`. |
| `src/factory/commands/goal.py` | `/goal` handler: parse one-line/verbose forms → create goal artifact. |
| `pi-ext/factory-watch/...` | `/goal` command wiring (thin; heavy lifting in Python). |
| `tests/unit/goals/test_lifecycle.py` `test_evaluator.py` `test_registry.py` `tests/unit/commands/test_goal.py` | unit tests. |

**cool_physical_ai_project:** `goals/GOAL-NAV-003.md` gains a filled `state/metric/target`,
plus a `scripts/demo_goal_cycle.py` that walks the declared metric through
`NOT_REACHED→REACHED→REGRESSED` to satisfy the Phase 2 exit demo.

## Task 1: Goal lifecycle state machine

**Files:** `src/factory/goals/lifecycle.py`, `tests/unit/goals/test_lifecycle.py`
**Interfaces:**
```python
GoalState = Literal["DECLARED","ACTIVE","EVALUATING","NOT_REACHED","REACHED","REGRESSED","BLOCKED"]
_TRANSITIONS: dict[GoalState, set[GoalState]]   # spec §13 edges
def can_transition(from_: GoalState, to: GoalState) -> bool
def transition(from_: GoalState, to: GoalState) -> GoalState   # raises TransitionError
```

- [ ] **Step 1: Failing tests** — encode spec §13 as an adjacency table and assert
  every legal edge + a set of illegal ones (e.g. `REACHED → DECLARED`, `NOT_REACHED → BLOCKED`
  if evidence exists). 
- [ ] **Step 2: Implement:**
```python
_TRANSITIONS = {
  "DECLARED": {"ACTIVE"},
  "ACTIVE":   {"EVALUATING", "BLOCKED"},
  "EVALUATING":{"NOT_REACHED","REACHED","BLOCKED"},
  "NOT_REACHED":{"ACTIVE","EVALUATING","BLOCKED"},   # retry allowed
  "REACHED":  {"EVALUATING", "REGRESSED"},
  "REGRESSED": {"ACTIVE","EVALUATING"},               # re-validate
  "BLOCKED":  {"ACTIVE"},
}
def transition(f,t):
    if t not in _TRANSITIONS[f]: raise TransitionError(f"{f} -> {t} not allowed")
    return t
```
- [ ] **Step 3:** unit suite + lint + commit.

## Task 2: Goal schema + registry

**Files:** `src/factory/goals/schema.py`, `registry.py`, `src/factory/schemas/goal.schema.json`,
`tests/unit/goals/test_registry.py`
**Interfaces:**
```python
@dataclass(frozen=True) class Goal:
    id: str; title: str; path: Path; feature: list[str]; requirements: list[str]
    metric: dict; target: dict;  # {operator, value}
    state: GoalState; created_from: str | None; scope_errors: list[str]
def load_goal(path) -> Goal
def load_goals(root) -> dict[str, Goal]      # keys by id; duplicate id raises DuplicateGoalIdError
```
- [ ] **Step 1: Failing tests** — parse a well-formed `GOAL-NAV-003.md`; absent frontmatter
  degrades to recorded `scope_errors` (never crashes the set); duplicate id raises.
- [ ] **Step 2: Implement** mirroring `adr.py` (`parse_adr`/`load_adrs`) exactly, plus
  `goal.schema.json` requiring `id/title/feature/requirements/metric/target`; `state`
  defaults to `DECLARED`. `target` = `{operator: ">=", value: 0.90}`; `metric` =
  `{name, source_experiment}`.
- [ ] **Step 3:** unit suite + lint + commit.

## Task 3: Deterministic evaluator + evidence

**Files:** `src/factory/goals/evaluator.py`, `tests/unit/goals/test_evaluator.py`
**Interfaces:**
```python
OPS = {">=": operator.ge, "<=": operator.le, ">": operator.gt, "<": operator.lt, "==": operator.eq}
@dataclass(frozen=True) class GoalResult:
    goal_id: str; state: GoalState; passed: bool; value: float; target_value: float
    operator: str; evidence: dict   # {experiment, run, commit, metrics_path, recorded_at}
def evaluate(path: Path, value: float, run_id: str, commit: str, metrics_path: Path) -> GoalResult
```
- [ ] **Step 1: Failing tests** — spec AC-04: `0.93 >= 0.90` → `passed=True`, `state=REACHED`;
  AC-07: later `0.82` from `REACHED` → `REGRESSED`; `NOT_REACHED` when first below target;
  `BLOCKED` when metric source/experiment missing.
- [ ] **Step 2: Implement:**
```python
def evaluate(goal, value, *, run_id, commit, metrics_path):
    if goal.metric is None or goal.metric.get("name") is None or goal.metric.get("source_experiment") is None:
        return GoalResult(goal.id, "BLOCKED", False, value, ...)
    op = OPS[goal.target["operator"]]
    passed = bool(op(value, goal.target["value"]))
    prior = goal.state
    state = "REACHED" if passed else ("REGRESSED" if prior == "REACHED" else "NOT_REACHED")
    return GoalResult(goal.id, state, passed, value, goal.target["value"],
                      goal.target["operator"],
                      {"experiment": goal.metric["source_experiment"], "run": run_id,
                       "commit": commit, "metrics_path": str(metrics_path)})
```
- [ ] **Step 3:** unit suite + lint + commit.

## Task 4: Persist evidence + transition log

**Files:** `src/factory/goals/registry.py` (extend), `src/factory/goals/cli.py`,
`tests/unit/goals/test_cli.py`
- [ ] **Step 1: Failing tests** — after `evaluate`, the goal file's frontmatter records
  `state`, `result{value,target}`, `evidence{experiment,run,commit,metrics}` (spec §15) and an
  append-only `history` entry; the transition log is appended, never rewritten.
- [ ] **Step 2: Implement** a `record(result, goal_path)` that reads frontmatter, sets
  `state`+`result`+`evidence`, pushes to `history`, and writes back atomically. Append-only
  `goals/<id>-transitions.jsonl` for audit; deterministic ordering by recorded timestamp.
- [ ] **Step 3:** full suite + lint + commit.

## Task 5: `factory goals` CLI + `query_goal`/`query_goals` in `system`

**Files:** `src/factory/goals/cli.py`, `src/factory/system/queries.py`
- [ ] **Step 1:** CLI subcommands `list/show/create/set-state/evaluate/history`. `create`
  writes a goal file from `--feature/--requirements/--metric/--target/--state`.
- [ ] **Step 2:** in `system/queries.py`, add `query_goal(root, id)` (single goal +
  current state + latest evidence + history) and `query_goals(root, scope)` (goals bound to a
  feat:/sr: via `demonstrates` edges) — output renders through the existing claim/freshness
  plumbing (goals exposed to agent in Inc 4, human view in Inc 6).
- [ ] **Step 3:** full suite + lint + commit.

## Task 6: `/goal` command + goal-reached notification

**Files:** `src/factory/commands/goal.py`, `pi-ext/factory-watch` `/goal` wiring,
`tests/unit/commands/test_goal.py`
- [ ] **Step 1:** handler for spec §12 UX:
```python
def parse_goal_cmd(arg: str) -> dict:
    # short form: "NAV-REQ-021 reacquisition_rate >= 0.90"
    #   -> {requirement, metric, target}
    # long form: 'FEAT-NAV-017 "...intent..." metric=.. target=">=0.90" experiment=SIM-047'
    #   -> agent fills missing unambiguous config (feature from sr's `contains` parent)
def create_goal(root, parsed) -> Goal
```
Agent MAY infer missing config when unambiguous (spec §12); anything ambiguous escalates to the human.
- [ ] **Step 2:** notification shim `notify_goal_transition(prev, result)` called after
  `evaluate` — prints the spec §16 "✓ GOAL REACHED" block (rich cockpit notification is Inc 4/6);
  regression path uses spec §17 wording.
- [ ] **Step 3:** full suite + lint + commit.

## Task 7: goal-aware requirement status (additive)

**Files:** `src/factory/trace/validation_status.py` (extend), `tests/unit/trace/test_validation_status.py`
- [ ] **Step 1:** map goal outcome into the D5 vocabulary without disturbing v1 status:
  a requirement all of whose goals are `REACHED` reports `VALIDATED`; a `REGRESSED` goal reports
  `REGRESSED`; goals exist but none reached yet reports `VERIFICATION_PENDING`; no goals → v1 behavior unchanged.
- [ ] **Step 2:** this is **derived** (computed from goals), never stored — matching spec §28
  ("shall not become VALIDATED merely because implementation exists"). Add a `requirement_validation(goals)` pure function + tests.
- [ ] **Step 3:** full v1 suite MUST stay green; commit.

## Task 8: Phase 2 exit demo + review handoff

- [ ] **Step 1:** author `cool_physical_ai_project/scripts/demo_goal_cycle.py`:
```python
g = load_goal("goals/GOAL-NAV-003.md")
results = [evaluate(g, v, run_id=f"RUN-demo{i}", commit=sha, metrics_path="evidence/runs/x/metrics.json")
           for i, v in enumerate([0.71, 0.93, 0.82])]
# assert states == [NOT_REACHED, REACHED, REGRESSED]
```
- [ ] **Step 2:** reviewer sub-agent — compliance review vs spec §11–§18 (state model, AC-04..07,
  evidence retention, notification, regression) + D3 additive rule. Fix findings as `T-###`.
- [ ] **Step 3:** update task checkboxes; note escalations.

## Acceptance for Increment 2

- AC-03 (goal creation), AC-04 (evaluation→REACHED), AC-05 (evidence retention), AC-06
  (notification on NOT_REACHED→REACHED), AC-07 (REGRESSED + notified) all pass as unit + demo tests.
- Lifecycle matches spec §13 exactly; determinism enforced (no LLM for REACHED).
- Every v1 test green; no existing verb/command/schema changed.
