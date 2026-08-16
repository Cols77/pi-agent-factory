# Plan: Tree-Sitter Engine Setup for Consumer Projects + Code-Context Hook Fix

**Date:** 2026-08-16
**Status:** Draft for review
**Source:** `docs/superpowers/specs/2026-08-14-code-context-bundle-design.md`
**Required sub-skill:** superpowers:subagent-driven-development. Py: `pytest.mark.unit`;
TS: vitest; ruff 100 / pyright standard.

## Problem (verified 2026-08-16)

1. **Hook is dead on arrival.** `factory-init-command.ts:199` assigns the whole
   `resolveProjectRoot(ctx.cwd)` **object** to `root` instead of destructuring
   `{ root }` (all three sibling call sites destructure). `hasCodeIndex(root)` then
   throws `ERR_INVALID_ARG_TYPE` (path must be string), the handler's try/catch
   swallows it, and the `before_agent_start` injection silently returns `{}`.
   Evidence: zero `factory-code-context` custom messages in every session transcript;
   `tsc --noEmit` already flags lines 200/201/204 (the gate is red because of it).
2. **Engine never reaches consumers.** Consumers install `pi-agent-factory` as a path
   dev-dep **without** the `code-index` extra, so tree-sitter grammars only exist in
   the factory repo's own venv. `buildCodeIndex`/`renderIndexSlice` spawn
   `uv run python` from the consumer cwd → consumer venv → no tree-sitter → silent
   `stdlib-ast` fallback. `latest.json` in `cool_physical_ai_project` says
   `engine: stdlib-ast`.
3. **Freshness ignores engine.** `ensure_fresh` (store.py) reuses the stored index on
   fingerprint match alone; a stdlib-built index is never upgraded to tree-sitter even
   after the grammars become available.
4. **Baseline gate red (pre-existing, out of scope):** `type-compat-check.ts:27`
   (ExtensionAPI/PiApi drift) and `system-page-dom.test.ts:424` pre-date this work and
   are unrelated. Only the `factory-init-command.ts:200-204` TS errors are ours.

## Global constraints

- Reuse `factory.freshness.fingerprint`; never build a parallel checksum.
- Tree-sitter stays an optional accelerator: stdlib fallback must keep working.
- All changes land in the `fix/code-context-tree-sitter-engine` worktree branch.

---

### Task 1: Fix destructuring bug + testable glue handler (TS)

**Files:** `pi-ext/factory-watch/src/factory-init-command.ts`,
`pi-ext/factory-watch/src/code-context-inject.ts`, `pi-ext/factory-watch/test/`.

^- [ ] **Step 1 (tests):** Extract the `before_agent_start` injection decision into a
  pure, exported function in `code-context-inject.ts`
  (e.g. `composeCodeContextMessage(ctx, injectedSessions)` returning the
  `BeforeAgentStartEventResult` or `{}`), so the handler body is unit-testable.
  Tests in `test/code-context-inject.test.ts` (following the existing
  `write-chunk-guard.test.ts` fake-event pattern): with a stub EventCtx whose
  `cwd` resolves via git to a real project containing a `.factory/code-index/latest.json`,
  the composed result carries `customType: "factory-code-context"` and non-empty
  content. Without an index, `{}`. Second call (same root+sessionId) returns `{}`.
  This test class must catch the object-vs-string bug.
^- [ ] **Step 2 (implement):** fix line ~199: `const { root } = resolveProjectRoot(ctx.cwd);`
  and route the handler through the extracted pure function. No behaviour change
  otherwise.
^- [ ] **Step 3:** `npm test --prefix pi-ext/factory-watch` (vitest, targeted file +
  full suite) + `npx tsc --noEmit` shows the 200/201/204 errors gone; commit.

### Task 2: Engine-aware freshness upgrade (Python)

**Files:** `src/factory/codeindex/sigs.py`, `src/factory/codeindex/store.py`,
`src/factory/codeindex/build.py`, `tests/unit/codeindex/`.

^- [ ] **Step 1 (tests):** `preferred_engine()` returns `"tree-sitter"` when the
  tree-sitter grammars import, else `"stdlib-ast"`. `ensure_fresh` rebuilds (new
  fingerprint files, changed `engine`) when the stored index's engine differs from
  `preferred_engine()` AND the preferred engine is available; it reuses a fresh index
  whose engine already matches. Existing fingerprint-reuse behaviour unchanged when
  engines match.
^- [ ] **Step 2 (implement):** export `preferred_engine()` from `sigs.py` (reuse the
  existing grammar try-import logic); `ensure_fresh` rebuilds when
  `stored.engine != preferred_engine(available)` or fingerprint changed. Keep the
  `"no-files"` short-circuit.
^- [ ] **Step 3:** `uv run python -m pytest -m unit -q` (codeindex subset + full) +
  ruff; commit.

### Task 3: Shared interpreter resolution + factory-init wiring (TS + profile)

**Files:** `pi-ext/factory-watch/src/code-context-inject.ts`,
`pi-ext/factory-watch/src/factory-init-command.ts`, `pi-ext/factory-watch/src/factory-init.ts`,
`pi-ext/factory-watch/test/`.

^- [ ] **Step 1 (tests):** a resolver `resolveIndexPython(root, factoryRoot)` returns
  candidate argv lists that try the factory checkout's own environment first
  (e.g. `uv run --project <factoryRoot> python -m factory.codeindex ...`), then the
  consumer env (`uv run python`), then plain `python` — because the factory venv is
  where the `code-index` extra lives today. Unit tests assert precedence and that the
  factory-root form is preferred when present; `renderIndexSlice`/`buildCodeIndex`
  accept the resolved argv. `runFactoryInit` records a `codeindex` block
  (`engine`, `interpreter`, `prefer: "tree-sitter"`) in `project-profile.json`
  (schema bump) and `/factory-doctor` prints the active engine + interpreter.
^- [ ] **Step 2 (implement):** shared resolver used by `buildCodeIndex` and
  `renderIndexSlice`; factory-init runs the builder with the resolved argv after
  writing the profile (best-effort, non-fatal) and persists the `codeindex` block;
  doctor surfaces it.
^- [ ] **Step 3:** vitest (targeted + full) + typecheck (200-204 remain gone) +
  Python unit + ruff; commit.

### Task 4: Slice annotation + docs + whole-branch review

^- [ ] **Step 1:** the injected slice carries a one-line engine note
  (`engine: tree-sitter | stdlib-ast` from `latest.json`) so the agent knows what it
  is reading; update `docs/superpowers/specs/2026-08-14-code-context-bundle-design.md`
  trigger/freshness section to describe consumer-project engine setup (factory venv
  preferred at init, engine-aware freshness, `code-index` extra for published
  installs) and tick this plan's boxes.
^- [ ] **Step 2:** full guard suite in the worktree — Python unit, vitest, ruff,
  `npx tsc --noEmit` (only the two pre-existing unrelated errors may remain),
  gate script — then a final reviewer sub-agent over the whole branch.

---

## Risks / open items

- Changing the resolver argv order could break environments without a factory
  checkout (published install): keep the plain-`python` fallback and treat any spawn
  failure as non-fatal (`renderIndexSlice` already returns `""` on all failures).
- `project-profile.json` schema bump must not break `/factory-init --check` or the
  profile-signature comparison (additive optional key only).
- The two pre-existing gate errors (`type-compat-check.ts:27`,
  `system-page-dom.test.ts:424`) stay out of scope; report them at handoff.