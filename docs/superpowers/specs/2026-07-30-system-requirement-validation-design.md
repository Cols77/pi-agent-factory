# Design: System-Requirement Validation for the pif factory

**Date:** 2026-07-30
**Status:** Draft for review
**Author:** Colin AUBE (with Claude)
**Case study:** the Physical AI drone project (`cool_physical_ai_project`)

---

## 1. Problem

pif today validates **coherence** (does the work match the spec/plan/task) and
**code quality** (YAGNI/DRY + Definition of Done), but it has no notion of a
**standing system requirement**: an artifact with a stable ID that (a) states an
acceptance contract in testable terms, (b) is traced down to the code that
implements it and the check that validates it, (c) is validated by an
*executable* run that captures **metrics against a threshold**, and (d) is
reviewed by a human across all of those layers at once.

The pipeline already has most of the skeleton for this:

- `CONTEXT_GATHERER → DEV → VALIDATION → REVIEW → SESSION_REVIEW`
  (`src/factory/orchestrator/roles.py`, `nodes.py`, `runner.py`).
- A **VALIDATION role that is currently dormant** — `run_validation` runs the sim
  gate deterministically with no agent call (see the standing comment in
  `roles.py`).
- A **REVIEW agent** that already emits human-check `verify[]` items plus a
  `confidence` line.
- A **human review guide** (`review_guide.py` → `review-guide.json`) rendered by
  **two surfaces** — the TUI (`review-overlay.ts`) and the zero-dependency local
  web server (`review-server.ts`) — per the 2026-07-29 dual-surface design.
- A **spec → plan → task** pipeline where tasks carry a `dod:` block
  (`plan_to_tasks.py`).

What is missing is the **requirement layer** that threads an ID through all of
it. This design adds it, using the drone project's **computer-vision perception**
and **navigation/LLM decision-making** subsystems as the proving ground.

## 2. Goal (settled during brainstorming)

Add a first-class system-requirement layer with six components, each mapping onto
an existing pipeline seam:

1. **Requirement register** — `requirements/SR-###.md`, one file per requirement,
   ContextGit-style metadata (EARS statement, acceptance binding, upstream links,
   content checksum for staleness).
2. **Authoring flow** — requirements are distilled during brainstorming and
   *materialized* into the register; the **plan command consumes** the register
   and every task declares `satisfies: [SR-###]`. The plan never invents
   requirements.
3. **Validation execution** — activate the dormant VALIDATION role to run each
   bound requirement's check via a **harness contract**, capturing a metrics JSON
   + artifacts, then render a report.
4. **System-requirement review agent** — a new `REQ_REVIEW` role that verifies
   traceability + metric-vs-threshold and emits requirement-scoped human-check
   items (distinct from the existing code-quality REVIEW).
5. **Human review guide / control points** — extend `review-guide.json` and both
   review surfaces into a **requirement-scoped, four-layer review**
   (requirement → implementation → validation code → metrics/report), each an
   explicit approve/reject gate.
6. **Testbench integration contract** — a thin seam, *aligned to* the parallel
   sim-testbench design (§10), so the two efforts never deadlock.

### 2.1 Decisions locked during brainstorming

- **Requirements live in their own register** (not embedded as spec prose, not
  invented by the plan). The spec stays narrative; the plan stays work-breakdown.
- **Two validation domains behind one harness contract:**
  - **Perception** (sea segmentation, target detection) → **fixture harness** over
    labeled imagery, using the **Telekinesis** CV library (Cornea for
    segmentation, Retina for detection). Deterministic, single-run metrics.
  - **Behavioral** (navigation preemption, LLM tool use) → **sim testbench**,
    which simulates targets and swim/surf zones and feeds the planner/agent
    **ground-truth** detections (no CV in the sim loop). Non-deterministic,
    validated as a **pass-rate over N trials**.
- **Metrics + visualizations** surface as an **HTML/metrics panel inside the
  existing local web review surface** plus a numeric pass/fail table in the TUI —
  not a competing browser mechanism. The **live** sim testbench remains the place
  to set up and re-watch experiments.
- **Increment 1 is a navigation-preemption requirement run against a static
  recorded trace fixture**, so the spine ships fully decoupled from whether the
  testbench code exists yet.

## 3. Prior art borrowed (concepts, not code)

- **ContextGit** — typed, prefixed requirement IDs; metadata-in-file; a single
  git-friendly index; **checksum-based staleness** so a changed upstream
  requirement flags its downstream artifacts.
- **DroneReqValidator (DRV/DroneWiS)** — the pattern of monitoring a drone run
  against predefined acceptance parameters and emitting an **acceptance-test
  report** with a dashboard.
- **RobBDD / behaviour-driven acceptance testing of robotic systems** — EARS →
  executable acceptance, **temporal fluents** ("property holds *during* an
  interval"), and systematic scenario variation. We borrow the *shape* of
  time-anchored assertions without adopting the full JSON-LD/SPARQL toolchain.
- **R2Code / TVR** — a **self-reflective LLM traceability agent** that verifies
  requirement→code→test links and recovers missing ones; the model for
  `REQ_REVIEW`.
- **"Validating agentic behavior when correct isn't deterministic"** — behavioral
  and LLM-tool-use requirements are validated by **pass-rate over N trials**
  against a threshold, not a single boolean.

## 4. Architecture

The requirement layer threads the existing pipeline; new pieces are marked `*`.

```
requirements/SR-###.md *            (register: statement + binding + checksum)
        │  upstream/downstream edges
        ▼
spec.md ──▶ /specify-requirements * ──▶ plan.md ──▶ tasks (satisfies:[SR-###]) *
                                                        │
                CONTEXT_GATHERER ──▶ DEV ──▶ VALIDATION ──▶ REQ_REVIEW * ──▶ REVIEW ──▶ SESSION_REVIEW
                                              │ (activated)     │
                                              ▼                 ▼
                          harness contract *          traceability + metric check *
                          ├── fixture harness (Telekinesis)     │
                          └── sim testbench (Recorder trace)     │
                                     │                           │
                                     ▼                           ▼
                          validation-report.json * ──▶ review-guide.json (extended *)
                                                              │
                                          ┌───────────────────┴───────────────────┐
                                     review-overlay.ts (TUI)          review-server.ts (web + metrics panel *)
                                          └───────────────────┬───────────────────┘
                                                     review-decision.json  (unchanged handshake)
```

## 5. Requirement register

### 5.1 File format (`requirements/SR-###.md`)

One requirement per file, in the **case-study repo** (`cool_physical_ai_project`).
The register mechanism (schema, index, checksum, traceability queries) is a
**generic factory capability**; the requirement *content* is domain-specific.

```yaml
---
id: SR-001
title: "Navigation preempts patrol for an in-zone shark"
statement: >                       # EARS: When <trigger>, the <system> shall <response>
  When a shark is detected inside or adjacent to an active swim zone,
  the navigation system shall preempt the current patrol and investigate
  before resuming patrol.
domain: behavioral                 # behavioral | perception
upstream: [BR-002]                 # traceability edge up (business/mission need)
binding:
  harness: sim-testbench           # sim-testbench | telekinesis-fixture
  experiment: shark_warning        # scenario name / fixture-set id
  metric: preemption_success_rate
  trials: 20                       # >1 ⇒ stochastic; 1/absent ⇒ deterministic
  assert: ">= 0.90"
  window: { after_event: shark_detected, within_s: 5 }   # optional temporal fluent
checksum: sha256:<content-hash>    # of statement+binding; drives staleness
---

## Rationale
Swimmer safety: an unconfirmed shark near a swim zone must interrupt routine
patrol. Maps to the sim testbench's `shark_warning` scenario (patrol → investigate
→ confirm → warn → resume).

## Notes
Ground-truth detections are supplied by the sim (no CV in the loop for this SR).
```

Two binding shapes:

- **Deterministic (perception):** `metric` is single-run (`mean_iou`,
  `detection_map`); `assert` compares once. Example `SR-101` in §13.
- **Stochastic (behavioral / LLM tool use):** `trials > 1`; the metric is a
  **pass-rate** aggregated over N runs; `assert` compares the rate. Optional
  `window` encodes a temporal fluent (assert holds within N seconds of an event).

### 5.2 Index, traceability, and staleness

- A generated index (`requirements/index.json`, gitignored build artifact)
  aggregates all `SR-###.md` plus the reverse edges discovered from task
  frontmatter (`satisfies:`), commit trailers (`Satisfies: SR-###`), and binding
  targets. This is the traceability DAG: `BR → SR → task → code → validation`.
- **Staleness:** the `checksum` covers `statement` + `binding`. When a requirement
  changes, its recorded validation runs and its `satisfies:`-linked tasks are
  flagged **stale** (their last validation no longer proves the current
  statement). Staleness is surfaced in review (§9) and by a
  `factory requirements status` CLI; it never hard-blocks, it warns.

### 5.3 CLI surface (`src/factory/requirements/`)

- `factory requirements new` — scaffold an `SR-###.md` (id allocation +
  checksum), used by the authoring step.
- `factory requirements index` — (re)build `index.json` from files + edges.
- `factory requirements status [--stale]` — list requirements, coverage
  (has-code? has-passing-validation?), and staleness.
- `factory requirements show SR-###` — the requirement + its full trace.

## 6. Authoring flow

1. **Brainstorming** (unchanged skill) surfaces the acceptance criteria in
   conversation ("preemption must succeed ≥ 90% of the time", "segmentation IoU
   ≥ 0.80").
2. **`/specify-requirements`** — a thin materialization step (a factory command +
   a short skill) that turns those criteria into `SR-###.md` files via
   `factory requirements new`, lints each statement toward **EARS** phrasing, and
   requires a `binding`. It is human-gated: the register is the acceptance
   contract, so it gets an explicit read-through before planning.
3. **Planning** (`writing-plans` + `plan_to_tasks.py`) — the plan references
   requirement IDs; `plan_to_tasks.py` learns a `satisfies:` frontmatter key and
   carries it onto each task. The `CONTEXT_GATHERER` manifest gains the referenced
   `SR` bodies so the dev agent implements against the contract, not just the DoD.

`plan_to_tasks.py` change is additive: tasks without `satisfies:` behave exactly
as today.

## 7. Validation execution (activate the VALIDATION role)

`run_validation` (`nodes.py`) is extended from "run the sim gate" to "run the
bound validation for every `SR` this task satisfies." It stays **deterministic
orchestration** — no LLM needed to *run* a harness — driven entirely by the
`binding`.

### 7.1 Harness contract (`src/factory/validation/harness.py`)

A single Python interface, two implementations:

```python
class Harness(Protocol):
    def run(self, binding: Binding, workdir: Path) -> HarnessResult: ...

@dataclass(frozen=True)
class HarnessResult:
    metric_value: float          # single-run value, or aggregated pass-rate
    passed: bool                 # metric_value vs binding.assert
    trials: list[TrialResult]    # per-trial detail (1 entry when deterministic)
    artifacts: list[Path]        # PNGs/overlays/frames for the report
    raw: dict                    # harness-native detail (trace path, per-class AP, …)
```

- **`SimTestbenchHarness`** (behavioral SRs): resolves `binding.experiment` to a
  sim-testbench **scenario**, runs it **headless N times** (varying the seed),
  loads each run's **Recorder trace**, and runs a **metric extractor** over the
  trace (§7.2). Aligns to the sim-testbench design's `Recorder`/`Frame` and
  `python -m sim` (§10).
- **`TelekinesisFixtureHarness`** (perception SRs): runs the Telekinesis pipeline
  (Cornea segmentation / Retina detection) over a labeled fixture set once and
  computes IoU / mAP against ground truth (§11).

### 7.2 Metric extractors (`src/factory/validation/metrics/`)

Pure functions `extract(trace_or_preds, groundtruth, binding) -> float`, unit
testable in isolation:

- `preemption_success_rate` — over the trace's `active_directive` sequence: did an
  override/investigate directive fire within `binding.window` of the trigger
  event, and did patrol resume afterward? Pass-rate over trials.
- `llm_tool_use_accuracy` — the fraction of trials in which the agent issued the
  **expected tool/directive with correct args** at the decision point (compared
  to a per-scenario expectation). Handles LLM non-determinism by construction (N
  trials).
- `mean_iou`, `detection_map` — perception extractors over Telekinesis outputs.

### 7.3 Report artifact (`validation-report.json` + rendered panel)

The VALIDATION step writes `sessions/.factory-transcripts/<sid>/validation-report.json`:

```json
{
  "task": "T-042",
  "requirements": [
    { "id": "SR-001", "domain": "behavioral", "metric": "preemption_success_rate",
      "value": 0.90, "assert": ">= 0.90", "passed": true, "trials": 20,
      "artifacts": ["trajectory.png", "event-timeline.png", "tool-trace.json"] }
  ]
}
```

`review_guide.py` folds this into `review-guide.json` (§9). The **web review
surface** renders a **Metrics panel** from it (charts + embedded artifact PNGs);
the **TUI** renders the numeric pass/fail table and an "open report" action that
launches the web surface on the metrics panel. No new browser mechanism — this
extends `review-server.ts`, which already serves self-contained, CSP-safe HTML.

## 8. System-requirement review agent (`REQ_REVIEW`)

A **new role**, inserted after VALIDATION and before the existing code-quality
REVIEW. Distinct responsibility, modeled on R2Code/TVR: verify the requirement is
genuinely satisfied and *traced*, not that the code is tidy.

- **Skills:** `["verification-before-completion", "requirement-traceability-audit"]`
  (the latter vendored under `.pi/skills/` per `roles.py`'s hard-load contract —
  see §16).
- **Scope:** read-only (`allow=[]`, `bash="deny"`), like REVIEW.
- **Inputs:** the `SR` bodies this task satisfies, the diff, and
  `validation-report.json`.
- **Emits** a fenced JSON block:

```json
{
  "per_requirement": [
    { "id": "SR-001",
      "implemented": true,     "implements_note": "override path in priority_filter.py",
      "validated": true,       "metric_ok": true,  "margin": "0.90 vs >=0.90 (tight)",
      "stale": false,
      "confidence": "medium — passes exactly at threshold; margin is thin",
      "verify": [
        { "item": "Re-run shark_warning with a different seed; confirm preempt still fires within 5s",
          "file": "src/drone/mission/priority_filter.py", "why": "pass-rate is exactly at threshold" }
      ] }
  ]
}
```

The `margin`/`confidence`/`verify` fields deliberately flag **threshold-tight**
passes — exactly where a human should look. Findings flow into the review guide as
requirement-anchored items (§9).

## 9. Human review guide / control points

Extend the focus-guide (`review_guide.py` → `review-guide.json`) into a
**requirement-scoped** structure consumed by both surfaces (dual-surface design
§9 handshake unchanged).

### 9.1 `review-guide.json` additions

A `requirements[]` array, each entry carrying the four review layers:

```
requirements: [
  { id, statement,
    implementation: { files: [...] },        // ② diff filtered to files touching this SR
    validation:     { harness, experiment, binding },  // ③ how it's checked
    metrics:        { value, assert, passed, margin, artifacts },  // ④ from validation-report.json
    reqReview:      { confidence, verify: [...] },      // from REQ_REVIEW
    stale: false }
]
```

Existing gate-log summaries and code-review `verify[]` items remain; the
requirements array is additive, so a task with no `SR` renders exactly as today.

### 9.2 Surfaces

- **TUI (`review-overlay.ts`)** — a new **Requirements section** in the summary
  view:
  ```
  SR-001  nav preempts for in-zone shark     [pass 0.90 ≥ 0.90  ⚠ tight]
    ① statement   ② 2 files   ③ sim:shark_warning×20   ④ [o] open metrics
  ```
  Selecting a requirement filters the file view to its implementing files (layer
  ②) and shows its validation binding (③); `o` opens the web metrics panel (④).
  Requirement-anchored annotations reuse the existing `Annotation` model
  (a `file`-less annotation keyed to the SR id).
- **Web (`review-server.ts`)** — a **Requirements tab** listing each SR with the
  four layers inline, and a **Metrics panel** rendering charts from
  `validation-report.json` plus embedded artifact PNGs (trajectory, event
  timeline, tool-call trace; PR curve / confusion matrix / IoU heatmap for
  perception). Diff coloring stays CSS-only per the dual-surface non-goals.

Both surfaces still write the identical `review-decision.json`; approve/reject and
line-anchored feedback are unchanged. Requirement staleness renders as a warning
badge, never a hard block.

## 10. Testbench integration contract

The sim-testbench design (`2026-07-30-sim-testbench-design.md`) already reserves
the seam for us: §8 and §10.2 leave a `requirements: []` field on captured
scenarios "for the future requirements addon," and its Non-Goals name the
"Requirements tracking system (separate parallel effort)" — this design.

We **align to their artifacts** rather than invent a contract:

- **Input:** a **scenario YAML** (their format) whose optional `requirements:`
  field we populate with `SR-###` ids. `binding.experiment` names the scenario.
- **Execution:** a **headless replay** entrypoint. Their spec already has
  `python -m sim <scenario.yaml>`, a `Recorder`, and `Recorder.save(path)`.
- **Output we consume:** the **Recorder trace file** (list of `Frame`:
  `mission_clock`, `drone_pose`, `detections`, `active_directive`,
  `waypoint_status`). Our metric extractors read this; nothing more is required
  from them.

**The one thing we ask of the testbench session:** a documented, seedable headless
run that **writes the trace to a known path** (e.g.
`python -m sim <scenario> --headless --seed S --record out/trace.json`). This is a
small addition to what their spec already describes and is the entire contract.
Until it lands, `SimTestbenchHarness` reads a **static recorded trace fixture**
(a saved `trace.json`) so Increment 1 ships decoupled (§14).

## 11. Telekinesis (perception) binding

For perception SRs (Increment 3), `TelekinesisFixtureHarness` runs the
**Telekinesis Agentic Skill Library**:

- **Cornea** — sea-surface **segmentation** (color-space HSV/LAB or SAM/BiRefNet
  skills) → mask → `mean_iou` against labeled fixtures.
- **Retina** — **target detection** (YOLOX/RF-DETR, or Grounding DINO open-vocab
  for "swimmer/surfer/shark") → boxes → `detection_map` against labeled fixtures.

**Open item:** confirm the exact package/import path and skill call signatures for
Cornea/Retina before binding (§17). The harness isolates this behind the `Harness`
interface, so the exact API is contained to one file.

## 12. Visualizations (per domain)

| Domain | Metrics | Report visuals (artifact PNGs / panel) |
|--------|---------|----------------------------------------|
| Behavioral — preemption | preemption success-rate, latency-to-preempt | top-down **trajectory**, **event timeline** (trigger → preempt → resume) |
| Behavioral — LLM tool use | tool-call accuracy, arg correctness (pass-rate) | **tool-call trace** (expected vs actual per trial) |
| Perception — segmentation | mean IoU | **IoU heatmap**, per-frame mask **overlays** |
| Perception — detection | mAP, precision/recall | **PR curve**, **confusion matrix**, box overlays |

The sim testbench's own `MatplotlibPlotter` already produces trajectory /
detection-timeline / confidence-vs-range figures; where present we **embed those
PNGs** rather than re-plotting, and add only the assertion overlay (pass/fail vs
threshold).

## 13. Case-study requirements (concrete)

- **`SR-001` (behavioral, Increment 1)** — nav preempts patrol for an in-zone
  shark. `sim-testbench` / `shark_warning` / `preemption_success_rate` ≥ 0.90 over
  20 trials, within 5 s of `shark_detected`.
- **`SR-002` (behavioral, Increment 2)** — the LLM agent issues the correct
  `override`/warn tool calls with correct args during the shark cycle.
  `llm_tool_use_accuracy` ≥ 0.90 over 20 trials.
- **`SR-101` (perception, Increment 3)** — sea segmentation `mean_iou` ≥ 0.80 over
  the labeled fixture set (`telekinesis-fixture` / Cornea).
- **`SR-102` (perception, Increment 3)** — target detection `detection_map` ≥ 0.75
  (`telekinesis-fixture` / Retina).

## 14. Increment sequencing

- **Increment 1 — the spine (decoupled).** `SR-001` only, end-to-end against a
  **static recorded trace fixture**: register file + `factory requirements`
  CLI(new/index/status/show) → task `satisfies:` link in `plan_to_tasks.py` →
  `SimTestbenchHarness` reading the fixture trace → `preemption_success_rate`
  extractor → `validation-report.json` → `REQ_REVIEW` role →
  requirement-scoped section in both review surfaces (trajectory + event-timeline
  PNGs, numeric table + metrics panel). Proves the whole thread with one metric,
  no testbench dependency, no LLM in validation.
- **Increment 2 — stochastic + live.** Wire the real headless testbench run (the
  §10 contract), add `SR-002` LLM-tool-use with the N-trial pass-rate path and the
  tool-call-trace visual.
- **Increment 3 — perception + traceability.** `TelekinesisFixtureHarness`
  (Cornea/Retina) for `SR-101/102`; PR-curve/confusion/IoU-heatmap visuals; the
  traceability-graph view and staleness surfacing across the whole register.

## 15. Testing strategy

- **Python — register/CLI:** `SR-###.md` parse + checksum; `index` builds the DAG
  from files + `satisfies:` edges; `status --stale` flags a mutated requirement.
- **Python — extractors:** each metric extractor over a **synthetic trace**
  (preemption fires / does not fire / fires late) and synthetic preds (IoU/mAP)
  against known ground truth; pass-rate aggregation over N trials.
- **Python — harness:** `SimTestbenchHarness` against a fixture `trace.json`
  yields the expected `HarnessResult`; deterministic vs stochastic branches.
- **Python — role wiring:** `run_validation` runs bindings for a task's `SR`s and
  writes `validation-report.json`; `REQ_REVIEW` prompt/scope/skill registered and
  invoked in `runner.py`; `plan_to_tasks.py` carries `satisfies:`.
- **Python — review guide:** `review_guide.py` folds `validation-report.json` +
  `REQ_REVIEW` output into `review-guide.json`; a task with no `SR` is unchanged.
- **TS — surfaces:** TUI renders the Requirements section and filters files to an
  SR; `o` opens metrics; web `/api/review` includes `requirements[]` and the
  Metrics panel renders from `validation-report.json`; both still write the
  unchanged `review-decision.json`.

## 16. Files touched (anticipated)

**Factory (`pi-agent-factory`):**
- `src/factory/requirements/` (new) — register schema, index, checksum,
  traceability, CLI.
- `src/factory/validation/harness.py`, `.../metrics/` (new) — contract + extractors.
- `src/factory/orchestrator/roles.py` — add `REQ_REVIEW` (skill/scope/prompt);
  activate VALIDATION.
- `src/factory/orchestrator/nodes.py`, `runner.py` — run bindings, insert
  `REQ_REVIEW`, write `validation-report.json`.
- `src/factory/orchestrator/plan_to_tasks.py` — carry `satisfies:`.
- `src/factory/orchestrator/review_guide.py` — fold requirements into the guide.
- `.pi/skills/requirement-traceability-audit/SKILL.md` (new, vendored — required
  by the hard-load contract in `roles.py`).
- `pi-ext/factory-watch/src/review-overlay.ts`, `review-server.ts` — Requirements
  section/tab + Metrics panel (reuse `review-model.ts`, `review-diff.ts`).

**Case study (`cool_physical_ai_project`):**
- `requirements/SR-###.md` — the actual requirements.
- validation fixtures: a recorded `trace.json` (Increment 1), labeled CV fixtures
  (Increment 3).
- the sim testbench's reserved `requirements:` scenario field, populated.

## 17. Non-goals & open items

**Non-goals (YAGNI):** JSON-LD/SPARQL requirement modeling (borrow RobBDD's fluent
*shape* only); auto-generating requirements from the spec without human gating;
requirement editing UI in the web surface; CV inside the sim loop (explicitly a
testbench non-goal); syntax highlighting / GitHub sync (inherited from the
dual-surface non-goals).

**Open items:**
1. Exact Telekinesis Cornea/Retina package + call signatures (§11) — confirm
   before Increment 3; isolated behind `Harness`.
2. The testbench's seedable headless `--record <path>` entrypoint (§10) — the sole
   ask of the parallel session; Increment 1 uses a static trace fixture until then.
3. EARS-lint strictness for `/specify-requirements` — advisory vs. blocking (lean
   advisory to start).
