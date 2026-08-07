# System Navigator — Implementation Plan

> **Status:** Draft for written review. **This implementation plan is provisional.** No implementation begins until the design (`2026-08-08-system-navigator-briefing-validation-guide-design.md`) receives written approval and the open approval questions in its §12 are answered. The task ordering below is contingent on that approval; no code is produced before approval.

> **For agentic workers:** REQUIRED SUB-SKILL: use the relevant implementation workflow. Steps below are intentionally TDD-sized and ordered for low-risk delivery.

**Goal:** Build the `/system` navigator that presents feature/SR briefings, a validation matrix, a decision timeline, and a grounded natural-language guide over recorded evidence.

**Architecture:** Python owns the query/model layer and emits JSON projections. TypeScript only renders those projections in the browser and PIF surfaces. The navigator never invents provenance, never re-derives freshness in TypeScript, and degrades visibly when evidence is missing or stale.

**Tech Stack:** Python 3.11+, dataclasses, pathlib, json, jsonschema, subprocess Git, pytest; TypeScript, Vitest, existing browser server/UI.

---

## Global Constraints

- Recorded, derived, synthesized, and missing claims must stay distinct; freshness is preserved per claim.
- Freshness is content-based, never mtime-based.
- Browser/PIF code must not duplicate query, freshness, or provenance logic.
- No inferred timeline actors or rationale: absent actor/action/timestamp is marked unknown/not-recorded/missing, never guessed.
- No model-based synthesis: the guide is deterministic template assembly unless separately approved and evidence-cited.
- Missing or corrupt evidence degrades one scope, not the whole navigator.
- `/review-plans` and existing evidence surfaces remain compatible during rollout.
- No unrelated docs or runtime behavior changes outside the navigator path.

---

## File Structure

**Create:**
- `src/factory/system/__init__.py`
- `src/factory/system/models.py`
- `src/factory/system/queries.py`
- `src/factory/system/cli.py`
- `src/factory/system/__main__.py`
- `src/factory/schemas/system_briefing.schema.json`
- `src/factory/schemas/system_matrix.schema.json`
- `src/factory/schemas/system_timeline.schema.json`
- `src/factory/schemas/system_guide.schema.json`
- `tests/unit/system/test_models.py`
- `tests/unit/system/test_queries.py`
- `tests/unit/system/test_cli.py`
- `tests/integration/system/test_navigator_projection.py`
- `pi-ext/factory-watch/src/system-client.ts`
- `pi-ext/factory-watch/src/system-page.ts`
- `pi-ext/factory-watch/test/system-client.test.ts`
- `pi-ext/factory-watch/test/system-page.test.ts`

**Modify:**
- `pi-ext/factory-watch/src/docs-server.ts`
- `pi-ext/factory-watch/src/index.ts`
- `pi-ext/factory-watch/src/process-control.ts`
- `pi-ext/factory-watch/src/docs-html.ts` or equivalent system page shell
- existing browser/PIF tests

---

## Task 1: Python system model and schemas

**Files:**
- Create `src/factory/system/models.py`
- Create `src/factory/schemas/system_*.json`
- Create `tests/unit/system/test_models.py`

**Interfaces:**
- `SystemScopeRef`
- `SystemCitation`
- `SystemClaim`
- `ValidationMatrixRow`
- `DecisionTimelineEvent`
- `SystemGuide`
- `FreshnessState`

- [ ] **Step 1: Write failing model/schema tests**

Cover:
- claim-class preservation (`recorded|derived|synthesized|missing`)
- freshness states (`fresh|stale|degraded|missing`)
- top-level schema rejection of unknown fields
- citation retention and anchor round-tripping
- timeline event ordering fields

- [ ] **Step 2: Verify red state**

Run: `uv run pytest tests/unit/system/test_models.py -v`
Expected: fail because the package and schema files do not exist.

- [ ] **Step 3: Implement dataclasses and schema contracts**

Keep the shapes narrow and explicit. `additionalProperties: false` at the top level; allow controlled extensibility only where paragraph/detail payloads need it.

- [ ] **Step 4: Run tests and static checks**

Run: `uv run pytest tests/unit/system/test_models.py -v && uv run pyright && uv run ruff check src tests`
Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add src/factory/system/models.py src/factory/schemas/system_*.json tests/unit/system/test_models.py
git commit -m "feat(system): define navigator model and schemas"
```

---

## Task 2: Python queries and CLI

**Files:**
- Create `src/factory/system/queries.py`
- Create `src/factory/system/cli.py`
- Create `src/factory/system/__main__.py`
- Create `tests/unit/system/test_queries.py`
- Create `tests/unit/system/test_cli.py`
- Create `tests/integration/system/test_navigator_projection.py`

**Interfaces:**
- `query_brief(repo_root: Path, scope: SystemScopeRef) -> dict`
- `query_matrix(repo_root: Path, scope: SystemScopeRef) -> dict`
- `query_timeline(repo_root: Path, scope: SystemScopeRef) -> dict`
- `query_guide(repo_root: Path, scope: SystemScopeRef) -> dict`
- `list_scopes(repo_root: Path) -> list[SystemScopeRef]`

- [ ] **Step 1: Write failing query tests**

Fixtures should include a spec/plan/task/SR slice plus one validation report and one decision artifact. Assert:
- exact scope resolution only
- stale evidence downgrades a row but does not crash the query
- missing evidence becomes `missing`, not guessed
- timeline order is deterministic
- timeline actor/action/timestamp absence is marked missing/degraded, not guessed

- [ ] **Step 2: Verify import/path failures first**

Run: `uv run pytest tests/unit/system/test_queries.py tests/unit/system/test_cli.py -v`
Expected: fail before implementation exists.

- [ ] **Step 3: Implement query composition**

Reuse existing loaders; do not add parallel parsing rules. Build brief, matrix, timeline, and guide from the same recorded inputs the evidence lifecycle already exposes.

- [ ] **Step 4: Implement the CLI**

Subcommands:
- `brief`
- `matrix`
- `timeline`
- `guide`
- `scope`

Emit JSON only on `--json`; structured errors go to stderr with non-zero exit codes.

- [ ] **Step 5: Run the query/CLI/integration suite**

Run: `uv run pytest tests/unit/system tests/integration/system -q`
Expected: pass.

- [ ] **Step 6: Commit**

```bash
git add src/factory/system/queries.py src/factory/system/cli.py src/factory/system/__main__.py tests/unit/system/test_queries.py tests/unit/system/test_cli.py tests/integration/system/test_navigator_projection.py
git commit -m "feat(system): add navigator queries and cli"
```

---

## Task 3: Browser and PIF projections

**Files:**
- Create `pi-ext/factory-watch/src/system-client.ts`
- Create `pi-ext/factory-watch/src/system-page.ts`
- Modify `pi-ext/factory-watch/src/docs-server.ts`
- Modify `pi-ext/factory-watch/src/index.ts`
- Modify `pi-ext/factory-watch/src/process-control.ts`
- Create `pi-ext/factory-watch/test/system-client.test.ts`
- Create `pi-ext/factory-watch/test/system-page.test.ts`

**Interfaces:**
- `loadSystemBriefing(...)`
- `loadSystemMatrix(...)`
- `loadSystemTimeline(...)`
- `loadSystemGuide(...)`
- browser routes for `/system` and `/api/system/*`

- [ ] **Step 1: Write failing browser tests**

Cover:
- route selection and scope parsing
- exact command invocation to Python
- recorded/derived/synthesized/missing badge rendering
- stale/degraded label rendering
- loopback/path-confined failures

- [ ] **Step 2: Verify red state**

Run: `npm --prefix pi-ext/factory-watch test -- --run system-client system-page`
Expected: fail because the client/page do not exist.

- [ ] **Step 3: Implement the client wrappers**

Keep them as thin JSON subprocess shims only. No freshness, ranking, or provenance logic in TypeScript.

- [ ] **Step 4: Implement the `/system` page and routes**

The page should show a scope picker, brief, matrix, timeline, and guide tabs. Routes must reject arbitrary paths and only serve declared repo-local data.

- [ ] **Step 5: Run browser tests and typecheck**

Run: `npm --prefix pi-ext/factory-watch test && npm --prefix pi-ext/factory-watch run typecheck`
Expected: pass.

- [ ] **Step 6: Commit**

```bash
git add pi-ext/factory-watch/src/system-client.ts pi-ext/factory-watch/src/system-page.ts pi-ext/factory-watch/src/docs-server.ts pi-ext/factory-watch/src/index.ts pi-ext/factory-watch/src/process-control.ts pi-ext/factory-watch/test/system-client.test.ts pi-ext/factory-watch/test/system-page.test.ts
git commit -m "feat(factory-watch): add system navigator projections"
```

---

## Task 4: Grounded natural-language guide and rollout

> Synthesis is deterministic template assembly over recorded/derived inputs — it does not invoke a language model and never invents connective rationale. Model-based synthesis is out of scope unless separately approved and evidence-cited.

**Files:**
- Modify `src/factory/system/queries.py`
- Modify `pi-ext/factory-watch/src/system-page.ts`
- Modify docs/README surfaces only if needed for the new command entry point
- Add/extend tests under `tests/unit/system/` and `pi-ext/factory-watch/test/`

**Interfaces:**
- guide paragraph synthesis with citations and freshness
- degradation fallback to recorded-only prose
- optional `/system` default entry point, if approved

- [ ] **Step 1: Write failing synthesis tests**

Assert:
- every synthesized sentence cites evidence
- a stale dependency marks the paragraph stale
- missing support degrades the prose rather than fabricating confidence
- the browser falls back to brief + matrix + timeline when synthesis fails
- guide synthesis is deterministic template assembly, not a model call

- [ ] **Step 2: Verify failure-first behavior**

Run: `uv run pytest tests/unit/system -q`
Expected: red until synthesis/degradation logic exists.

- [ ] **Step 3: Implement grounded prose assembly**

Keep synthesis conservative and deterministic: short paragraphs, explicit citations, explicit freshness labels, template-driven assembly only (no model invocation, no invented rationale).

- [ ] **Step 4: Wire rollout behavior**

Keep `/review-plans` intact. Introduce `/system` as an additional navigator path first; promote it to the default only after approval.

- [ ] **Step 5: Run full gates**

Run: `uv run pytest -q && uv run pyright && uv run ruff check src tests && npm --prefix pi-ext/factory-watch test && npm --prefix pi-ext/factory-watch run typecheck`
Expected: pass.

- [ ] **Step 6: Commit**

```bash
git add src/factory/system/queries.py pi-ext/factory-watch/src/system-page.ts tests/unit/system pi-ext/factory-watch/test
git commit -m "feat(system): ground navigator prose and finish rollout"
```

---

## Plan self-review

- Data flow is one-directional: Python computes; TypeScript renders.
- No step asks the browser to infer provenance or freshness.
- Each task is independently testable and commit-sized.
- The default-entry-point decision remains explicitly open.
- This is a provisional plan; no implementation begins until written approval of the design and answers to its open approval questions.
