# Grill-Understanding Node — Implementation Plan

**Date:** 2026-08-12
**Status:** Draft for review
**Source:** `docs/superpowers/specs/2026-08-12-grill-understanding-node-design.md` (§0 re-grounding correction) and the additional-requirements section added to
`docs/superpowers/plans/engineering-context/increment-07-context-delta-validation.md`
(2026-08-12). This plan owns the **§A grill node** (factory-side); §B (explainer as
traced SR-linked artifact) is gated on the open Obsidian-vs-`diagram-design` conflict.

> **For agentic workers:** REQUIRED SUB-SKILL: use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement task-by-task. Checkboxes track progress.

## Grounding (verified against current `pi-agent-factory` main, `design/curation-workflow`)

- Node pipeline lives in `src/factory/orchestrator/runner.py` (`run_task`) and `nodes.py`; nodes are `context-gather → dev → validation → review → human-review`, with an `execution.record(...)` journal (`node`, `state`, `next_node`, `remaining`), a `resume_at`/`next_node` resume mechanism, `code-commit` and `evidence-finalize` nodes, and `--auto` runs with `human_review is None`.
- Human-in-the-loop gate precedent: `src/factory/orchestrator/human_review.py` — `FileHumanReviewGate(transcript_dir, repo_root, poll_interval)` polls `<transcript_dir>/review-decision.json`, archives reviewed diffs, and is constructed in `__main__.py` (`human_review = None if args.auto else FileHumanReviewGate(transcript_dir, repo_root=repo_root)`).
- Extension: `pi-ext/factory-watch/src/index.ts` — `startBackgroundWidgetPoll` already flags `human-review`/blocked and dev-escalation; mission-control `runMissionControl` dispatches `review`/`pair-dev`; `spawnTerminalWindow` opens a `pi --session` window (pair-dev pattern). `findSkillFile` resolves project `.pi/skills` then factory `.pi/skills` (no global fallback yet).
- Existing explainers: `<repo>/docs/visual-explain/<slug>.{md,svg,html}` with Obsidian-style frontmatter (`title`, `tags`) but **no `id`, no `explains:` SR link, no freshness fingerprint**. Existing samples in `cool_physical_ai_project/docs/visual-explain/` (this is the target project being enhanced, i.e. `ctx.cwd`).

## Global constraints

- Additive and non-colliding: the repo has uncommitted in-progress `/visual-explain` work (`index.ts`, `skill-prompt.ts` `buildVisualExplainSeedPrompt`, `.pi/skills/diagram-design/`). This plan must not rewrite those hunks; it reuses `buildSkillBlock`/`findSkillFile` and adds new code only.
- Verdicts never hard-block the run: `agreed` / `not-agreed` / `skipped` all proceed to `dev`.
- Reuse the existing staleness engine (`factory.freshness.fingerprint`, `factory.evidence.reconcile.STALE_VALIDATION`) — do not build a parallel checksum.
- Py: `pytestmark = pytest.mark.unit`, `from __future__ import annotations`, ruff 100. TS: vitest.

---

### Task 1: Grill gate (Python orchestrator)

**Files:** extend `src/factory/orchestrator/human_review.py` (or a new `grill.py` alongside), fixture tests in `tests/unit/orchestrator/`.

- [x] **Step 1 (failing tests):** `FileGrillGate(transcript_dir, repo_root, poll_interval)` polls `<transcript_dir>/grill-result.json` (no `--auto` side effects; a stale-but-readable file unblocks; a reader test round-trips `GrillResult`). A `FakeGrillGate` scripts `[agreed, not-agreed, skipped]`.
- [x] **Step 2 (implement):** mirror `FileHumanReviewGate`:
  ```python
  @dataclass
  class GrillResult:
      decision: str          # "agreed" | "not-agreed" | "skipped"
      summary: str | None = None
      explainers: int = 0    # visual explainers reused/generated this grill
  class GrillGate(Protocol):
      def request_grill(self, task_id: str) -> GrillResult: ...
  class FileGrillGate:
      def __init__(self, transcript_dir, repo_root=None, *, verdict_path: str = "grill-result.json", poll_interval: float = 1.0): ...
      def request_grill(self, task_id: str) -> GrillResult:
          # poll verdict_path; on read unlink it; a generous idle/total timeout
          # (env-tunable, mirroring FACTORY_AGENT_*_TIMEOUT_S) records
          # GrillResult(decision="not-agreed", summary="grill timed out").
  class FakeGrillGate:  # scripted, like FakeHumanReviewGate
  ```
- [x] **Step 3:** full `uv run python -m pytest` + lint; commit.

### Task 2: Grilled manifest + reuse lookup helper

**Files:** new `src/factory/trace/explainers.py` (pure functions) + tests in `tests/unit/trace/`.

- [x] **Step 1 (failing tests):** `load_explainers(root)` reads `docs/visual-explain/*.md` frontmatter into `{id, path, explains:[sr ids], ...}`; `list_fresh_explainers(root, sr_ids)` returns those whose `explains:` intersects `sr_ids` AND whose recorded dependency fingerprint matches current content (reuse `factory.freshness.fingerprint.fingerprint_value/file`), filtering out stale ones; explainers with no `explains:` or no fingerprint are **not** considered fresh (fall back to generate).
- [x] **Step 2 (implement):** two pure functions. This is the deterministic basis for "route to existing **up-to-date** explainers" — an explainer only counts as reusable if its SR linkage is current. No writes to explainer files here (that is Task 4/§B).
- [x] **Step 3:** suite + lint; commit.

### Task 3: Grill node in the pipeline

**Files:** `src/factory/orchestrator/nodes.py` (add `run_grill` or inline step), `runner.py` (call it), `__main__.py` (construct the gate), tests in `tests/unit/orchestrator/`.

- [x] **Step 1 (failing tests):** with `human_review is not None` and a `FakeGrillGate([agreed])`, `run_task` runs the grill after `context-gather`, before `dev`, and proceeds; `[skipped]` and `[not-agreed]` both proceed to `dev`; with `human_review is None` (`--auto`) the grill node is **not** invoked.
- [x] **Step 2 (implement):** in `run_task`, after the context-gatherer returns a usable manifest and before the dev inner loop:
  ```python
  if human_review is not None and grill_gate is not None:
      status.report(task_id=task.id, node="grill", node_state="blocked",
                    attempt=1, max_attempts=1,
                    handoff="grill your understanding before implementation (advised)")
      if execution is not None:
          execution.record(node="grill", state="started", attempt=1,
                           next_node="dev", remaining={})
      grill = grill_gate.request_grill(task.id)
      if execution is not None:
          execution.record(node="grill", state="completed", attempt=1,
                           next_node="dev",
                           data={"decision": grill.decision, "explainers": grill.explainers})
      # not-agreed/abandoned is NOT a block; carry the verdict for Task 5's flag.
  ```
  Thread a `grill: GrillResult | None` through `run_task` so `human-review` can later read it. Keep `resume_at` behavior: a resumed run that already passed the grill never re-grills (`resume_at in {"dev","validation",...}` skips it).
- [x] **Step 3:** suite + lint; commit.

### Task 4: Grill seed + interactive session (extension, additive)

**Files:** `pi-ext/factory-watch/src/skill-prompt.ts` (add `buildGrillSeedPrompt`), `pi-ext/factory-watch/src/index.ts` (additive regex/flag + mission-control select + session spawn), `test/handler.test.ts`.

- [x] **Step 1 (failing tests):** `buildGrillSeedPrompt(taskText, skillBlocks, freshExplainerSummary, grillResultPath)` renders skill blocks + deterministic instructions; handler unit-test asserts a `[Grill now]/[Skip]` select is offered at `grill:blocked` and `[Skip]` writes `grill-result.json` `{decision:"skipped"}`.
- [x] **Step 2 (implement):**
  - `buildGrillSeedPrompt`: hard-loads `grill-understanding` (resolve via `findSkillFile`); scopes to the task (body, DoD, `satisfies`, touched code paths); injects the `list_fresh_explainers` summary; instructs: one-question-at-a-time, verify against code, **on a wrong concept reuse the listed fresh explainer if one matches (read the `.md`, view the `.svg`), else generate a new visual explainer via `visual-explainer`/`diagram-design`**; require the user to state understanding in their own words; then write `<grillResultPath>` with `decision` and `explainers` count.
  - `index.ts`: in `startBackgroundWidgetPoll` + `runMissionControl`, add `grill:blocked` detection; on it raise the select; `[Grill now]` → build the seed, write a fresh session file, `spawnTerminalWindow("pi", ["--session", path], {cwd: ctx.cwd})`; `[Skip]` → write `grill-result.json`. Abandonment: a gate timeout (Task 1) is the safety net; optional process-exit watcher is a follow-up (see Risks).
- [x] **Step 3:** TS vitest + Python suite + lint; commit.

### Task 5: not-agreed → review-stage flag

**Files:** `src/factory/orchestrator/runner.py` (review-guide), `pi-ext/factory-watch/src/review-guide.ts` + review banner.

- [x] **Step 1 (failing tests):** when `grill.decision == "not-agreed"`, `write_review_guide` includes `guide["grill"] = {"verdict":"not-agreed","summary":...}`; extension banner renders the pairing warning when present.
- [x] **Step 2 (implement):** extend the `guide` dict in `run_task` (Task 3 already threads `grill` here); add the `grill` field to `ReviewGuide` in `review-guide.ts` and render the warning in the review banner.
- [x] **Step 3:** suite + lint; commit.

### Task 6: Review handoff

- [x] **Step 1:** reviewer sub-agent — verify: (a) never a hard block; (b) `--auto` skips the grill; (c) reuse of existing fresh explainers is deterministic and stale explainers fall back to generate; (d) additive, no collision with in-progress `/visual-explain` hunks; (e) no parallel staleness engine.
- [x] **Step 2:** fix findings; update checkboxes.

---

## Risks / open items

- **§B prerequisite (RESOLVED 2026-08-12 — SCC canonica, Obsidian personal-only):** explainers under `docs/visual-explain/` are authored via `diagram-design` (no automated Obsidian-open); files stay Obsidian-compatible so the human may view them in their own vault. Task 2’s `list_fresh_explainers` still needs explainers to carry `id` + `explains:` + a dependency fingerprint in frontmatter — until that §B scaffolding is authored, existing explainers have none and the grill falls back to generate-always. Adding the authoring side of that scaffolding is the §B follow-up (not this plan).
- **Session seeding for the grill window:** creating a *fresh standalone interactive* `pi --session` (not `ctx.newSession`, which replaces the session) needs a spike — write a JSONL session file with the seed and spawn it; validate it triggers a model turn.
- **Abandonment detection:** relying on the gate timeout is the safe baseline; a watcher that writes `not-agreed` when the grill window exits without a verdict is a follow-up (with the mission-control loop alive).
