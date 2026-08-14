# Increment 3 — Simulation Evidence (Implementation Plan)

**Status:** Draft for written review. Assumes locked D1–D5. Reuses `factory.evidence`,
`factory.validation.sim_harness` and Inc 1/Inc 2 primitives.
**Source phase:** Engineering Context spec §37 **Phase 3 — Simulation evidence.**
**Landing repo:** pi-agent-factory (ingestion + queries) + cool_physical_ai_project
(scenarios bound to goals, run generation).
**Sub-agents:** dev=`pi -p prompts/increment-03-dev.md`, review=`pi -p prompts/increment-03-review.md`.

## Goal

Connect the full evidence chain the spec demands (§20 run bundle, §18 goal→requirement,
§19 metric model, §29 v-cycle health):

```
requirement → goal → experiment → run → metric → evidence
```

with real drone scenarios from cool_physical_ai_project producing run bundles whose
metrics feed goal evaluation (Inc 2) and requirement status (Inc 2 Task 7).

**Available requirement evidence today:** the product already exposes a measured
state-machine slice for this chain — SR-066 + SR-067/068/071/076/080/081/082 bound to
`sim-testbench` (`unit_pass_rate`, `assert "== 1.0"`) through the evolved harness's pytest
trial source, plus SR-001/066 frame-trace and SR-086/087/088/101 planner contracts. A later,
additive batch also bound the observation/relevance/belief family (SR-040/041/042/043/044/045/
047/048) and the mission-trigger + event-store families (SR-032/036/092/135/164/166/167/174) the
same way, taking the measured set to **29 bound requirements** (each `value 1.0, passed true`,
`trials == declared`) with real per-SR tests driving `RelevanceGate`, `legacy_adapter`,
`TriggerManager`, `MissionManager`, and `JsonlEventStore`. Inc 3's
seed-run work can lift these concrete requirement-level measurements as the
`requirement → ... → evidence` input for the run chain and Inc 7's goal-aware status.

A further additive batch bound the deterministic safety-governor family (SR-034/102/103/104/
105/106/107/108/109/111/112/113/114/115) the same way, taking the measured set to
**43 bound requirements** — per-SR tests driving `SafetyGovernor` (and the `SkillExecutor`
acceptance gate for SR-034), each `value 1.0, passed true`; SR-110 (clamp reason code) and
SR-151 (generated-test process claim) stay `[proposed]` because no real clamp/process path
exists to assert.

## Reuse (do not rebuild)

- **Run manifests:** `factory.evidence.manifests` `write_run_manifest/load_run_manifest/list_run_manifests`
  already implement spec §20 `manifest.json`. Extend ingestion, don't fork.
- **Sim harness + scorers:** `factory.validation.sim_harness.SimTestbenchHarness`, `scorer_registry`,
  and the product's `sim-testbench` harness config in `.factory/factory.yaml`.
- **Goal evaluation:** `factory.goals.evaluator.evaluate` (Inc 2).
- **Requirement status:** `factory.trace.validation_status` (Inc 2 Task 7).
- **Freshness/reconcile:** `factory.evidence.reconcile`, `factory.freshness` for stale-code detection.
- **Run node kind:** `run` literal reserved in Inc 1 Task 1 — now populated from manifests.

## Global constraints (Program §6 + D3)

- Additive; existing harness/manifest surface stays working and un-changed.
- Deterministic ordering of runs/metrics-history; never newest-by-mtime only — use manifest
  recorded timestamps/ids.
- Rebuildable derived chain: everything derives from canonical `manifest.json/metrics.json`
  on disk; no persistent index in this increment (add in Inc 7 only if measured).
- A missing/renamed evidence file degrades one run's chain, never the engine.

## File structure (additive)

| File | Responsibility |
|---|---|
| `src/factory/simulation/__init__.py` `registry.py` | Experiment/run registry loaded from `evidence/runs/*/manifest.json`. |
| `src/factory/simulation/evidence.py` | `run_nodes`, `metric_values(manifest, metrics_json)`, `latest_failure`, `metric_history`. |
| `src/factory/evidence/manifests.py` | (extend, additive) `load_run_manifest` tolerant of newer manifest keys; no schema break. |
| `src/factory/system/queries.py` | `query_simulation_run`, `query_latest_simulation`, `query_latest_failure`, `query_metric_history`. |
| `src/factory/schemas/run.schema.json` | Run manifest contract (spec §20 fields). |
| `tests/unit/simulation/test_registry.py` `test_evidence.py` | unit tests. |

**cool_physical_ai_project:**
| File | Responsibility |
|---|---|
| `scenarios/*.yaml` | Bind scenario ⇄ experiment ids (e.g. `multiple_threats` ⇄ SIM that scores reacquisition). |
| `scripts/run_simulation.py` | Wrap `SimTestbenchHarness` → emit run bundle into `evidence/runs/RUN-*/`. |
| `evidence/runs/<a few seed runs>` | Committed manifests + metrics for SIM-047-style evidence. |

## Task 1: Run manifest schema + tolerant loader

**Files:** `src/factory/schemas/run.schema.json`, `src/factory/evidence/manifests.py` (additive),
`tests/unit/evidence/test_manifest_roundtrip.py`
- [x] **Step 1: Failing tests** — a manifest with spec §20 fields (`run/experiment/feature/
  requirements/goals/commit/result`) writes then loads losslessly; a manifest missing optional
  new keys still loads under v1 (backward-compat); a malformed manifest degrades to a
  `scope_errors`-carrying run, never raises.
- [x] **Step 2: Implement** `run_manifest_schema` validation wired into `write_run_manifest`
  (add a `feature`/`goals` field if not already present, default-safe) and a tolerant
  `load_run_manifest` that returns unknown fields untouched.
- [x] **Step 3:** full v1 suite green + lint + commit.

## Task 2: Run/experiment registry

**Files:** `src/factory/simulation/registry.py`, `tests/unit/simulation/test_registry.py`
**Interfaces:**
```python
@dataclass(frozen=True) class Run:
    run_id: str; experiment: str; feature: str|None; requirements: list[str]
    goals: list[str]; commit: str|None; result: str|None; path: Path; scope_errors: list[str]
def load_runs(evidence_dir: Path) -> list[Run]
def runs_for(evidence_dir, *, feature=None, requirement=None, experiment=None, goal=None) -> list[Run]
def latest_run(evidence_dir, feature) -> Run|None     # deterministic: sort by run_id/recorded ts
```
- [ ] **Step 1: Failing tests** — parse a `RUN-20260811-1702/` from seed manifests; filter by
  each dimension; `latest_run` is deterministic and returns `None` on empty (legitimate state).
- [ ] **Step 2: Implement** reusing `list_run_manifests`; expose `run` nodes through
  `factory.trace.model`'s `load_nodes`? No — keep runs in `factory.simulation` (they are
  evidence, not trace nodes); the model's reserved `run` literal is a projection alias.
- [ ] **Step 3:** full suite + lint + commit.

## Task 3: Metric ingestion + `metric_values`/`latest_failure`/`metric_history`

**Files:** `src/factory/simulation/evidence.py`, `tests/unit/simulation/test_evidence.py`
**Interfaces:**
```python
def metric_values(run: Run, metrics_json: dict) -> dict[str, float]
def metric_history(evidence_dir, metric_id) -> list[dict]   # [{run, commit, value, ts}] ascending
def latest_failure(evidence_dir, feature) -> Run|None       # most recent run with result != passed
def evidence_for_goal(evidence_dir, goal_id) -> list[Run]   # runs whose manifest lists the goal
```
- [ ] **Step 1: Failing tests** — spec §9.3 style history (`0.71 → 0.83 → 0.87` ascending);
  `latest_failure` deterministic; `evidence_for_goal` finds runs that list a goal.
- [ ] **Step 2: Implement** pure functions over manifests+metrics.json; `metric_history` sorts by
  manifest `recorded_ts` then `run_id` (stable tiebreak), never by mtime.
- [ ] **Step 3:** full suite + lint + commit.

## Task 4: Auto-evaluate goals from latest evidence

**Files:** `src/factory/simulation/evidence.py` (extend), `src/factory/goals/evaluator.py` (unchanged)
- [ ] **Step 1:** `evaluate_goals_from_runs(evidence_dir, goals)` — for each goal, take its
  experiment's latest passing-complete run, read the goal's `metric.name` from `metrics.json`,
  call `evaluate`, persist via Inc 2 `record`. This is the automatic pipeline spec §14/§16/§17 wants.
- [ ] **Step 2: Failing tests** — a new higher run flips a goal to REACHED and records evidence;
  a later lower run flips REACHED→REGRESSED (AC-07) automatically.
- [ ] **Step 3:** full suite + lint + commit.

## Task 5: Query surface (`query_simulation_run`, `query_latest_simulation`, `query_latest_failure`, `query_metric_history`)

**Files:** `src/factory/system/queries.py`
- [ ] **Step 1:** add four queries in the existing claim/freshness plumbing; each derives from
  `factory.simulation` (recorded claims with citations), matching AC-01's "latest simulation
  evidence" slot.
- [ ] **Step 2:** full suite + lint + commit.

## Task 6: Wire drone scenarios + seed evidence (cool_physical_ai_project)

- [ ] **Step 1:** `scripts/run_simulation.py`: load the `sim-testbench` harness config, run a
  scenario, write a `RUN-<ts>/` bundle (manifest + metrics.json + optional events/report) under
  `evidence/runs/`.
- [ ] **Step 2:** bind `multiple_threats.yaml`/`shark_warning.yaml` to experiments that score
  the reacquisition metric from `drone.validation.scorers`. Run the harness, commit 3 seed runs
  (one above, one below, one after a regression) so Inc 4/Inc 6 have real data.
- [ ] **Step 3:** run `python -m factory.system` queries against the seed runs; full gates green.

## Task 6b: Evidence sensitivity — patch-reversal (brief §5.2)

**Files:** `scripts/run_sensitivity.py` (product), `tests/unit/simulation/test_sensitivity.py`,
`src/factory/simulation/sensitivity.py`
**Ruling (brief §5.2 "Tests must prove sensitivity"):** a green simulation is not strong evidence
for a feature if it stays green after the feature is removed. The reference slice must prove the
same evidence **fails or materially changes** when the capability under test is disabled, on
paired seeds.

- [ ] **Step 1: Failing tests** — define the sensitivity harness contract: run scenario on the
  implementation, then with the behavior disabled, and assert the target metric degrades beyond a
  threshold on **paired seeds** (same seed both ways).
  - persistent-belief: disable `target_memory`/belief merge ⇒ duplicate investigations rise or
    reacquisition_rate drops materially vs the enabled run.
  - safety governor: inject an invalid/stale planner output ⇒ the governor deterministically
    rejects it and the fallback is visible in the run trace.
  - (Inc 6/7 follow-up) visualisation: corrupt/remove one evidence artifact ⇒ only the affected
    view degrades while the cockpit exposes the missing dependency (honest-incompleteness).
- [ ] **Step 2: Implement** `sensitivity.evaluate(feature, enabled_evidence, disabled_evidence,
  keys, tol)` returning per-metric deltas + a `SENSITIVE/INSENSITIVE` verdict; expose via a
  `sensitivity` subcommand; wire a gate note (not a hard CI block this slice) in the seed runs.
- [ ] **Step 3:** full suite + lint + commit `feat(sim): add evidence-sensitivity (patch-reversal) check`.

## Task 7: Review handoff

- [ ] **Step 1:** reviewer sub-agent — compliance vs spec §18–§20, §29–§30 (chain completeness,
  run format, v-cycle health, requirement goal linkage, stale evidence) + D3 additive rule.
- [ ] **Step 2:** fix findings as `T-###`; update checkboxes.

## Acceptance for Increment 3

- The chain `requirement → goal → experiment → run → metric → evidence` resolves end-to-end
  against real drone seed runs (AC-04/AC-07 driven by real evidence, not hand-fed values).
- `query_metric_history` returns deterministic ascending history; `latest_failure` returns the
  right run.
- v1 manifests continue to load unchanged (D3); full suite green.
- brief §5.2 sensitivity: disabling persistent belief / injecting an invalid governor output
  makes the reference evidence fail or degrade materially on paired seeds (patch-reversal
  principle demonstrated for the slice).
