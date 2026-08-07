# System Navigator — Implementation Plan

> **Status:** Approved for implementation. All open design questions are resolved (design §12), and the user approved the revised design in writing on 2026-08-07.

> **For agentic workers:** REQUIRED SUB-SKILL: use the relevant implementation workflow. Steps below are intentionally TDD-sized and ordered for low-risk delivery.

**Goal:** Build the `/system` navigator that presents feature/SR briefings, a validation matrix, a decision timeline, and a grounded natural-language guide over recorded evidence.

**Architecture:** Python owns the query/model layer and emits JSON projections. TypeScript only renders those projections in the browser and PIF surfaces. The navigator never invents provenance, never re-derives freshness in TypeScript, and degrades visibly when evidence is missing or stale.

**Tech Stack:** Python 3.11+, dataclasses, pathlib, json, jsonschema, subprocess Git, pytest; TypeScript, Vitest, existing browser server/UI.

---

## Global Constraints

- Recorded, derived, synthesized, and missing claims must stay distinct; freshness is preserved per claim.
- Claim class and freshness are orthogonal, coupled only by `missing ⟺ n/a` (design §3.2).
- Freshness is content-based, never mtime-based.
- Browser/PIF code must not duplicate query, freshness, or provenance logic — extend `system-context-tools.ts`, never fork a parallel client.
- The subprocess shim is shared: `trace-cli.ts` and `system-cli.ts` both use one extracted `cli-runner.ts` helper. Refactoring `trace-cli.ts` onto it is explicitly in scope (user decision, 2026-08-07) and is the one sanctioned exception to the no-unrelated-changes constraint below. Its existing tests must stay green and unmodified in behavior.
- Python is invoked as `uv run python -m factory.system ...`. There is no `factory` console script.
- No inferred timeline actors or rationale: absent actor/action/timestamp is marked unknown/not-recorded/missing, never guessed.
- No model-based synthesis: the guide is fixed scaffolding plus verbatim spans.
- Plan checkbox state is never treated as recorded completion evidence (design §3.4).
- No derived index and no cache; projections are computed on demand.
- Missing or corrupt evidence degrades one scope, not the whole navigator.
- `/review-plans` and existing evidence surfaces remain compatible; `/system` stays opt-in.
- No unrelated docs or runtime behavior changes outside the navigator path.

---

## Verification discipline

`pyproject.toml` sets `addopts = "-m unit"`. Any pytest command that names an integration path **without** selecting the marker collects zero tests and exits green. Verified before writing this plan:

```
uv run pytest tests/integration -q --collect-only
→ No tests collected
```

Every integration command in this plan therefore passes `-m 'unit or integration'`. Task 0 registers the marker. Do not "fix" a red integration run by dropping the marker selector.

**rtk filter hazard.** This environment routes commands through the `rtk` token-optimizing proxy, and its pytest filter has been observed reporting "No tests collected" for a run that actually collected 6 tests. Any command whose result depends on collection counts, deselection, or red/green state must be run as `rtk proxy uv run pytest ...` so the real pytest summary is visible. Verified on 2026-08-07:

```
rtk proxy uv run pytest tests/integration --collect-only -q
→ no tests collected (6 deselected)

rtk proxy uv run pytest tests/integration -m 'unit or integration' --collect-only -q
→ 6 tests collected
```

---

## File Structure

**Create:**
- `src/factory/system/__init__.py`
- `src/factory/system/models.py`
- `src/factory/system/bundles.py`
- `src/factory/system/queries.py`
- `src/factory/system/guide.py`
- `src/factory/system/cli.py`
- `src/factory/system/__main__.py`
- `src/factory/schemas/system_bundle.schema.json`
- `src/factory/schemas/system_claim.schema.json`
- `src/factory/schemas/system_matrix_row.schema.json`
- `src/factory/schemas/system_timeline_event.schema.json`
- `src/factory/schemas/system_response.schema.json`
- `src/factory/schemas/system_guide.schema.json`
- `tests/unit/system/test_models.py`
- `tests/unit/system/test_bundles.py`
- `tests/unit/system/test_queries.py`
- `tests/unit/system/test_timeline.py`
- `tests/unit/system/test_guide.py`
- `tests/unit/system/test_cli.py`
- `tests/integration/system/test_navigator_projection.py`
- `tests/integration/system/test_guide_export.py`
- `pi-ext/factory-watch/src/cli-runner.ts`
- `pi-ext/factory-watch/src/system-cli.ts`
- `pi-ext/factory-watch/src/system-page.ts`
- `pi-ext/factory-watch/test/cli-runner.test.ts`
- `pi-ext/factory-watch/test/system-cli.test.ts`
- `pi-ext/factory-watch/test/system-page.test.ts`

**Modify:**
- `pyproject.toml` (register the `integration` marker)
- `pi-ext/factory-watch/src/trace-cli.ts` (refactor onto the shared `cli-runner.ts`)
- `pi-ext/factory-watch/src/system-context-tools.ts` (extend with navigator queries)
- `pi-ext/factory-watch/test/system-context-tools.test.ts`
- `pi-ext/factory-watch/src/docs-server.ts`
- `pi-ext/factory-watch/src/index.ts`
- `pi-ext/factory-watch/src/process-control.ts`

> `system-cli.ts` is a subprocess shim only, built on the shared `cli-runner.ts`. It is not a second tool-registration surface — registration stays in `system-context-tools.ts`.

> **Schema granularity (user ruling, 2026-08-07).** Task 1's schemas are **record-level**, named for the types design §7.2/§7.3/§7.4 actually define: `system_claim`, `system_matrix_row`, `system_timeline_event`. The earlier File Structure named these at collection level (`system_briefing`, `system_matrix`, `system_timeline`), which described a different thing — the §7.1 top-level envelope. That envelope is a separate schema, `system_response.schema.json`, created in Task 2 and extended as timeline and guide land. Record schemas validate one record; the response schema validates the whole payload.

> **Sizing note:** `docs-html.ts` is 31.1K and `index.ts` is 31.7K. The `/system` page shell goes in the new `system-page.ts`; only wiring lands in those two files. Do not graft the navigator UI into `docs-html.ts`.

---

## Task 0: Repository preconditions

**Files:** Modify `pyproject.toml`

- [ ] **Step 1: Register the `integration` marker**

Add `integration: slower tests that touch the filesystem or subprocesses` to `[tool.pytest.ini_options].markers`. Do not change `addopts`.

- [ ] **Step 2: Prove the gate now works**

Run: `uv run pytest tests/integration -q -m 'unit or integration' --collect-only`
Expected: a non-zero collected count. If it still reports "No tests collected", stop — the gate is still lying.

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml
git commit -m "test: register integration marker so integration gates cannot pass empty"
```

---

## Task 1: Python system model, schemas, and bundle declarations

**Files:**
- Create `src/factory/system/__init__.py`, `models.py`, `bundles.py`
- Create `src/factory/schemas/system_bundle.schema.json` and `system_*.schema.json`
- Create `tests/unit/system/test_models.py`, `tests/unit/system/test_bundles.py`

**Interfaces:**
- `SystemScopeRef`, `SystemCitation`, `SystemClaim`, `BundleDeclaration`
- `ValidationMatrixRow`, `DecisionTimelineEvent`, `SystemGuide`, `FreshnessState`
- `load_bundle(repo_root: Path, bundle_id: str) -> BundleDeclaration`
- `list_bundles(repo_root: Path) -> list[BundleDeclaration]`

- [ ] **Step 1: Write failing model/schema tests**

Cover:
- claim-class preservation (`recorded|derived|synthesized|missing`)
- freshness states (`fresh|stale|degraded|n/a`)
- the coupling rule in **both** directions: `kind == missing` ⟺ `freshness == n/a`; assert every illegal cell is rejected
- top-level schema rejection of unknown fields
- citation retention and anchor round-tripping
- `spans` allowed only on `synthesized` records
- timeline event ordering fields

- [ ] **Step 2: Write failing bundle tests**

Cover:
- a bundle parses to a label plus a list of exact member refs
- the schema **rejects** any status, claim, rationale, or free-prose field
- an unresolvable member is reported `missing` and degrades the bundle without dropping it
- duplicate members are rejected
- an absent bundle directory returns no bundles and raises nothing; `scope` reports no bundle scopes
- the bundle itself is emitted as a citation for the membership list

- [ ] **Step 3: Verify red state**

Run: `uv run pytest tests/unit/system -v`
Expected: fail because the package and schema files do not exist.

- [ ] **Step 4: Implement dataclasses, schemas, and bundle loading**

Keep the shapes narrow and explicit. `additionalProperties: false` at the top level; allow controlled extensibility only where paragraph/detail payloads need it. Resolve the bundle directory from repo config; do not hardcode it. An absent directory returns no bundles rather than raising.

- [ ] **Step 5: Run tests and static checks**

Run: `uv run pytest tests/unit/system -v && uv run pyright && uv run ruff check src tests`
Expected: pass.

- [ ] **Step 6: Commit**

```bash
git add src/factory/system src/factory/schemas/system_*.json tests/unit/system
git commit -m "feat(system): define navigator model, schemas, and bundle declarations"
```

---

## Task 2: Brief and matrix queries plus the CLI

**Files:**
- Create `src/factory/system/queries.py`, `cli.py`, `__main__.py`
- Create `src/factory/schemas/system_response.schema.json` (the §7.1 top-level envelope; brief and matrix members now, timeline and guide added in Tasks 3 and 5)
- Create `tests/unit/system/test_queries.py`, `tests/unit/system/test_cli.py`

**Interfaces:**
- `query_brief(repo_root: Path, scope: SystemScopeRef) -> dict`
- `query_matrix(repo_root: Path, scope: SystemScopeRef) -> dict`
- `list_scopes(repo_root: Path) -> list[SystemScopeRef]`

- [ ] **Step 1: Write failing query tests**

Fixtures include a bundle, spec/plan/task/SR slice, one validation report, one decision artifact. Assert:
- exact scope resolution only, including `bundle:` and `sr:`
- SR refs resolve through `factory.requirements.register`, not a hardcoded path
- stale evidence downgrades a row but does not crash the query
- missing evidence becomes `missing`, not guessed
- matrix `status` carries the recorded outcome only; staleness lives on `freshness`
- plan checkbox state is never emitted as `recorded`

- [ ] **Step 2: Verify red state**

Run: `uv run pytest tests/unit/system/test_queries.py tests/unit/system/test_cli.py -v`
Expected: fail before implementation exists.

- [ ] **Step 3: Implement brief and matrix composition**

Reuse existing loaders from `factory.trace`, `factory.requirements`, `factory.evidence`, and `factory.validation`; do not add parallel parsing rules.

- [ ] **Step 4: Implement the CLI**

Subcommands `brief`, `matrix`, `scope`, invoked as `python -m factory.system`. Emit JSON only on `--json`; structured errors go to stderr with non-zero exit codes. `timeline` and `guide` are registered in Tasks 3 and 5.

- [ ] **Step 5: Run the suite**

Run: `uv run pytest tests/unit/system -q && uv run pyright && uv run ruff check src tests`
Expected: pass.

- [ ] **Step 6: Commit**

```bash
git add src/factory/system tests/unit/system
git commit -m "feat(system): add navigator brief and matrix queries with cli"
```

---

## Task 3: Decision timeline query

Split from the query work because timeline carries the hardest rules — ordering fallback, unknown actors, and gap marking — and deserves its own red/green cycle.

**Files:**
- Modify `src/factory/system/queries.py`, `src/factory/system/cli.py`
- Create `tests/unit/system/test_timeline.py`
- Create `tests/integration/system/test_navigator_projection.py`

**Interfaces:**
- `query_timeline(repo_root: Path, scope: SystemScopeRef) -> dict`

- [ ] **Step 1: Write failing timeline tests**

Assert:
- ordering is deterministic from recorded timestamps
- missing timestamps fall back to recorded sequence numbers with a visible warning
- absent actor/action is `unknown`/`not-recorded` and the event is marked missing/degraded
- ordering is never inferred from content or rationale
- events retain their citations

- [ ] **Step 2: Verify red state**

Run: `uv run pytest tests/unit/system/test_timeline.py -v`
Expected: fail.

- [ ] **Step 3: Implement timeline composition and register the subcommand**

- [ ] **Step 4: Write the integration projection test**

Temp repo with a bundle, spec, SR, task, validation report, and decision artifacts. Assert a missing manifest or missing blob degrades only that scope.

- [ ] **Step 5: Run unit and integration suites**

Run: `uv run pytest tests/unit/system tests/integration/system -q -m 'unit or integration'`
Expected: pass, with a non-zero collected count.

- [ ] **Step 6: Commit**

```bash
git add src/factory/system tests/unit/system tests/integration/system
git commit -m "feat(system): add navigator decision timeline"
```

---

## Task 4: Browser and PIF projections

**Files:**
- Create `pi-ext/factory-watch/src/cli-runner.ts`, `src/system-cli.ts`, `src/system-page.ts`
- Modify `pi-ext/factory-watch/src/trace-cli.ts` (refactor onto the shared helper)
- Modify `pi-ext/factory-watch/src/system-context-tools.ts` and its test
- Modify `pi-ext/factory-watch/src/docs-server.ts`, `src/index.ts`
- Create `pi-ext/factory-watch/test/cli-runner.test.ts`, `test/system-cli.test.ts`, `test/system-page.test.ts`

**Interfaces:**
- `runJsonCli<T>(cwd: string, bin: string, args: string[]): CliResult<T>` in `cli-runner.ts`
- `buildSystemCommand(sub: string[]): { bin: string; args: string[] }`
- `loadSystemBriefing(...)`, `loadSystemMatrix(...)`, `loadSystemTimeline(...)`
- browser routes for `/system` and `/api/system/*`

- [ ] **Step 1: Write failing browser tests**

Cover:
- route selection and scope parsing
- exact command invocation: `uv run python -m factory.system ...`, mirroring `trace-cli.ts:75`
- recorded/derived/synthesized/missing badge rendering
- stale/degraded label rendering
- loopback/path-confined failures

- [ ] **Step 2: Verify red state**

Run: `npm --prefix pi-ext/factory-watch test -- --run system-cli system-page`
Expected: fail because the shim and page do not exist.

- [ ] **Step 3: Extract the shared shim and build on it**

Extract the `spawnSync` + JSON + `CliResult<T>` logic currently inside `trace-cli.ts` into a new `cli-runner.ts` exporting `runJsonCli<T>`. Refactor `trace-cli.ts` to call it, and build `system-cli.ts` on it too. This is a user decision (2026-08-07) taken over the alternative of duplicating the shim.

Constraints on the refactor:
- `trace-cli.ts`'s existing tests must pass **unmodified** — if a test needs changing, the refactor changed behavior and is wrong;
- the refactor is behavior-preserving: no new options, no changed error shapes, no changed command construction;
- `cli-runner.ts` holds process/JSON mechanics only — no freshness, ranking, or provenance logic in TypeScript.

Write `test/cli-runner.test.ts` covering the helper directly: non-zero exit, unparseable stdout, and the success path.

- [ ] **Step 4: Extend the existing tool surface**

Add the navigator queries to `system-context-tools.ts` and its test. Do **not** create a new registration surface — `system-context-tools.ts` and `trace-tools.ts` already exist, and a third would let two code paths disagree about freshness.

- [ ] **Step 5: Implement the `/system` page and routes**

Scope picker plus brief, matrix, and timeline tabs, all in `system-page.ts`. Routes reject arbitrary paths and serve only declared repo-local data. Wiring only in `docs-server.ts` and `index.ts`.

- [ ] **Step 6: Run browser tests and typecheck**

Run: `npm --prefix pi-ext/factory-watch test && npm --prefix pi-ext/factory-watch run typecheck`
Expected: pass.

- [ ] **Step 7: Commit**

```bash
git add pi-ext/factory-watch/src pi-ext/factory-watch/test
git commit -m "feat(factory-watch): add system navigator projections"
```

---

## Task 5: Grounded guide, export, command entry, and rollout

> Synthesis is fixed scaffolding plus **verbatim spans** copied from cited sources. No paraphrase, no model invocation, no invented connective rationale.

**Files:**
- Create `src/factory/system/guide.py`, `tests/unit/system/test_guide.py`
- Create `tests/integration/system/test_guide_export.py`
- Modify `src/factory/system/cli.py`, `pi-ext/factory-watch/src/system-page.ts`, `src/process-control.ts`, `src/index.ts`

**Interfaces:**
- `query_guide(repo_root: Path, scope: SystemScopeRef) -> dict`
- `export_guide(repo_root: Path, scope: SystemScopeRef, dest: Path) -> Path`
- registered command opening the navigator

- [ ] **Step 1: Write failing synthesis tests**

Assert:
- every emitted span appears **verbatim** in its cited source (substring containment)
- no paraphrase path exists: text not traceable to a span is rejected
- the collapse predicate is binary — all dependencies fresh renders prose, anything else renders recorded bullets
- there is no stale-but-visible paragraph
- missing support degrades to bullets rather than fabricating confidence
- guide assembly is deterministic: the same inputs produce byte-identical output
- no model call is made

- [ ] **Step 2: Write failing export tests**

Assert:
- export writes the generation timestamp and full citation set
- the exported file carries the not-a-source-of-truth header
- export is written outside evidence/manifest directories, with a confined path
- **re-citing an exported guide is refused** — the navigator will not resolve a scope ref pointing at one, and will not accept it as a citation
- without an explicit `--export`, nothing is written

- [ ] **Step 3: Verify red state**

Run: `uv run pytest tests/unit/system tests/integration/system -q -m 'unit or integration'`
Expected: red until synthesis, collapse, and export logic exist.

- [ ] **Step 4: Implement guide assembly and export**

Keep synthesis conservative: short paragraphs, verbatim spans, explicit citations, explicit freshness labels, template-driven assembly only.

- [ ] **Step 5: Wire the guide tab, command entry, and fallback**

Add the guide tab to `system-page.ts` with fallback to brief + matrix + timeline when synthesis fails. Register the command in `process-control.ts` / `index.ts` so `/system` opens without going through the docs browser, and test that registration explicitly. `/system` stays **opt-in** and does not become the default entry point. Keep `/review-plans` intact.

- [ ] **Step 6: Run full gates**

Run: `uv run pytest -q -m 'unit or integration' && uv run pyright && uv run ruff check src tests && npm --prefix pi-ext/factory-watch test && npm --prefix pi-ext/factory-watch run typecheck`
Expected: pass, with a non-zero collected count on the Python side.

- [ ] **Step 7: Commit**

```bash
git add src/factory/system tests/unit/system tests/integration/system pi-ext/factory-watch/src pi-ext/factory-watch/test
git commit -m "feat(system): ground navigator prose, add export, finish rollout"
```

---

## Plan self-review

- Data flow is one-directional: Python computes; TypeScript renders.
- No step asks the browser to infer provenance or freshness.
- Every integration command selects the marker, so no gate can pass on an empty collection.
- Task 0 fixes the gate before any step depends on it.
- Timeline is split out because its ordering and unknown-actor rules are the highest-risk logic.
- The PIF surface is extended, not forked; no third registration surface is created.
- The subprocess shim is extracted once and shared by `trace-cli.ts` and `system-cli.ts`, so the duplication a reviewer would flag never lands.
- The navigator UI lands in `system-page.ts`, not in the 31K `docs-html.ts`.
- Export is the only write path, and exported guides cannot re-enter as evidence.
- Approved: the user signed off on the revised design in writing on 2026-08-07, clearing implementation.
