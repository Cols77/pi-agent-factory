# Design: Grill-My-Understanding Node for the Dev Factory

**Date:** 2026-08-12
**Status:** Draft for review — **re-grounded 2026-08-12 against current `pi-agent-factory` main** (this file was originally drafted against a stale worktree; see correction note below)
**Author:** Colin AUBE (with Claude)

---

## 0. Re-grounding correction (2026-08-12)

Initial drafting of this spec happened against a **stale linked worktree** (`pi-agent-factory-wt/traceui`, branch `design/doctor`, 189 commits behind main). That worktree has since been removed; the design was re-checked against current **main** (`pi-agent-factory`, `design/curation-workflow`). Corrections:

- **The staleness engine already exists on main** — `src/factory/freshness/` (fingerprints files/trees/values) and `src/factory/evidence/reconcile.py` (`ReconcileKind.STALE_VALIDATION`). §7's and earlier claims that these were “planned, not implemented” were wrong (based on the stale tree).
- The core node/gate shape (`runner.py`, `human_review.py` gate) still holds, but main's gate now archives diffs and takes `repo_root`, and `runner.py` has a `resume_at`/`next_node` mechanism — the grill node must slot into the node pipeline consistently with both.
- **Where this feature lives:** the overlapping parts (SR↔code staleness, grill/visual-explainer comprehension hook) are owned by `docs/superpowers/plans/engineering-context/increment-07-context-delta-validation.md`, which has been **updated 2026-08-12** to fold in these additional requirements (grill node + traced explainer staleness). That plan is authoritative for the overlap; this spec is the shared design record for the genuinely-new pieces.
- **Surface decision (RESOLVED 2026-08-12): SCC canonical, Obsidian personal-only.** The factory/extension never auto-opens Obsidian; `docs/visual-explain/` explainers are authored via `diagram-design` and remain Obsidian-compatible only so the human can personally view them in their own vault. See the resolved §C in `increment-07-context-delta-validation.md`.

---

## 1. Problem & Framing

The dev factory is a deterministic pipeline: `context-gather → dev → validation →
review → human-review`. The human is only guaranteed a meaningful checkpoint at
`human-review`, *after* the implementation is done. Two weaknesses follow:

1. **The human may not be able to meaningfully review the diff.** There is no
   earlier step that verifies the human understands the task they are about to
   approve. A reviewer who does not understand the task, its DoD, the requirements
   it satisfies, or the code it touches is reviewing cold.
2. **Review quality depends on the human.** The existing review surface (see
   §7 below) is only as good as the reviewer's grasp of what was actually built.

This design adds an optional-but-strongly-advised **`grill` node** to the
pipeline: a human-in-the-loop dialogue, run *before* implementation starts, that
uses the **grill-understanding** skill to question the human about their
understanding of the task — so they enter the run ready to meaningfully review
the code that will be produced.

The grill is **not mandatory**. It can be skipped explicitly, and it never hard
blocks the pipeline.

### 1.1 Why a node (not an extension-side pre-step)

The first design considered asking the question from the `/factory-run` command
handler before spawning the run in the extension (`index.ts`). That path was
rejected because of session mechanics: the only way for the extension to drive a
model dialogue is `ctx.newSession()`, which **replaces the current session and
makes `ctx` stale** (the code comment on `/plan` and `/clear` states "nothing may
touch ctx after this call"). A grill-then-run in one handler cannot keep the
mission-control dashboard alive across that call.

Hosting the grill as an **orchestrator node** dissolves the problem: the
orchestrator is a detached process that stays alive and blocks on a gate — exactly
like `human-review` — while the extension, which owns the interactive UI, hosts the
grill on the side. The pipeline continues automatically after the grill; no
re-invocation, no session replacement, no stale `ctx`.

---

## 2. Goals

- Add a `<grill>` node to `run_task()` that fires whenever a **human is in the
  loop** (`human_review is not None`), positioned **after `context-gather` and
  before `dev`** — so the task is validated as coherent/runnable first, but the
  human is grilled before any implementation exists.
- Run a relentless, one-question-at-a-time dialogue using the **generic
  `grill-understanding` skill**, scoped to this task by the seed prompt.
- Produce explicit **verdicts** and never hard-block: `agreed` / `not-agreed` /
  `skipped` all proceed to `dev`.
- Give the user an explicit **`[Grill now]` / `[Skip]`** choice when the node is
  hit, plus safe abandonment so a stalled grill can't hang the pipeline.
- Surface a `not-agreed` outcome at the human-review banner so the reviewer is
  reminded to review carefully (or pair).
- Make the grill skill bucket (**`grill-understanding`**, **`visual-explainer`**,
  **`diagram-design`**) available **globally** on this machine, not vendored into
  any single project.

---

## 3. Non-Goals

- **The grill is not a hard gate.** No verdict blocks `dev`. See §5.
- **No new command surface.** `/factory` and `/factory-run` both run the same
  `run_task()`; the node is governed by "human review is on," not by which command
  launched it. `--auto` (no human) is grill-free.
- **Not a persistent "already grilled" memory.** The node grills fresh every run;
  the explicit `[Skip]` is the escape hatch. No cross-run state.
- **Not authoring the grill skill from scratch.** We reuse the existing generic
  `grill-understanding`, `visual-explainer`, and `diagram-design` skills as-is.
- **Not fixing the review-guide defect** (§7) as part of this work — it is tracked
  as a separate follow-up.

---

## 4. Architecture

### 4.1 The node

`run_task()` (`src/factory/orchestrator/runner.py`) gains a `grill` step between
`run_context_gatherer` and the `dev` inner loop:

```
context-gather ──> [grill:blocked] ──> dev ──> validation ──> review ──> human-review
                        │
                        └─ waits on sessions/.factory-transcripts/<sid>/grill-result.json
```

- It runs only when `human_review is not None`. In `--auto` (the orchestrator is
  called without a `HumanReviewGate`), the grill step is skipped entirely, exactly
  matching how the `human-review` node is skipped (the inner loop runs once, no
  blocking gate).
- It reports via `status.report(node="grill", node_state="blocked", ...)` so the
  extension's watcher can react, and it records a `NodeEvent("grill", ...)`.

### 4.2 The gate

A `GrillGate` mirrors `HumanReviewGate` / `FileHumanReviewGate`
(`src/factory/orchestrator/human_review.py`):

```python
class GrillResult:
    decision: str          # "agreed" | "not-agreed" | "skipped"
    summary: str | None    # optional one-liner
    explainers: int        # number of visual explainers produced (0 if none)

class GrillGate(Protocol):
    def request_grill(self, task_id: str) -> GrillResult: ...

class FileGrillGate:
    # polls <transcript_dir>/grill-result.json until present;
    # applies a generous idle/total timeout (env-tunable, mirroring
    # FACTORY_AGENT_IDLE_TIMEOUT_S / _TOTAL_TIMEOUT_S in pi_backend.py) that
    # records {"decision":"not-agreed","summary":"grill timed out"} so a dead
    # or hung grill can never block the pipeline forever.

class FakeGrillGate:
    # scripted decisions for tests, matching FakeHumanReviewGate.
```

### 4.3 The result record

`<transcript_dir>/grill-result.json` (the same `sessions/.factory-transcripts/<sid>/`
directory that already holds `review-decision.json`, gate logs, and the
review-guide). Schema:

```json
{
  "decision": "agreed",
  "summary": "user demonstrated understanding of task T-004, DoD, and touched files",
  "explainers": 1,
  "updated_at": "2026-08-12T14:03:22Z"
}
```

Three writers produce it:
- the **grill session** writes `agreed` (only after the user explicitly states,
  in their own words, that they understand the task) or `not-agreed` (explicit
  failure to reach agreement), as its terminal action;
- the **extension** writes `skipped` when the user chooses `[Skip]`;
- the **gate timeout** writes `not-agreed` ("grill timed out") as a safety net.

---

## 5. Trigger, UX & Verdicts

### 5.1 Hit time

When status shows `node === "grill" && node_state === "blocked"`, the extension's
watcher (`startBackgroundWidgetPoll` / `runMissionControl` in `index.ts`, which
already flags `human-review`/blocked and `devEscalated`) raises a select raised in
mission control:

```
Grill your understanding of T-004 first?
(strongly advised, so you can meaningfully review the implementation)

[ Grill now ]    [ Skip ]
```

### 5.2 Grill now

The extension spawns an **interactive `pi --session` terminal window** (the
`spawnTerminalWindow` / `pair-dev` pattern) seeded with a deterministic prompt:

```
<skill block: grill-understanding (hard-loaded)>
Scope: the USER's understanding of THIS task — its body, Definition of Done,
       its deliverables, the requirements it satisfies, and the concrete code
       paths it touches. NOT the whole repo.
Rules: one question at a time; verify every answer against the code (you have
       read access to the repo); never feed the answer.
Tutoring: when a concept is wrong, produce a visual explainer via
       visual-explainer (SVG + note, opened in Obsidian).
Exit: do NOT consider the session complete until the user explicitly states in
       their own words that they understand the task. Then write
       <abs path>/grill-result.json  with decision "agreed".
       If the user explicitly cannot demonstrate understanding, write
       decision "not-agreed" (with any explainers count).
<task content: full tasks/T-###.md text>
```

The skill blocks are resolved with `findSkillFile`, which gains a **global
fallback** (see §6.2). The seed uses task content read from `tasks/T-###.md`
(deterministic), not a model-chosen skill.

### 5.3 Skip

The extension writes `grill-result.json` with `decision: "skipped"`; the gate
unblocks and `dev` starts immediately.

### 5.4 Abandonment

If the grill window is closed mid-way (or the grill process dies) without a
verdict, the pipeline must proceed, not hang:
- the gate timeout (§4.2) records `not-agreed` ("grill timed out") as the
  safety net;
- the exact mechanism for the extension to detect a closed grill window and
  write `not-agreed` without blocking the mission-control loop is flagged as a
  spike (§8.1).

### 5.5 Verdict semantics

| verdict | effect |
|---|---|
| `agreed` | proceed to `dev` |
| `not-agreed` | proceed to `dev`, **flag human-review** (§5.6) |
| `skipped` | proceed to `dev`, no flag |

All three proceed. The grill never hard-blocks.

### 5.6 Review-stage flag

When the verdict is `not-agreed`/`abandoned`, `runner.py` includes it in the
`review-guide.json` it already builds at human-review time, e.g.
`guide["grill"] = {"verdict": "not-agreed", "summary": ...}`. The extension's
review surface (`review-guide.ts` / review banner in mission control) prepends a
warning when present:

> You did not demonstrate understanding of this task in the grill. Review the
> diff carefully or open a dev session (/factory-watch → pair) before approving.

This is the concrete realization of the "not-agreed flags the review stage"
decision — it does not block, it orients the human (and offers pairing when they
clearly are not ready).

---

## 6. Skills & Infrastructure

### 6.1 Global install

The generic **`grill-understanding`** skill depends on **`visual-explainer`**
(tutoring), which in turn depends on **`diagram-design`** (referenced as the
relative path `../diagram-design/SKILL.md` and ships
`scripts/open_in_obsidian.py`). All three presently live as siblings in
`cool_physical_ai_project/.pi/skills/` only.

Decision: install all three **as siblings in the global per-user skills dir**
(`~/.agents/skills/`, here `C:\Users\33630\.agents\skills\`), so they are
available to any project on this machine — not vendored into any one repo —
while preserving the `visual-explainer/../diagram-design` relative reference and
the Obsidian helper script.

### 6.2 `findSkillFile` global fallback

`pi-ext/factory-watch/src/factory-skills.ts` `findSkillFile(cwd, name)` currently
resolves only:

1. `<cwd>/.pi/skills/<name>/SKILL.md`
2. `factorySkillsDir()` = `<factory-repo>/.pi/skills/<name>/SKILL.md`

It gains a third candidate, **after** the project-local ones (project wins,
global is the fallback):

3. `<homedir>/.agents/skills/<name>/SKILL.md`

This keeps the factory's hard-load determinism (the skill is still read and
injected into the seed at spawn) while honoring "global, not project-specific."

---

## 7. Adjacent defect (out of scope, tracked separately)

**Observation reported:** the human-review guide sometimes asks the human to run
scripts/tests that the `validation` node already executed.

**Root cause (diagnosed in code):**
1. Review `verify` items are free-text emitted by the LLM `REVIEW` agent. The
   prompt (`ROLE_PROMPTS[REVIEW]`) instructs "behaviors to check, never commands
   the factory has already executed," but nothing enforces it deterministically —
   non-determinism sometimes yields a command-like verify item, relayed verbatim.
2. `compose_prompt` renders "What happened this run" as only
   `- node: result (N attempts)` — **no gate names, no pass/fail counts** — so a
   compliant reviewer still cannot know which suites already ran.
3. `read_validation()` / `read_requirements_report()` are wired into the `guide`
   dict in `runner.py` *after* the reviewer produced its verify items, and the
   reviewer never saw them at prompt time.
4. `write_review_guide` dumps JSON as-is; `review-guide.ts` renders it to the
   human untouched. No post-processing filter strips command-like or
   already-run-suite verify items.

**Desired follow-up (separate ticket):** feed the validation node's actual gate
results to the reviewer at prompt time, and/or deterministically filter verify
items that reference gates/suites the validation node already ran. This is a
distinct defect, deliberately **not** folded into the grill node work.

---

## 8. Risks, Spikes & Testing

### 8.1 Spike — seeding a fresh interactive session

The one implementation dependency: the extension must create and seed a *new,
standalone, interactive* `pi` session for the grill window. The `/plan` precedent
seeds via `ctx.newSession()` (which replaces the session — not wanted here).
Spike before implementation: write a JSONL session file containing the seed and
launch it via `spawnTerminalWindow("pi", ["--session", <path>], ...)` so the grill
runs interactively as a fresh conversation while the current session's
mission-control stays alive. Validate the seed triggers a model turn and that the
grill window's writes land in the repo-relative paths.

### 8.2 Abandonment detection

Confirm how the extension observes the grill window's exit (without blocking the
mission-control loop) so it can write the `not-agreed`/`abandoned` record, or rely
solely on the gate timeout (§4.2). Resolution goes in the plan.

### 8.3 Testing

Follow existing patterns (`tests/unit/orchestrator/test_*.py` and
`pi-ext/factory-watch/test/handler.test.ts`):
- `FakeGrillGate` scripted `[agreed, not-agreed, skipped]` drive the node verdicts
  in `run_task`; assert `dev` runs and the review-guide `grill` field is set.
- `--auto` (no `HumanReviewGate`) skips the grill node entirely.
- `FileGrillGate` polls and times out → `not-agreed` when a stale result exists.
- Extension: watcher flags `grill:blocked`; mission-control raises
  `[Grill now]/[Skip]`; `[Skip]` writes `grill-result.json`; banner warning shows
  on `not-agreed`.
- `findSkillFile` global fallback resolves the skill from `~/.agents/skills/`.
- Obsidian explainer / visual-explainer path exercised in the grill-session smoke
  test with a fake/absent Obsidian (graceful degradation documented).

---

## 9. Deliverables

- `src/factory/orchestrator/` — `GrillGate`/`FileGrillGate`/`FakeGrillGate`,
  `run_grill` node step wired into `run_task` after context-gather and before dev,
  review-guide `grill` field on `not-agreed`.
- `pi-ext/factory-watch/src/` — watcher flag for `grill:blocked`; mission-control
  `[Grill now]/[Skip]` select; grill-window spawn + seed; `findSkillFile` global
  fallback; review banner warning.
- `~/.agents/skills/` — install `grill-understanding`, `visual-explainer`,
  `diagram-design` (siblings, global).
- Tests for the above.
