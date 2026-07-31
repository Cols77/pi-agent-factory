# Design: Polish Workflow + Project-Agnostic Validation Node

**Date:** 2026-07-31
**Status:** Draft for review
**Author:** Colin AUBE (with Claude)
**Builds on:** `2026-07-30-system-requirement-validation-design.md` (Increment 1A, merged)

---

## 1. Problem

Increment 1A gave the factory a standing system-requirement layer with an
**automated** validation node: a requirement's `binding` (harness + experiment +
metric + threshold) is run and scored to pass/fail. Three gaps remain:

1. **Project-agnostic validation.** 1A's node resolves `binding.harness` via a
   single `default_harness_for` that only knows `sim-testbench`. Real use needs a
   repo to declare *its own* validators — the drone repo runs its simulator, a
   perception task scores fixtures, a webapp runs an e2e suite. The node core must
   stay domain-blind.
2. **Meaningful validation (human-in-the-loop).** A coding agent can write
   hollow tests that pass without validating anything. A human must be able to
   **easily confirm whether a requirement genuinely works** — and to catch the
   case where an automated metric is green but the behaviour is actually wrong.
3. **A place to explore and give feedback.** Beyond the task-by-task dev flow
   (`factory-run`), the user wants a **polish workflow**: exercise real use cases,
   say what went wrong in natural language, and have that turn into fix-work to
   iterate on — without leaving the pi session.

This design adds the **exploratory face** of the validation node (the polish
workflow) and the **trust model** that keeps validation meaningful, while keeping
the automated face (1A + Increment 1B) as the standing regression gate.

## 2. Goal (settled during brainstorming)

**The validation node has two faces that share one feedback spine**, driven by a
per-project registry:

```
                 project registry (per-repo: .factory/…)
                 ├── harnesses:   {sim-testbench, telekinesis-fixture, playwright-e2e, …}   ← automated
                 └── playgrounds: {sim-testbench, webapp-devserver, perception-viewer, …}   ← exploratory
                          │                                        │
        AUTOMATED FACE (1A/1B, the dev gate)      EXPLORATORY FACE (polish, human-judged)
        Harness.run() → metrics → pass/fail       Playground.setup(usecase) → human play-tests
        scoped by task.satisfies + full-suite      human gives feedback (conversational)
        regression each iteration                          │
                          │                                │
                          └──────────► finding / failure ◄─┘
                                        │
                     finding → bug → fix-task ROUTER  (one spine; generalizes sim-testbench bug_to_task)
                                        │
                                   task ledger  ──►  factory-run fixes it  ──►  re-validate / re-polish
```

### 2.1 Decisions locked during brainstorming

- **Polish is a separate human-driven loop** (`factory polish`), connected to
  `factory-run` only through the **shared task ledger** (via the router). Not a
  second dev pipeline.
- **Polish is exploratory and human-judged**, not an automated metric sweep. The
  human exercises a use case and judges what went wrong.
- **Playground owns the environment lifecycle** (setup / teardown); the **pif
  session owns the feedback** (conversational) and its **synthesis into tickets**.
- **Contracts are defined our side** and shipped decoupled: P1 runs against a thin
  reference playground; the drone sim testbench and the webapp implement the
  contract later.
- **Trust model:** the SR acceptance contract is **human-owned**; the DEV agent is
  scope-blocked from editing it. The **full SR suite is validated every
  factory-run iteration** (standing regression); expensive harnesses may opt out
  via `periodic`. Polish is the human's periodic **meaningfulness** check and can
  target the *validation itself*, not just the implementation.

## 3. The validation node is project-agnostic

The node never mentions drones. A repo declares what it has in a **per-project
registry** under `.factory/` (discovered by the factory when it runs against that
repo):

```python
# .factory/registry.py  (per project; imported by the factory)
from factory.validation.harness import Harness
from factory.polish.playground import Playground

HARNESSES: dict[str, Harness] = {...}      # automated validators this repo provides
PLAYGROUNDS: dict[str, Playground] = {...}  # exploratory environments this repo provides
```

- **Automated face:** 1A's `default_harness_for` generalizes to read `HARNESSES`
  from the project registry (this lands with **Increment 1B**, §8).
- **Exploratory face:** `factory polish` reads `PLAYGROUNDS` (this design, §5).

The drone repo registers `sim-testbench` (both a harness and a playground); a
webapp registers a `devserver` playground + a `playwright-e2e` harness; a
perception task registers a `telekinesis-fixture` harness + a viewer playground.

## 4. Trust & meaningfulness model

This is the answer to "avoid the coding agent setting up meaningless tests."

### 4.1 The acceptance contract is human-owned

- The requirement register is authored/gated by a human (`/specify-requirements`).
  The `binding` (which scenario, which metric, which threshold) is the acceptance
  contract.
- The **DEV agent's write-scope excludes `requirements/**` and the validation
  harness code** (a scope-guard rule — see `pi-ext/scope-guard`). When factory-run
  implements an SR-linked task, the agent writes *implementation against a fixed
  contract*: it cannot rewrite the contract, lower a threshold, or replace the
  real-scenario check with a hollow assertion to make itself pass.
- Therefore the **SR suite is the meaningful layer**: unlike the agent's own TDD
  unit tests (which can be hollow — exactly the failure mode to guard), an SR
  validation runs a human-specified scenario against a human-set threshold. The
  agent can game a test it authored; it cannot game an acceptance check it does
  not own.

### 4.2 Standing full-suite regression (every iteration)

- Each factory-run iteration validates the task's `satisfies:` SRs **as a gate**,
  **plus re-runs all other SRs as regression**. A previously-green SR going red
  flags/blocks — so once an SR is confirmed meaningful it stays consistently
  validated across iterations.
- **Cost control:** a binding may be marked `cadence: periodic` (vs. the default
  `every_iteration`) so an expensive harness (heavy sim, long e2e) runs on a
  full-sweep cadence (end-of-plan / on-demand) instead of every iteration. The
  gate for the *current* task's `satisfies:` SRs always runs regardless of cadence.
- This lives in the automated face and lands with **Increment 1B** (§8). It is the
  prerequisite for "consistently validated across iterations."

### 4.3 Polish re-grounds the suite (meaningfulness)

- The human periodically play-tests a use case and confirms an SR *genuinely*
  works. A polish **finding can target the SR/binding itself** — "this check is
  hollow / doesn't capture what I care about" — producing a fix-task against the
  *validation*, not the implementation. Human judgment continuously re-grounds the
  automated suite so green never drifts away from real.

## 5. The polish workflow

`factory polish` is a **pif session** (conversational), connected to factory-run
only through the ledger.

### 5.1 Contracts (`src/factory/polish/`)

```python
# playground.py
@dataclass
class PlaygroundSession:
    entrypoints: list[str]     # URLs/paths to open in the navigator (frontend, backend/docs)
    describe: str              # what's running + how to interact
    def teardown(self) -> None: ...   # kill dev servers, close browser, clean up

class Playground(Protocol):
    def list_usecases(self) -> list[str]: ...
    def setup(self, usecase: str) -> PlaygroundSession: ...

# finding.py
@dataclass(frozen=True)
class Finding:
    usecase: str
    description: str            # the human's "what went wrong", as synthesized
    snapshot: dict             # reproducible state (e.g. sim scenario snapshot, or route/steps)
    sr: str | None = None      # optional SR-### this violates → becomes task.satisfies
    artifacts: list[str] = ()  # screenshots, logs, repro files
```

The **Playground owns only the environment lifecycle**. Feedback capture and its
synthesis into `Finding`s is the polish session's job (§5.2) — this is what lets
the same contract serve both the drone (discrete bug-capture) and the webapp
(free-form conversation).

### 5.2 The polish session loop

1. `factory polish --usecase <name>` (or interactive pick from `list_usecases()`).
2. `Playground.setup(usecase)` → spins the environment up, waits for health,
   returns entrypoints; the session **opens the navigator** to them.
3. The agent invites feedback: *"It's up at <entrypoints> — play around and tell
   me what you find."* The human **explores and gives feedback naturally in the pi
   session**; the agent accumulates it, may drive/screenshot the environment
   itself (browser tools), and asks clarifying questions.
4. The human signals **done**.
5. The agent **synthesizes** the accumulated feedback into a **proposed ticket
   list + an action summary** ("I'll create T-x…T-y with these titles/DoDs,
   linking SR-… where relevant").
6. On **human confirmation**, the **router** (§6) creates the tickets in the
   ledger; then `PlaygroundSession.teardown()`; the session ends.

Nothing is written to the ledger until the human confirms the summarized actions.

### 5.3 Two feedback sources, one synthesis

The discrete style (the drone sim testbench's press-B bug-capture → a snapshot
YAML) and the conversational style (webapp free-form chat) are just two ways to
accumulate feedback. Both converge on the **same step 5–6**: agent synthesizes →
human confirms → router creates → teardown. The confirm-before-create summary is
the universal default for every playground.

## 6. The finding → bug → fix-task router (`src/factory/polish/routing.py`)

One spine, harness/playground-agnostic. `route(finding) -> Task`:

- Creates a task file in the ledger: `title` from the finding, `body` = the
  description + the reproducible `snapshot`, `satisfies: [finding.sr]` when a
  requirement was linked, and a DoD like *"the `<usecase>` use case no longer
  exhibits: `<description>`"*.
- Generalizes the sim testbench's planned `bug_to_task` (its spec's T-050) into
  the single place findings become tasks, so routing is uniform across
  playgrounds.

## 7. Coordination with the sim-testbench session

Two touchpoints (both already half-reserved in the sim-testbench design):

1. Its bug-capture's reserved `requirements: []` field → populate with the linked
   `SR-###` so a captured bug can carry its requirement link.
2. Its planned `bug_to_task` (T-050) should **emit a `Finding` into our router**
   rather than create tasks itself, so there is a single routing spine.

This is the only ask of that session; the drone sim testbench then becomes a
`Playground` implementation (§ P3) whose discrete captures feed the same
synthesis/confirm step.

## 8. Relationship to Increment 1B (automated face)

The **standing full-suite regression** (§4.2) and the **project harness registry**
(§3) are the automated-face counterparts and land with **Increment 1B**, which
wires 1A's runner into `factory-run` (activate the VALIDATION role, fold
`validation-report.json` into `review-guide.json`). 1B is therefore the
prerequisite for "consistently validated every iteration." The **polish P-series
is decoupled** from 1B and can proceed in parallel (it only needs the ledger + the
router).

1B must also resolve the deferred 1A item: `binding.trials` is currently ignored
(the report shows the fixture's trial count, not the requirement's declared
count) — 1B needs a guard (`len(trials) >= binding.trials`) or a `declared_trials`
field so review surfaces don't misreport "N trials passed."

## 9. The webapp P2 target (concrete)

`C:/coding/markdown_pdf_system` — a CV/resume + markdown→PDF webapp with
`frontend/` and `backend/` directories. Its `Playground.setup(usecase)`:

- starts the backend and the frontend using the repo's documented dev commands
  (see its `README.md` / `COMMANDS.md`), waits for both to be healthy,
- returns the frontend URL (and backend/docs URL) as `entrypoints`,
- `teardown()` stops both processes.

Use cases are the app's flows (e.g. "sign-in", "tailor CV", "convert markdown",
"job search") — declared by the project's `PLAYGROUNDS` registry entry. This is
the proving ground for the conversational-synthesis loop (§5.2).

## 10. Increment sequencing

- **P1 — decoupled spine (buildable now).** `Playground`/`PlaygroundSession` +
  `Finding` + the **router** + the `factory polish` session loop
  (setup → open navigator → conversational feedback → synthesize → confirm →
  create tickets → teardown), proven against a **thin reference playground**
  (e.g. a headless "replay a drone scenario + accept a typed finding" stub). No
  dependency on the unbuilt sim-testbench interactive pieces or on 1B.
- **P2 — webapp playground.** `markdown_pdf_system` implements `Playground`:
  launch front+back, open the browser, conversational feedback → synthesized
  tickets. The real proving ground for the natural-chat model.
- **P3 — drone sim testbench playground.** The sim testbench implements
  `Playground` (discrete bug-capture feeding the same synthesis/confirm step),
  once its interactive/bug pieces (T-046/047) land; reconcile `bug_to_task` into
  the router (§7).

## 11. Deferred steps / iterate-after (KEEP — resume points)

These are intentionally out of P1's scope; revisit in the noted increment:

- **[1B] Automated face wiring** — activate the VALIDATION role in `factory-run`
  to call `run_requirement_validation`; fold `validation-report.json` into
  `review-guide.json`; **project harness registry** (§3) replacing
  `default_harness_for`; **standing full-suite regression** with the
  `cadence: every_iteration | periodic` policy (§4.2); resolve the `binding.trials`
  discrepancy (§8).
- **[1C] TS review surfaces** — requirement-scoped section/tab + metrics panel in
  the TUI + local web review surfaces (from the 1A design).
- **[Trust] Scope-guard rule** — add the DEV-role write-block on `requirements/**`
  and harness code (§4.1) as an explicit scope-guard entry when 1B activates
  SR-linked tasks.
- **[P2 detail] markdown_pdf_system launch commands** — confirm the exact dev
  commands + health checks + the initial use-case list from its README/COMMANDS.md
  when P2 is planned.
- **[P3] Sim-testbench Playground** — depends on sim-testbench T-046/047/050;
  reconcile `bug_to_task` → router (§7).
- **[Perception] Telekinesis harness + viewer playground** — the perception
  domain (Cornea/Retina fixtures) from the 1A design's Increment 3; confirm the
  Telekinesis API before binding.
- **[Suites/tags] Use-case grouping** — optional tags/suites on requirements and
  playground use cases so `factory polish --suite <x>` and the automated sweep can
  select "the right use cases for the type of work." Nice-to-have once multiple
  use cases exist.

## 12. Non-goals & open items

**Non-goals (P1):** automated metric sweeps in polish (polish is human-judged);
building the webapp or drone playgrounds (P2/P3); the 1B automated regression
(separate spec); a GUI for polish (it is a pif conversation).

**Open items:**
1. Exact `markdown_pdf_system` dev/launch commands + health checks (§9, deferred to
   P2 planning).
2. How `teardown()` guarantees process cleanup on abnormal session exit (P1 must
   handle the crash/interrupt path so dev servers don't leak).
3. Whether the router should de-duplicate near-identical findings across a single
   polish session before creating tickets (lean: surface duplicates in the
   confirm summary, let the human merge).
