# FEAT-17 Planning Workflow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `subagent-driven-development` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make FEAT-17 a deterministic, inspectable planning workflow that captures user intent, verifies intent/spec/plan/task/register consistency, preserves a deferred human-review seam, and suggests—but never silently starts—the governed development workflow.

**Architecture:** The Python backend owns the canonical planning contract and deterministic gates. User/agent interaction only authors bounded source files: `intent.json`, an authority `spec.md`, and a writing-plans-format plan. A pure checker derives a stable report from those files and the existing register/trace/plan parsers; a thin CLI adapter writes only run evidence and reports. The existing `/plan` host command remains a thin authoring adapter and later consumes this contract rather than reimplementing checks.

**Tech Stack:** Python 3.11–3.12, dataclasses, `pathlib`, JSON, PyYAML/frontmatter already in the repo, argparse, pytest, ruff, pyright. No new runtime dependency. TypeScript host wiring is a later task only after the Python contract is proven.

## Global Constraints

- Canonical source artifacts are files; indexes, reports, and UI projections are derived and disposable.
- The checker is pure/read-only over inputs; it never invokes an LLM, adopts an SR, writes a decision, starts development, or silently falls back.
- Missing, malformed, contradictory, stale, or unresolvable input is a failed gate with deterministic findings and a non-zero CLI exit.
- Semantic SR authoring and semantic alignment approval remain human-consent operations; `human_review` cannot be self-certified.
- FEAT-17 owns planning composition and gate output; FEAT-16 owns general workflow interpretation; FEAT-13 owns governed execution; FEAT-14 owns gate taxonomy; registration is delegated to health-resolution.
- Use exact relative paths in persisted records and stable sorted output. Never persist absolute machine-specific paths in the contract.
- Never push or merge. Commits are scoped to the task’s files.

---

## Contract checkpoint (must land before parallel work)

Before implementation, agree these exact interfaces. Later tasks must not rename them without updating all consumers and tests:

```python
@dataclass(frozen=True)
class PlanningInput:
    intent_path: Path
    spec_path: Path
    plan_path: Path
    project_root: Path
    run_id: str

@dataclass(frozen=True)
class PlanningFinding:
    code: str
    severity: Literal["error", "warning"]
    subject: str
    detail: str

@dataclass(frozen=True)
class PlanningReport:
    schema: int
    run_id: str
    ok: bool
    artifacts: tuple[dict[str, object], ...]
    findings: tuple[PlanningFinding, ...]
    next_actions: tuple[dict[str, object], ...]
    review_required: bool
    suggestion: dict[str, object] | None

def check_planning_input(input: PlanningInput) -> PlanningReport: ...
def write_planning_run(root: Path, report: PlanningReport) -> Path: ...
def build_downstream_suggestion(
    report: PlanningReport,
    decision: Mapping[str, object] | None = None,
) -> dict[str, object] | None: ...
```

The report JSON ordering is fixed: `schema`, `run_id`, `ok`, `artifacts`, `findings`, `next_actions`, `review_required`, `suggestion`. Findings sort by severity (`error` first), then code, then subject, then detail. Artifact records sort by relative path. A suggestion is non-null only when `report.ok` is true; `starts_automatically` is always `false`.

---

## Task 1: Add the pure planning contract and fail-closed checker

**Objective:** Add the deterministic source-artifact checker without any CLI or host side effects.

**Files:**
- Create: `src/coherence/planning/__init__.py`
- Create: `src/coherence/planning/model.py`
- Create: `src/coherence/planning/check.py`
- Test: `tests/unit/coherence/test_planning_check.py`

**Interfaces:**
- Consumes: `substrate.ledger.plans.parse_plan_tasks`, `coherence.trace.model`/existing register readers only where needed, and `pathlib.Path`.
- Produces: `PlanningInput`, `PlanningFinding`, `PlanningReport`, `check_planning_input`.

- [ ] **Step 1: Write the failing test**

Create a temporary project with:

```text
.intent/intent.json
 docs/superpowers/specs/intent-spec.md
 docs/superpowers/plans/intent-plan.md
 tasks/T-001-first.md
```

The intent file must contain:

```json
{
  "schema": 1,
  "prompt": "Build a deterministic planner",
  "answers": [
    {"id": "goal", "text": "Build a deterministic planner"},
    {"id": "constraint-files", "text": "Files remain canonical"}
  ]
}
```

The spec must have frontmatter `id`, `title`, `status`, and body containing `goal` and `constraint-files`. The plan must have frontmatter `spec_ref: intent-spec.md`, both `### Task 1:` and `### Task 2:` sections, and each task’s `**Files:**` block. The generated task must carry `source_plan: docs/superpowers/plans/intent-plan.md` and `source_task: 1`.

Assert the checker returns `ok is False` for a missing generated task, with an `error` finding code `PLAN_TASK_PARITY`. Add a second test with a complete fixture and assert `ok is True`, `review_required is True`, and no suggestion is emitted by the pure checker until the explicit review/consent seam is resolved.

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
uv run pytest tests/unit/coherence/test_planning_check.py -q
```

Expected: FAIL because `coherence.planning` does not exist.

- [ ] **Step 3: Write the minimal implementation**

Implement these rules in `check.py`:

1. Read every input as UTF-8; catch `OSError`, `UnicodeError`, JSON errors, YAML/frontmatter errors, and parser errors into stable findings.
2. Require intent JSON `schema == 1`, non-empty `prompt`, and an `answers` list whose entries have non-empty `id` and `text`.
3. Require the authority spec frontmatter fields `id`, `title`, `status`; record its relative path and SHA-256 hash.
4. Require the plan’s `spec_ref` to resolve to the exact authority spec path or canonical spec id, and require at least one task section. Use `parse_plan_tasks` for task grammar; do not duplicate its regex.
5. Load tasks from `project_root/tasks`; for every plan task require exactly one task with matching `source_plan` and `source_task`; report missing and duplicate mappings as `PLAN_TASK_PARITY`.
6. For each intent answer id, require the id to occur as a token in the spec and plan text; report uncovered answers as `INTENT_UNCOVERED`. Report a deterministic `SPEC_UNSUPPORTED_CLAIM` only for explicit `claim:<id>` tokens in the spec that have no intent answer id—do not pretend to solve unrestricted semantic entailment.
7. Emit `review_required: True` for every otherwise valid report. Do not write review files or a positive suggestion in this task.

Use deterministic relative paths (`Path.relative_to(project_root).as_posix()`), stable hashes, and sorted findings. Do not use shell commands or model calls.

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
uv run pytest tests/unit/coherence/test_planning_check.py -q
uv run ruff check src/coherence/planning tests/unit/coherence/test_planning_check.py
uv run pyright src/coherence/planning
```

Expected: focused tests pass; ruff and pyright report no new errors.

- [ ] **Step 5: Commit**

```bash
git add src/coherence/planning tests/unit/coherence/test_planning_check.py
git commit -m "feat: add deterministic planning consistency checker"
```

---

## Task 2: Add planning run evidence, review seam, and downstream suggestion

**Objective:** Persist a derived planning report and expose explicit human-review/consent state without fabricating approval.

**Files:**
- Modify: `src/coherence/planning/model.py`
- Modify: `src/coherence/planning/check.py`
- Create: `src/coherence/planning/run.py`
- Test: `tests/unit/coherence/test_planning_run.py`

**Interfaces:**
- Consumes: Task 1’s `PlanningReport` and `PlanningInput`.
- Produces: `write_planning_run(root, report) -> Path`, `build_downstream_suggestion(report) -> dict[str, object] | None`, and a strict review-decision reader for `.factory/planning/<run_id>/review-decision.json`.

- [ ] **Step 1: Write the failing test**

Add tests that:

```python
report = check_planning_input(valid_input)
path = write_planning_run(root, report)
assert path == root / ".factory" / "planning" / "run-001" / "report.json"
payload = json.loads(path.read_text(encoding="utf-8"))
assert list(payload) == ["schema", "run_id", "ok", "artifacts", "findings", "next_actions", "review_required", "suggestion"]
assert payload["suggestion"] is None
```

Write a valid review decision with `decision: approve`, `reviewer: human`, a non-empty `reason`, and exactly the current artifact paths. Assert `build_downstream_suggestion(report)` still returns `None` until the decision is supplied through the function’s explicit decision argument. Then assert an approved decision produces `action == "suggest_downstream"`, `workflow == "standard"`, the plan path and sorted task ids, `starts_automatically is False`, and prerequisites containing `human_review` and `requirement_consent`. Add tests for reject/defer, malformed decision, wrong reviewer, and changed artifact hash; all must produce no suggestion.

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
uv run pytest tests/unit/coherence/test_planning_run.py -q
```

Expected: FAIL because the run writer and decision-aware suggestion do not exist.

- [ ] **Step 3: Write the minimal implementation**

Implement:

- `write_planning_run` under `.factory/planning/<run_id>/report.json` using a temp file in the same directory and `os.replace`; never overwrite a source artifact.
- A strict `read_review_decision(path, report)`: require JSON object, `schema == 1`, exact `run_id`, `decision in {approve,reject,defer}`, `reviewer == "human"`, non-empty `reason`, and exact sorted `reviewed_artifacts` equal to the report’s source paths. Invalid decisions return a deterministic error state, never approval.
- `build_downstream_suggestion(report, decision=None)`: return `None` unless report is structurally valid, all findings are non-error, the supplied decision is valid and approved, and all artifact hashes still match. On success derive task ids from current task files and return:

```python
{
    "action": "suggest_downstream",
    "workflow": "standard",
    "plan": "docs/superpowers/plans/intent-plan.md",
    "tasks": ["T-001", "T-002"],
    "prerequisites": ["human_review", "requirement_consent"],
    "starts_automatically": False,
}
```

Do not call FEAT-13. Do not write an approve decision. Keep review browsing/visualization deferred; this task only stabilizes the file contract.

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
uv run pytest tests/unit/coherence/test_planning_run.py -q
uv run ruff check src/coherence/planning tests/unit/coherence/test_planning_run.py
uv run pyright src/coherence/planning
```

Expected: focused tests pass and no new lint/type errors.

- [ ] **Step 5: Commit**

```bash
git add src/coherence/planning tests/unit/coherence/test_planning_run.py
git commit -m "feat: add planning review seam and downstream suggestion"
```

---

## Task 3: Expose the deterministic planning gate through `coherence plan`

**Objective:** Make the backend contract usable as a first-class CLI without changing the fixed existing CLI groups beyond adding the planned `plan` group.

**Files:**
- Modify: `src/coherence/cli.py`
- Create: `src/coherence/planning/cli.py`
- Test: `tests/unit/coherence/test_planning_cli.py`

**Interfaces:**
- Consumes: `check_planning_input`, `write_planning_run`, and `build_downstream_suggestion`.
- Produces: `coherence plan check --intent <path> --spec <path> --plan <path> --run-id <id> [--project-root <dir>] [--json]`, plus `coherence plan suggest --run-id <id> --project-root <dir> [--json]`.

- [ ] **Step 1: Write the failing test**

Test the Python function directly and through the installed entry point:

```python
assert main(["plan", "check", "--project-root", str(root), "--intent", str(intent), "--spec", str(spec), "--plan", str(plan), "--run-id", "run-001", "--json"]) == 1
payload = json.loads(capsys.readouterr().out)
assert payload["ok"] is False
assert "findings" in payload
```

Add a valid fixture test asserting `plan check --json` returns exit 0 only if the report is structurally valid (even though `review_required` remains true). Add `plan suggest` tests for no decision (exit 1), rejected decision (exit 1), and approved decision (exit 0 with `action == "suggest_downstream"`). Assert the CLI never starts a child process by monkeypatching the process API or, preferably, by checking that the suggestion is only JSON output and no status/run files appear outside `.factory/planning/`.

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
uv run pytest tests/unit/coherence/test_planning_cli.py -q
```

Expected: FAIL because the `plan` group is not registered.

- [ ] **Step 3: Write the minimal implementation**

Use argparse. `plan check` constructs `PlanningInput`, runs the pure checker, writes the report, prints stable JSON with `suggestion: null` unless an approved decision is explicitly present, and returns 0 for a structurally valid report or 1 for errors. `plan suggest` reads the stored report and the review decision from the exact run directory, re-checks current hashes before suggesting, prints the suggestion, and returns 1 when no valid approval exists. Catch expected `OSError`, `ValueError`, and JSON errors at the CLI boundary and print a deterministic error report rather than a traceback.

Register `"plan": planning_main` in `coherence.cli.GROUPS`. Preserve existing group argv unchanged. Do not add a broad `coherence bootstrap` alias yet; `coherence plan check` is the first stable backend front door, while the full init/authoring composition remains a later thin host task.

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
uv run pytest tests/unit/coherence/test_planning_cli.py tests/unit/coherence/test_cli.py -q
uv run coherence plan --help
uv run coherence plan check --help
uv run ruff check src/coherence/planning src/coherence/cli.py tests/unit/coherence/test_planning_cli.py
uv run pyright src/coherence/planning src/coherence/cli.py
```

Expected: focused tests pass, help shows both subcommands, and no new lint/type errors.

- [ ] **Step 5: Commit**

```bash
git add src/coherence/cli.py src/coherence/planning/cli.py tests/unit/coherence/test_planning_cli.py
 git commit -m "feat: expose deterministic planning gate"
```

---

## Task 4: Wire the existing `/plan` authoring host to the backend gate

**Objective:** Ensure the existing planning command invokes the deterministic checker after authoring/decomposition and reports the result, without moving enforcement into TypeScript.

**Files:**
- Modify: `pi-ext/factory-watch/src/skill-prompt.ts`
- Modify: `pi-ext/factory-watch/src/index.ts`
- Test: `pi-ext/factory-watch/test/skill-prompt.test.ts` (or the existing test file that covers plan seed prompts)

**Interfaces:**
- Consumes: Task 3’s CLI contract and the existing `buildPlanSeedPrompt` / `/plan` command.
- Produces: an instruction in the seed prompt to persist verbatim intent/answers, write the authority spec before SR derivation, run `uv run coherence plan check`, and display but not execute the downstream suggestion.

- [ ] **Step 1: Write the failing test**

Add assertions that `buildPlanSeedPrompt` contains all of these exact concepts: `intent.json`, `spec.md`, `coherence plan check`, `plan_to_tasks`, `human`, `requirement_consent`, `starts_automatically`, and `do not start`.

Add a command-level test that a blank `/plan` argument still rejects without creating a session. Keep the existing skill-loading and session behavior tests green.

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
npm test --prefix pi-ext/factory-watch -- --runInBand
```

Expected: the new seed-prompt assertions fail because the current prompt only runs `plan_to_tasks` and does not describe the deterministic gate.

- [ ] **Step 3: Write the minimal implementation**

Update only the seed prompt so it instructs the authoring agent to:

1. preserve the user’s original prompt and clarified answers in a schema-versioned `intent.json`;
2. write the agreed authority `spec.md` before deriving SRs/features;
3. author the existing writing-plans-format plan and run `plan_to_tasks`;
4. run `uv run coherence plan check ... --json` and treat any error finding as blocking;
5. surface the explicit human-review/consent seam and never write an approval itself;
6. show any `suggest_downstream` output with `starts_automatically: false` and wait for a separate user action.

Do not make TypeScript compute findings, compare hashes, or call FEAT-13 directly. If command-level wiring is needed, invoke the Python CLI through the existing shell/terminal adapter and only render its canonical JSON.

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
npm test --prefix pi-ext/factory-watch -- --runInBand
npm run build --prefix pi-ext/factory-watch
```

Expected: extension tests and build pass.

- [ ] **Step 5: Commit**

```bash
git add pi-ext/factory-watch/src/skill-prompt.ts pi-ext/factory-watch/src/index.ts pi-ext/factory-watch/test/skill-prompt.test.ts
 git commit -m "feat: route plan authoring through coherence gate"
```

---

## Task 5: Add the bootstrap composition and available deterministic gates

**Objective:** Reuse existing factory-init, plan-to-tasks, register/check, and health readers in one inspectable bootstrap composition, while deferring full workflow interpretation and human browsing.

**Files:**
- Create: `src/coherence/planning/bootstrap.py`
- Modify: `src/coherence/planning/cli.py`
- Test: `tests/unit/coherence/test_planning_bootstrap.py`
- Modify: `docs/superpowers/specs/2026-08-27-feat17-planning-bootstrap-design.md` only if implementation facts require an update.

**Interfaces:**
- Consumes: Task 3 CLI, Task 4 host contract, `substrate.ledger.plans.run`, existing `coherence register check`, and existing health readers.
- Produces: `coherence plan bootstrap --project-root <dir> --intent <path> --spec <path> --plan <path> --run-id <id> [--decompose] [--json]`.

- [ ] **Step 1: Write the failing test**

Create a blank temporary project with a minimal `.factory/factory.yaml`, `intent.json`, authority spec, and two-task plan. Run the composition with `--decompose` and assert:

- the task files are created by `substrate.ledger.plans.run`;
- the output contains the deterministic planning report and exact task ids;
- it returns non-zero if the plan/spec link or task parity is broken;
- it does not write `requirements/SR-*.md`, FEAT dossiers, bundles, or a review approval automatically;
- the output includes a `next_actions` entry naming the delegated health-resolution registration/consent step.

Add a test that a project with no `.factory/factory.yaml` returns a clear bootstrap prerequisite error rather than claiming readiness.

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
uv run pytest tests/unit/coherence/test_planning_bootstrap.py -q
```

Expected: FAIL because no bootstrap composition exists.

- [ ] **Step 3: Write the minimal implementation**

Implement the composition as a thin Python function:

1. validate the project root and required `.factory/factory.yaml`;
2. run `substrate.ledger.plans.run` only when `--decompose` is explicit;
3. invoke Task 3’s planning check after decomposition;
4. append deterministic next actions for human consent and delegated registration; do not create SRs/features/bundles in this layer;
5. return the canonical report and task ids.

Do not implement FEAT-16’s general interpreter here. The bootstrap name is a workflow contract; the minimal `bootstrap` template can be added only when the workflow model exists. Do not run the first governed task automatically; emit a suggestion only.

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
uv run pytest tests/unit/coherence/test_planning_bootstrap.py -q
uv run ruff check src/coherence/planning tests/unit/coherence/test_planning_bootstrap.py
uv run pyright src/coherence/planning
```

Expected: focused tests pass and no new lint/type errors.

- [ ] **Step 5: Commit**

```bash
git add src/coherence/planning/bootstrap.py src/coherence/planning/cli.py tests/unit/coherence/test_planning_bootstrap.py docs/superpowers/specs/2026-08-27-feat17-planning-bootstrap-design.md
 git commit -m "feat: compose planning bootstrap workflow"
```

---

## Task 6: Register FEAT-17 trace links and prove the feature against the live register

**Objective:** Make every delivered FEAT-17 artifact traceable to the seven FEAT-17 SRs and run the available deterministic Coherence gates.

**Files:**
- Modify: `requirements/SR-043.md`
- Modify: `requirements/SR-044.md`
- Modify: `requirements/SR-050.md`
- Modify: `requirements/SR-051.md`
- Modify: `requirements/SR-052.md`
- Modify: `requirements/SR-053.md`
- Modify: `requirements/SR-054.md`
- Modify: `bundles/FEAT-017.json`
- Modify: `docs/features/FEAT-017.md`
- Create: `tasks/T-<allocated>-feat17-planning-workflow.md`
- Test: `tests/unit/coherence/test_planning_trace_contract.py`

**Interfaces:**
- Consumes: the implemented planning files and existing register/bundle grammar.
- Produces: task-level `satisfies`/`source_plan` links, FEAT-017 membership, and a test proving the produced planning artifacts are named in the trace contract.

- [ ] **Step 1: Write the failing test**

Assert that the FEAT-017 dossier lists `SR-043`, `SR-044`, and `SR-050` through `SR-054`, that `bundles/FEAT-017.json` lists the same seven SR refs, and that a task satisfying FEAT-017 has a source plan. Assert the test fails before the task and trace links are added.

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
uv run pytest tests/unit/coherence/test_planning_trace_contract.py -q
```

Expected: FAIL because no implementation task accounts for the new FEAT-17 SRs.

- [ ] **Step 3: Write the minimal trace declarations**

Create the allocated task file with frontmatter containing `satisfies` or the repository’s canonical justification shape for `SR-043`, `SR-044`, `SR-050`, `SR-051`, `SR-052`, `SR-053`, and `SR-054`, plus `source_plan` pointing at this plan and a non-empty DoD. Add implementation file references in the task body exactly as the repository’s trace parser expects. Keep semantic SR acceptance human-approved; do not add bindings or fake measurements.

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
uv run pytest tests/unit/coherence/test_planning_trace_contract.py -q
uv run coherence register check --project-root .
uv run coherence navigate health --json
uv run coherence trace check --project-root .
```

Expected: the new FEAT-17 task is discoverable and its links are structurally valid. Existing unrelated health gaps may remain; record them rather than claiming the repository is green.

- [ ] **Step 5: Commit**

```bash
git add requirements/SR-043.md requirements/SR-044.md requirements/SR-050.md requirements/SR-051.md requirements/SR-052.md requirements/SR-053.md requirements/SR-054.md bundles/FEAT-017.json docs/features/FEAT-017.md tasks/T-<allocated>-feat17-planning-workflow.md tests/unit/coherence/test_planning_trace_contract.py
 git commit -m "chore: trace planning workflow artifacts to FEAT-017"
```

---

## Task 7: Holistic integration review and available-gate deployment

**Objective:** Verify all cross-task wiring and run the available deterministic gates without pretending deferred features exist.

**Files:**
- No production file changes expected unless review findings require a scoped fix.
- Reports: `.factory/planning/<run-id>/report.json` is derived evidence and must remain ignored/disposable if the project’s ignore policy requires it.

**Interfaces:**
- Consumes: all prior tasks.
- Produces: verified CLI help/output, test/lint/type reports, and a reviewer-confirmed statement of deferred human browsing/visualization.

- [ ] **Step 1: Write the failing integration test**

Add an end-to-end fixture test that executes `coherence plan bootstrap --decompose --json`, reads the report, modifies the spec, and asserts the next `plan suggest` refuses the stale report. Assert the approved review path only suggests and never starts a governed run.

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
uv run pytest tests/unit/coherence/test_planning_integration.py -q
```

Expected: FAIL until all prior layers are wired.

- [ ] **Step 3: Implement only integration fixes**

Fix only real cross-task defects: CLI dispatch, path normalization, stale-hash handling, report ordering, missing trace link, or a false green. Do not add the deferred Obsidian/review browser or a full FEAT-16 interpreter as scope creep.

- [ ] **Step 4: Run all available gates**

Run:

```bash
uv run pytest tests/unit/coherence/test_planning_check.py tests/unit/coherence/test_planning_run.py tests/unit/coherence/test_planning_cli.py tests/unit/coherence/test_planning_bootstrap.py tests/unit/coherence/test_planning_trace_contract.py tests/unit/coherence/test_planning_integration.py -q
uv run ruff check src tests
uv run pyright
uv run coherence register check --project-root .
uv run coherence navigate health --json
uv run coherence trace check --project-root .
```

Expected: all new focused tests, ruff, and pyright pass. Register/health/trace output is recorded verbatim, including pre-existing unrelated gaps. No push or merge occurs.

- [ ] **Step 5: Independent holistic review**

Dispatch two fresh reviewers in parallel:

1. **Spec-compliance:** compare every FEAT-17 design section and SR-043/SR-044/SR-050–054 against the full diff; require coverage of cross-artifact consistency, intent alignment, deferred review seam, explicit downstream suggestion, and delegated registration.
2. **Code-quality/security fail-closed:** inspect path traversal/absolute-path persistence, malformed UTF-8/JSON/frontmatter, stale hash bypass, error handling, shell/process invocation, and accidental automatic development/approval. Any silent fallback or unhandled I/O error is a blocker.

If either reviewer fails, use a fresh fixer, re-run the relevant tests/gates, and re-review until both are silent. Finish with a holistic cross-task wiring check that verifies the CLI calls Python backend code and no TypeScript module reimplements the gate.

- [ ] **Step 6: Commit any review fix and prepare handoff**

Use scoped adds and an exact message such as:

```bash
git add <reviewed-files>
git commit -m "fix: harden deterministic planning gate"
```

Report branch, commits, focused gate output, live register/health output, and explicitly state that the human SR browsing/visualization surface and full FEAT-16 workflow interpreter remain deferred. Wait for explicit `yes push`/`merge`.

---

## Acceptance matrix

| Requirement | Deterministic acceptance evidence |
|---|---|
| SR-043 | `plan bootstrap --decompose` composes init prerequisite → plan → tasks → check and emits delegated next actions without auto-running development |
| SR-044 | no SR adoption or approve decision is written by the planner; only a strict human review file can authorize suggestion |
| SR-050 | schema-versioned intent stores verbatim prompt/answers and is hashed in the report |
| SR-051 | missing/malformed/stale/cross-reference/task parity defects produce stable error findings and non-zero exit |
| SR-052 | uncovered answer ids and explicit unsupported claim ids are reported; unrestricted semantic alignment remains human-reviewed |
| SR-053 | approved, fresh report emits `suggest_downstream` with `workflow`, plan, tasks, prerequisites, and `starts_automatically: false` |
| SR-054 | strict `review-decision.json` contract exists now; browsing/visualization is a future projection and never fabricated |

## Explicit deferrals

- Obsidian/SR review workbench and browser visualization are not implemented in this increment; the review decision contract is stable so that surface can write it later.
- Full FEAT-16 modular workflow model/interpreter and the complete `bootstrap` template library are not implemented here; FEAT-17 ships the planning contract and a thin composition first.
- FEAT-13 governed execution is not started by this workflow; the downstream suggestion is an explicit handoff only.
- Health-resolution feature/bundle registration remains the single registration path; FEAT-17 does not clone it.

## Verification baseline

Before finalizing, compare against live `main`/feature branch outputs, not stale handoff numbers. `coherence register check` currently has no `--json` option in this checkout; use its human-readable exit/result for that gate, while `navigate health --json` is the machine-readable health contract.

## Plan self-review

- Every design delta is covered by Tasks 1–7 or explicitly deferred above.
- All new interfaces are named in the contract checkpoint and reused consistently.
- Tests require RED before production implementation and are scoped to the vertical slice.
- The plan does not introduce a second register, evidence engine, workflow authority, or host-side gate implementation.
- The implementation task’s SR trace links are included before claiming FEAT-17 progress.
- Review gates are independent, fail-closed, and run after integration.
- All task steps contain concrete implementation instructions; no unfinished implementation instruction is present.

---

**Saved as:** `docs/superpowers/plans/2026-08-27-feat17-planning-workflow-plan.md`
**Execution:** use the `subagent-driven-development` workflow task-by-task; do not push or merge without explicit user instruction.
