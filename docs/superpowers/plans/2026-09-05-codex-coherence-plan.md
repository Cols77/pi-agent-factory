# Codex Coherence Plan Skill Implementation Plan

> For agentic workers: REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (- [ ]) syntax for tracking.

**Goal:** Add a project-local $coherence-plan Codex skill backed by a deterministic, argv-safe adapter over the existing Coherence planning legal-actions projection.

**Architecture:** Keep Coherence as the authority for planning state and legal actions. Add a standard-library helper under the Codex skill that validates inputs, invokes uv run coherence plan legal-actions --json, and fails closed on invalid output. Put the conversation workflow, consent boundaries, and fix-review-fix loop in SKILL.md; do not change the existing planner, Pi adapter, or Hermes adapter.

**Tech Stack:** Python 3.12 standard library, pytest, Codex Agent Skills (SKILL.md plus optional agents/openai.yaml), Markdown.

**Source spec:** docs/superpowers/specs/2026-09-05-codex-coherence-plan-design.md

**Global constraints:**

- Work only in C:\coding\pi-agent-factory-wt\guided-plan-workflow.
- Preserve the pre-existing untracked .hermes/plans/ directory and do not stage it.
- Use .agents/skills/coherence-plan/ for the Codex project-local skill.
- Do not modify the canonical Coherence planner, action registry, Pi adapter, or Hermes adapter.
- Backend invocations must use argv lists with shell=False; never build shell command strings.
- Exit code 0 means a valid ready projection; exit code 1 is accepted only with a valid blocked projection.
- No host action may grant consent, adopt requirements, bypass gates, or launch downstream work.
- Follow TDD: write and run a failing test before production implementation in each code task.

---

### Task 1: Add the fail-closed legal-actions helper

**Files:**

- Create: .agents/skills/coherence-plan/scripts/coherence_plan.py
- Create: tests/unit/codex/__init__.py
- Create: tests/unit/codex/test_coherence_plan_helper.py

**Interfaces:**

- build_legal_actions_command(project_root: Path, run_id: str) -> list[str]
- parse_projection(raw: str, run_id: str) -> dict[str, Any]
- query_legal_actions(project_root: Path, run_id: str) -> dict[str, Any]
- main(argv: Sequence[str] | None = None) -> int

- [ ] Step 1: Write failing helper tests.

Load the skill-local script with importlib.util.spec_from_file_location so tests
do not require the .agents directory to be a Python package. Cover exact argv
construction for run-001; unsafe run IDs never reaching subprocess.run; ready
projection on exit 0; blocked projection on exit 1; malformed JSON, non-integer
schema, mismatched run ID, and starts_automatically true; unexpected exit code 2
failing even when stdout is valid JSON; and main printing JSON and returning
the projection status.

Use a fixture with schema 1, run_id run-001, boolean blocked, reason string or
null, legal_next_actions list[str], and starts_automatically false. Monkeypatch
subprocess.run to return CompletedProcess([], returncode, stdout, stderr). Assert
every backend argument is a string and shell=False.

- [ ] Step 2: Run the helper tests and verify the expected red failure.

Run:

    uv run pytest tests/unit/codex/test_coherence_plan_helper.py -q -o addopts=''

Expected: collection or test failure because the helper does not yet exist.

- [ ] Step 3: Implement the minimal helper.

Implement coherence_plan.py with SAFE_RUN_ID equal to
^[A-Za-z0-9][A-Za-z0-9._-]*$, build_legal_actions_command validating the run ID
and directory and returning the exact argv list:
uv, run, coherence, plan, legal-actions, --project-root, root, --run-id,
run-id, --json.

Implement parse_projection using json.loads. Require schema exactly 1, the
exact run ID, boolean blocked, string-or-null reason, list[str]
legal_next_actions, and starts_automatically exactly False.

Implement query_legal_actions with subprocess.run(command, cwd=project_root,
capture_output=True, text=True, check=False, shell=False). Accept only return
codes 0 and 1; reject all other codes even with valid-looking stdout. The CLI
parser exposes legal-actions --project-root PATH --run-id ID. On an OS,
runtime, or validation error print a schema-1 blocked object with reason
BACKEND_INVALID, an empty action list, starts_automatically false, and bounded
error text, then return 1. On valid output print JSON and return 1 only when
blocked is true.

- [ ] Step 4: Run focused tests and lint.

    uv run pytest tests/unit/codex/test_coherence_plan_helper.py -q -o addopts=''
    uv run ruff check .agents/skills/coherence-plan/scripts/coherence_plan.py tests/unit/codex

Expected: all focused tests pass and Ruff reports no errors.

- [ ] Step 5: Commit Task 1.

    git add .agents/skills/coherence-plan/scripts/coherence_plan.py tests/unit/codex/__init__.py tests/unit/codex/test_coherence_plan_helper.py
    git commit -m "feat(codex): add coherence plan projection helper"

The commit must not include .hermes/plans/.

### Task 2: Add the Codex skill and contract metadata

**Files:**

- Create: .agents/skills/coherence-plan/SKILL.md
- Create: .agents/skills/coherence-plan/agents/openai.yaml
- Create: tests/unit/codex/test_coherence_plan_contract.py

**Interfaces:**

- Explicit invocation: $coherence-plan.
- Legal-action check: uv run python .agents/skills/coherence-plan/scripts/coherence_plan.py legal-actions --project-root <root> --run-id <id>.
- Only author-spec, author-plan, review-spec, and review-plan can enter the bounded author/review loop; all other actions are display-only.

- [ ] Step 1: Write failing skill-contract tests.

Assert SKILL.md has frontmatter with name coherence-plan and description,
names $coherence-plan, invokes the helper, and contains the phrases Coherence
remains the authority, never infer, never grant consent, never adopt, never
launch downstream, starts_automatically, and fix-review-fix.

Assert openai.yaml contains display name Coherence Plan, a short description,
and a default prompt containing $coherence-plan but not downstream.

- [ ] Step 2: Run the contract tests and verify the expected red failure.

    uv run pytest tests/unit/codex/test_coherence_plan_contract.py -q -o addopts=''

Expected: failure because SKILL.md and openai.yaml do not yet exist.

- [ ] Step 3: Add the skill instructions.

The skill must require a safe named run ID and planning request; use explicit
Coherence start --json or resume --json without silent fallback; query the
helper after start/resume and every state-changing operation; treat blocked,
reason, legal_next_actions, and starts_automatically == false as authority;
stop on blocked output; and allow only backend-declared author/review actions
into the loop.

Document the fix-review-fix loop: inspect bounded context, make the smallest
fix, run focused tests/gates, perform a fresh requirement review, apply valid
findings, and re-check the projection. Stop on reviewer acceptance, an
authoritative Coherence block, or a human decision boundary.

Explicitly forbid consent, adoption, warning acceptance, gate bypass, downstream
materialization/execution, merge, and push. State that handoff is reported but
never executed, and Codex /plan is separate.

- [ ] Step 4: Add Codex metadata.

Create agents/openai.yaml with display_name Coherence Plan, short_description
Inspect and continue named Coherence planning runs, and a default_prompt that
contains $coherence-plan and does not claim downstream authority.

- [ ] Step 5: Run contract tests and lint.

    uv run pytest tests/unit/codex/test_coherence_plan_contract.py -q -o addopts=''
    uv run ruff check tests/unit/codex/test_coherence_plan_contract.py

Expected: all contract tests pass and Ruff reports no errors.

- [ ] Step 6: Commit Task 2.

    git add .agents/skills/coherence-plan/SKILL.md .agents/skills/coherence-plan/agents/openai.yaml tests/unit/codex/test_coherence_plan_contract.py
    git commit -m "feat(codex): add coherence plan skill"

### Task 3: Document host parity and verify the surface

**Files:**

- Modify: README.md in the host integration and repository layout sections.
- Create: tests/integration/test_codex_coherence_plan_surface.py

- [ ] Step 1: Write failing surface test.

Assert that the skill, helper, and metadata files exist and README contains
both $coherence-plan and coherence plan legal-actions.

- [ ] Step 2: Run the surface test and verify the expected red failure.

    uv run pytest tests/integration/test_codex_coherence_plan_surface.py -q -o addopts=''

Expected: failure because README does not yet document the Codex skill.

- [ ] Step 3: Add the README note.

Document that .agents/skills/coherence-plan/ is the project-local Codex
adapter, invoked as $coherence-plan <run-id>, consumes the same coherence plan
legal-actions --json projection as Pi and Hermes, keeps handoff non-executing,
and does not replace Codex /plan. Add the path to the repository layout list
alongside .pi/skills/.

- [ ] Step 4: Run conformance verification.

    uv run pytest tests/integration/test_codex_coherence_plan_surface.py tests/unit/codex -q -o addopts=''
    uv run pytest tests/unit/hermes/test_coherence_plan_plugin.py tests/unit/coherence/test_planning_cli.py tests/unit/coherence/test_planning_session.py -q -o addopts=''
    uv run ruff check .agents/skills/coherence-plan/scripts/coherence_plan.py tests/unit/codex tests/integration/test_codex_coherence_plan_surface.py
    uv run pyright .agents/skills/coherence-plan/scripts/coherence_plan.py
    git diff --check

Expected: selected tests pass, Ruff and Pyright report no errors, and
git diff --check is silent. Report unrelated repository-wide baseline failures
separately.

- [ ] Step 5: Commit Task 3.

    git add README.md tests/integration/test_codex_coherence_plan_surface.py
    git commit -m "docs(codex): document coherence plan skill"

### Final review checkpoint

After all tasks, run the changed-surface tests and inspect the final diff. A
fresh final reviewer must confirm helper parity with Pi/Hermes, argv safety,
fail-closed handling for invalid state, consent/adoption/gate/downstream
boundaries, intended files only, and an unstaged .hermes/plans/ directory.
