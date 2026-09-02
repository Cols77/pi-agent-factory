# FEAT-15 — Polish Flow (POLISH-FLOW)

_Status: **design dossier** (2026-08-27). Owner: Python factory polish loop + a surfaced product
surface. This makes the iterative refinement workflow a first-class, maintained, surfaced feature —
it **already exists** in `src/factory/polish/` but is absent from the feature list and unpositioned.
Planning/design only.

_Parent: `docs/superpowers/specs/2026-08-26-coherence-inc9-programme-session-capture.md` (FEAT-15
proposal). Companions: FEAT-14 (VALIDATION-GATES — provides `sim_human_visualization`), FEAT-16
(MODULAR-WORKFLOWS — the `polish` template), FEAT-13 (GOVERNED-EXECUTION-DRIVER runs it), FEAT-10
(console surfaces it)._

---

## 1. Purpose

Let a user **exercise the system / a real use case, say what's wrong in natural language, and have
that turn into fix-work that lands and re-gates** — without leaving the session. It is the
"polish workflow that allows to refine iteratively the behavior of the system under development."

The design origin (`docs/superpowers/specs/2026-07-31-polish-workflow-and-validation-node-design.md`)
already frames it as the **exploratory face** of validation with a **human-in-the-loop** guarantee: a
coding agent can write hollow tests that pass without validating anything, so a **human must confirm a
requirement genuinely works** (live, in the playground) before it is accepted.

---

## 2. Built-already vs genuinely-new (honest delta)

### Already built (real, cite these — do not claim they're missing)
- **The polish loop is implemented:** `src/factory/polish/` — `orchestrator.py`, `playground.py`,
  `sim_live.py`, `devserver.py`, `findings.py`, `routing.py`, `synthesis.py`, `worker.py`,
  `executor.py`, `gates.py`, `session.py`, `cli.py`. It already does: find a finding → isolate a
  worktree → run a dev agent → fast-forward integration → re-gate → play-test.
- **Design/decs:** `2026-07-31-polish-workflow-and-validation-node-design.md` (two faces: automated
  harness + exploratory playground; "a human must confirm a requirement genuinely works").
- **Config:** `src/factory/config.py` parses `gates`, `harnesses`, `playgrounds` from `factory.yaml`.
- **Gates respect:** `2026-08-05-project-configurable-gates-design.md` — undeclared gate skips.

### The honest delta (why it needs a FEAT)
- It is **absent from the FEAT-1..17 list** — so it looks like a gap and is **unpositioned as a
  maintained roadmap feature** and **unsurfaced**.
- The **configurable-gates lesson is unfixed at the product level**: the 2026-08-05 spec records a
  real incident where polish burned ~46 minutes + 12.5MB/37MB of agent transcript against a validation
  gate the target project could never satisfy, and ended "failed" with 0-byte gate logs. The loop has
  since been made gate-aware, but **no regression/assertion enforces it**.
- No **nameable, inspectable "polish" workflow** (FEAT-16 template) exists yet.
- No **human-visualization gate** (`sim_human_visualization`, FEAT-14) formalizes the "human confirms
  it genuinely works" step.

So FEAT-15 = **surface + consolidate + integrate + harden**, not new enforcement.

---

## 3. Proposed design

### 3a. Polish is a named workflow (FEAT-16 template)
Declare **`polish`** as a pre-defined workflow template (YAML-canonical):
```
polish:
  name: polish
  steps:
    - {node: "finding",        on_pass: next, on_fail: stop}          # capture the use-case/finding
    - {node: "worktree-isolate", on_pass: next}                       # isolate a worktree
    - {node: "dev",             gates: [unit], max_attempts: 3}
    - {node: "validation",      gates: [integration]}
    - {node: "review",          gates: [agentic_review]}
    - {node: "human-visual-confirm", gates: [sim_human_visualization]} # human confirms genuinely-works
```
The `sim_human_visualization` gate (FEAT-14) **blocks until a human confirms** in the playground
(`sim_live`/`devserver`) — it never auto-passes. This is the FEAT-15 + FEAT-14 seam.

### 3b. Surfaces
- **Console (FEAT-10):** a "Polish" entry/tab shows a polish run streaming (finding → dev → re-gate →
  human-confirm), reusing the FEAT-12 live progress stream.
- **Governed exec (FEAT-13):** `coherence run-governed --workflow polish <usecase>` runs the loop as
  a traced, gated run (the FEAT-12/13 machinery).
- **CLI:** `coherence run polish <usecase|finding>` (via factory-run / the polish CLI).

### 3c. Hardening — the gate-respect guarantee
Add an **assertion/regression test** that a project with no `sim`/`sim_live` does **not** fail polish
(undeclared gate → skip). This is the anti-recurrence of the 46-minute burn. Verify on a webapp-style
fixture and the drone-style fixture.

---

## 4. Scope — ONE tracer-bullet through every layer

Vertical: substrate (workflow model FEAT-16) → factory (polish loop reuse) → coherence (gate
taxonomy `sim_human_visualization` FEAT-14) → host (CLI) → console (FEAT-10).

- **P-01 — `polish` workflow template.** Wire the FEAT-16 `polish` template to the existing
  `src/factory/polish/` loop. **Verify:** `coherence run polish <usecase>` enters the loop; a real fix
  lands + re-gates end-to-end. **Acceptance:** a fix produced by dev is committed + validated.
- **P-02 — `sim_human_visualization` gate (FEAT-14).** Add the gate to the taxonomy, wired to
  `playground.confirm`. **Verify:** a confirmation blocks until a human confirms; **no auto-pass**.
  **Acceptance:** "human confirms genuinely works" is enforced, not assumed.
- **P-03 — Console + governed surfaces.** "Polish" tab in FEAT-10; `--workflow polish` in FEAT-13.
  **Verify:** a polish run streams its steps on the console; drivable from governed exec.
  **Acceptance:** a user can start + watch + act on a polish iteration end-to-end.
- **P-04 — Gate-respect regression guard.** **Verify:** a repo without `sim` does NOT fail polish
  (skip); a repo with it runs it. **Acceptance:** the 2026-08-05 46-min burn cannot recur.

---

## 5. Files likely to change (planned)

- **Reuse:** `src/factory/polish/**` (orchestrator, playground, sim_live, devserver, findings,
  routing, synthesis, worker, executor), `factory/config.py`, `factory/polish/gates.py`.
- **New:** `polish` workflow template YAML (FEAT-16), `sim_human_visualization` gate registration
  (FEAT-14), console "Polish" tab (FEAT-10), gate-respect regression test.
- **Consumers:** FEAT-13 `--workflow polish`, FEAT-10 console tab.

## 6. Risks & open questions

- **Human-visualization gate must not auto-pass** — it is the whole point ("meaningful validation").
- **Playground blocking semantics** — a human-confirm step blocks; define timeout/abort/escalt an
  unconfirmed finding rather than silently green.
- **Overlap with FEAT-16** — the `polish` template is the *mechanical loop*; FEAT-15 owns the
  *human-in-the-loop polish experience + surfaces + hardening*. Keep them as distinct scopes, one doc
  cross-referencing the other.
- **Overlap with FEAT-14 action** — `sim_human_visualization` is a *gate* (FEAT-14 owns the taxonomy),
  polish *consumes* it. FEAT-15 must not redefine the taxonomy.

## 7. Feature completion / acceptance (NOT a task DoD)

> Note on levels: "Definition of done" is **task-scoped** — `dod_met` is a field on
> `TaskResult` (`src/factory/orchestrator/types.py`), the gate a *task* passes. A feature is an
> aggregate: it is complete only when the tasks satisfying its SRs each pass their own DoD and the
> feature's invariants are satisfied + gated. The completion criteria below are that feature-level
> aggregate.

### Feature completion criteria

A user can run a polish iteration end-to-end (use-case/finding → worktree-dev → re-gate → **human
playground-confirm**) — surfaced in the console (FEAT-10), drivable by governed exec (FEAT-13), as a
declared `polish` workflow (FEAT-16), with the human-visualization gate (FEAT-14) blocking until real
confirmation, and a regression guard proving no project ever burns against an unsatisfiable gate
again. **No auto-pass of human validation.**

**Verdict: YES, a distinct FEAT** — it is a maintained product surface (the human-in-the-loop polish
experience), distinct from the mechanical `polish` template (FEAT-16) and the gate taxonomy (FEAT-14).
