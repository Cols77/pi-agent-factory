# Design: Increment 2 — Webapp Live Harness + Deterministic Polish Node

Date: 2026-08-01
Status: Approved (brainstorming) — ready for implementation planning
Builds on: `2026-07-30-system-requirement-validation-design.md` (§14 Increment
sequencing), `2026-07-31-polish-workflow-and-validation-node-design.md`
(project-agnostic validation node, §3/§4/§9/§10).

## 1. Problem

Increment 1 (the "spine": 1A/1B/1C) proved the whole requirement-validation
thread against a **static recorded trace fixture** — register → binding → harness
→ `validation-report.json` → `REQ_REVIEW` → requirement-scoped review surfaces.
The original Increment 2 ("stochastic + live", §14 of the 1A design) was to wire
the **drone sim testbench**: a seedable headless run that writes a trace to a
known path (§10 testbench-integration contract). That seam has **not landed** —
`src/sim/` has a `Recorder.save()` but no headless `--seed`/`--record` entrypoint,
so `SimTestbenchHarness` still reads a fixture. Increment 2 is therefore blocked on
another session's deliverable.

Separately, the polish workflow's control loop lives in a **skill**
(`.pi/skills/polish/SKILL.md`): an LLM runs discover → setup → gather feedback →
synthesize → confirm → route, while the Python side (`run_polish_session`) is only
a lifecycle wrapper (setup → open browser → `route()` **pre-supplied** findings →
teardown). This does **not** reuse the deterministic-orchestration philosophy that
factory-run's runner embodies (Python owns the topology; the LLM is invoked as
bounded roles at fixed nodes).

## 2. Goal (settled during brainstorming)

Retarget Increment 2 away from the drone-sim dependency to the **CareerOS webapp**
(`C:/coding/markdown_pdf_system`), which already ships the missing brick: Playwright
gives a **seedable, headless run that emits artifacts** — exactly the §10 seam. Two
faces, both on the webapp:

- **Face A — Automated:** the first *live* harness (`PlaywrightE2EHarness`), plus
  the project harness registry that lets a repo declare it.
- **Face B — Deterministic polish orchestrator:** re-architect polish so a Python
  orchestrator owns the loop (factory-run philosophy), runs front+back and opens a
  browser, captures human feedback live, and has **factory-run immediately handle**
  the resulting tickets in the background while the human keeps play-testing.

### 2.1 Decisions locked during brainstorming

1. **Scope:** retarget only. `SR-002` (drone LLM-tool-use) and drone-sim-live
   **defer** to a later increment; perception stays Increment 3.
2. **Dependency:** sits on **Increment 1B** (VALIDATION-role wiring + harness
   registry seam) and **1C** (requirement-scoped review surfaces). Both must be in
   the base main line before Face A is meaningful end-to-end.
3. **Fix cadence:** **background / async, live** — a confirmed finding is handled
   by factory-run in the background; the human never blocks and re-verifies fixes
   live via dev-server hot-reload.
4. **Fix isolation:** **serial worker + isolated worktree + fast-forward
   integrate** — findings queue; one fix at a time. Each fix runs factory-run in a
   throwaway git worktree at live HEAD, and only the finished, green, committed
   result is fast-forwarded into the live branch the dev-server watches. The live
   working tree therefore only ever transitions between committed, validated
   states — never a mid-fix edit — and a failed fix touches it not at all. Serial
   + no human commits to live ⇒ live HEAD is stable during a fix ⇒ the FF always
   succeeds (no integrator/merge-conflict machinery). This also honors the
   standing "never work in the live checkout" rule.
5. **Two deterministic gates** (see §6): a lightweight **pre-queue glance** and a
   post-fix **acceptance checklist** against the reloaded webapp.
6. **"Green" for auto-commit:** factory-run's automated VALIDATION passes (the
   task's `satisfies:` SR gate **plus** standing regression, §4.2 of the polish/
   validation-node design); factory-run's **internal human-review gate is
   auto-approved for polish-originated tasks** — the human's live re-test is the
   real acceptance.
7. **UI surface:** reuse the in-session mission-control / factory-watch surface
   (feedback input + live queue/fix-progress panel + the two gates), not a bare CLI.

## 3. Face A — `PlaywrightE2EHarness` (the "stochastic + live" milestone)

### 3.1 Project harness registry (generalize `default_harness_for`)

1B selects a harness via `default_harness_for(traces_dir)` — a single hard-coded
default. Generalize this to a **per-project registry** (the §3 seam of the polish/
validation-node design):

```python
# markdown_pdf_system/.factory/registry.py  (imported by the factory)
from factory.validation.harness import Harness
HARNESSES: dict[str, Harness] = {
    "playwright-e2e": PlaywrightE2EHarness.from_config(...),
}
```

- The factory, running against a repo, loads that repo's `.factory/registry.py`
  and resolves `binding.harness` against `HARNESSES`, falling back to the built-in
  default only when a project declares none (preserving 1B's behaviour for the
  drone repo). Keep 1B's "missing harness/scenario **warns**, does not hard-fail"
  semantics.
- The DEV agent's write-scope **excludes** `requirements/**` and harness code
  (§4.1 trust model) — this is a scope-guard entry to add when SR-linked webapp
  tasks run (carried as a deferred item, §9).

### 3.2 The harness

`PlaywrightE2EHarness` is the analog of `SimTestbenchHarness`, but it **executes**
a run instead of replaying a fixture:

- **Input:** a `binding` whose `experiment` names a Playwright spec/tag and whose
  `metric` is `e2e_pass_rate`; `binding.trials` = N seeded runs.
- **Execution:** invoke Playwright headless with a per-trial seed (env var, e.g.
  `E2E_SEED`), against the app served by the `devserver` playground. Each run
  writes its JSON reporter output to a known path under `workdir`.
- **Output:** fold each run's reporter JSON into a `TrialResult(seed, passed)`;
  `metric_value = pass_rate = mean(passed)`; `passed = evaluate_assertion(rate,
  binding.assert_expr)`. Reuse the existing `HarnessResult`/`TrialResult` shapes
  and the `declared-vs-actual trials` guard 1B added, so review surfaces report N
  correctly.
- **Determinism note:** Playwright is stochastic (network/timing); the N-trial
  pass-rate path is what makes this the genuine "stochastic + live" milestone (vs.
  Increment 1's deterministic fixture replay).

### 3.3 Webapp SRs (human-authored)

Author 2–3 SRs in the register, each bound to a Playwright spec + threshold, e.g.:

- `SR-010` — sign-in flow succeeds. `e2e_pass_rate ≥ 0.95` over N runs.
- `SR-011` — tailor-CV emits a valid (non-empty, parseable) PDF. `e2e_pass_rate ≥
  0.90`.
- (optional) `SR-012` — markdown→PDF conversion renders. threshold TBD by author.

Prove the thread live: all green, then intentionally break a flow → the bound SR
goes **red** in the review surfaces and the standing regression flags it.

## 4. Face B — Deterministic polish orchestrator

Replace the skill-owned loop with a Python orchestrator modelled on factory-run's
runner. **Python owns the topology**; the LLM is invoked as exactly one bounded
role.

### 4.1 Node flow

1. **setup** — the `devserver` playground starts backend + frontend (using the
   repo's documented dev commands + health checks from `.factory/factory.yaml`),
   waits for both healthy, opens the browser to the frontend entrypoint.
2. **feedback-capture loop** — the human play-tests and types natural-language
   feedback; capture is **non-blocking** (the loop never waits on the fix-worker).
3. **`SYNTHESIS` role** (the only LLM call) — raw feedback → structured
   `Finding`(s): title, one-line description, repro `snapshot` (route/steps/state),
   `artifacts` (screenshots), linked `SR-###` if it violates a known requirement.
   Bounded, single-purpose — it does **not** own the loop.
4. **Gate 1 — pre-queue glance** (§6.1).
5. **serial fix-worker** (§5) — drains the queue, runs factory-run on the live
   branch, commits on green, dev-server hot-reloads.
6. **Gate 2 — post-fix acceptance checklist** (§6.2).
7. **teardown** — stop backend + frontend (the existing idempotent teardown with
   SIGTERM/atexit guards is retained).

### 4.2 What changes vs. today

- The loop, both gates, queue management, and worker triggering move **out of the
  skill into Python**. The skill (if kept at all) shrinks to a thin "how to talk to
  the human" prompt used only inside the `SYNTHESIS` node.
- `run_polish_session` grows from a lifecycle wrapper into the orchestrator; it no
  longer takes a pre-supplied `findings` list — it **produces** findings from live
  feedback.
- The `route()` spine (`src/factory/polish/routing.py`) is reused unchanged as the
  single place a `Finding` becomes a `T-###` task.

## 5. The serial background fix-worker (worktree-isolated)

- A single worker drains the finding queue **one at a time** on a background
  thread; the worker itself is a pure queue/thread and delegates each finding to a
  `FixExecutor`.
- **Worktree isolation + fast-forward integrate.** The `WorktreeIsolatedExecutor`
  creates a throwaway git worktree at live HEAD, `route()`s the finding into the
  worktree's `tasks/`, and runs factory-run **inside the worktree** — so every
  intermediate dev edit happens off the tree the dev-server watches. Only on green
  does it fast-forward the finished commit(s) into the live branch, so the live
  working tree updates **once, atomically, to a consistent validated state**, and
  the dev-server hot-reloads exactly once. A failed fix's worktree is discarded and
  the live tree is never touched.
- **Commit-on-green:** factory-run's own VALIDATION must pass — the task's
  `satisfies:` SR gate **plus** standing regression (§4.2 of the validation-node
  design). factory-run's **internal human-review gate is auto-approved** for
  polish-originated tasks (`--auto` mode / no `HumanReviewGate`), because the
  human's live re-test is the acceptance.
- On green → fast-forward into live → dev-server hot-reloads → the change surfaces
  in Gate 2. On red (validation fails, or a non-fast-forwardable result) → the
  worktree is discarded and the ticket surfaces in Gate 2 as **failed-to-fix**, not
  silently dropped.
- **Why the FF is always clean (no integrator needed):** the worker is serial and
  the human never commits to the live branch, so live HEAD is stable for the
  duration of a fix ⇒ the fix branch is strictly ahead ⇒ `merge --ff-only` always
  succeeds. A long fix delays later queued fixes but never blocks the human's
  testing. (Edge case: if live HEAD ever moved, rebase-then-FF; noted, not the
  norm.)

## 6. The two deterministic gates

Both gates are **deterministic** (orchestrator-built, not LLM-driven).

### 6.1 Gate 1 — pre-queue glance (lightweight)

- When `SYNTHESIS` produces a `Finding`, the synthesized ticket (title +
  one-line + linked `SR-###`) is shown for a quick **accept / edit / discard**
  before it enters the queue.
- Preserves the current "nothing is written to the ledger until the human
  confirms" rule — just moved from the skill into the orchestrator. Kept
  intentionally light so it does not stall async immediacy.

### 6.2 Gate 2 — post-fix acceptance checklist

- As the worker lands fixes on green and the app hot-reloads, each landed change
  appears as a row in a running, deterministic list: **what changed, which
  finding/ticket, which `SR-###`**.
- **Tick = done/accept:** the change is confirmed; if it was `SR`-linked, ticking
  **re-grounds** that requirement (§4.3 — human judgment confirms the check is
  meaningful).
- **Comment = wrong:** a change that didn't work or isn't correct → the comment
  becomes a **new `Finding`, linked to the original**, and is re-queued for the
  worker (the rework loop) via the same `route()` spine.
- Failed-to-fix tickets (§5) also appear here for the human to comment/redirect.

## 7. UI surface

Reuse the in-session mission-control / factory-watch surface (the area the 1C
review surfaces already live in):

- a **feedback input** (natural-language, non-blocking),
- a **live queue / fix-progress panel** (queued → running → committed/failed),
- **Gate 1** inline accept/edit/discard on synthesis,
- **Gate 2** the running acceptance checklist with tick / comment affordances.

No new web server is required beyond what factory-watch already provides; the
polish orchestrator drives this surface the way the runner drives review.

## 8. Testing strategy

- **Harness registry:** loading a project `.factory/registry.py` resolves
  `binding.harness` to the declared harness; absent registry → built-in default;
  unknown harness → warn, not hard-fail.
- **`PlaywrightE2EHarness`:** against a **recorded Playwright reporter JSON
  fixture** (pass / fail / mixed trials), yields the expected `HarnessResult`
  (per-trial booleans, pass-rate, assertion). The live Playwright invocation is
  covered by one thin smoke test that actually runs a trivial spec headless with a
  seed and asserts a report file is produced.
- **Orchestrator nodes:** feedback → `SYNTHESIS` (faked LLM) → `Finding`;
  Gate 1 accept/edit/discard transitions; enqueue; worker green→commit vs.
  red→failed-to-fix; Gate 2 tick (re-ground) and comment (new linked finding
  re-queued). Deterministic; no live LLM.
- **`route()`** remains covered by existing polish routing tests; add the
  rework-loop case (comment → new finding → route).
- **Playground:** the CareerOS `devserver` playground `setup`/`teardown` health
  and idempotent-teardown behaviour (reuse existing DevServerPlayground tests;
  confirm exact CareerOS dev commands from its README/COMMANDS.md).

## 9. Deferred steps / iterate-after (KEEP — resume points)

- **[Scope-guard]** DEV write-block on `requirements/**` + harness code (§3.1,
  §4.1 trust model) as an explicit scope-guard entry when SR-linked webapp tasks
  run.
- **[SR-002 / drone-live]** the original Increment-2 drone path (LLM-tool-use
  accuracy, tool-call-trace visual) resumes once the sim-testbench headless
  `--seed --record` entrypoint (§10) lands.
- **[Perception]** Increment 3 (Telekinesis/Cornea/Retina) unchanged.
- **[Parallelism]** *concurrent* fix execution (multiple worktrees at once) + a
  serialized integrator for cross-fix ordering — deferred. Increment 2 is
  **serial** worktree isolation with a plain fast-forward (§5); concurrency is the
  future extension.
- **[Suites/tags]** use-case grouping so the sweep/polish can select "the right
  use cases for the type of work" (from the validation-node design's deferred
  list).
- **[CareerOS launch detail]** confirm exact dev commands + health checks + the
  initial use-case list from CareerOS's README/COMMANDS.md when planning.

## 10. Non-goals & open items

- **Non-goals:** drone-sim live run; `SR-002`; perception; *concurrent* (parallel)
  fix execution; a new standalone web server; changing the register/CLI authored in
  1A. (Serial worktree-isolated fix execution IS in scope — §5.)
- **Open items to resolve in planning:** the exact Playwright JSON reporter shape
  and seed-injection mechanism for CareerOS. (Resolved during planning: factory-run
  `--auto` is the auto-approve mode — no new flag; the orchestrator surfaces onto
  factory-watch via an atomic-JSON file bridge, Plan B2.)
