# Test Campaign Reduction and Impact Routing — Surgical Implementation Plan

> **For Hermes:** Use the `subagent-driven-development` skill to implement this plan task-by-task, with a fresh spec-compliance reviewer and a fail-closed code-quality reviewer for every task.

**Goal:** Reduce test-campaign wall time and maintenance duplication without reducing coverage of active FEAT-backed behavior, while allowing proven deprecated-wrapper coverage to shrink safely.

**Architecture:** Keep canonical behavior tests on `coherence.*` and `substrate.*`; treat `factory.*` compatibility tests as temporary migration-contract coverage. Classify tests by real external boundaries rather than by `tmp_path` usage. Add a conservative, deterministic path-bucket selector that broadens on uncertainty and leaves precise codemap-based selection for a later increment.

**Tech Stack:** Python 3.11–3.12, pytest, GitHub Actions, existing `coherence.policy`/`substrate.codemap` code, no new test-runner dependency in this increment.

---

## Decisions locked during review

1. **Primary objective:** reduce total test-campaign execution time, especially wall-clock time, while preserving active behavior coverage.
2. **Coverage rule:** coverage may be reduced for genuinely deprecated API wrappers and old-vs-new parity contracts. Coverage must not be reduced for behavior still used by an active FEAT or current production path.
3. **Impact routing:** use conservative path buckets first. Unknown, shared, configuration, fixture, schema, policy, or generated-artifact changes broaden the selected campaign; they never silently skip an active area.
4. **Test classification:** direct Git, subprocess, server, browser, extension, or process-boundary behavior is integration/e2e. Pure deterministic tests that use `tmp_path` only for serialization/projection setup remain unit tests.
5. **Real boundary preservation:** do not replace real Git/subprocess tests with mocks merely to improve timing.
6. **Parallelism:** parallelize independent CI campaigns/jobs first. Do not add `pytest-xdist` or another test-runner dependency in this increment.
7. **Scope:** this plan covers items 6–9 only. It does not remove active FEAT implementations, remove all `factory.*` shims, implement codemap-precise test selection, or redesign production orchestration.

## FEAT and contract boundary

This cleanup supports, rather than removes, behavior owned by:

- **FEAT-001:** traceability/codemap reachability;
- **FEAT-006:** evidence and freshness contracts;
- **FEAT-008:** goals/simulation projections;
- **FEAT-009/010/011/012:** host, console, governed execution, and progress behavior;
- **FEAT-014/015:** validation gates and polish flow.

The only intentionally removable coverage is duplicate or deprecated-wrapper coverage after an equivalent canonical assertion is present. Every deletion must include an explicit old-test → retained-test mapping in the commit or review notes.

## Baseline checkpoint

Run from a clean implementation worktree based on the approved current branch. Do not include unrelated working-tree FEAT/spec/plan edits in the implementation commits.

Record before/after results for:

```bash
uv run python -m pytest --collect-only -q
uv run python -m pytest -q -o addopts='' tests/unit/coverage/test_imports.py tests/unit/substrate/test_codemap_imports.py
uv run python -m pytest -q -o addopts='' tests/unit/substrate/test_legacy_import_matrix.py tests/unit/substrate/test_compatibility_paths.py
uv run python -m pytest -q -o addopts='' tests/unit/freshness --durations=20
uv run python -m pytest -q -o addopts='' tests/unit/orchestrator --durations=20
```

Capture elapsed time, collected/pass/fail counts, and the 20 slowest tests. A timing change is not accepted if it hides a failure or reduces active-contract coverage.

---

## Task 1: Consolidate the duplicate coverage-import tests

**Objective:** Remove the proven duplicate legacy coverage-import file while preserving its one unique transitive-reachability behavior.

**Files:**
- Modify: `tests/unit/substrate/test_codemap_imports.py`
- Delete after migration: `tests/unit/coverage/test_imports.py`
- Inspect only: `src/substrate/codemap/imports.py`, `src/factory/coverage/imports.py`

**Step 1: Write the canonical regression first**

Copy the semantic assertion from `tests/unit/coverage/test_imports.py::test_transitive_imports_reaches_implementation` into `tests/unit/substrate/test_codemap_imports.py`, changing only the import and fixture calls to the canonical `substrate.codemap` API. Preserve the expected transitive closure, not merely the top-level direct import.

**Step 2: Verify the new assertion is meaningful**

Run:

```bash
uv run python -m pytest -q -o addopts='' tests/unit/substrate/test_codemap_imports.py::test_transitive_imports_reaches_implementation
```

Expected: the test passes against the canonical implementation and fails if the transitive edge is removed. Do not accept a tautological assertion that checks only object identity or a direct import.

**Step 3: Compare the remaining seven behaviors**

Verify the canonical suite still covers the legacy cases:

- true/false overlap;
- self-overlap exclusion;
- relative-import resolution;
- node-id selection;
- missing selection honesty;
- unresolved-import honesty;
- no-import behavior.

**Step 4: Delete only the redundant file**

After the canonical suite passes, delete `tests/unit/coverage/test_imports.py`. Do not delete `tests/unit/coverage/test_coherence_parity.py`; it contains distinct canonical audit and migration checks.

**Step 5: Verify and commit**

```bash
uv run python -m pytest -q -o addopts='' tests/unit/substrate/test_codemap_imports.py
uv run python -m pytest -q -o addopts='' tests/unit/coverage/test_coherence_parity.py
uv run ruff check tests/unit/substrate/test_codemap_imports.py
```

Commit only the canonical test and deletion with a message such as:

```text
test: consolidate coverage import reachability tests
```

Acceptance criteria:

- the seven duplicated behaviors remain green;
- the transitive reachability behavior remains green under the canonical import;
- no active FEAT/codemap behavior is lost;
- the legacy file is the only deleted test file in this task.

---

## Task 2: Reduce duplicate legacy-import representative tests

**Objective:** Keep the compatibility contract while removing representative-callable tests already covered by the deeper compatibility-path suite.

**Files:**
- Modify: `tests/unit/substrate/test_legacy_import_matrix.py`
- Inspect/retain: `tests/unit/substrate/test_compatibility_paths.py`
- Retain unique coverage for: `factory.validation.manifest_validator`

**Step 1: Build the overlap table**

For each representative test in `test_legacy_import_matrix.py`, map it to the exact assertion in `test_compatibility_paths.py`. The likely duplicates include:

- factory paths;
- validation schema/KB/session validators;
- orchestrator ledger;
- plan-to-tasks;
- skills;
- Pi backend;
- orchestrator types;
- evidence manifests.

Do not remove a test merely because its name is similar. Confirm equivalent warning, identity/delegation, and result assertions.

**Step 2: Preserve the migration contract**

Keep:

- the whole-module warning matrix;
- the mixed-symbol warning matrix;
- the unique manifest-validator representative test;
- any representative test whose behavior is not covered by `test_compatibility_paths.py`.

These tests remain required while the extension and downstream scripts still call deprecated paths.

**Step 3: Remove only proven duplicate representatives**

Delete or merge only the representative-callable tests whose full assertions are already covered. Do not modify the canonical behavior tests in `test_compatibility_paths.py` as part of this task.

**Step 4: Verify and commit**

```bash
uv run python -m pytest -q -o addopts='' \
  tests/unit/substrate/test_legacy_import_matrix.py \
  tests/unit/substrate/test_compatibility_paths.py
uv run python -m pytest -q -o addopts='' tests/unit/substrate/test_compatibility_shims.py
uv run ruff check tests/unit/substrate/test_legacy_import_matrix.py
```

Commit with a message such as:

```text
test: consolidate duplicate legacy import representatives
```

Acceptance criteria:

- warning behavior remains tested;
- unique manifest-validator compatibility remains tested;
- every removed representative has a retained equivalent assertion;
- the old namespace remains callable and tested during its compatibility window.

---

## Task 3: Reclassify tests by external boundary

**Objective:** Stop real Git/subprocess/server/browser/process tests from executing under the default Python unit campaign without misclassifying deterministic `tmp_path` tests.

**Files to inspect and likely modify:**
- `tests/unit/freshness/test_deps.py`
- `tests/unit/freshness/test_historical_preservation.py`
- `tests/unit/orchestrator/test_git_ops.py`
- `tests/unit/orchestrator/test_run_checkpointing.py`
- `tests/unit/orchestrator/test_recovery.py`
- `tests/unit/orchestrator/test_continuation.py`
- `tests/unit/orchestrator/test_execution.py`
- `tests/unit/orchestrator/test_runner_e2e.py`
- `tests/unit/orchestrator/test_nodes_context_dev.py`
- `tests/unit/orchestrator/test_nodes_val_review.py`
- `tests/unit/substrate/test_agents_backend.py`
- `tests/unit/system/test_worker.py`
- `tests/unit/polish/test_devserver.py`
- `tests/unit/polish/test_sim_live.py`
- `tests/unit/polish/test_session.py`
- `tests/unit/polish/test_orchestrator.py`
- relevant local `conftest.py` files

**Step 1: Produce the classification inventory**

Use AST/search inspection to identify direct calls to:

```text
subprocess.run / Popen / communicate
Git command helpers
socket or HTTP server setup
Playwright/browser APIs
npm/node commands
thread/process server startup
```

Record file, test node, boundary type, current marker, target marker, and reason. A file containing both pure and boundary tests must be split or marked at function/class scope; do not move the whole file automatically.

**Step 2: Apply the external-boundary rule**

- direct real Git/subprocess/process behavior → `integration`;
- browser/server/extension interaction → `integration` or `e2e`;
- complete multi-stage runner transition → `e2e`;
- pure parsing, model, monkeypatch, deterministic projection, or `tmp_path`-only behavior → `unit`.

Do not classify a test as integration solely because it uses `tmp_path`.

**Step 3: Update marker tests and campaign snapshots**

Update marker assertions in:

```text
tests/unit/coherence/policy/test_ci.py
tests/unit/coherence/test_register_markers.py
```

and any affected collection/count assertions. Remove assumptions that every test under `tests/unit/` is necessarily a unit test.

**Step 4: Verify marker separation**

Run:

```bash
uv run python -m pytest --collect-only -q -m unit -o addopts=''
uv run python -m pytest --collect-only -q -m integration -o addopts=''
uv run python -m pytest --collect-only -q -m e2e -o addopts=''
```

Then run the moved suites directly. Confirm that the default unit campaign no longer launches real Git/subprocess/browser work, while the moved tests still execute in their appropriate campaign.

Acceptance criteria:

- no real external boundary is silently left in the default unit campaign;
- no deterministic unit behavior is moved merely because it uses `tmp_path`;
- all moved active-contract tests remain required in integration/e2e validation;
- `sim`, `agent`, and `sr` are not invented as replacement execution campaigns.

---

## Task 4: Add conservative changed-scope campaign routing

**Objective:** Run only impacted campaign families for ordinary changes while broadening safely for shared or uncertain changes.

**Files:**
- Create: `src/coherence/policy/impact.py`
- Create: `tests/unit/coherence/policy/test_impact.py`
- Create or modify: `scripts/ci/changed_campaigns.py` (use the repository’s existing scripts convention if a better exact location is found)
- Modify: `.github/workflows/ci.yml`
- Modify only if required by the selected-command projection: `src/coherence/policy/ci.py` and its tests

**Step 1: Define a pure path classifier**

Implement a deterministic function over normalized repository-relative paths. It must return a stable ordered set of campaign families, for example:

```text
unit
integration
e2e
extensions
static
structural
full
```

The names are internal campaign identifiers, not new Coherence CLI groups or project gate vocabulary.

Initial conservative rules:

| Changed paths | Required campaign expansion |
|---|---|
| `src/coherence/**` | unit plus relevant integration; static |
| `src/factory/orchestrator/**` | unit plus integration/e2e; static |
| `src/factory/polish/**` | unit plus integration/e2e; static |
| `src/substrate/**` | unit plus integration; static |
| `tests/**` | campaign containing the changed tests plus affected runtime bucket; unknown test infrastructure broadens |
| `pi-ext/**` | extensions plus relevant Python integration |
| `.factory/**`, `pyproject.toml`, `uv.lock`, `scripts/**`, schemas, fixtures, policy/compiler files | full or the broadest applicable campaign |
| docs/requirements/plans only | structural trace/register checks, unless an active fixture/loader is changed |
| unknown/unclassifiable/shared paths | full |

The classifier must fail closed: an empty or uncertain classification must never produce a narrower campaign than the conservative default.

**Step 2: Keep command authority centralized**

Do not duplicate gate command strings in the router. Project gate declarations remain in `.factory/factory.yaml`; the policy layer remains responsible for command substitution and ordering. If the current flattened `required_ci_commands()` API cannot select campaigns without string heuristics, add a typed projection beside it and test that the existing all-command behavior remains unchanged.

**Step 3: Add changed-file acquisition without provider-specific logic in the classifier**

The pure classifier accepts paths. The CI adapter may obtain paths from:

- PR base/head diff;
- push before/after diff;
- local working-tree diff for manual use.

If the diff cannot be obtained reliably, emit the broad/full campaign instead of an empty selection.

**Step 4: Parallelize independent CI jobs**

Update `.github/workflows/ci.yml` so the selected campaign families run as independent jobs or matrix entries. Preserve blocking status for every selected active campaign. Extension scripts remain direct required gates; they must not be hidden inside Python `unit`.

Keep full validation available for release/manual runs even when an ordinary change selects a narrower set.

**Step 5: Test the routing table**

Add table-driven tests for:

- one path in each subsystem;
- shared/config/fixture/schema changes;
- documentation-only changes;
- unknown paths;
- mixed changes that union campaigns;
- empty/unavailable diff input;
- stable ordering and no duplicate commands.

Acceptance criteria:

- ordinary targeted changes do not run unrelated campaigns;
- uncertainty broadens to a safe superset;
- no active FEAT-backed test area can be skipped by an unknown path;
- command declarations remain centralized;
- the full campaign remains available and unchanged semantically.

---

## Task 5: Optimize freshness test fixtures without faking Git behavior

**Objective:** Reduce repeated real-Git setup cost while preserving historical freshness semantics.

**Files:**
- Modify: `tests/unit/freshness/conftest.py`
- Modify only where needed: `tests/unit/freshness/test_deps.py`, `tests/unit/freshness/test_historical_preservation.py`

**Step 1: Separate pure policy tests from repository-history tests**

Identify tests that can construct freshness models directly and keep those unit-level. Keep tests that assert real commit/history behavior as integration-level boundary tests.

**Step 2: Add an immutable seeded repository fixture**

Create a session/module-scoped baseline repository with the minimum required files, Git identity, and initial commit. Each mutating test receives an isolated copy or equivalent isolated worktree; no test may mutate the shared baseline.

Do not share a mutable Git directory between tests. Do not replace commit-based assertions with mocks.

**Step 3: Preserve special-history cases explicitly**

Tests covering semantic changes, implementation-only changes, missing dependencies, historical preservation, and branch/commit transitions must continue to create the specific commits they assert. Optimize setup around those commits rather than deleting the history.

**Step 4: Measure and verify**

```bash
uv run python -m pytest -q -o addopts='' tests/unit/freshness --durations=20
uv run python -m pytest -q -o addopts='' tests/unit/freshness/test_deps.py tests/unit/freshness/test_historical_preservation.py
```

Acceptance criteria:

- freshness behavior and history assertions remain unchanged;
- no shared mutable fixture causes order dependence;
- the freshness campaign is materially faster than the recorded baseline or the change is reverted;
- marker reclassification and fixture optimization do not hide failures.

---

## Task 6: Optimize orchestrator test setup without changing production semantics

**Objective:** Reduce repeated process/setup overhead while preserving real process-boundary, recovery, checkpoint, human-review, and continuation contracts.

**Files:**
- Inspect/modify only test fixtures/helpers in `tests/unit/orchestrator/`
- Likely candidates: `tests/unit/orchestrator/_skill_fixtures.py`, local fixture modules, and repeated subprocess helpers
- Do not modify production orchestrator code in this task

**Step 1: Inventory repeated setup**

Measure which tests repeatedly create repositories, subprocess environments, skill fixtures, run directories, or identical static payloads. Separate immutable data from per-test mutable state.

**Step 2: Share only immutable setup**

Use session/module-scoped immutable fixtures for static skills, schemas, and baseline files. Keep run state, journals, checkpoints, human decisions, and process handles function-scoped and isolated.

Do not reuse mutable `.pi`/run-state directories across tests. Do not replace the real subprocess boundary in tests that assert decoding, exit codes, interruption, recovery, or resume behavior.

**Step 3: Keep e2e transitions explicit**

`tests/unit/orchestrator/test_runner_e2e.py` and tests exercising full node transitions remain e2e/integration coverage. Fixture optimization must not collapse them into parser-only tests.

**Step 4: Measure and verify**

```bash
uv run python -m pytest -q -o addopts='' tests/unit/orchestrator --durations=20
uv run python -m pytest -q -o addopts='' tests/unit/orchestrator/test_recovery.py tests/unit/orchestrator/test_continuation.py tests/unit/orchestrator/test_run_checkpointing.py
```

Acceptance criteria:

- recovery, continuation, checkpoint, human-review, and process-output contracts remain covered;
- no test-order dependence is introduced;
- orchestrator campaign wall time improves against baseline;
- no production behavior change is included in this task.

---

## Task 7: Holistic campaign verification and rollback checkpoint

**Objective:** Prove that the four cleanup areas reduce campaign time without dropping active-contract coverage.

**Verification:**

```bash
uv run python -m pytest -q -o addopts='' \
  tests/unit/substrate/test_codemap_imports.py \
  tests/unit/substrate/test_legacy_import_matrix.py \
  tests/unit/substrate/test_compatibility_paths.py \
  tests/unit/coherence/policy \
  tests/unit/freshness \
  tests/unit/orchestrator

uv run python -m pytest --collect-only -q -m unit -o addopts=''
uv run python -m pytest --collect-only -q -m integration -o addopts=''
uv run python -m pytest --collect-only -q -m e2e -o addopts=''
uv run ruff check .
uv run pyright
```

`pyright` and unrelated pre-existing failures must be recorded separately from failures introduced by this increment. Run the extension typecheck and direct gate scripts from their package/repository roots as applicable.

Produce a final mapping table containing:

```text
removed test/file
retained equivalent assertion
active FEAT or deprecated-wrapper contract
new marker/campaign
before elapsed time
after elapsed time
```

Rollback rule: each task is a separate commit. If a timing optimization creates order dependence, coverage loss, or a false-negative routing case, revert that task rather than weakening the acceptance test.

---

## Risks and explicit non-goals

- **False-negative impact routing:** mitigated by broadening on unknown/shared/config/fixture changes and retaining full validation.
- **Deprecated-path confusion:** a test importing `factory.*` may still cover canonical behavior. Retarget behavior tests before deleting them; remove only wrapper/parity assertions proven unnecessary.
- **Git fixture contamination:** mitigated by isolated copies/worktrees and immutable baselines.
- **CI compute versus wall time:** parallel jobs may reduce elapsed time while increasing runner minutes. Record both where the CI platform exposes them; do not claim total savings from wall-clock reduction alone.
- **Overclassification:** filesystem use alone is not enough to move a test out of unit.
- **Scope creep:** do not add `pytest-xdist`, implement codemap-precise selection, remove all compatibility shims, or alter production orchestrator semantics in this plan.
