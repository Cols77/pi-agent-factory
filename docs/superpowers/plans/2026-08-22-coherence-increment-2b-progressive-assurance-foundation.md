# Coherence Increment 2B: Progressive Assurance Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the four foundational gaps from the progressive-assurance spec (blocking own-SR
validation errors, typed justification, `NC-*` nonconformance records, mandatory context-manifest
identity/proof) and ship the generic profile/obligation compiler that Increment 2C (CI) and
Increment 3B (obligation-aware views) both build on. A fifth task (Task 7) closes a gap the
review round found in how the first two land together: the trace graph must actually understand
typed justification too, not just `substrate.ledger.tasks`, or Task 2's typed justification and
Task 4's T-031 migration leave `coherence trace check` (a blocking CI obligation from Increment
2C onward) permanently red for any task justified by a non-`satisfies` kind.

**Architecture:** Every new module stays inside its existing layer. `substrate/policy/` holds the
pure, repo-root-only profile vocabulary and the `Obligation` data contract (no trace-graph
knowledge, mirroring how `substrate/validators/manifest.py` stays pure). `coherence/policy/`
holds the compiler that resolves an artifact's effective profile through the trace graph and
compiles obligations from it (mirrors how `coherence.navigate.health` composes `coherence.trace`
+ substrate loaders without substrate importing coherence). `factory/memory/nonconformance.py`
mirrors `factory/memory/failure_record.py` exactly — same directory-per-record-type, id-keyed,
degrade-not-crash discipline. `substrate/ledger/tasks.py` gains typed `justification` alongside
the unchanged `satisfies` (legacy shorthand, zero task-file migration required); `coherence/trace/
model.py` gains the matching typed-lifecycle-edge vocabulary and reads the same `justification:`
field independently (it never imports `substrate.ledger.tasks` — it stays a pure frontmatter
reader, same discipline as `substrate/policy/vocabulary.py`). The behaviour changes to
already-shipped code are `factory/validation/pipeline.py::validate_task_requirements` (starts
distinguishing a task's own justified SR from an unrelated periodic SR when a validation entry
errors instead of running), `factory/orchestrator/nodes.py::run_validation` (now actually gates on
that corrected verdict instead of silently ignoring it), and `coherence/trace/gaps.py::find_gaps`
(the `task_no_sr` check no longer requires the `satisfies` kind specifically).

**Tech Stack:** Python 3.11+, `python-frontmatter`, `jsonschema` (Draft 2020-12), dataclasses,
`argparse`, `pyyaml`, pytest, Ruff, Pyright.

**Spec:** `docs/superpowers/specs/2026-08-22-coherence-progressive-assurance-design.md` (§1 items
1–3, §4, §5, §13), amending `docs/superpowers/specs/2026-08-18-coherence-toolset-design.md`. §13
("Amendment record: closing the review-round gaps") records five corrected decisions from a
same-day review round; this plan reflects all five — see Tasks 1, 6, and 7 below.

## Global Constraints

- Gate vocabulary is fixed: `unit`, `sim`, `integration`, `full` (AGENTS.md). Do not invent new
  gate names.
- Python 3.11–3.12, Ruff line-length 100, Pyright standard mode (AGENTS.md).
- `substrate` never imports `factory` or `coherence`. `coherence` may import `substrate` and
  `factory`, never the reverse (existing layering, unchanged by this plan).
- A malformed `NC-*` record or context manifest degrades to a reported error; it must never crash
  the whole load (established by `factory/memory/failure_record.py` and `coherence/trace/model.py`
  and preserved here for both new record types). **This does NOT extend to tasks**: verified
  against the real `src/substrate/ledger/tasks.py`, `_parse` already raises `ValueError` on a
  missing required field for the whole `load_tasks(tasks_dir)` call — pre-existing behavior, not
  introduced by this plan — and this plan's new `_parse_justification` (Task 2) adds a second
  raise path (`InvalidJustificationError`) with the same all-or-nothing shape: one malformed task
  file aborts loading every task in the directory. Making task-loading degrade-not-crash for
  consistency with `NC-*`/`FR-*` would be a real, larger change to already-shipped code and is out
  of scope for this plan; the constraint above is scoped to what this plan actually adds
  (`NC-*` and the manifest identity check), not overclaimed as a universal rule tasks already
  follow.
- `requiredness` is exactly one of `not_applicable | advisory | required | blocking`
  (spec §4). Only `prototype` and `high_assurance` presets are compiled in this plan (D16);
  `exploration`/`product` are accepted as schema values but must raise
  `UncompiledPresetError` at compile time, never silently fall back. A profile string outside the
  full known-preset vocabulary (`substrate.policy.vocabulary.KNOWN_PRESETS`) is a distinct,
  earlier failure — `InvalidProfileError`, a configuration error, never a silent fallback (spec
  §13; Task 6).
- Existing `satisfies:` task frontmatter must keep working with **zero file edits** (spec §4,
  "typed task justification").
- Suspect-edge validity has no automatic path back to `valid` at any `requiredness` level (spec
  §13): a deferred or exempt gap classifies as `waived`, never `valid`. This plan does not
  implement suspect-edge validity itself (Increment 6), but Task 7's `task_no_sr` fix must not
  invent one either — a task justified only by a non-`satisfies` kind is fully justified (no
  `task_no_sr` gap), which is a *different* claim than "its edge is valid"; this plan makes no
  validity claim at all, only a justification-presence one.

---

## File Structure

**Create:**

- `src/substrate/policy/__init__.py`
- `src/substrate/policy/vocabulary.py` — profile dimensions, presets, project-default/path-override
  resolution primitives (pure, repo-root-only, no trace-graph import)
- `src/substrate/policy/obligation.py` — `Obligation` dataclass, `Requiredness` literal
- `src/substrate/schemas/nonconformance.schema.json`
- `src/substrate/schemas/profile.schema.json` — validates a resolved `profile:` value against
  `KNOWN_PRESETS` (Task 6, spec §13)
- `src/factory/memory/nonconformance.py` — `NonconformanceRecord`, `load_nonconformances`,
  mirrors `failure_record.py`
- `src/coherence/policy/__init__.py`
- `src/coherence/policy/compiler.py` — `resolve_profile`, `compile_obligations`
  (trace-graph-aware; `coherence`-layer, not `substrate`)
- `docs/nonconformances/NC-0001-catchup-tab-orientation.md`
- `tests/unit/substrate/policy/test_vocabulary.py` — **no** `tests/unit/substrate/policy/__init__.py`
  (verified: `tests/unit/substrate/` is flat, no existing subdirectory there carries an
  `__init__.py`; a new subdirectory under it matches that convention, unlike `tests/unit/coherence/`
  and `tests/unit/memory/`, which already have one at their own top level)
- `tests/unit/substrate/policy/test_obligation.py`
- `tests/unit/coherence/policy/__init__.py` (`tests/unit/coherence/` already has its own
  `__init__.py`, so a new subdirectory under it follows suit)
- `tests/unit/coherence/policy/test_compiler.py`
- `tests/unit/memory/test_nonconformance.py` — **not** `tests/unit/factory/memory/` (verified:
  `tests/unit/memory/` already exists, already has `__init__.py`, and is exactly where
  `test_failure_record.py` — the record type this mirrors — actually lives; `tests/unit/factory/`
  has no `memory/` subdirectory at all today)
- `tests/unit/memory/test_t031_link.py` — likewise under the real `tests/unit/memory/`, not
  `tests/unit/factory/memory/` (missing from an earlier draft's Create list; added here)
- `tests/unit/substrate/ledger/test_tasks_justification.py` (no `__init__.py` here either, for the
  same flat-`tests/unit/substrate/` reason as `policy/` above)
- `tests/unit/trace/test_model_edges.py` — no new file: **modify** the existing file (see below)
- `tests/unit/trace/test_model_nodes.py` — no new file: **modify** the existing file (see below)
- `tests/unit/trace/test_gaps.py` — no new file: **modify** the existing file (see below)

**Modify:**

- `src/factory/validation/pipeline.py` — `validate_task_requirements` distinguishes own-SR errors
- `src/factory/orchestrator/nodes.py` — `run_validation` gates on `ok`, not a self-recomputed
  `reds`/`warns` split that never consulted it (Task 1 Step 5 — a real runtime bug found by
  reading the source, not merely a test-fixture change)
- `tests/unit/validation/test_pipeline.py` — rename/fix `test_missing_harness_is_warning_not_failure`,
  add one full-sweep companion test (Task 1)
- `tests/unit/orchestrator/test_nodes_requirement_validation.py` — rename/fix
  `test_missing_harness_warns_not_fails`, add one companion test (Task 1)
- `src/substrate/ledger/tasks.py` — `Justification`, `Task.justification`, backward-compat parse
- `src/coherence/trace/model.py` — `Node.scope_error`, `EdgeKind` gains typed lifecycle/
  justification kinds, `extract_edges`'s task branch reads `justification:` (Task 7)
- `src/coherence/trace/gaps.py` — `task_no_sr` fires on absence of ANY justification-derived edge,
  not specifically `satisfies` (Task 7)
- `tests/unit/trace/test_model_edges.py`, `tests/unit/trace/test_model_nodes.py`,
  `tests/unit/trace/test_gaps.py` — new coverage for the above (Task 7)
- `src/substrate/schemas/context_manifest.schema.json` — `checks` gains `"minItems": 1`
- `src/substrate/validators/manifest.py` — `identity_errors`, `task_id` param threaded through
  `validate_manifest_document`
- `src/factory/validation/manifest_validator.py` — passes `task_id=task.id if task else None`
- `tests/unit/test_manifest_validator.py` — `test_valid_manifest_no_checks` renamed and now
  expects a schema error (empty `checks` is no longer valid); add `test_valid_manifest_with_one_check`,
  `test_manifest_task_id_mismatch_rejected`, `test_manifest_task_id_match_accepted`; fix
  `test_missing_source_file_reports_error`, `test_anchor_is_stripped_before_existence_check`,
  `test_legacy_proven_field_is_stripped_not_rejected`, `test_evidence_style_checks_are_dropped_not_rejected`
  (renamed), `test_coverage_floor_requires_modify_deliverable` — every one of these currently
  builds a manifest with empty/default `checks` (Task 5)
- `tests/unit/substrate/test_validator_inversion.py` — fix
  `test_validate_manifest_document_valid_manifest_no_checks_is_clean` **and** (found by reading
  the full file, not named in the original review) `test_pure_document_matches_legacy_validate_manifest_for_the_coverage_floor`
  — both build a manifest with default empty `checks` (Task 5)
- `tests/unit/orchestrator/test_runner.py`, `test_run_next.py`, `test_human_review_gate_in_runner.py`,
  `test_grill_in_runner.py`, `test_context_limit_continuation.py`, `test_runner_e2e.py`,
  `tests/integration/orchestrator/test_resume_run.py` — each adds one real `files_exist` check to
  an existing `"coherence": {"checks": []}` manifest fixture (Task 5). **Verified NOT needed**:
  `tests/unit/orchestrator/test_context_packet.py` — its `_manifest()` fixture is never passed
  through `validate_manifest`/`validate_manifest_document` (`build_context_packet`,
  `primary_paths`, and `compose_prompt` are plain consumers of the dict, confirmed by reading
  `src/factory/orchestrator/context_packet.py` and `src/factory/orchestrator/prompts.py`), so
  `minItems: 1` never fires against it — left unmodified, on purpose, not by oversight.
- `src/substrate/schemas/feat.schema.json` — `profile` added to `properties` (Task 6, spec §13)
- `src/coherence/policy/compiler.py` — `_ci_verification_obligation` reuses
  `factory.orchestrator.backends`'s `{python}` substitution; `resolve_profile`/`compile_obligations`
  gain `nodes=`/`edges=` passthrough (Task 6, spec §13)
- `tasks/T-031-catchup-tab-orientation-metadata.md` — `satisfies: []` → typed `justification`

---

### Task 1: Make a task's own requirement-validation error blocking

Fixes spec §1 gap 1: `validate_task_requirements` currently treats an "error" entry (harness
missing, execution error) on a task's own SR identically to a setup gap on an unrelated,
periodic-cadence SR — both are non-blocking warnings today. The invariant kernel's rule 1 ("an
execution error, missing executable or invalid result cannot become pass") requires the task's
own SR to block.

**Verified against the real file** (`tests/unit/validation/test_pipeline.py` already exists, 138
lines, with its own working fixtures: `_SR` template, `_CONFIG`, `_project(tmp_path)`, and a
module-level `_write_sr(req_dir, sr_id, cadence)` helper already used by `_project` to seed
SR-001 at `every_iteration` cadence and SR-002 at `periodic` cadence). Two consequences that
change this task's shape from an earlier draft:

1. A new helper named `_write_sr(root, sr_id, *, with_binding)` would silently shadow the
   existing module-level `_write_sr(req_dir, sr_id, cadence)` that `_project` (and therefore
   several pre-existing tests) already depends on. Rather than inventing a second helper and
   renaming around the collision, Step 1 below reuses the file's own existing `_project`/
   `_write_sr` fixtures directly — no new helper, no collision.
2. `tests/unit/validation/test_pipeline.py::test_missing_harness_is_warning_not_failure` already
   calls `validate_task_requirements(tmp_path, ["SR-001"])` — SR-001 **is** the task's own SR —
   and asserts `ok is True`. That is exactly the bug this task fixes; the assertion is now wrong
   and the test's name no longer describes what it tests. It must be renamed and its assertion
   flipped, not left alongside a new, differently-named test that duplicates its setup.
3. **`factory/orchestrator/nodes.py::run_validation` — the actual orchestrator call site — never
   reads the `ok` this function returns.** It calls `validate_task_requirements(repo_root,
   satisfies or [])`, discards `ok`, and independently recomputes `warns = [e["id"] for e in
   report["requirements"] if "error" in e]` — treating *every* error entry as a non-blocking
   warning, regardless of whether it is the task's own SR. Fixing `validate_task_requirements`'s
   return value alone does not change orchestrator behavior: an own-SR execution error would
   still only warn at runtime. This task must also fix `run_validation` to gate on `ok`, or its
   stated goal is not actually achieved end-to-end. (This is a real, verified finding from
   reading `src/factory/orchestrator/nodes.py` directly — the plan's own "Interfaces" claim below
   that callers "need no change" was wrong; the real one does.)

**Files:**
- Modify: `src/factory/validation/pipeline.py:29-48`
- Modify: `src/factory/orchestrator/nodes.py` — `run_validation` gates on `ok`, not a
  self-recomputed `reds`/`warns` split that never consulted it
- Test: `tests/unit/validation/test_pipeline.py` (exists — rename/fix
  `test_missing_harness_is_warning_not_failure`, add one full-sweep companion test)
- Test: `tests/unit/orchestrator/test_nodes_requirement_validation.py` (exists — rename/fix
  `test_missing_harness_warns_not_fails`, add one companion test)

**Interfaces:**
- Consumes: `factory.requirements.register.{Requirement, load_register}`,
  `factory.validation.report.run_requirement_validation` (unchanged signatures)
- Produces: `validate_task_requirements(repo_root, satisfies, *, full_sweep=False) ->
  tuple[dict, bool]` — same signature, corrected `ok` semantics. `run_validation` now reads this
  `ok` directly for its FAIL/PASS gate (see Step 5 below).

- [ ] **Step 1: Fix `tests/unit/validation/test_pipeline.py`.**

Rename `test_missing_harness_is_warning_not_failure` to `test_missing_harness_on_own_sr_blocks`
and flip its assertion (it already sets up exactly the right scenario — SR-001 is the task's own
SR via `satisfies=["SR-001"]`, and `_project` already declares no working harness for it once the
test overwrites `.factory/factory.yaml`):

```python
def test_missing_harness_on_own_sr_blocks(tmp_path):
    # SR-001 is the task's own justified SR (satisfies=["SR-001"]); its harness
    # isn't declared, so validation reports an "error" entry. Invariant kernel
    # rule 1: an execution error on a task's OWN justified SR cannot become
    # pass -- this used to assert ok is True (the bug this task fixes).
    _project(tmp_path)
    (tmp_path / ".factory" / "factory.yaml").write_text("harnesses: {}\n", encoding="utf-8")
    report, ok = validate_task_requirements(tmp_path, ["SR-001"])
    assert ok is False
    assert "error" in report["requirements"][0]
```

Add a companion test proving the still-a-warning case, reusing `_project`'s own SR-002
(`_write_sr(req, "SR-002", "periodic")`) and `full_sweep=True` to select it by cadence, not by
`satisfies` — this is the real full-sweep exercise an earlier draft of this test lacked (SR-002
is periodic, not `every_iteration`, so only `full_sweep=True` pulls it in):

```python
def test_unrelated_periodic_sr_error_stays_a_warning(tmp_path):
    # The task names nothing itself (satisfies=[]); SR-001 (every_iteration)
    # and SR-002 (periodic) are both swept in only because full_sweep=True,
    # not because the task claims either -- neither is in own_ids, so an
    # error on either stays a warning: ok is True.
    _project(tmp_path)
    (tmp_path / ".factory" / "factory.yaml").write_text("harnesses: {}\n", encoding="utf-8")
    report, ok = validate_task_requirements(tmp_path, [], full_sweep=True)
    ids = [e["id"] for e in report["requirements"]]
    assert "SR-002" in ids
    periodic_entry = next(e for e in report["requirements"] if e["id"] == "SR-002")
    assert "error" in periodic_entry
    assert ok is True
```

- [ ] **Step 2: Run the tests to verify they fail.**

Run: `rtk proxy uv run python -m pytest tests/unit/validation/test_pipeline.py -v`
Expected: `test_missing_harness_on_own_sr_blocks` FAILS (`ok is False` assertion fails — current
code returns `ok=True` for pure-error entries); `test_unrelated_periodic_sr_error_stays_a_warning`
PASSES already (documents the behaviour this task must not change).

- [ ] **Step 3: Implement the minimal fix in `validate_task_requirements`.**

```python
def validate_task_requirements(
    repo_root: Path, satisfies: list[str], *, full_sweep: bool = False
) -> tuple[dict, bool]:
    reqs = load_register(repo_root / "requirements")
    harnesses = load_config(repo_root).harnesses

    def harness_for(name: str) -> Harness:
        h = harnesses.get(name)
        if h is None:
            raise ValueError(f"no harness {name!r} declared in .factory/factory.yaml")
        return h

    own_ids = set(satisfies)  # the task's own justified SRs -- see select_requirement_ids
    ids = select_requirement_ids(reqs, satisfies, full_sweep=full_sweep)
    report = run_requirement_validation(ids, reqs, harness_for, repo_root)
    # Invariant kernel rule 1: an execution error, missing executable or invalid
    # result on a task's OWN justified SR cannot become pass -- it blocks, exactly
    # like a ran-and-failed assertion. An "error" entry on an SR the task did not
    # name (only swept in by full_sweep's periodic cadence) is still a setup gap
    # unrelated to this task's claim, surfaced as a warning, not a hard failure.
    reds = any(e.get("passed") is False for e in report["requirements"])
    own_errors = any(
        "error" in e and e.get("id") in own_ids for e in report["requirements"]
    )
    ok = not (reds or own_errors)
    return report, ok
```

- [ ] **Step 4: Run the tests to verify they pass.**

Run: `rtk proxy uv run python -m pytest tests/unit/validation/test_pipeline.py -v`
Expected: PASS, including both fixed/new tests and every pre-existing test in the file
(`test_validate_task_requirements_ok`, `test_harness_lookup_is_by_instance_key_not_type`, etc. —
none of these name an own-SR error, so none change).

- [ ] **Step 5: Fix `run_validation` to actually gate on `ok`.**

`src/factory/orchestrator/nodes.py::run_validation` currently discards the `ok` this function
returns and recomputes `warns` from every `"error" in e` entry regardless of ownership. Replace
its post-`validate_task_requirements` block:

```python
    warns: list[str] = []
    if repo_root is not None:
        report, ok = validate_task_requirements(repo_root, satisfies or [])
        if transcript_dir is not None:
            write_validation_report(transcript_dir / "validation-report.json", report)
        own_ids = set(satisfies or [])
        # reds/warns here only build the human-readable status messages; `ok`
        # (from validate_task_requirements, fixed above) is the single source
        # of truth for blocking. Before this task, gating on a self-recomputed
        # `reds` (RAN-and-failed only) meant an own-SR execution error never
        # blocked here no matter what validate_task_requirements returned --
        # that is the actual runtime bug Task 1 exists to close.
        reds = [
            e["id"] for e in report["requirements"]
            if e.get("passed") is False or ("error" in e and e.get("id") in own_ids)
        ]
        warns = [
            e["id"] for e in report["requirements"]
            if "error" in e and e.get("id") not in own_ids
        ]
        if not ok:
            status.report(
                task_id=task_id,
                node="validation",
                node_state="fail",
                attempt=1,
                max_attempts=1,
                handoff=f"requirements failed: {', '.join(reds)}",
            )
            return NodeOutcome.FAIL, NodeEvent(
                "validation",
                "fail",
                1,
                {"failed_requirements": reds, "requirement_warnings": warns},
            )
        if warns:
            status.report(
                task_id=task_id,
                node="validation",
                node_state="running",
                attempt=1,
                max_attempts=1,
                handoff=(
                    f"⚠ not validated (no harness/scenario defined): {', '.join(warns)} — "
                    "declare a harness in .factory/factory.yaml or run /specify-requirements"
                ),
            )
```

- [ ] **Step 6: Fix `tests/unit/orchestrator/test_nodes_requirement_validation.py`.**

`test_missing_harness_warns_not_fails` (SR-001 is the task's own SR via `satisfies=["SR-001"]`,
harness undeclared) asserts `NodeOutcome.PASS` with `requirement_warnings == ["SR-001"]` — the
same bug, one layer up. Rename and flip it:

```python
def test_missing_harness_on_own_sr_fails(tmp_path):
    # SR-001 is the task's own justified SR; no harness is declared for it,
    # so validate_task_requirements reports an "error" entry. Invariant
    # kernel rule 1 (Task 1, Increment 2B): this must fail the node, the same
    # way test_fails_when_sr_red does -- both are the task's own SR not
    # resolving to a clean pass. This test used to assert PASS (the bug).
    _project(tmp_path, [GOOD, GOOD])
    (tmp_path / ".factory" / "factory.yaml").write_text("harnesses: {}\n", encoding="utf-8")
    outcome, ev = run_validation(_Gates(), "T-1", repo_root=tmp_path, satisfies=["SR-001"])
    assert outcome == NodeOutcome.FAIL
    assert ev.extra["failed_requirements"] == ["SR-001"]
```

Add a companion test proving an SR the task does not own still only warns, reusing `_project`'s
own working SR-001 (so the own-SR side stays green) and adding a second, `every_iteration`-cadence
SR-002 (default cadence when omitted — `coherence.register.register.Binding.cadence` defaults to
`"every_iteration"`) with an undeclared harness name, so `select_requirement_ids` sweeps it in
even though `satisfies` never names it:

```python
def test_error_on_a_sr_the_task_does_not_own_still_warns(tmp_path):
    from factory.requirements.register import content_checksum, parse_requirement

    _project(tmp_path, [GOOD, GOOD])  # SR-001: bound, harnessed, green
    sr2 = tmp_path / "requirements" / "SR-002.md"
    sr2.write_text(
        "---\nid: SR-002\ntitle: t2\nstatement: s2\ndomain: behavioral\n"
        "binding:\n  harness: not-declared\n  experiment: e\n"
        "  metric: m\n  trials: 1\n  assert: '>= 0.90'\n"
        "checksum: null\n---\nbody\n",
        encoding="utf-8",
    )
    sr2.write_text(
        sr2.read_text(encoding="utf-8").replace(
            "checksum: null", f"checksum: {content_checksum(parse_requirement(sr2))}"
        ),
        encoding="utf-8",
    )
    outcome, ev = run_validation(_Gates(), "T-1", repo_root=tmp_path, satisfies=["SR-001"])
    assert outcome == NodeOutcome.PASS
    assert ev.extra["requirement_warnings"] == ["SR-002"]
```

- [ ] **Step 7: Run both fixed test files.**

Run: `rtk proxy uv run python -m pytest tests/unit/validation/test_pipeline.py tests/unit/orchestrator/test_nodes_requirement_validation.py -v`
Expected: PASS, all tests in both files.

- [ ] **Step 8: Run the wider validation and orchestrator suites for regressions.**

Run: `rtk proxy uv run python -m pytest tests/unit -k "validation or orchestrator" -q`
Expected: PASS. No other test in either suite hard-codes an own-SR error as non-blocking (only
the two renamed above did).

- [ ] **Step 9: Commit.**

```bash
git add src/factory/validation/pipeline.py src/factory/orchestrator/nodes.py \
        tests/unit/validation/test_pipeline.py \
        tests/unit/orchestrator/test_nodes_requirement_validation.py
git commit -m "fix(validation): a task's own SR validation error blocks, not warns"
```

### Task 2: Typed task justification, backward-compatible with `satisfies:`

Implements spec §4 "typed task justification": `satisfies | corrects | mitigates | implements |
maintains | explores`, each naming a target id. Existing `satisfies:` frontmatter parses as
shorthand for `justification: [{satisfies: ...}]` — no existing task file needs editing.

**Files:**
- Modify: `src/substrate/ledger/tasks.py`
- Test: `tests/unit/substrate/ledger/test_tasks_justification.py`

**Interfaces:**
- Produces: `substrate.ledger.tasks.Justification(kind: str, target_id: str)` (frozen dataclass),
  `substrate.ledger.tasks.InvalidJustificationError(ValueError)`, `Task.justification: list[Justification]`
  (new field, default `[]`). `Task.satisfies` keeps its existing type (`list[str]`) and existing
  meaning — it is now *derived* from `justification` (every entry of kind `"satisfies"`), not
  parsed independently, so every existing consumer (`factory/orchestrator/nodes.py`,
  `factory/validation/pipeline.py`) needs no change.

- [ ] **Step 1: Write the failing tests.**

```python
import pytest
from pathlib import Path

from substrate.ledger.tasks import InvalidJustificationError, Justification, load_tasks

pytestmark = pytest.mark.unit


def _write_task(root: Path, name: str, frontmatter_extra: str) -> Path:
    (root / "tasks").mkdir(exist_ok=True)
    path = root / "tasks" / name
    path.write_text(
        f"---\nid: T-900\ntitle: t\nstatus: todo\ndod:\n- 'done'\n{frontmatter_extra}---\nbody\n",
        encoding="utf-8",
    )
    return path


def test_legacy_satisfies_becomes_typed_justification(tmp_path):
    _write_task(tmp_path, "T-900.md", "satisfies:\n- SR-001\n")
    task = load_tasks(tmp_path / "tasks")[0]
    assert task.satisfies == ["SR-001"]
    assert task.justification == [Justification("satisfies", "SR-001")]


def test_explicit_justification_corrects(tmp_path):
    _write_task(
        tmp_path, "T-900.md", "justification:\n- corrects: NC-0001\n"
    )
    task = load_tasks(tmp_path / "tasks")[0]
    assert task.satisfies == []  # corrects is not a satisfies-kind entry
    assert task.justification == [Justification("corrects", "NC-0001")]


def test_justification_mixed_kinds(tmp_path):
    _write_task(
        tmp_path,
        "T-900.md",
        "justification:\n- satisfies: SR-002\n- mitigates: FR-EXAMPLE\n",
    )
    task = load_tasks(tmp_path / "tasks")[0]
    assert task.satisfies == ["SR-002"]
    assert task.justification == [
        Justification("satisfies", "SR-002"),
        Justification("mitigates", "FR-EXAMPLE"),
    ]


def test_unknown_justification_kind_raises(tmp_path):
    _write_task(tmp_path, "T-900.md", "justification:\n- rejects: SR-001\n")
    with pytest.raises(InvalidJustificationError):
        load_tasks(tmp_path / "tasks")


def test_multi_key_justification_entry_raises(tmp_path):
    _write_task(
        tmp_path, "T-900.md", "justification:\n- satisfies: SR-001\n  corrects: NC-0001\n"
    )
    with pytest.raises(InvalidJustificationError):
        load_tasks(tmp_path / "tasks")
```

- [ ] **Step 2: Run the tests to verify they fail.**

Run: `rtk proxy uv run python -m pytest tests/unit/substrate/ledger/test_tasks_justification.py -v`
Expected: FAIL — `ImportError: cannot import name 'Justification'`.

- [ ] **Step 3: Implement.**

```python
_JUSTIFICATION_KINDS = (
    "satisfies", "corrects", "mitigates", "implements", "maintains", "explores",
)


class InvalidJustificationError(ValueError):
    pass


@dataclass(frozen=True)
class Justification:
    kind: str
    target_id: str


def _parse_justification(meta: dict) -> list["Justification"]:
    raw = meta.get("justification")
    if raw is None:
        # Legacy shorthand: satisfies: [...] means justification: [{satisfies: ...}].
        satisfies_value = meta.get("satisfies") or []
        if isinstance(satisfies_value, str):
            satisfies_value = [satisfies_value]
        return [Justification("satisfies", str(s)) for s in satisfies_value]
    if not isinstance(raw, list):
        raise InvalidJustificationError(
            "justification must be a list of single-key {kind: target_id} mappings"
        )
    out: list[Justification] = []
    for entry in raw:
        if not isinstance(entry, dict) or len(entry) != 1:
            raise InvalidJustificationError(
                f"each justification entry must be a single {{kind: target_id}} mapping, got {entry!r}"
            )
        ((kind, target_id),) = entry.items()
        if kind not in _JUSTIFICATION_KINDS:
            raise InvalidJustificationError(
                f"unknown justification kind {kind!r} (have {_JUSTIFICATION_KINDS})"
            )
        out.append(Justification(str(kind), str(target_id)))
    return out
```

Add `justification: list[Justification] = field(default_factory=list)` to `Task`. In `_parse`,
replace the existing `satisfies_value = meta.get("satisfies") or []` block with:

```python
justification = _parse_justification(meta)
satisfies = [j.target_id for j in justification if j.kind == "satisfies"]
```

and pass both `satisfies=satisfies, justification=justification` into the returned `Task(...)`.
Add `Justification` and `InvalidJustificationError` to the module (no `__all__` currently exists
in this file — do not add one; keep the existing plain-import convention).

- [ ] **Step 4: Run the tests to verify they pass.**

Run: `rtk proxy uv run python -m pytest tests/unit/substrate/ledger/test_tasks_justification.py -v`
Expected: PASS.

- [ ] **Step 5: Run the full ledger/orchestrator suites for regressions.**

Run: `rtk proxy uv run python -m pytest tests/unit -k "ledger or tasks or orchestrator" -q`
Expected: PASS unchanged — every existing task file using `satisfies:` produces the identical
`Task.satisfies` value as before.

- [ ] **Step 6: Commit.**

```bash
git add src/substrate/ledger/tasks.py tests/unit/substrate/ledger/test_tasks_justification.py
git commit -m "feat(tasks): typed justification, satisfies: kept as shorthand"
```

### Task 3: `NC-*` nonconformance records

Implements spec §5's record type: structurally parallel to `FR-*` (`factory/memory/failure_record.py`).
Health surfacing of `NONCONFORMANCE_OPEN`/`NONCONFORMANCE_CLOSED` findings is explicitly out of
scope here — it lands in Increment 5 (health-vector dimension 9, "nonconformance/change closure"),
which owns `coherence/navigate/health.py`; this task only ships the record type itself.

**Files:**
- Create: `src/substrate/schemas/nonconformance.schema.json`
- Create: `src/factory/memory/nonconformance.py`
- Test: `tests/unit/memory/test_nonconformance.py` (verified: `tests/unit/memory/` already exists
  with its own `__init__.py` and is where `test_failure_record.py` — the record type this
  mirrors — actually lives; `tests/unit/factory/memory/` does not exist)

**Interfaces:**
- Produces: `factory.memory.nonconformance.NonconformanceRecord`,
  `factory.memory.nonconformance.DuplicateNonconformanceIdError`,
  `factory.memory.nonconformance.load_nonconformances(repo_root: Path) -> dict[str, NonconformanceRecord]`,
  `factory.memory.nonconformance.nonconformances_dir(repo_root: Path) -> Path`
  (`docs/nonconformances/`). Consumed by Task 4 (T-031 link) directly by reference, and by
  Increment 5's health dimension 9 later.

- [ ] **Step 1: Write the schema.**

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://factory.local/schemas/nonconformance.schema.json",
  "title": "Nonconformance record frontmatter",
  "type": "object",
  "additionalProperties": false,
  "required": ["id", "title", "status"],
  "properties": {
    "id": {
      "type": "string",
      "pattern": "^NC-[0-9]+$",
      "description": "Stable identity. Scope refs use this (nc:NC-0001), never the filename."
    },
    "title": {"type": "string", "minLength": 1},
    "external_ref": {
      "type": ["string", "null"],
      "pattern": "^[a-z][a-z-]*:.+$",
      "description": "A citation, not a live sync (e.g. gh-issue:1). Coherence never calls out to the tracker."
    },
    "detected_by": {"type": ["string", "null"]},
    "status": {"type": "string", "enum": ["open", "corrected", "waived"]},
    "corrected_by": {
      "type": ["string", "null"],
      "pattern": "^T-[0-9]+$",
      "description": "The task whose justification names `corrects: <this id>`."
    }
  }
}
```

- [ ] **Step 2: Write the failing tests.**

```python
import pytest
from pathlib import Path

from factory.memory.nonconformance import (
    DuplicateNonconformanceIdError,
    load_nonconformances,
)

pytestmark = pytest.mark.unit


def _write_nc(root: Path, filename: str, body: str) -> None:
    (root / "docs" / "nonconformances").mkdir(parents=True, exist_ok=True)
    (root / "docs" / "nonconformances" / filename).write_text(body, encoding="utf-8")


def test_no_directory_returns_empty(tmp_path):
    assert load_nonconformances(tmp_path) == {}


def test_load_valid_record(tmp_path):
    _write_nc(
        tmp_path,
        "NC-0001.md",
        "---\nid: NC-0001\ntitle: t\nexternal_ref: gh-issue:1\nstatus: corrected\n"
        "corrected_by: T-031\n---\nbody\n",
    )
    records = load_nonconformances(tmp_path)
    assert records["NC-0001"].external_ref == "gh-issue:1"
    assert records["NC-0001"].corrected_by == "T-031"
    assert records["NC-0001"].scope_errors == []


def test_malformed_record_degrades_to_scope_errors(tmp_path):
    _write_nc(tmp_path, "NC-0002.md", "---\ntitle: no id\n---\nbody\n")
    records = load_nonconformances(tmp_path)
    assert records == {}  # no id -> not keyed, but load must not crash


def test_duplicate_id_raises(tmp_path):
    _write_nc(tmp_path, "a.md", "---\nid: NC-0003\ntitle: a\nstatus: open\n---\n")
    _write_nc(tmp_path, "b.md", "---\nid: NC-0003\ntitle: b\nstatus: open\n---\n")
    with pytest.raises(DuplicateNonconformanceIdError):
        load_nonconformances(tmp_path)
```

- [ ] **Step 3: Run the tests to verify they fail.**

Run: `rtk proxy uv run python -m pytest tests/unit/memory/test_nonconformance.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'factory.memory.nonconformance'`).

- [ ] **Step 4: Implement, mirroring `failure_record.py` exactly.**

```python
"""Nonconformance records: a defect/change-request corrected by a task.

`docs/nonconformances/NC-*.md`. Structurally parallel to `docs/failures/FR-*.md`
(`factory.memory.failure_record`): identity is the `id` in YAML frontmatter,
never the filename; a malformed record degrades into `scope_errors` instead of
crashing the set; `external_ref` is a citation (`gh-issue:1`), never a live
sync -- coherence never calls the tracker's API.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import frontmatter

from substrate.validators.schema import SCHEMA_DIR, validate

_SCHEMA = SCHEMA_DIR / "nonconformance.schema.json"
_NC_DIR_PARTS = ("docs", "nonconformances")


class DuplicateNonconformanceIdError(ValueError):
    """Two nonconformance files declare the same `id`."""


@dataclass(frozen=True)
class NonconformanceRecord:
    id: str | None
    title: str | None
    path: Path
    external_ref: str | None = None
    detected_by: str | None = None
    status: str = "open"
    corrected_by: str | None = None
    scope_errors: list[str] = field(default_factory=list)


def parse_nonconformance(path: Path) -> NonconformanceRecord:
    """Parse one nonconformance record. Never raises: a bad record degrades itself."""
    try:
        post = frontmatter.load(str(path))
    except (OSError, ValueError) as exc:
        return NonconformanceRecord(
            id=None, title=None, path=path, scope_errors=[f"{path}: unreadable ({exc})"]
        )

    meta = dict(post.metadata)
    if not meta:
        return NonconformanceRecord(
            id=None,
            title=None,
            path=path,
            scope_errors=[f"{path}: no frontmatter; a nonconformance record must declare id, title and status"],
        )

    errors = validate(meta, _SCHEMA)
    return NonconformanceRecord(
        id=meta.get("id"),
        title=meta.get("title"),
        path=path,
        external_ref=meta.get("external_ref"),
        detected_by=meta.get("detected_by"),
        status=meta.get("status", "open"),
        corrected_by=meta.get("corrected_by"),
        scope_errors=errors,
    )


def nonconformances_dir(repo_root: Path) -> Path:
    return repo_root.joinpath(*_NC_DIR_PARTS)


def load_nonconformance(path: Path) -> NonconformanceRecord:
    return parse_nonconformance(path)


def load_nonconformances(repo_root: Path) -> dict[str, NonconformanceRecord]:
    """Load every nonconformance record under `docs/nonconformances/`, keyed by id.

    An absent directory is a legitimate state, not an error. Duplicate ids raise.
    """
    directory = nonconformances_dir(repo_root)
    if not directory.is_dir():
        return {}
    loaded: dict[str, NonconformanceRecord] = {}
    for path in sorted(directory.glob("*.md")):
        rec = parse_nonconformance(path)
        if rec.id is None:
            continue
        if rec.id in loaded:
            raise DuplicateNonconformanceIdError(
                f"nonconformance id {rec.id!r} is declared by both {loaded[rec.id].path} and {path}"
            )
        loaded[rec.id] = rec
    return loaded
```

- [ ] **Step 5: Run the tests to verify they pass.**

Run: `rtk proxy uv run python -m pytest tests/unit/memory/test_nonconformance.py -v`
Expected: PASS.

- [ ] **Step 6: Commit.**

```bash
git add src/substrate/schemas/nonconformance.schema.json src/factory/memory/nonconformance.py \
        tests/unit/memory/test_nonconformance.py
git commit -m "feat(memory): NC-* nonconformance records, mirroring FR-*"
```

### Task 4: Link T-031 to GitHub issue #1 via `NC-0001`

The concrete instance spec §5 requires: `T-031` corrects the exact symptom filed as issue #1
(the intermittent "no orientation for tab Catchup" gate failure). `T-031` is currently untracked
(`status: done`, `satisfies: []`) — this task gives it its first commit alongside `NC-0001`.

**Files:**
- Create: `docs/nonconformances/NC-0001-catchup-tab-orientation.md`
- Create: `tests/unit/memory/test_t031_link.py`
- Modify: `tasks/T-031-catchup-tab-orientation-metadata.md`

**Interfaces:**
- Consumes: `factory.memory.nonconformance` (Task 3), `substrate.ledger.tasks.Justification` (Task 2)

- [ ] **Step 1: Write `NC-0001`.**

```markdown
---
id: NC-0001
title: Catchup tab has no orientation metadata
external_ref: gh-issue:1
detected_by: gate-flake-investigation
status: corrected
corrected_by: T-031
---

## Symptom

The watch-extension gate intermittently failed with `no orientation for tab Catchup`. The static
shell declares `#tabCatchup`, but `PANELS_DATA.panels` had entries through `Diagram` only. The
bundle-scope test also inspected every `[role=tab]` without filtering hidden tabs, even though
`configureTabs('bundle')` hides Catchup — so the failure surfaced only under some tab-visibility
orderings, reading as vitest flakiness rather than a missing-data bug.

Filed as GitHub issue #1 ("pi-ext factory-watch vitest suite is flaky under full parallel run"),
discovered while finishing `feat/coherence-increment-1c`.

## Correction

`T-031` adds a `Catchup` entry to `PANELS_DATA.panels` (label, `what_it_shows`, `how_to_read`) and
fixes the bundle-scope orientation test to respect the tab-visibility contract: hidden tabs are
not asserted as rendered for a scope that hides them, while the Catchup scope's own orientation
line is explicitly covered.
```

- [ ] **Step 2: Update `T-031`'s frontmatter.**

Replace `satisfies: []` with:

```yaml
justification:
  - corrects: NC-0001
```

Leave every other field (`dod`, `source_plan`, `status: done`, `title`) unchanged — this task
retrofits traceability onto already-completed work, it does not reopen it.

- [ ] **Step 3: Verify the link resolves.**

Verified: `tests/unit/conftest.py` has no `repo_root` fixture (it carries only a module-path
comment, no fixtures at all), and there is no repo-root `conftest.py` either. The real,
established convention for "the actual checked-out repo, not a `tmp_path` fixture" across this
test suite is a module-level constant — e.g. `tests/unit/substrate/test_no_forbidden_imports.py`:
`REPO_ROOT = Path(__file__).resolve().parents[3]`. For a file at `tests/unit/memory/test_t031_link.py`
(three path segments below the repo root, the same depth as that file), `parents[3]` is exactly
right — no fixture needed, no placeholder math, no `__import__(...)` indirection.

This test only proves the substrate-layer link (Task 2's `Justification` parsing, Task 3's
`NonconformanceRecord` loading). The coherence-layer claim — that `coherence.trace.gaps.find_gaps`
no longer reports `task_no_sr` for T-031 now that its only justification is `corrects`, not
`satisfies` — is asserted by Task 7 instead of here: `coherence.trace.model.extract_edges` does
not yet read `justification:` at this point in the plan (Task 7 adds that), so asserting it here
would fail until Task 7 also lands, not at this task's own checkpoint. Task 7 owns both the fix
and its real-repo proof (this closes the review's finding that Task 4 alone verifies only the
substrate layer — the coherence layer is verified too, just by the task that actually implements
it).

```python
"""T-031 traces to gh-issue:1 via NC-0001 (spec section 5) -- exercised against
the real repo tree, not a tmp_path fixture, because the point is to prove the
actual on-disk task and nonconformance record link, not a synthetic one."""
from __future__ import annotations

from pathlib import Path

import pytest

from factory.memory.nonconformance import load_nonconformances
from substrate.ledger.tasks import Justification, load_tasks

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[3]


def test_t031_corrects_nc_0001():
    task = next(t for t in load_tasks(REPO_ROOT / "tasks") if t.id == "T-031")
    assert task.justification == [Justification("corrects", "NC-0001")]

    nc = load_nonconformances(REPO_ROOT)["NC-0001"]
    assert nc.corrected_by == "T-031"
    assert nc.external_ref == "gh-issue:1"
```

Place this as `tests/unit/memory/test_t031_link.py`.

Run: `rtk proxy uv run python -m pytest tests/unit/memory/test_t031_link.py -v`
Expected: PASS.

- [ ] **Step 4: Commit.**

```bash
git add tasks/T-031-catchup-tab-orientation-metadata.md docs/nonconformances/NC-0001-catchup-tab-orientation.md \
        tests/unit/memory/test_t031_link.py
git commit -m "fix(traceability): link T-031 to gh-issue:1 via NC-0001"
```

### Task 5: Mandatory context-manifest checks and task-id identity

Implements spec §1 gap 3: the schema currently permits an empty `checks` array (zero proof
obligations, still schema-valid), and nothing cross-checks a manifest's declared `task_id`
against the task it was actually gathered for.

**Blast radius, verified against the real repo.** `validate_manifest_document` returns EARLY on
any schema error — before context-ref/identity/coverage/check errors ever run (confirmed by
reading `src/substrate/validators/manifest.py`). `minItems: 1` therefore breaks every existing
test whose manifest fixture has empty or default `checks`, not just the one test an earlier draft
of this task named. Verified by reading each file in full:

- `tests/unit/test_manifest_validator.py`: `test_valid_manifest_no_checks`,
  `test_missing_source_file_reports_error`, `test_anchor_is_stripped_before_existence_check`,
  `test_legacy_proven_field_is_stripped_not_rejected`,
  `test_evidence_style_checks_are_dropped_not_rejected`, `test_coverage_floor_requires_modify_deliverable`.
- `tests/unit/substrate/test_validator_inversion.py`:
  `test_validate_manifest_document_valid_manifest_no_checks_is_clean` **and**
  `test_pure_document_matches_legacy_validate_manifest_for_the_coverage_floor` — the second one is
  not named by the review that flagged this task; it was found here by reading the whole file, and
  it breaks for the exact same reason (default empty `checks`).
- Seven orchestrator/integration test files, verified by grepping each for `"checks": []`:
  `tests/unit/orchestrator/test_runner.py`, `test_run_next.py`,
  `test_human_review_gate_in_runner.py`, `test_grill_in_runner.py`,
  `test_context_limit_continuation.py`, `test_runner_e2e.py`,
  `tests/integration/orchestrator/test_resume_run.py`. **Verified NOT affected**, despite being
  named by the review that flagged this task:
  `tests/unit/orchestrator/test_context_packet.py` — its manifest fixture is never passed through
  `validate_manifest`/`validate_manifest_document` at all (confirmed by reading
  `src/factory/orchestrator/context_packet.py` and `src/factory/orchestrator/prompts.py`: neither
  imports schema validation), and `tests/unit/orchestrator/test_runner_e2e.py`'s own
  `test_context_reject_short_circuits` — its manifest sets `"reject": {"reason": "x"}`, and
  `factory.orchestrator.nodes.run_context_gatherer` returns on the `reject` branch *before* ever
  calling `validate_manifest` (confirmed by reading `src/factory/orchestrator/nodes.py` — the
  `if manifest.get("reject"):` short-circuit precedes the `validate_manifest(...)` call), so schema
  validation never runs against it either.
- **The real, evaluable check shape** every fixture below reuses is `{"name": ..., "kind":
  "files_exist", "args": {"paths": [...]}}` — verified against `src/factory/evidence/connectors.py`
  (`FilesExist.kind = "files_exist"`, `args_schema` requires `paths: list[str]`) and against how
  `test_connector_check_evaluated_pass`/`test_connector_check_evaluated_fail` in
  `tests/unit/test_manifest_validator.py` already call it. An earlier draft of this task's Step 2
  used `"kind": "file_exists"` / `"args": {"path": ...}` (singular) — that kind does not exist in
  `DEFAULT_REGISTRY`; fixed below.

**Files:**
- Modify: `src/substrate/schemas/context_manifest.schema.json`
- Modify: `src/substrate/validators/manifest.py`
- Modify: `src/factory/validation/manifest_validator.py`
- Test: `tests/unit/test_manifest_validator.py`
- Test: `tests/unit/substrate/test_validator_inversion.py`
- Test: `tests/unit/orchestrator/test_runner.py`, `test_run_next.py`,
  `test_human_review_gate_in_runner.py`, `test_grill_in_runner.py`,
  `test_context_limit_continuation.py`, `test_runner_e2e.py`
- Test: `tests/integration/orchestrator/test_resume_run.py`

**Interfaces:**
- Produces: `substrate.validators.manifest.identity_errors(manifest: dict, task_id: str | None) ->
  list[str]`; `validate_manifest_document(manifest, repo_root, check_errors, coverage_errors,
  *, task_id: str | None = None) -> list[str]` (new keyword-only param, default `None` — every
  existing caller that doesn't pass a task keeps working, since `identity_errors` is a no-op
  when `task_id is None`).
- Consumes (unchanged): `substrate.validators.schema.{SCHEMA_DIR, validate}`.

- [ ] **Step 1: Add `"minItems": 1` to the schema.**

In `src/substrate/schemas/context_manifest.schema.json`, change:

```json
"checks": {
  "type": "array",
  "items": { ... }
}
```

to:

```json
"checks": {
  "type": "array",
  "minItems": 1,
  "items": { ... }
}
```

- [ ] **Step 2: Update the existing test that now contradicts the new contract.**

`tests/unit/test_manifest_validator.py::test_valid_manifest_no_checks` currently asserts that a
manifest with `checks: []` validates cleanly — that assertion is now wrong. Rename and replace it,
and add a companion proving a real, evaluable check passes cleanly:

```python
def test_empty_checks_now_rejected(tmp_path):
    # A context-gatherer that emits zero proof obligations must fail schema
    # validation, not pass silently (spec §1 gap 3).
    errors = validate_manifest(_manifest(tmp_path), tmp_path)  # default checks=[]
    assert any("checks" in e for e in errors)


def test_valid_manifest_with_one_check(tmp_path):
    (tmp_path / "spec.md").write_text("x", encoding="utf-8")
    checks = [{"name": "n", "kind": "files_exist", "args": {"paths": ["spec.md"]}}]
    errors = validate_manifest(_manifest(tmp_path, checks=checks), tmp_path)
    assert errors == []
```

`files_exist` (not `file_exists`) with `args: {"paths": [...]}` (a list, not `path` singular) is
the real connector kind registered in `DEFAULT_REGISTRY` (`src/factory/evidence/connectors.py`),
already used correctly by this same file's `test_connector_check_evaluated_pass`; every fixture
fix in the remaining steps of this task reuses this exact check shape.

- [ ] **Step 2a: Fix every other test in this file whose fixture now hits the new schema error.**

Each of these currently builds a manifest with empty/default `checks` and asserts on
context-ref/coverage behavior that never runs once schema fails first. Give each one real check
against a file the fixture already creates, so it keeps testing what it was testing instead of a
schema error:

```python
def test_missing_source_file_reports_error(tmp_path):
    m = _manifest(
        tmp_path,
        checks=[{"name": "c", "kind": "files_exist", "args": {"paths": ["tasks/T-001.md"]}}],
        source_files=["src/does_not_exist.py"],
    )
    errors = validate_manifest(m, tmp_path)
    assert any("does_not_exist" in e for e in errors)


def test_anchor_is_stripped_before_existence_check(tmp_path):
    (tmp_path / "spec.md").write_text("x", encoding="utf-8")
    m = _manifest(
        tmp_path,
        checks=[{"name": "c", "kind": "files_exist", "args": {"paths": ["spec.md"]}}],
        spec=["spec.md#section"],
    )
    assert validate_manifest(m, tmp_path) == []


def test_legacy_proven_field_is_stripped_not_rejected(tmp_path):
    m = _manifest(
        tmp_path,
        checks=[{"name": "c", "kind": "files_exist", "args": {"paths": ["tasks/T-001.md"]}}],
    )
    m["coherence"]["proven"] = True
    assert validate_manifest(m, tmp_path) == []


def test_evidence_style_checks_are_dropped_but_the_resulting_emptiness_now_fails_schema(tmp_path):
    # Regression pedigree unchanged: deepseek-v4-flash emitted checks like
    # {"name": "x", "evidence": "recorder.py exists", "pass": false} with no
    # kind/args -- normalize_manifest still strips them (no machine-verifiable
    # claim survives). What changes here is what happens AFTER stripping: a
    # manifest whose checks are stripped to [] is exactly "zero proof
    # obligations, still schema-valid" -- the bug spec §1 gap 3 targets, in a
    # different disguise -- so minItems: 1 now catches it as a schema error
    # instead of a silent pass. This is the new, correct default-deny stance,
    # not a regression of the original strip-not-reject fix: the STRIPPING
    # behavior (hollow checks never survive into the manifest) is unchanged
    # and still asserted below; only the final validity verdict changed.
    m = _manifest(
        tmp_path,
        checks=[
            {"name": "c1", "evidence": "src/sim/recorder.py exists", "pass": False},
            {"name": "c2", "evidence": "test file exists", "pass": True},
        ],
    )
    errors = validate_manifest(m, tmp_path)
    assert any("checks" in e for e in errors)
    assert m["coherence"]["checks"] == []


def test_coverage_floor_requires_modify_deliverable(tmp_path):
    from factory.orchestrator.ledger import Task
    from pathlib import Path
    task = Task(id="T-001", title="t", status="todo", dod=["done"],
                body="- Modify: `src/b.py`", path=Path("x"))
    # Manifest gathered nothing but a real, passing, unrelated check; the
    # Modify: deliverable is still uncovered even though every declared check
    # passes -> still an error (honest-but-hollow).
    m = _manifest(
        tmp_path,
        checks=[{"name": "c", "kind": "files_exist", "args": {"paths": ["tasks/T-001.md"]}}],
    )
    errors = validate_manifest(m, tmp_path, task=task)
    assert any("src/b.py" in e and "not gathered" in e for e in errors)
```

(`_manifest`'s own setup already writes `tasks/T-001.md`, so every fixture above reuses that real,
already-existing path for its check rather than inventing a new file.)

- [ ] **Step 2b: Fix `tests/unit/substrate/test_validator_inversion.py`.**

Two tests build a manifest with default empty `checks` and pass it straight to
`validate_manifest_document`:

```python
def test_validate_manifest_document_valid_manifest_no_checks_is_clean(tmp_path):
    manifest = _manifest(
        tmp_path,
        checks=[{"name": "c", "kind": "files_exist", "args": {"paths": ["tasks/T-001.md"]}}],
    )
    assert validate_manifest_document(manifest, tmp_path, _no_errors, _no_errors) == []
```

(Renaming this one is optional — `_no_checks_is_clean` no longer describes it exactly, but leaving
the name as-is and fixing only the body is also fine here since the surrounding suite doesn't
cross-reference this name elsewhere; either is acceptable.)

```python
def test_pure_document_matches_legacy_validate_manifest_for_the_coverage_floor(tmp_path):
    from factory.evidence.coverage import coverage_errors as compute_coverage_errors
    from factory.orchestrator.ledger import Task
    from factory.validation.manifest_validator import validate_manifest as legacy_validate_manifest

    task = Task(
        id="T-001", title="t", status="todo", dod=["done"],
        body="- Modify: `src/b.py`", path=Path("x"),
    )
    manifest = _manifest(
        tmp_path,
        checks=[{"name": "c", "kind": "files_exist", "args": {"paths": ["tasks/T-001.md"]}}],
    )

    def _coverage_errors(normalized: dict) -> list[str]:
        return compute_coverage_errors(task.body, normalized.get("context", {}), tmp_path)

    pure_errors = validate_manifest_document(
        copy.deepcopy(manifest), tmp_path, _no_errors, _coverage_errors
    )
    legacy_errors = legacy_validate_manifest(copy.deepcopy(manifest), tmp_path, task=task)

    assert pure_errors == legacy_errors
    assert any("src/b.py" in e and "not gathered" in e for e in pure_errors)
```

- [ ] **Step 2c: Fix the orchestrator stub-agent manifest fixtures.**

Each file below scripts a `CONTEXT_GATHERER` stub whose manifest flows through
`run_context_gatherer` → `validate_manifest`. Every one already creates a real file its
`source_files`/`context.task` names — reuse that path for a real `files_exist` check. Add
`"checks": [{"name": "c", "kind": "files_exist", "args": {"paths": [<real path>]}}]` in place of
`"checks": []` in each of these functions:

- `tests/unit/orchestrator/test_runner.py::_manifest()` — `["src/x.py"]` (created by `_repo`).
- `tests/unit/orchestrator/test_run_next.py::_scripts()` and
  `test_review_kb_entries_selected_from_actual_changed_files_not_manifest`'s inline `manifest`
  — both `["src/x.py"]` (created by `_repo`).
- `tests/unit/orchestrator/test_human_review_gate_in_runner.py::_scripts()`,
  `_already_done_scripts()`, and `_base_manifest()` — all three, `["src/x.py"]` (created by
  `_repo`).
- `tests/unit/orchestrator/test_grill_in_runner.py::_scripts()` — `["src/x.py"]` (created by
  `_repo`).
- `tests/unit/orchestrator/test_context_limit_continuation.py::test_context_limit_gets_fresh_call_for_context_gatherer`'s
  inline manifest dict — `["task.md"]` (the test writes `(tmp_path / "task.md")` itself, two lines
  above). Its sibling test, `test_context_limit_gets_fresh_call_without_spending_dev_retry`, calls
  `run_dev` directly with a manifest that is never schema-validated (`run_dev` never calls
  `validate_manifest`) — verified unaffected, left as-is.
- `tests/unit/orchestrator/test_runner_e2e.py::_manifest()` — `["src/x.py"]` (created by `_repo`).
  Its `test_context_reject_short_circuits` builds its own inline manifest with `"reject": {...}"` —
  verified unaffected (reject short-circuits before `validate_manifest` runs; see this task's
  intro) and left as-is.

Example (`test_runner.py`, same shape in every file above):

```python
def _manifest():
    return {
        "task_id": "T-001", "generated_by": "context-gatherer",
        "generated_at": "2026-07-16T14:32:10Z",
        "coherence": {"checks": [{"name": "c", "kind": "files_exist", "args": {"paths": ["src/x.py"]}}]},
        "context": {"task": "tasks/T-001.md", "source_files": ["src/x.py"], "skills": []},
        "reject": None,
    }
```

- [ ] **Step 2d: Fix the integration test's fake-`pi` payload.**

`tests/integration/orchestrator/test_resume_run.py` embeds the manifest JSON as a literal inside a
generated Python script (the fake `pi` CLI). `_write_task_repo` already writes `tasks/T-001.md`,
which `context.task` already names — add the same real check against it:

```python
"        _emit({'task_id': _task_id(prompt), 'generated_by': 'context-gatherer', "
"'generated_at': '2026-08-07T12:00:00Z', "
"'coherence': {'checks': [{'name': 'c', 'kind': 'files_exist', 'args': {'paths': ['tasks/T-001.md']}}]}, "
"'context': {'task': 'tasks/T-001.md', 'source_files': [], 'skills': []}, 'reject': None})\n"
```

- [ ] **Step 3: Write the failing identity test.**

```python
def test_manifest_task_id_mismatch_rejected(tmp_path):
    from substrate.ledger.tasks import Task
    m = _manifest(tmp_path, checks=[{"name": "n", "kind": "k", "args": {}}])
    m["task_id"] = "T-999"  # gathered for a different task than the one running
    task = Task(id="T-001", title="t", status="todo", dod=["d"], body="", path=tmp_path / "tasks" / "T-001.md")
    errors = validate_manifest(m, tmp_path, task=task)
    assert any("task_id" in e for e in errors)


def test_manifest_task_id_match_accepted(tmp_path):
    from substrate.ledger.tasks import Task
    m = _manifest(tmp_path, checks=[{"name": "n", "kind": "k", "args": {}}])
    task = Task(id="T-001", title="t", status="todo", dod=["d"], body="", path=tmp_path / "tasks" / "T-001.md")
    errors = validate_manifest(m, tmp_path, task=task)
    assert not any("task_id" in e for e in errors)
```

- [ ] **Step 4: Run the tests to verify the new ones fail.**

Run: `rtk proxy uv run python -m pytest tests/unit/test_manifest_validator.py -v`
Expected: `test_manifest_task_id_mismatch_rejected` FAILS (no identity check exists yet);
`test_empty_checks_now_rejected` FAILS too until Step 1's schema edit lands (run Step 1 first if
executing steps strictly in order — both land together in this task).

- [ ] **Step 5: Implement `identity_errors` and thread `task_id` through.**

In `src/substrate/validators/manifest.py`, add:

```python
def identity_errors(manifest: dict, task_id: str | None) -> list[str]:
    """The manifest's declared task_id must match the task it was gathered for.

    `task_id=None` means the caller has no task context (e.g. ad-hoc manifest
    validation outside a dispatched task) -- nothing to cross-check against.
    """
    if task_id is None:
        return []
    declared = manifest.get("task_id")
    if declared != task_id:
        return [f"task_id: manifest declares {declared!r}, but this is task {task_id!r}"]
    return []
```

Thread it through `validate_manifest_document`:

```python
def validate_manifest_document(
    manifest: dict,
    repo_root: Path,
    check_errors: Callable[[dict], list[str]],
    coverage_errors: Callable[[dict], list[str]],
    *,
    task_id: str | None = None,
) -> list[str]:
    manifest = normalize_manifest(manifest)
    errors = validate(manifest, _SCHEMA)
    if errors:
        return errors

    out: list[str] = list(context_ref_errors(manifest, repo_root))
    out += identity_errors(manifest, task_id)
    out += coverage_errors(manifest)
    out += check_errors(manifest)
    return out
```

- [ ] **Step 6: Wire the caller.**

In `src/factory/validation/manifest_validator.py::validate_manifest`, change the final line to:

```python
    return validate_manifest_document(
        manifest, repo_root, _check_errors, _coverage_errors,
        task_id=task.id if task is not None else None,
    )
```

- [ ] **Step 7: Run the full manifest-validator test file to verify everything passes.**

Run: `rtk proxy uv run python -m pytest tests/unit/test_manifest_validator.py tests/unit/substrate/test_validator_inversion.py -v`
Expected: PASS, all tests in both files.

- [ ] **Step 8: Run the wider suite for callers of `validate_manifest_document` outside this file.**

Run: `rtk proxy uv run python -m pytest tests/unit -k "manifest or orchestrator" -q` and
`rtk proxy uv run python -m pytest tests/integration/orchestrator/test_resume_run.py -v`
Expected: PASS. Any caller not yet updated for the new keyword-only `task_id` param is unaffected
(it defaults to `None`, preserving old behaviour for that caller); every fixture fixed in Steps
2a–2d above now supplies a real, evaluable check instead of `[]`.

- [ ] **Step 9: Commit.**

```bash
git add src/substrate/schemas/context_manifest.schema.json src/substrate/validators/manifest.py \
        src/factory/validation/manifest_validator.py tests/unit/test_manifest_validator.py \
        tests/unit/substrate/test_validator_inversion.py \
        tests/unit/orchestrator/test_runner.py tests/unit/orchestrator/test_run_next.py \
        tests/unit/orchestrator/test_human_review_gate_in_runner.py \
        tests/unit/orchestrator/test_grill_in_runner.py \
        tests/unit/orchestrator/test_context_limit_continuation.py \
        tests/unit/orchestrator/test_runner_e2e.py \
        tests/integration/orchestrator/test_resume_run.py
git commit -m "fix(manifest): mandatory checks and task_id identity cross-check"
```

### Task 6: Profile vocabulary, `Obligation` contract, and the `ci_verification` obligation

Ships the generic policy compiler spec §4 describes. Per D16, obligation compilation itself is
scoped to the `prototype` **and** `high_assurance` presets in this task — both, matching D16 and
`COMPILED_PRESETS = ("prototype", "high_assurance")` below exactly (an earlier draft of this
task's header said "`prototype` only," contradicting both its own code three lines later and D16
itself; corrected here). Increment 6B adds the remaining three obligation kinds
(`verification_result`, `human_review` at full strength, and any others that increment specifies)
— it does not add a preset. `ci_verification` is compiled here, not deferred to 6B, because
Increment 2C's CI workflow needs it immediately (spec §7: "bootstrapped `prototype` in
Increment 2B"), and per spec §13's third divergence, `ci_verification` is `blocking` under every
default preset from day one, not phased in as advisory-then-promoted.

**Files:**
- Create: `src/substrate/policy/__init__.py`
- Create: `src/substrate/policy/vocabulary.py`
- Create: `src/substrate/policy/obligation.py`
- Create: `src/substrate/schemas/profile.schema.json` — validates a resolved `profile:` value
  against `KNOWN_PRESETS` (spec §13)
- Create: `src/coherence/policy/__init__.py`
- Create: `src/coherence/policy/compiler.py`
- Modify: `src/substrate/schemas/feat.schema.json` — `profile` added to `properties` (spec §13)
- Test: `tests/unit/substrate/policy/test_vocabulary.py`
- Test: `tests/unit/substrate/policy/test_obligation.py`
- Test: `tests/unit/coherence/policy/test_compiler.py`

**Interfaces:**
- Produces (substrate, pure): `substrate.policy.vocabulary.{DIMENSIONS, KNOWN_PRESETS,
  COMPILED_PRESETS, DEFAULT_PRESET, UncompiledPresetError, InvalidProfileError,
  ProfileConflictError, project_default_profile(root) -> str, path_override_profile(root,
  rel_path) -> str | None, artifact_profile_override(path) -> str | None}`. All three resolution
  functions now validate their resolved string against `KNOWN_PRESETS` (via
  `profile.schema.json`) before returning it, raising `InvalidProfileError` for a name outside
  the whole known vocabulary — distinct from `UncompiledPresetError`, which is `coherence`-layer
  and means a REAL, known preset (e.g. `exploration`) that just isn't compiled yet (spec §13).
- Produces (substrate, pure): `substrate.policy.obligation.{Requiredness, Obligation}` — the
  compiled contract `{id, scope_ref, kind, requiredness, reason, source_policy, state,
  resolve_cmd}`. `resolve_cmd` is a structured `tuple[str, ...] | None`: each tuple item is one
  fully substituted, runnable command; tuple order and duplicates are meaningful and must be
  preserved end-to-end. It is not a semicolon-delimited string.
- Produces (coherence, trace-aware): `coherence.policy.compiler.{resolve_profile(root, scope_ref
  = "project", *, nodes=None, edges=None) -> str, compile_obligations(root, scope_ref = "project",
  *, nodes=None, edges=None) -> list[Obligation], UnsupportedScopeError}`. `scope_ref="project"`
  is the only project-wide resolution path and may inherit `project_default_profile`; every other
  scope must identify an existing, supported trace artifact and fails closed with
  `UnsupportedScopeError` when its kind, syntax, or artifact identity is unknown. An unknown
  artifact must never masquerade as a project-scope obligation through profile fallback. The
  `nodes=`/`edges=` keyword-only passthrough
  mirrors `coherence.navigate.health`'s own functions (`bundle_readiness` et al. in
  `src/coherence/navigate/health.py`: `nodes: list[trace_model.Node] | None = None, edges: ... =
  None`, loading only when not supplied) — required by Increment 5's health dimension 11
  (`human_review`), which already calls `compile_obligations(root, f"sr:{n.id}", nodes=nodes,
  edges=edges)` in a per-SR loop and must not reload the trace graph once per SR (verified against
  `docs/superpowers/plans/2026-08-20-coherence-increment-5-status-focus-dispatcher.md`, which
  already writes exactly this call). Consumed directly by Increment 2C (CI) and Increment 3B
  (obligation-aware views).
- Consumes: `coherence.trace.model.{load_nodes, extract_edges}` (already shipped, Increment 2),
  `substrate.config.load_gate_declarations` (already shipped), `factory.config.load_config`
  (already shipped — reused by `_ci_verification_obligation`, see Step 10), and
  `factory.orchestrator.backends`'s existing `_target_python(repo_root) -> str` /
  `_quote_for_shell(path: str) -> str` (already shipped; verified exact names/signatures by
  reading `src/factory/orchestrator/backends.py`).

- [ ] **Step 1: Write the failing vocabulary tests.**

```python
import pytest
from pathlib import Path

from substrate.policy.vocabulary import (
    DEFAULT_PRESET,
    ProfileConflictError,
    artifact_profile_override,
    path_override_profile,
    project_default_profile,
)

pytestmark = pytest.mark.unit


def test_project_default_absent_config(tmp_path):
    assert project_default_profile(tmp_path) == DEFAULT_PRESET == "prototype"


def test_project_default_from_config(tmp_path):
    (tmp_path / ".factory").mkdir()
    (tmp_path / ".factory" / "factory.yaml").write_text("profile: high_assurance\n", encoding="utf-8")
    assert project_default_profile(tmp_path) == "high_assurance"


def test_artifact_override_from_frontmatter(tmp_path):
    (tmp_path / "requirements").mkdir()
    p = tmp_path / "requirements" / "SR-001.md"
    p.write_text("---\nid: SR-001\ntitle: t\nstatement: s\ndomain: d\nprofile: high_assurance\n---\n", encoding="utf-8")
    assert artifact_profile_override(p) == "high_assurance"


def test_path_override_most_specific_wins(tmp_path):
    (tmp_path / ".factory").mkdir()
    (tmp_path / ".factory" / "profile.yaml").write_text(
        "overrides:\n"
        "- path: 'src/*'\n  profile: prototype\n"
        "- path: 'src/critical/*'\n  profile: high_assurance\n",
        encoding="utf-8",
    )
    assert path_override_profile(tmp_path, "src/critical/x.py") == "high_assurance"
    assert path_override_profile(tmp_path, "src/other/x.py") == "prototype"


def test_path_override_equal_specificity_conflict_raises(tmp_path):
    (tmp_path / ".factory").mkdir()
    (tmp_path / ".factory" / "profile.yaml").write_text(
        "overrides:\n"
        "- path: 'src/a/*'\n  profile: prototype\n"
        "- path: 'src/b/*'\n  profile: high_assurance\n",
        encoding="utf-8",
    )
    # Both globs have equal specificity (2 segments) and would match a
    # differently-named file only if both patterns matched the same path --
    # construct that case directly:
    (tmp_path / ".factory" / "profile.yaml").write_text(
        "overrides:\n"
        "- path: 'src/*'\n  profile: prototype\n"
        "- path: '*/shared.py'\n  profile: high_assurance\n",
        encoding="utf-8",
    )
    with pytest.raises(ProfileConflictError):
        path_override_profile(tmp_path, "src/shared.py")


def test_unknown_preset_name_raises_invalid_profile_error(tmp_path):
    # "nonsense" is not in KNOWN_PRESETS at all -- a configuration error, never
    # a silent fallback (spec §13, guide §9.3). Contrast UncompiledPresetError,
    # raised by coherence.policy.compiler for a REAL, known-but-uncompiled
    # preset like "exploration" -- that error lives in coherence, not here.
    (tmp_path / ".factory").mkdir()
    (tmp_path / ".factory" / "factory.yaml").write_text("profile: nonsense\n", encoding="utf-8")
    with pytest.raises(InvalidProfileError):
        project_default_profile(tmp_path)


def test_invalid_profile_error_is_not_an_uncompiled_preset_error():
    from substrate.policy.vocabulary import InvalidProfileError, UncompiledPresetError

    assert not issubclass(InvalidProfileError, UncompiledPresetError)
    assert not issubclass(UncompiledPresetError, InvalidProfileError)
```

(Add `InvalidProfileError` to the `from substrate.policy.vocabulary import (...)` block at the top
of the test file alongside the existing imports.)

- [ ] **Step 2: Run the tests to verify they fail.**

Run: `rtk proxy uv run python -m pytest tests/unit/substrate/policy/test_vocabulary.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'substrate.policy'`).

- [ ] **Step 2a: Write `profile.schema.json`.**

Validates a single resolved `profile:` value against the known preset vocabulary — applies
uniformly wherever a profile override can be declared (`.factory/factory.yaml`'s project-default
`profile:` key, `.factory/profile.yaml`'s per-path `overrides[].profile`, and an artifact's own
frontmatter `profile:` key), since each of the three resolution functions below validates just the
one string it resolved, not the whole surrounding document. The seven policy dimensions are not
represented as data in this task (`DIMENSIONS` is a name tuple only, not yet consumed anywhere) —
deferred to whichever later increment first needs per-dimension configuration; this schema
therefore validates only `profile`, not per-dimension fields.

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://factory.local/schemas/profile.schema.json",
  "title": "Resolved profile value",
  "type": "object",
  "required": ["profile"],
  "additionalProperties": false,
  "properties": {
    "profile": {
      "type": "string",
      "enum": ["exploration", "prototype", "product", "high_assurance"]
    }
  }
}
```

- [ ] **Step 3: Implement `substrate/policy/vocabulary.py`.**

```python
"""Profile vocabulary: seven policy dimensions, presets, and the three-level
override resolution the guide's precedence rule describes (artifact/requirement
> feature/bundle > path/component > project default). Pure and repo-root-only
-- this module never imports coherence.trace; feature/bundle-level resolution
that needs the trace graph lives in `coherence.policy.compiler`.
"""
from __future__ import annotations

import fnmatch
from pathlib import Path

import frontmatter
import yaml

from substrate.validators.schema import SCHEMA_DIR, validate

DIMENSIONS = (
    "maturity", "consequence", "reversibility", "volatility",
    "verification_cost", "exposure", "collaboration",
)

# Every preset name the schema accepts. Only COMPILED_PRESETS actually compile
# obligations (D16) -- exploration/product are declared but untested until a
# real use case needs them.
KNOWN_PRESETS = ("exploration", "prototype", "product", "high_assurance")
COMPILED_PRESETS = ("prototype", "high_assurance")

DEFAULT_PRESET = "prototype"

_CONFIG_REL = (".factory", "factory.yaml")
_PROFILE_OVERRIDES_REL = (".factory", "profile.yaml")
_PROFILE_SCHEMA = SCHEMA_DIR / "profile.schema.json"


class UncompiledPresetError(ValueError):
    """A profile names a real preset (in KNOWN_PRESETS) that is not yet compiled."""


class InvalidProfileError(ValueError):
    """A profile string is not even a known preset name (contrast
    UncompiledPresetError: a REAL, known-but-uncompiled preset like
    `exploration`). Raised here, in substrate, at resolution time -- a
    configuration error, never a silent fallback (spec §13, guide §9.3)."""


class ProfileConflictError(ValueError):
    """Two path/component overrides of equal specificity disagree (never silently ordered)."""


def _validate_profile_value(value: str, *, source: str) -> str:
    errors = validate({"profile": value}, _PROFILE_SCHEMA)
    if errors:
        raise InvalidProfileError(
            f"{source}: {value!r} is not a known preset (have {KNOWN_PRESETS}): {'; '.join(errors)}"
        )
    return value


def project_default_profile(root: Path) -> str:
    path = root.joinpath(*_CONFIG_REL)
    if not path.exists():
        return DEFAULT_PRESET
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    value = str(data.get("profile") or DEFAULT_PRESET)
    return _validate_profile_value(value, source=f"{path}: profile")


def _path_overrides(root: Path) -> list[tuple[str, str]]:
    path = root.joinpath(*_PROFILE_OVERRIDES_REL)
    if not path.exists():
        return []
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return [
        (
            str(entry["path"]),
            _validate_profile_value(
                str(entry["profile"]), source=f"{path}: overrides[{i}].profile"
            ),
        )
        for i, entry in enumerate(data.get("overrides") or [])
    ]


def _specificity(glob: str) -> int:
    return len([p for p in glob.split("/") if p])


def path_override_profile(root: Path, rel_path: str) -> str | None:
    """Most-specific matching path/component override, or None.

    Ties in specificity between overrides naming DIFFERENT profiles raise
    ProfileConflictError rather than picking one arbitrarily.
    """
    matches = [(g, p) for g, p in _path_overrides(root) if fnmatch.fnmatch(rel_path, g)]
    if not matches:
        return None
    best_spec = max(_specificity(g) for g, _ in matches)
    best = [(g, p) for g, p in matches if _specificity(g) == best_spec]
    profiles = {p for _, p in best}
    if len(profiles) > 1:
        raise ProfileConflictError(
            f"{rel_path}: equal-specificity path overrides disagree: {sorted(profiles)}"
        )
    return best[0][1]


def artifact_profile_override(path: Path) -> str | None:
    try:
        post = frontmatter.load(str(path))
    except (OSError, ValueError):
        return None
    value = post.metadata.get("profile")
    if not value:
        return None
    return _validate_profile_value(str(value), source=f"{path}: profile")
```

- [ ] **Step 3a: Add `profile` to `feat.schema.json` (spec §13).**

`src/substrate/schemas/feat.schema.json` currently has `additionalProperties: false` and a
`required: ["id", "title", "requirements"]` list — verified by reading the file. Add `profile` to
`properties` only; do not touch `required` (a feature with no `profile` key still validates —
`profile` is an optional override, defaulting through project/path resolution when absent):

```diff
   "properties": {
     "id": {"type": "string", "pattern": "^FEAT-[A-Z0-9-]+$"},
     "title": {"type": "string", "minLength": 1},
+    "profile": {
+      "type": "string",
+      "enum": ["exploration", "prototype", "product", "high_assurance"]
+    },
     "requirements": {
       "type": "array",
       "minItems": 1,
       "items": {"type": "string", "pattern": "^SR-[A-Z0-9-]+$"}
     }
   }
```

This is what unblocks spec §8 step 3 / guide §11 step 3 (the dogfood exercise applies
`profile: high_assurance` to one seeded feature) — before this change, that frontmatter fails
schema validation outright since `additionalProperties: false` rejects any unlisted key.

- [ ] **Step 4: Run the vocabulary tests to verify they pass.**

Run: `rtk proxy uv run python -m pytest tests/unit/substrate/policy/test_vocabulary.py -v`
Expected: PASS.

- [ ] **Step 5: Write the failing `Obligation` contract test.**

```python
import pytest
from substrate.policy.obligation import Obligation

pytestmark = pytest.mark.unit


def test_obligation_is_the_documented_contract():
    ob = Obligation(
        id="ob:ci_verification:project",
        scope_ref="project",
        kind="ci_verification",
        requiredness="blocking",
        reason="every default preset requires CI-verified gates",
        source_policy="prototype",
        state="open",
        resolve_cmd=("pytest -m unit",),
    )
    assert ob.requiredness in ("not_applicable", "advisory", "required", "blocking")
    assert ob.resolve_cmd == ("pytest -m unit",)
```

- [ ] **Step 6: Implement `substrate/policy/obligation.py`.**

```python
"""The compiled Obligation contract (spec §4). Status, health, inbox, navigator
and gates consume this shape; none reinterpret the profile independently.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Requiredness = Literal["not_applicable", "advisory", "required", "blocking"]


@dataclass(frozen=True)
class Obligation:
    id: str
    scope_ref: str
    kind: str
    requiredness: Requiredness
    reason: str
    source_policy: str
    state: str
    resolve_cmd: tuple[str, ...] | None = None
```

- [ ] **Step 7: Run the obligation test to verify it passes.**

Run: `rtk proxy uv run python -m pytest tests/unit/substrate/policy/test_obligation.py -v`
Expected: PASS.

- [ ] **Step 8: Write the failing compiler tests.**

```python
import pytest
from pathlib import Path

from coherence.policy.compiler import (
    UnsupportedScopeError,
    compile_obligations,
    resolve_profile,
)
from substrate.policy.vocabulary import UncompiledPresetError

pytestmark = pytest.mark.unit


def _seed_gates(root: Path) -> None:
    # {python} deliberately included: every real gate command in
    # .factory/factory.yaml uses it (verified against tests/integration/
    # orchestrator/test_resume_run.py's own fixture), and this is exactly
    # what proves _ci_verification_obligation reuses backends.py's real
    # substitution instead of joining raw step.cmd strings.
    (root / ".factory").mkdir(exist_ok=True)
    (root / ".factory" / "factory.yaml").write_text(
        "gates:\n"
        "  unit:\n"
        "  - { cmd: '{python} -m pytest -m unit -q' }\n"
        "  sim:\n"
        "  - { cmd: '{python} -m pytest -m sim -q' }\n"
        "  full:\n"
        "  - { cmd: '{python} -m pytest -m unit -q' }\n",
        encoding="utf-8",
    )


def test_resolve_profile_project_default(tmp_path):
    assert resolve_profile(tmp_path, "project") == "prototype"


def test_resolve_profile_project_scope_uses_project_default_explicitly(tmp_path):
    (tmp_path / ".factory").mkdir()
    (tmp_path / ".factory" / "factory.yaml").write_text(
        "profile: high_assurance\n", encoding="utf-8"
    )
    assert resolve_profile(tmp_path, "project") == "high_assurance"


def test_resolve_profile_unknown_artifact_scope_fails_closed(tmp_path):
    (tmp_path / ".factory").mkdir()
    (tmp_path / ".factory" / "factory.yaml").write_text(
        "profile: high_assurance\n", encoding="utf-8"
    )
    with pytest.raises(UnsupportedScopeError):
        resolve_profile(tmp_path, "sr:SR-404")


def test_resolve_profile_unsupported_artifact_scope_fails_closed(tmp_path):
    with pytest.raises(UnsupportedScopeError):
        resolve_profile(tmp_path, "file:src/not-a-trace-artifact.py")


def test_resolve_profile_rejects_uncompiled_preset(tmp_path):
    (tmp_path / ".factory").mkdir()
    (tmp_path / ".factory" / "factory.yaml").write_text("profile: exploration\n", encoding="utf-8")
    with pytest.raises(UncompiledPresetError):
        resolve_profile(tmp_path, "project")


def test_compile_obligations_ci_verification_substitutes_python_like_backends_does(tmp_path):
    _seed_gates(tmp_path)
    obligations = compile_obligations(tmp_path, "project")
    ci = next(o for o in obligations if o.kind == "ci_verification")
    assert ci.requiredness == "blocking"
    assert ci.source_policy == "prototype"
    # No literal "{python}" survives -- backends._target_python/_quote_for_shell
    # already ran, producing a real interpreter path/token in its place.
    assert all("{python}" not in command for command in (ci.resolve_cmd or ()))
    assert any("-m pytest -m unit -q" in command for command in (ci.resolve_cmd or ()))


def test_compile_obligations_preserves_configured_order_and_duplicates(tmp_path):
    _seed_gates(tmp_path)
    obligations = compile_obligations(tmp_path, "project")
    ci = next(o for o in obligations if o.kind == "ci_verification")

    assert ci.resolve_cmd is not None
    assert len(ci.resolve_cmd) == 3
    assert ci.resolve_cmd[0].endswith("-m pytest -m unit -q")
    assert ci.resolve_cmd[1].endswith("-m pytest -m sim -q")
    assert ci.resolve_cmd[2] == ci.resolve_cmd[0]


def test_compile_obligations_task_justification_for_task_scope(tmp_path):
    # task_justification lands here (not deferred to Increment 6B) because it
    # is a direct sibling of this same increment's typed-justification work
    # (Task 2) -- Increment 4's verification_result and Increment 6's
    # human_review obligation kinds are added by those increments' own plans,
    # since each is grounded in that increment's own deliverable.
    _seed_gates(tmp_path)
    (tmp_path / "tasks").mkdir()
    (tmp_path / "tasks" / "T-900.md").write_text(
        "---\nid: T-900\ntitle: t\nstatus: todo\ndod:\n- 'd'\n---\nbody\n", encoding="utf-8",
    )
    obligations = compile_obligations(tmp_path, "task:T-900")
    tj = next(o for o in obligations if o.kind == "task_justification")
    assert tj.requiredness == "advisory"  # prototype is the project default here
    assert tj.state == "open"  # T-900 has no justification at all


def test_resolve_profile_honors_preloaded_nodes_and_edges(tmp_path, monkeypatch):
    # Increment 5's per-SR health loop calls compile_obligations(root,
    # f"sr:{n.id}", nodes=nodes, edges=edges) inside a loop over every SR --
    # it must never trigger a fresh trace_model.load_nodes per call.
    from coherence.trace import model as trace_model

    (tmp_path / "docs" / "features").mkdir(parents=True)
    (tmp_path / "docs" / "features" / "FEAT-001.md").write_text(
        "---\nid: FEAT-001\ntitle: f\nprofile: high_assurance\nrequirements: [SR-001]\n---\n",
        encoding="utf-8",
    )
    (tmp_path / "requirements").mkdir()
    (tmp_path / "requirements" / "SR-001.md").write_text(
        "---\nid: SR-001\ntitle: t\nstatement: s\ndomain: d\n"
        "binding:\n  harness: h\n  experiment: e\n  metric: m\n  assert: '>= 0.9'\n---\n",
        encoding="utf-8",
    )
    nodes = trace_model.load_nodes(tmp_path)
    edges = trace_model.extract_edges(tmp_path, nodes)

    def _boom(*_a, **_k):
        raise AssertionError("must not reload nodes when already supplied")

    monkeypatch.setattr(trace_model, "load_nodes", _boom)
    assert resolve_profile(tmp_path, "sr:SR-001", nodes=nodes, edges=edges) == "high_assurance"
```

- [ ] **Step 9: Run the tests to verify they fail.**

Run: `rtk proxy uv run python -m pytest tests/unit/coherence/policy/test_compiler.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'coherence.policy'`).

- [ ] **Step 10: Implement `coherence/policy/compiler.py`.**

```python
"""Resolve an artifact's effective profile through the trace graph, and
compile the Obligation set for it. This lives in `coherence`, not `substrate`,
because it needs `coherence.trace.model` to find an SR's owning feature --
substrate stays pure and repo-root-only (mirrors how `coherence.navigate.health`
composes `coherence.trace` + substrate loaders without substrate depending
back on coherence).
"""
from __future__ import annotations

from pathlib import Path

from coherence.trace import model as trace_model
from substrate.policy.obligation import Obligation
from substrate.policy.vocabulary import (
    COMPILED_PRESETS,
    UncompiledPresetError,
    artifact_profile_override,
    path_override_profile,
    project_default_profile,
)


class UnsupportedScopeError(ValueError):
    """The scope is not `project` and is not a supported, existing trace artifact."""


def resolve_profile(
    root: Path,
    scope_ref: str = "project",
    *,
    nodes: list[trace_model.Node] | None = None,
    edges: list[trace_model.Edge] | None = None,
) -> str:
    """Effective preset for scope_ref. Precedence: artifact/requirement >
    feature/bundle > path/component > project default. Raises
    UncompiledPresetError if the resolved preset is not in COMPILED_PRESETS.

    `nodes=`/`edges=` mirror `coherence.navigate.health`'s own passthrough
    pattern: a caller that already loaded the trace graph (e.g. Increment 5's
    per-SR health loop) supplies them so this never reloads per call.
    """
    if scope_ref == "project":
        profile = project_default_profile(root)
    else:
        if nodes is None:
            nodes = trace_model.load_nodes(root)
        by_id = {n.id: n for n in nodes}
        scope_kind, separator, artifact_id = scope_ref.partition(":")
        if not separator or not scope_kind or not artifact_id:
            raise UnsupportedScopeError(
                f"{scope_ref!r}: only `project` or a kind:id artifact scope is supported"
            )
        # Trace nodes use both bare artifact IDs (for SR/task files) and
        # kind-prefixed IDs (for plan/spec files), so accept either exact form
        # but require the prefix to agree with the loaded node's kind.
        node = by_id.get(scope_ref) or by_id.get(artifact_id)
        if node is None or node.kind != scope_kind:
            raise UnsupportedScopeError(
                f"{scope_ref!r}: unknown or unsupported trace artifact scope"
            )
        profile = artifact_profile_override(node.path)
        if profile is None and node.kind == "sr":
            if edges is None:
                edges = trace_model.extract_edges(root, nodes)
            owning_feature = next(
                (by_id.get(e.src) for e in edges if e.kind == "contains" and e.dst == node.id),
                None,
            )
            if owning_feature is not None:
                profile = artifact_profile_override(owning_feature.path)
        if profile is None:
            rel = str(node.path.relative_to(root)).replace("\\", "/")
            profile = path_override_profile(root, rel)
        if profile is None:
            # This fallback is intentionally limited to a known artifact that
            # has no narrower override; `scope_ref="project"` is handled above.
            profile = project_default_profile(root)
    if profile not in COMPILED_PRESETS:
        raise UncompiledPresetError(
            f"{scope_ref}: profile {profile!r} is not yet compiled (compiled presets: {COMPILED_PRESETS})"
        )
    return profile


def compile_obligations(
    root: Path,
    scope_ref: str = "project",
    *,
    nodes: list[trace_model.Node] | None = None,
    edges: list[trace_model.Edge] | None = None,
) -> list[Obligation]:
    """Every default preset compiles a blocking ci_verification obligation (D18)
    -- CI (Increment 2C) reads this, never a hand-maintained step list. A
    `task:*` scope additionally compiles task_justification. Increment 4 and
    Increment 6 extend this SAME function with verification_result and
    human_review respectively (see those plans' addenda) -- each new kind is
    appended to the branch for the scope kind it applies to, never a parallel
    compiler. `nodes=`/`edges=` pass straight through to `resolve_profile`.
    """
    profile = resolve_profile(root, scope_ref, nodes=nodes, edges=edges)
    obligations = [_ci_verification_obligation(root, scope_ref, profile)]
    if scope_ref.startswith("task:"):
        obligations.append(_task_justification_obligation(root, scope_ref, profile))
    return obligations


def _ci_verification_obligation(root: Path, scope_ref: str, profile: str) -> Obligation:
    """Reuses `factory.config.load_config` (already parses `.factory/factory.yaml`
    into `FactoryConfig.gates`, layering-legal here since `coherence` may
    import `factory`) instead of re-parsing the YAML a second time, and reuses
    `factory.orchestrator.backends`'s own `{python}` substitution
    (`_target_python`/`_quote_for_shell`) instead of joining raw `step.cmd`
    strings -- spec §13's first corrected decision: one substitution rule,
    not two. Both are imported locally, matching this file's existing style
    for `factory`-layer imports (`_task_justification_obligation` below
    already imports `substrate.ledger.tasks` locally the same way), so every
    cross-layer dependency stays visible at its call site.
    """
    from factory.config import load_config
    from factory.orchestrator.backends import _quote_for_shell, _target_python

    gates = load_config(root).gates
    python = _quote_for_shell(_target_python(root))
    cmds = tuple(
        step.cmd.replace("{python}", python) for steps in gates.values() for step in steps
    )
    return Obligation(
        id=f"ob:ci_verification:{scope_ref}",
        scope_ref=scope_ref,
        kind="ci_verification",
        requiredness="blocking",
        reason=f"every default preset ({profile}) requires CI-verified gates (D18)",
        source_policy=profile,
        state="open",
        resolve_cmd=cmds or None,
    )


def _task_justification_obligation(root: Path, scope_ref: str, profile: str) -> Obligation:
    from substrate.ledger.tasks import get_task, load_tasks

    task_id = scope_ref.partition(":")[2]
    task = get_task(load_tasks(root / "tasks"), task_id)
    has_justification = bool(task and task.justification)
    requiredness = "blocking" if profile == "high_assurance" else "advisory"
    return Obligation(
        id=f"ob:task_justification:{scope_ref}",
        scope_ref=scope_ref,
        kind="task_justification",
        requiredness=requiredness,
        reason=(
            f"{profile} requires every task to name a typed justification "
            "(satisfies/corrects/mitigates/implements/maintains/explores)"
        ),
        source_policy=profile,
        state="satisfied" if has_justification else "open",
        resolve_cmd=("add a `justification:` entry to the task's frontmatter",),
    )
```

Redundancy note (review's minor finding): three call sites independently re-parse
`.factory/factory.yaml`'s YAML — `factory.config.load_config`, `project_default_profile`
(`substrate.policy.vocabulary`), and (before this fix) `_ci_verification_obligation`. Reusing
`factory.config.load_config` above collapses `_ci_verification_obligation`'s copy into the first,
leaving exactly one deliberately-accepted redundancy: `project_default_profile` still parses its
own copy, because it lives in `substrate`, which may never import `factory` — there is no clean
fix available without breaking that layering rule, so it is intentionally left as-is rather than
forced.

- [ ] **Step 11: Run the tests to verify they pass.**

Run: `rtk proxy uv run python -m pytest tests/unit/coherence/policy/test_compiler.py -v`
Expected: PASS.

- [ ] **Step 12: Run the full unit suite for regressions.**

Run: `rtk proxy uv run python -m pytest -m unit -q`
Expected: PASS.

- [ ] **Step 13: Commit.**

```bash
git add src/substrate/policy src/substrate/schemas/profile.schema.json \
        src/substrate/schemas/feat.schema.json src/coherence/policy \
        tests/unit/substrate/policy tests/unit/coherence/policy
git commit -m "feat(policy): profile vocabulary, Obligation contract, ci_verification+task_justification compiler"
```

---

### Task 7: Typed lifecycle edges and a corrected `task_no_sr` check

Implements the "typed lifecycle relationships" bullet of spec §4 and closes a gap the review round
found in Task 4: after Task 4 migrates T-031 to `justification: [{corrects: NC-0001}]`, the trace
graph as shipped through Task 6 still only turns a `satisfies:`-kind entry into an edge —
`coherence.trace.model.extract_edges` never reads `justification:` at all, and
`coherence.trace.gaps.find_gaps`'s `task_no_sr` check fires whenever a task has no `satisfies`-kind
edge specifically. T-031 would therefore be permanently `task_no_sr` to `coherence trace check` —
a blocking CI obligation from Increment 2C onward — even though it is now fully justified by a
`corrects` edge. This task is appended here, as a new final task, rather than renumbering Tasks
1–6: `docs/superpowers/plans/2026-08-20-coherence-increment-4-audit-measurement-observations.md`
and `docs/superpowers/plans/2026-08-22-coherence-increment-6b-thin-vertical-slice.md` both already
reference "Increment 2B Task 1" / "Increment 2B Task 4" by number (verified by grepping
`docs/superpowers/plans/*.md` for `"Increment 2B Task"`); renumbering would break both.

**Design decisions made here, concretely (per the review's ask — no vagueness, no deferred
"implementer decides"):**

1. **EdgeKind gains the typed lifecycle kinds from spec §4** (`derives`, `decomposes`, `refines`,
   `allocates`, `implements`, `verifies`, `validates`, `mitigates`, `evidences`, `corrects`,
   `impacts`, `supersedes` — `satisfies` already exists) **plus `maintains` and `explores`**, the
   two task-justification kinds (`substrate.ledger.tasks._JUSTIFICATION_KINDS`, already shipped by
   Task 2) that spec §4's lifecycle-relationship list does not itself name. This is a deliberate
   addition beyond the review's literal enumeration, not an oversight: Task 2 already accepts
   `justification: [{maintains: ...}]` / `{explores: ...}` as valid task frontmatter, and this
   task's whole point is a 1:1 mapping from justification kind to edge kind — leaving two of the
   six task-justification kinds without a matching `EdgeKind` would reintroduce, for `maintains`/
   `explores` specifically, the exact false-positive `task_no_sr` class this task exists to close.
2. **`extract_edges`'s task branch reads `justification:`**, falling back to the legacy raw
   `meta.get("satisfies")` reading (byte-identical to today) only when `justification:` is absent.
   `satisfies`-kind entries produce the existing `"satisfies"` `EdgeKind`; the other five kinds
   each produce their own same-named `EdgeKind`.
3. **"Rejected at load" means, concretely: the offending entry produces no edge, and the task node
   degrades with a new `Node.scope_error: str | None = None` field recording why** — mirroring
   this repo's existing degrade-not-crash discipline (`_id_node`/`_file_node` already degrade a
   malformed file to a filename-labelled node rather than raising). **Considered and explicitly
   NOT chosen: routing this through `coherence.trace.gaps` as a new `GapKind`.** Verified by
   reading `tests/unit/system/test_remediation.py`: `GapKind` is exhaustively checked
   (`test_every_gap_kind_has_an_entry` asserts every `GapKind` has a `REMEDIATION` entry), and
   `tests/unit/system/test_table_drift.py::test_remediation_mirror_matches_python` additionally
   requires that entry to be mirrored byte-for-byte into
   `pi-ext/factory-watch/src/system-vocabulary-data.ts`'s `REMEDIATION_DATA` constant. Adding a
   `GapKind` is not merely a data-model change here — it is a UI-surface commitment (a headline, a
   why-it-matters paragraph, a real command, and a TypeScript mirror kept in sync). That is
   disproportionate to what is, in practice, a rare edge case: a hand-authored `justification:`
   entry naming a kind outside the known six, on a file that `substrate.ledger.tasks.load_tasks`
   (the path any real orchestrator run actually uses) already hard-raises `InvalidJustificationError`
   on — the harsher, pre-existing guard already catches this before it reaches a real run.
   `Node.scope_error` gives `coherence trace`-layer callers (which parse frontmatter independently
   of `substrate.ledger.tasks` and would otherwise silently drop the entry) a queryable degrade
   signal without that disproportionate ripple. This is the "minimal" channel the review's own
   phrasing allowed for as an alternative to a new gap kind.
4. **`task_no_sr` fires only when a task has no justification-derived edge of ANY kind at all** —
   not specifically no `satisfies` edge. A task whose only justification is `corrects` (T-031) is
   fully justified and gets no `task_no_sr` gap. This is a justification-presence claim only, not
   a validity claim — it says nothing about `suspect`/`valid`/`waived` edge state (spec §13's
   strict no-auto-restore rule, Increment 6's concern, is untouched by this task).
5. **NC-* targets are deliberately excluded from `dangling_reference` checking for the new edge
   kinds.** `coherence.trace.model.load_nodes` does not glob `docs/nonconformances/NC-*.md` as
   trace nodes at all (verified — only `sr`/`br`/`feat`/`diag`/`metric`/`goal`/`task`/`plan`/`spec`
   are globbed). Adding `corrects`/`mitigates`/etc. to `gaps.py`'s `vcycle_kinds` dangling-check set
   would therefore flag every single `corrects: NC-0001`-style edge as dangling, since its target
   never resolves to a trace node — a false positive, not a real fix. Left out of scope on purpose;
   making NC-* records first-class trace nodes is a larger, separate change for whichever
   increment first needs it (candidate: Increment 5's nonconformance health dimension).

**Files:**
- Modify: `src/coherence/trace/model.py` — `Node.scope_error`, `EdgeKind` additions,
  `_justification_scope_error`, `_edges_from_justification`, `JUSTIFICATION_EDGE_KINDS`
- Modify: `src/coherence/trace/gaps.py` — `task_no_sr` check
- Modify: `tests/unit/trace/test_model_edges.py`, `tests/unit/trace/test_model_nodes.py`,
  `tests/unit/trace/test_gaps.py`
- Test: `tests/unit/memory/test_t031_link.py` (Task 4) — no change to the file itself; this task's
  own verification (Step 8 below) is the coherence-layer half of what Task 4 could not yet assert

**Interfaces:**
- Produces: `coherence.trace.model.JUSTIFICATION_EDGE_KINDS: frozenset[str]` — the six task
  justification kinds (`satisfies`, `corrects`, `mitigates`, `implements`, `maintains`,
  `explores`), each also a valid `EdgeKind`. Consumed by `coherence.trace.gaps.find_gaps`'s
  corrected `task_no_sr` check.
- Modifies: `coherence.trace.model.Node` gains `scope_error: str | None = None` (backward
  compatible — appended after `diagram_file`, so every existing positional `Node(...)` call in
  `tests/unit/trace/test_gaps.py` and elsewhere still works unchanged).
- Modifies: `coherence.trace.model.extract_edges`'s task branch and
  `coherence.trace.gaps.find_gaps`'s `task_no_sr` check (see decisions above).

- [ ] **Step 1: Write the failing `extract_edges` tests.**

Add to `tests/unit/trace/test_model_edges.py` (reusing its existing `_write`/`_edges` helpers):

```python
def test_task_justification_corrects_produces_a_typed_edge(tmp_path):
    _write(
        tmp_path / "tasks" / "T-031.md",
        "---\nid: T-031\ntitle: t\nstatus: done\ndod: []\n"
        "justification:\n- corrects: NC-0001\n---\n",
    )
    edges = _edges(tmp_path)
    assert Edge("T-031", "NC-0001", "corrects") in edges
    assert not any(e.kind == "satisfies" for e in edges if e.src == "T-031")


def test_task_justification_mixed_kinds_produce_their_own_edges(tmp_path):
    _write(
        tmp_path / "tasks" / "T-900.md",
        "---\nid: T-900\ntitle: t\nstatus: todo\ndod: []\n"
        "justification:\n- satisfies: SR-002\n- mitigates: FR-EXAMPLE\n---\n",
    )
    edges = _edges(tmp_path)
    assert Edge("T-900", "SR-002", "satisfies") in edges
    assert Edge("T-900", "FR-EXAMPLE", "mitigates") in edges
```

(`test_task_declares_source_plan_and_satisfies` and `test_scalar_satisfies_is_accepted_as_single_edge`,
already in this file, exercise the legacy `satisfies:`-only shape and must keep passing byte-
identically — no change needed to either, they are the regression guard for Decision 2 above.)

- [ ] **Step 2: Write the failing `Node.scope_error` tests.**

Add to `tests/unit/trace/test_model_nodes.py` (reusing its existing `_write` helper):

```python
def test_task_with_unsupported_justification_kind_degrades_to_a_scope_error(tmp_path):
    _write(
        tmp_path / "tasks" / "T-902.md",
        "---\nid: T-902\ntitle: t\nstatus: todo\ndod: []\n"
        "justification:\n- rejects: SR-001\n---\n",
    )
    nodes = {n.id: n for n in load_nodes(tmp_path)}
    assert nodes["T-902"].scope_error is not None
    assert "rejects" in nodes["T-902"].scope_error


def test_task_with_well_formed_justification_has_no_scope_error(tmp_path):
    _write(
        tmp_path / "tasks" / "T-903.md",
        "---\nid: T-903\ntitle: t\nstatus: todo\ndod: []\n"
        "justification:\n- corrects: NC-0001\n---\n",
    )
    nodes = {n.id: n for n in load_nodes(tmp_path)}
    assert nodes["T-903"].scope_error is None
```

- [ ] **Step 3: Write the failing `task_no_sr` tests.**

Add to `tests/unit/trace/test_gaps.py` (reusing its existing `_task`/`_kinds` helpers):

```python
def test_task_with_only_a_corrects_edge_is_not_task_no_sr():
    # T-031's real case: justified solely by corrects: NC-0001.
    nodes = [_task("T-031")]
    edges = [Edge("T-031", "NC-0001", "corrects")]
    assert "task_no_sr" not in _kinds(find_gaps(nodes, edges, {}), "T-031")


def test_task_with_a_mitigates_edge_is_not_task_no_sr():
    nodes = [_task("T-001")]
    edges = [Edge("T-001", "FR-EXAMPLE", "mitigates")]
    assert "task_no_sr" not in _kinds(find_gaps(nodes, edges, {}), "T-001")


def test_task_with_only_a_source_plan_edge_still_gets_task_no_sr():
    # Negative case: a source_plan edge is not a justification -- proves the
    # fix widened the check to justification kinds, not to "any edge at all".
    nodes = [_task("T-001"), _plan("p1.md")]
    edges = [Edge("T-001", "plan:p1.md", "source_plan")]
    assert "task_no_sr" in _kinds(find_gaps(nodes, edges, {}), "T-001")
```

- [ ] **Step 4: Run the tests to verify they fail.**

Run: `rtk proxy uv run python -m pytest tests/unit/trace/test_model_edges.py tests/unit/trace/test_model_nodes.py tests/unit/trace/test_gaps.py -v`
Expected: FAIL — `justification:` produces no edges yet, `Node` has no `scope_error` field yet,
and `task_no_sr` still only checks for `satisfies`-kind edges.

- [ ] **Step 5: Implement the `model.py` changes.**

Add `scope_error: str | None = None` to `Node` (after `diagram_file`, so every existing positional
construction — including `tests/unit/trace/test_gaps.py`'s `_task()`/`_sr()` helpers — is
unaffected):

```python
@dataclass(frozen=True)
class Node:
    id: str
    kind: NodeKind
    title: str
    path: Path
    exempt: bool = False
    deferred: str | None = None
    proposed: bool = False
    diagram_file: str | None = None
    scope_error: str | None = None
```

Extend `EdgeKind`:

```python
EdgeKind = Literal[
    "source_plan",
    "satisfies",
    "upstream",
    "spec_ref",
    "parent_of",
    "verified_by",
    "demonstrates",
    "evaluates",
    "contains",
    "illustrates",
    # Typed lifecycle relationships (spec §4): intent, design, assurance, change.
    "derives",
    "decomposes",
    "refines",
    "allocates",
    "implements",
    "verifies",
    "validates",
    "mitigates",
    "evidences",
    "corrects",
    "impacts",
    "supersedes",
    # Task-justification-only kinds (substrate.ledger.tasks._JUSTIFICATION_KINDS)
    # that spec §4's lifecycle list does not itself name -- added so every
    # legal justification entry maps to a real edge kind (see Task 7 Decision 1).
    "maintains",
    "explores",
]

_JUSTIFICATION_KINDS = (
    "satisfies", "corrects", "mitigates", "implements", "maintains", "explores",
)
JUSTIFICATION_EDGE_KINDS: frozenset[str] = frozenset(_JUSTIFICATION_KINDS)
```

Add the scope-error check and use it in `_id_node`:

```python
def _justification_scope_error(meta: dict) -> str | None:
    """Mirrors substrate.ledger.tasks._parse_justification's shape/kind checks,
    independently -- this module never imports substrate.ledger.tasks (stays a
    pure frontmatter reader; extract_edges/load_nodes must work without it).
    """
    raw = meta.get("justification")
    if raw is None:
        return None
    if not isinstance(raw, list):
        return "justification must be a list of single-key {kind: target_id} mappings"
    for entry in raw:
        if not isinstance(entry, dict) or len(entry) != 1:
            return f"each justification entry must be a single {{kind: target_id}} mapping, got {entry!r}"
        ((kind, _target_id),) = entry.items()
        if kind not in _JUSTIFICATION_KINDS:
            return f"unknown justification kind {kind!r} (have {_JUSTIFICATION_KINDS})"
    return None
```

In `_id_node`, compute `scope_error` for task nodes only and pass it through:

```python
def _id_node(path: Path, kind: NodeKind) -> Node:
    post = _load_post(path)
    if post is None or "id" not in post.metadata:
        return Node(id=path.name, kind=kind, title=path.name, path=path)
    exempt, deferred = _disposition(post.metadata)
    scope_error = _justification_scope_error(post.metadata) if kind == "task" else None
    return Node(
        id=str(post.metadata["id"]),
        kind=kind,
        title=str(post.metadata.get("title", path.name)),
        path=path,
        exempt=exempt,
        deferred=deferred,
        proposed=kind == "sr" and "binding" not in post.metadata,
        diagram_file=str(post.metadata["diagram_file"])
        if kind == "diag" and "diagram_file" in post.metadata
        else None,
        scope_error=scope_error,
    )
```

Add the justification-to-edges helper:

```python
def _edges_from_justification(node_id: str, meta: dict) -> list[Edge]:
    """Task-node justification edges (spec §4 "typed task justification").
    Legacy `satisfies:` frontmatter with no `justification:` key is read as
    shorthand for `justification: [{satisfies: ...}]`, producing byte-
    identical `satisfies` edges to before this change. A malformed or
    unsupported-kind entry produces no edge here -- it is already recorded on
    the node as `scope_error` by `_id_node`/`_justification_scope_error`."""
    raw = meta.get("justification")
    if raw is None:
        return [Edge(node_id, sr_id, "satisfies") for sr_id in as_str_list(meta.get("satisfies"))]
    if not isinstance(raw, list):
        return []
    edges: list[Edge] = []
    for entry in raw:
        if not isinstance(entry, dict) or len(entry) != 1:
            continue
        ((kind, target_id),) = entry.items()
        if kind not in _JUSTIFICATION_KINDS:
            continue
        edges.append(Edge(node_id, str(target_id), kind))  # type: ignore[arg-type]
    return edges
```

In `extract_edges`, replace the task/sr/br branch's `satisfies` handling:

```python
    for node in nodes:
        if node.kind in ("task", "sr", "br"):
            post = _load_post(node.path)
            if post is None:
                continue
            meta = post.metadata
            source_plan = meta.get("source_plan")
            if source_plan:
                add(Edge(node.id, f"plan:{Path(str(source_plan)).name}", "source_plan"))
            if node.kind == "task":
                for edge in _edges_from_justification(node.id, meta):
                    add(edge)
            else:
                for sr_id in as_str_list(meta.get("satisfies")):
                    add(Edge(node.id, sr_id, "satisfies"))
            for upstream_id in as_str_list(meta.get("upstream")):
                add(Edge(node.id, upstream_id, "upstream"))
            for edge in edges_from_frontmatter(node.id, meta):
                add(edge)
        elif node.kind in ("feat", "metric", "goal", "run", "diag"):
            ...  # unchanged
```

(Only the `if node.kind in ("task", "sr", "br"):` branch's body changes; the `feat`/`metric`/
`goal`/`run`/`diag` and `plan` branches below it are untouched.)

- [ ] **Step 6: Implement the `gaps.py` `task_no_sr` fix.**

```python
from coherence.trace.model import Edge, JUSTIFICATION_EDGE_KINDS, Node
```

and, inside `find_gaps`'s task branch:

```python
        if node.kind == "task":
            if not any(e.kind in JUSTIFICATION_EDGE_KINDS for e in node_edges):
                add(
                    node,
                    "task_no_sr",
                    "task declares no justification "
                    "(satisfies/corrects/mitigates/implements/maintains/explores)",
                )
```

(Only the condition and detail string change; the `task_no_plan` and `task_plan_missing` checks
directly below it in the same branch are untouched.)

- [ ] **Step 7: Run the tests to verify they pass.**

Run: `rtk proxy uv run python -m pytest tests/unit/trace/test_model_edges.py tests/unit/trace/test_model_nodes.py tests/unit/trace/test_gaps.py -v`
Expected: PASS.

- [ ] **Step 8: Verify against the real T-031, closing Task 4's deferred coherence-layer check.**

```python
def test_t031_has_no_task_no_sr_gap_after_migrating_to_corrects():
    # Exercised against the real repo tree, not a tmp_path fixture -- same
    # REPO_ROOT convention as tests/unit/memory/test_t031_link.py (Task 4):
    # tests/unit/trace/test_gaps.py is the same depth below the repo root
    # (tests/unit/trace/), so parents[3] again.
    from pathlib import Path

    from coherence.trace.gaps import find_gaps
    from coherence.trace.model import extract_edges, load_nodes

    root = Path(__file__).resolve().parents[3]
    nodes = load_nodes(root)
    edges = extract_edges(root, nodes)
    gaps = find_gaps(nodes, edges, {})
    t031_gap_kinds = {g.kind for g in gaps if g.node_id == "T-031"}
    assert "task_no_sr" not in t031_gap_kinds
```

Add this to `tests/unit/trace/test_gaps.py`. This is the coherence-layer proof Task 4's own
verification step explicitly deferred to this task.

Run: `rtk proxy uv run python -m pytest tests/unit/trace/test_gaps.py -k t031 -v`
Expected: PASS (once Task 4 and this task are both merged — before Task 4, T-031 still has
`satisfies: []` and no justification at all, so this assertion would legitimately fail).

- [ ] **Step 9: Run the wider trace suite for regressions.**

Run: `rtk proxy uv run python -m pytest tests/unit/trace -v`
Expected: PASS, including every pre-existing test in `test_model_edges.py`, `test_model_nodes.py`,
`test_gaps.py`, `test_health.py`, `test_cli_check.py`, `test_cli_status.py`, `test_write.py`,
`test_explainers.py`, `test_propose.py`, `test_skill_contract.py`, `test_validation_status.py`.

- [ ] **Step 10: Run the full unit suite for regressions.**

Run: `rtk proxy uv run python -m pytest -m unit -q`
Expected: PASS. In particular `tests/unit/system/test_remediation.py` and
`tests/unit/system/test_table_drift.py` — this task adds no new `GapKind` (Decision 3 above), so
neither `REMEDIATION`'s exhaustiveness check nor its TypeScript mirror needs a corresponding
update; confirm both still pass exactly as-is, which is itself evidence the scope decision was
followed correctly.

- [ ] **Step 11: Commit.**

```bash
git add src/coherence/trace/model.py src/coherence/trace/gaps.py \
        tests/unit/trace/test_model_edges.py tests/unit/trace/test_model_nodes.py \
        tests/unit/trace/test_gaps.py
git commit -m "feat(trace): typed lifecycle edges, task_no_sr no longer requires satisfies specifically"
```

---

## Increment 2B Acceptance

- A task's own justified SR erroring during validation now fails the task; an unrelated
  periodic-cadence SR erroring stays a warning, and `run_validation` (the actual orchestrator call
  site) gates on that corrected `ok`, not a self-recomputed split that ignored it (Task 1).
- Every existing `satisfies:` task file parses identically to before; a new `justification:` list
  parses into typed `Justification` entries and rejects unknown kinds (Task 2).
- `NC-*` records load, degrade on malformed input, and raise only on true id collision (Task 3).
- `T-031` traces through `corrects: NC-0001`, and `NC-0001` cites `gh-issue:1` (Task 4).
- A context manifest with zero `checks` fails schema validation; a manifest gathered for the
  wrong task fails identity validation (Task 5).
- `coherence.policy.compiler.compile_obligations(root, "project")` returns a `blocking`
  `ci_verification` `Obligation` whose `resolve_cmd` matches the project's real declared gates
  under the `prototype` default (with `{python}` substituted via the same helper
  `factory.orchestrator.backends` already uses, never a literal `{python}`), and raises
  `UncompiledPresetError` for `exploration`/`product`; `compile_obligations(root, "task:<id>")`
  additionally returns a `task_justification` obligation, `advisory` under `prototype` and
  `blocking` under `high_assurance`; an out-of-vocabulary profile string raises
  `InvalidProfileError` instead of either (Task 6).
- `coherence.trace.gaps.find_gaps` no longer reports `task_no_sr` for a task whose only
  justification is a non-`satisfies` kind (`corrects`, `mitigates`, etc.) — verified directly
  against the real, on-disk T-031 (Task 7).
