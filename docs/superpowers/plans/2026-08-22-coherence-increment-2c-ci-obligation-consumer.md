# Coherence Increment 2C: CI as an Obligation Consumer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship `.github/workflows/ci.yml`, independent of `/factory-run`, that gates every push
and pull request on the repo's compiled `blocking` `ci_verification` obligations (project scope)
plus the small set of structural checks that sit outside `.factory/factory.yaml`'s `gates:`
block by construction — so CI cannot silently drift from what the orchestrator gates.

**Architecture:** A single new module, `coherence.policy.ci`, reads
`coherence.policy.compiler.compile_obligations` (Increment 2B) and turns `blocking`
`ci_verification` obligations' ordered `resolve_cmd` tuples into a flat, ordered command list,
preserving every tuple item and duplicate. It never
hand-lists gate commands itself — the one thing it does hard-code is the small, fixed set of
structural checks that sit outside `.factory/factory.yaml`'s `gates:` block by construction:
`coherence trace check` and `coherence register check`. There is no compiled obligation kind for
"the trace/register graph itself is internally consistent," so these two commands cannot be
expressed as a compiled `Obligation`'s `resolve_cmd` without inventing a second gates block —
this is a disclosed, plan-level exception to "no hand-maintained list," not something the
invariant kernel's seven rules (guide §3.3) mandate; none of those seven rules concern
trace/register graph integrity. The extension test suite (`pi-ext/factory-watch`) is **not** a
third hard-coded exception: `tests/gates/test_watch_ext_gate.py`, marked `pytest.mark.unit`,
already shells out to `npm run typecheck` then `npm test` (via `scripts/gates/watch_ext.py`), so
it runs automatically whenever the compiled `pytest -m unit ...` command runs — it is already
inside the obligation-compiled set, not outside it.

Scope, stated precisely (narrower than "CI enforces every obligation everywhere"): CI enforces
every `blocking` `ci_verification` obligation compiled at the `project` scope. A `blocking`
obligation of a different kind, or one compiled at a narrower `sr:`/`task:` scope (e.g. a future
increment's `verification_result` or `human_review` kind), is enforced by its own gate-protocol/
audit mechanism, not by this module — CI does not walk every SR or task in the repo to assemble
its command list, both because that would be invasive to add to a CI job and because those
obligations are naturally enforced through the audit/gate machinery the increments that compile
them already build.

The GitHub Actions workflow is a thin shell around this module: install (via `uv`, matching
AGENTS.md's own dev-command convention), call it, run what it prints — tolerating pytest's
"no tests collected" exit code only for commands that actually invoke pytest, so CI cannot go
red on a gate `/factory-run` would call passing while a non-pytest command's exit 5 remains a
failure.

**Tech Stack:** Python 3.11+, GitHub Actions (`ubuntu-latest`, `actions/checkout@v4`,
`actions/setup-python@v5`, `actions/setup-node@v4`), `uv` (dependency sync, matching AGENTS.md's
`uv run ...` convention), pytest.

**Spec:** `docs/superpowers/specs/2026-08-22-coherence-progressive-assurance-design.md` (§1 item
6, §3 D18, §7, §13).

## Global Constraints

- CI failure semantics follow the invariant kernel: an obligation whose check errors or cannot
  run is `blocking`-failing, never silently skipped (spec §7).
- No hand-maintained CI step list: everything sourced from `.factory/factory.yaml`'s declared
  gates via the compiled `ci_verification` obligation must come from
  `coherence.policy.compiler.compile_obligations`, never duplicated as a literal string in the
  workflow file (D18).
- Gate vocabulary is fixed: `unit`, `sim`, `integration`, `full` (AGENTS.md) — this plan adds no
  new gate names, only a consumer of the existing ones.
- Exit-5 semantics are a cross-boundary contract that must be resolved in this plan: the workflow
  classifies parsed argv by exact `pytest` token, while
  `factory.orchestrator.backends.ConfigGateRunner` currently treats every command exit 5 as a
  pass. Task 2A must either align the backend with the workflow's pytest-only behavior or
  explicitly document and test the intentional workflow/backend boundary; the mismatch cannot
  remain implicit.
- Python 3.11–3.12, Ruff line-length 100, Pyright standard mode (AGENTS.md).
- `{python}` template substitution in gate commands is owned entirely by Increment 2B's
  `coherence.policy.compiler` (which reuses `factory.orchestrator.backends`'s
  `_target_python`/`_quote_for_shell`, per spec §13's amendment) — by the time `resolve_cmd`
  reaches this plan's code, it is already an ordered tuple of plain, runnable command strings with
  no `{python}` placeholder left in it. This plan's own tests prove that rather than assuming it
  (Task 2).

## Known risk (disclosed, accepted): day-one CI may fail on pre-existing backlog

Independent of Task 1's fix below, this repo's `coherence trace check` and `coherence register
check` are red against `main` **today**, for reasons unrelated to this plan's own design (verified
by running both directly against this repo's real `tasks/`/`docs/superpowers/plans/` trees while
writing this plan):

- `coherence trace check` reports 62 pending gaps: 24 `task_no_sr`, 34 `plan_no_spec`, plus a
  handful of `task_no_plan`, `sr_unsatisfied` and `task_plan_missing` findings — pre-existing repo
  debt from tasks and plans committed before this traceability discipline existed. Exit code 1
  (`cmd_check` fails whenever any gap is `pending`).
- `coherence register check` crashes outright — an unhandled `ValueError` from
  `substrate.ledger.tasks._parse` — on `tasks/T-031-fix-report.md`'s missing frontmatter, until
  Task 1 below is done.

This plan does **not** attempt to clear the 62-gap backlog. That backlog is pre-existing repo debt
unrelated to the progressive-assurance design this plan implements; retroactively justifying ~24
old tasks and linking ~34 old plans to specs is its own, separately-scoped effort. Per spec
§7/§13, `ci_verification`'s structural floor (`coherence trace check` / `register check`) is
`blocking` under every default preset by deliberate design (D18, amended §13) — this plan does
**not** invent a mechanism to make it non-blocking as a workaround for the backlog.

**Consequence, stated plainly:** once `.github/workflows/ci.yml` (Task 3) is merged and runs
against `main` for the first time, it will most likely go red on the `coherence trace check` step,
independent of whether the code changes in that PR are otherwise correct. This is a known,
accepted outcome of shipping CI honestly against the repo's actual state rather than hiding the
backlog behind a softened check — not a defect in this plan. Clearing the backlog is out of scope
here and would need its own follow-up plan.

---

## File Structure

**Create:**
- `src/coherence/policy/ci.py` — `required_ci_commands(root) -> list[str]`
- `.github/workflows/ci.yml`
- `tests/unit/coherence/policy/test_ci.py`
- `tests/integration/test_ci_workflow_dry_run.py`

**Modify (exit-5 contract):**
- `src/factory/orchestrator/backends.py` — add the backend pytest-command helper and resolve its
  exit-5 normalization semantics as specified in Task 2A.
- `tests/unit/orchestrator/test_backends.py` — cover exact-argv pytest classification and the
  selected backend/workflow exit-5 contract, including a non-pytest command returning 5.

**Modify or delete (Task 1, prerequisite):**
- `tasks/T-031-fix-report.md` — currently crashes `coherence register check`; see Task 1.

---

### Task 1: Prerequisite — stop `tasks/T-031-fix-report.md` from crashing `register check`

`coherence register check` currently raises an unhandled `ValueError`: `substrate.ledger.tasks.
_parse` requires `id`, `title`, `status`, `dod` in a task file's frontmatter, and
`tasks/T-031-fix-report.md` has none at all (no `---` frontmatter block — it opens directly with
`# T-031 fix report`). It is a prose fix-report documenting a T-031 review-round follow-up, not a
task file, but its filename (`T-031-fix-report.md`) matches `load_tasks`'s `T-*.md` glob, so every
caller of `load_tasks` — including `coherence register check`'s `_findings` — tries to parse it as
one and crashes instead of degrading. This must be fixed before this plan's structural-check
command can run without crashing (see "Known risk" above for what still won't be *clean* — as
opposed to *crashing* — after this fix).

**Files:**
- Modify or delete: `tasks/T-031-fix-report.md`

- [ ] **Step 1: Decide the file's fate and act on it.**

  `tasks/T-031-fix-report.md` is real content (T-031's review-round fix report and verification
  output) — deleting it outright loses a legitimate record. Pick whichever of these fits what you
  find at execution time:

  - **Option A — give it real task frontmatter.** Add `id`, `title`, `status`, `dod` (and a
    `justification:` entry, e.g. naming what it corrects or supplements) so it parses as a proper
    task in the ledger.
  - **Option B — delete it**, if its content is judged genuinely superseded/redundant with what's
    already committed elsewhere (e.g. folded into `T-031`'s own commit history).
  - **Recommended, if execution time allows a third option** — move/rename it out of the
    `tasks/T-*.md` glob entirely (e.g. `docs/T-031-fix-report.md`): it is documentation *about* a
    task, not a task itself, so it does not need synthetic task frontmatter at all, and this
    preserves the content with the least invention. Move it before invoking `load_tasks`; after
    the move, that loader scans the remaining `tasks/T-*.md` files and no longer parses this
    report.

  Whichever option is chosen, `coherence register check` must stop raising when it walks `tasks/`.

- [ ] **Step 2: Confirm the crash is gone.**

  Run: `rtk proxy uv run python -m coherence register check`
  Expected: exits with a printed report (exit code 0 or 1 depending on remaining pending gaps —
  see "Known risk" above), never a Python traceback.

- [ ] **Step 3: Commit.**

```bash
# Option A: stage the frontmatter-bearing task file.
# git add tasks/T-031-fix-report.md
# Option B: stage the deletion.
# git rm tasks/T-031-fix-report.md
# Option C: move it out of the loader's tasks/T-*.md glob, then stage the destination.
# git mv tasks/T-031-fix-report.md docs/T-031-fix-report.md
# git add docs/T-031-fix-report.md
git commit -m "fix(tasks): stop T-031-fix-report.md from crashing register check"
```

### Task 2: `required_ci_commands` — obligation-derived commands plus the invariant-kernel floor

**Files:**
- Create: `src/coherence/policy/ci.py`
- Test: `tests/unit/coherence/policy/test_ci.py`

**Interfaces:**
- Consumes: `coherence.policy.compiler.compile_obligations(root, scope_ref="project") ->
  list[Obligation]` (Increment 2B) — by the time this plan's code sees it, each `blocking`
  `ci_verification` obligation's `resolve_cmd` is already a fully-substituted ordered tuple of
  runnable command strings (no `{python}` placeholder; see Global Constraints).
- Produces: `coherence.policy.ci.required_ci_commands(root: Path) -> list[str]`,
  `coherence.policy.ci.NoBlockingObligationError(RuntimeError)`. Consumed by Task 3's
  `.github/workflows/ci.yml` step and by Task 4's smoke test.

- [ ] **Step 1: Write the failing tests.**

```python
import sys
import pytest
from pathlib import Path

from coherence.policy.ci import NoBlockingObligationError, required_ci_commands
from substrate.policy.obligation import Obligation

pytestmark = pytest.mark.unit


def _seed(root: Path) -> None:
    # Mirrors this repo's own .factory/factory.yaml shape exactly: every step
    # is {python}-templated, and `full` carries all four of its real steps
    # (ruff, pyright, unit again, agent) -- a simplified stand-in without
    # {python} prefixes or the real 4-step `full` gate would hide both the
    # {python}-substitution bug and the day-one-command-set undercount this
    # fixture exists to catch.
    (root / ".factory").mkdir()
    (root / ".factory" / "factory.yaml").write_text(
        "gates:\n"
        "  unit:\n"
        "    - { cmd: \"{python} -m pytest -m unit -q --ignore=tests/gates/test_all_gate.py\" }\n"
        "  sim:\n"
        "    - { cmd: \"{python} -m pytest -m sim -q\" }\n"
        "  integration:\n"
        "    - { cmd: \"{python} -m pytest tests/integration/ -q -m integration\" }\n"
        "  full:\n"
        "    - { cmd: \"{python} -m ruff check .\" }\n"
        "    - { cmd: \"{python} -m pyright\" }\n"
        "    - { cmd: \"{python} -m pytest -m unit -q --ignore=tests/gates/test_all_gate.py\" }\n"
        "    - { cmd: \"{python} -m pytest -m agent -q\" }\n",
        encoding="utf-8",
    )


def test_includes_every_declared_gate_command_with_python_substituted(tmp_path):
    _seed(tmp_path)
    cmds = required_ci_commands(tmp_path)
    # 2B's compile_obligations already substitutes {python} (it reuses
    # factory.orchestrator.backends._target_python/_quote_for_shell) -- prove
    # that actually happened rather than trusting it silently: no {python}
    # placeholder survives, and a real interpreter path is present instead.
    assert not any("{python}" in c for c in cmds)
    assert any(sys.executable in c for c in cmds)
    assert any(
        c.endswith("-m pytest -m unit -q --ignore=tests/gates/test_all_gate.py") for c in cmds
    )
    assert any(c.endswith("-m pytest -m sim -q") for c in cmds)
    assert any(c.endswith("-m pytest tests/integration/ -q -m integration") for c in cmds)
    assert any(c.endswith("-m ruff check .") for c in cmds)
    assert any(c.endswith("-m pyright") for c in cmds)
    # full's 4th step -- a truthful superset of spec §7's day-one example
    # list, not a contradiction of it: CI runs every compiled blocking
    # command, and `full` really does include `pytest -m agent -q`.
    assert any(c.endswith("-m pytest -m agent -q") for c in cmds)
    configured = cmds[:-2]
    assert len(configured) == 7
    assert configured[0].endswith("-m pytest -m unit -q --ignore=tests/gates/test_all_gate.py")
    assert configured[1].endswith("-m pytest -m sim -q")
    assert configured[2].endswith("-m pytest tests/integration/ -q -m integration")
    assert configured[3].endswith("-m ruff check .")
    assert configured[4].endswith("-m pyright")
    assert configured[5] == configured[0]
    assert configured[6].endswith("-m pytest -m agent -q")


def test_includes_structural_checks_always(tmp_path):
    _seed(tmp_path)
    cmds = required_ci_commands(tmp_path)
    assert "coherence trace check" in cmds
    assert "coherence register check" in cmds


def test_no_gates_declared_raises_rather_than_silently_gating_nothing(tmp_path):
    (tmp_path / ".factory").mkdir()
    (tmp_path / ".factory" / "factory.yaml").write_text("harnesses: {}\n", encoding="utf-8")
    with pytest.raises(NoBlockingObligationError):
        required_ci_commands(tmp_path)


def test_commandless_blocking_obligation_is_rejected_even_with_another_commanded_one(
    tmp_path, monkeypatch
):
    from coherence.policy import ci

    monkeypatch.setattr(
        ci,
        "compile_obligations",
        lambda _root, _scope_ref: [
            Obligation(
                id="ob:ci_verification:project:unit",
                scope_ref="project",
                kind="ci_verification",
                requiredness="blocking",
                reason="unit",
                source_policy="prototype",
                state="open",
                resolve_cmd=("python -m pytest -m unit -q",),
            ),
            Obligation(
                id="ob:ci_verification:project:missing",
                scope_ref="project",
                kind="ci_verification",
                requiredness="blocking",
                reason="missing command",
                source_policy="prototype",
                state="open",
                resolve_cmd=None,
            ),
        ],
    )
    with pytest.raises(NoBlockingObligationError):
        required_ci_commands(tmp_path)
```

Note: the extension test suite is deliberately **not** covered by a
`test_includes_extension_tests_only_when_extension_present`-style test here — `required_ci_commands`
does not hard-code an `npm test` line at all (see Task 2's implementation notes below for why).

- [ ] **Step 2: Run the tests to verify they fail.**

Run: `rtk proxy uv run python -m pytest tests/unit/coherence/policy/test_ci.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'coherence.policy.ci'`).

- [ ] **Step 3: Implement.**

```python
"""CI reads the compiled obligation set; it never maintains its own step list
(D18). `required_ci_commands` returns every command backing a `blocking`
`ci_verification` obligation compiled at the `project` scope, plus the small,
fixed set of structural checks that sit outside `.factory/factory.yaml`'s
`gates:` block by construction -- there is no compiled obligation kind for
"the trace/register graph itself is internally consistent," so `coherence
trace check` / `coherence register check` are hard-coded here as a disclosed,
plan-level exception to "no hand-maintained list," not a kernel-mandated one
(the invariant kernel's seven rules, guide §3.3, do not cover trace/register
graph integrity).

Scope: this compiles obligations at the `project` scope only. A `blocking`
obligation compiled at a narrower scope (`sr:`, `task:` -- e.g. a future
increment's `verification_result` or `human_review` kind) is enforced by its
own gate-protocol/audit mechanism, not by this module -- CI does not walk
every SR/task in the repo to assemble its command list.

The extension test suite (`pi-ext/factory-watch`) is NOT a separate
hard-coded line here: `tests/gates/test_watch_ext_gate.py`, marked
`pytest.mark.unit`, already shells out to `npm run typecheck` then `npm test`
(via `scripts/gates/watch_ext.py`), so it runs automatically whenever the
compiled `pytest -m unit ...` command runs -- it is already inside the
obligation-compiled set. A second, hard-coded `npm test` line here would
both duplicate it and be strictly weaker (it would skip the typecheck step).
"""
from __future__ import annotations

from pathlib import Path

from coherence.policy.compiler import compile_obligations

# There is no compiled obligation kind for trace/register graph integrity --
# these sit outside .factory/factory.yaml's gates: block entirely, so they
# cannot be expressed as a compiled Obligation without inventing a second
# gates block. Hard-coded here as the one disclosed exception to "no
# hand-maintained list" (see module docstring).
_STRUCTURAL_COMMANDS = ("coherence trace check", "coherence register check")


class NoBlockingObligationError(RuntimeError):
    """No blocking ci_verification obligation compiled -- CI must fail loud,
    never gate nothing."""


def required_ci_commands(root: Path) -> list[str]:
    obligations = compile_obligations(root, "project")
    blocking = [
        o
        for o in obligations
        if o.kind == "ci_verification" and o.requiredness == "blocking"
    ]
    if not blocking or any(
        not o.resolve_cmd or any(not command.strip() for command in o.resolve_cmd)
        for o in blocking
    ):
        raise NoBlockingObligationError(
            "every blocking ci_verification obligation must have a resolve_cmd; "
            "declare a command for each blocking gate in .factory/factory.yaml"
        )
    commands: list[str] = []
    for obligation in blocking:
        commands.extend(obligation.resolve_cmd or ())
    commands.extend(_STRUCTURAL_COMMANDS)
    return commands
```

- [ ] **Step 4: Run the tests to verify they pass.**

Run: `rtk proxy uv run python -m pytest tests/unit/coherence/policy/test_ci.py -v`
Expected: PASS.

- [ ] **Step 5: Commit.**

```bash
git add src/coherence/policy/ci.py tests/unit/coherence/policy/test_ci.py
git commit -m "feat(ci): required_ci_commands reads the compiled obligation set"
```

### Task 2A: Resolve the backend/workflow exit-5 contract

The workflow in Task 3 uses pytest-only exact argv classification, but
`ConfigGateRunner.run_detail` currently normalizes every command with exit 5. Add the backend
helper and make the relationship explicit before accepting the CI consumer.

**Files:**
- Modify: `src/factory/orchestrator/backends.py`
- Test: `tests/unit/orchestrator/test_backends.py`

- [ ] **Step 1: Add the backend helper and choose the contract.**

  Add a focused helper (for example, `_is_pytest_command`) that classifies a command from parsed
  argv by exact `pytest` token membership, covering both `pytest ...` and `python -m pytest ...`
  while rejecting a non-pytest command such as `python -m ruff check pytest-config`. Then choose
  and record exactly one of these outcomes:

  - **Align backend semantics:** normalize exit 5 only when the helper identifies pytest, so
    `ConfigGateRunner` and the Task 3 workflow share the pytest-only contract.
  - **Document a deliberate boundary:** retain the backend's broader exit-5 normalization, but
    document in the helper/backend contract and this plan that `/factory-run` and CI intentionally
    classify exit 5 differently, including the consequence for non-pytest commands.

  Do not leave the current mismatch undocumented or describe the workflow as matching the backend
  until this choice is made.

- [ ] **Step 2: Test the helper and the selected semantics.**

  In `tests/unit/orchestrator/test_backends.py`, assert that exact-token pytest invocations are
  recognized, that `pytest` appearing only inside another token is rejected, and that a command
  returning exit 5 follows the selected alignment-or-boundary contract. The test must include a
  non-pytest exit-5 case so the behavior cannot regress to an undocumented blanket normalization.

- [ ] **Step 3: Run the focused backend tests.**

  Run: `rtk proxy uv run python -m pytest tests/unit/orchestrator/test_backends.py -v`
  Expected: PASS, with the chosen workflow/backend exit-5 relationship covered by assertions.

- [ ] **Step 4: Commit.**

```bash
git add src/factory/orchestrator/backends.py tests/unit/orchestrator/test_backends.py
git commit -m "fix(gates): make exit-5 semantics explicit across CI and orchestrator"
```

### Task 3: `.github/workflows/ci.yml`

**Files:**
- Create: `.github/workflows/ci.yml`

**Interfaces:**
- Consumes: `coherence.policy.ci.required_ci_commands` (Task 2), invoked via a small inline
  Python one-liner rather than a new `scripts/` entry point — this workflow is the only consumer,
  so a standalone script would be an extra file with one caller.

**Note on spec §11 scope:** §11 describes CI's own workflow eventually being tested "against a
seeded repo state in a dry-run job before it gates real PRs" — a staged GitHub Actions job with
its own fixture repo state. This plan does **not** build that job. Task 4's smoke test is a
narrower, already-achievable substitute: it proves `required_ci_commands` resolves a well-formed
command list, not that a staged job gates a seeded PR. A true seeded-repo dry-run job is a
worthwhile follow-up but is explicitly out of this plan's scope.

- [ ] **Step 1: Write the workflow.**

```yaml
name: CI

on:
  push:
  pull_request:

jobs:
  gates:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - uses: actions/setup-node@v4
        with:
          node-version: "20"
          cache: "npm"
          cache-dependency-path: pi-ext/factory-watch/package-lock.json

      # `uv`, not `pip install -e ".[dev]"` -- this repo's dev tooling (ruff,
      # pyright, pytest) lives under pyproject.toml's [dependency-groups]
      # "dev", which `pip install -e .` never installs at all (it only
      # installs [project.optional-dependencies], whose sole extra is
      # "code-index"). `uv sync` reads the committed uv.lock and installs the
      # project plus its default "dev" group into a real .venv, matching
      # AGENTS.md's `uv run ...` convention exactly.
      - name: Install uv
        run: python -m pip install uv

      - name: Install extension dependencies
        if: hashFiles('pi-ext/factory-watch/package.json') != ''
        run: npm ci --prefix pi-ext/factory-watch

      - name: Sync Python dependencies (uv.lock, dev group included)
        run: uv sync --locked

      # required_ci_commands' resolve_cmd values already carry a real,
      # substituted interpreter path (2B's compiler reuses
      # factory.orchestrator.backends._target_python, which resolves to
      # <repo_root>/.venv/{bin,Scripts}/python when that .venv exists -- the
      # one `uv sync` above just created) -- so those commands need no `uv
      # run` prefix here. What DOES need PATH help is the small set of bare,
      # non-{python}-templated commands this module hard-codes itself
      # (`coherence trace check`, `coherence register check`): putting the
      # synced venv's bin/ on PATH once, here, resolves the `coherence`
      # console script for them without wrapping every compiled command
      # individually.
      - name: Put the synced venv on PATH
        run: echo "$(pwd)/.venv/bin" >> "$GITHUB_PATH"

      - name: Resolve required gates from the compiled obligation set
        run: |
          python -c "
          from pathlib import Path
          from coherence.policy.ci import required_ci_commands
          for cmd in required_ci_commands(Path('.')):
              print(cmd)
          " > "$RUNNER_TEMP/required-gates.txt"
          cat "$RUNNER_TEMP/required-gates.txt"

      - name: Run every required gate
        run: |
          set -e
          while IFS= read -r cmd; do
            echo "+ $cmd"
            set +e
            eval "$cmd"
            rc=$?
            set -e
            # This is the workflow side of Task 2A's resolved exit-5 contract:
            # classify parsed argv by exact token membership, not by a substring
            # search. It recognizes both `pytest ...` and `python -m pytest ...`,
            # while `python -m ruff check pytest-config` is not pytest. If Task
            # 2A selects a deliberate backend boundary, its documentation must
            # say so rather than claiming these semantics are shared.
            read -r -a argv <<< "$cmd"
            is_pytest=false
            for token in "${argv[@]}"; do
              if [ "$token" = "pytest" ]; then
                is_pytest=true
                break
              fi
            done
            # Exit 5 means pytest's "no tests collected" only when this
            # command actually invokes pytest. A non-pytest command returning
            # 5 is a real failure and must stop CI.
            if [ "$rc" -ne 0 ]; then
              if [ "$rc" -eq 5 ] && [ "$is_pytest" = true ]; then
                :
              else
                exit "$rc"
              fi
            fi
          done < "$RUNNER_TEMP/required-gates.txt"
```

- [ ] **Step 2: Validate the workflow YAML parses.**

Run: `rtk proxy uv run python -c "import yaml, pathlib; yaml.safe_load(pathlib.Path('.github/workflows/ci.yml').read_text())"`
Expected: no exception (confirms valid YAML before relying on GitHub's own linting).

- [ ] **Step 3: Commit.**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: add obligation-driven GitHub Actions workflow"
```

### Task 4: Smoke test — `required_ci_commands` resolves against this repo's real config

Per spec §11, CI's own workflow is ideally tested "against a seeded repo state in a dry-run job
before it gates real PRs" — building that staged job is out of this plan's scope (see the note in
Task 3). What this task proves instead, narrower and achievable today, is that
`required_ci_commands` resolves a non-empty, well-formed command list against **this repo's real**
`.factory/factory.yaml` — it does **not** prove that a real CI run over this repo would currently
pass end to end (see "Known risk" above: it currently would not, on the structural floor).

**Files:**
- Create: `tests/integration/test_ci_workflow_dry_run.py`

**Interfaces:**
- Consumes: `coherence.policy.ci.required_ci_commands` (Task 2).

- [ ] **Step 1: Write the failing test.**

```python
import os
import shlex
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

from coherence.policy.ci import required_ci_commands

pytestmark = pytest.mark.integration


def test_required_ci_commands_resolves_a_well_formed_list_against_this_repo():
    # Narrower than a full CI dry-run: spec §11's "seeded repo state...before
    # it gates real PRs" staged job is explicitly out of this plan's scope
    # (see Task 3's note). This only proves the command list
    # required_ci_commands would hand to the workflow is non-empty and
    # well-formed against this repo's REAL .factory/factory.yaml -- it does
    # NOT assert those commands would currently all pass if run (they would
    # not: see "Known risk" above -- coherence trace check has a pending
    # backlog today).
    repo_root = Path(__file__).resolve().parents[2]
    commands = required_ci_commands(repo_root)
    assert commands, "required_ci_commands must resolve at least one command"
    assert all(isinstance(c, str) and c.strip() for c in commands)
    assert "coherence trace check" in commands
    assert "coherence register check" in commands
    assert any("pytest" in c and "-m unit" in c for c in commands)


def _workflow_steps(repo_root: Path) -> list[dict]:
    workflow = yaml.safe_load(
        (repo_root / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    )
    return workflow["jobs"]["gates"]["steps"]


def _workflow_step(steps: list[dict], name: str) -> dict:
    return next(step for step in steps if step.get("name") == name)


def test_workflow_installs_the_runtime_and_locked_dependencies():
    repo_root = Path(__file__).resolve().parents[2]
    steps = _workflow_steps(repo_root)
    assert any(step.get("uses") == "actions/setup-python@v5" for step in steps)
    assert any(step.get("uses") == "actions/setup-node@v4" for step in steps)
    assert any(step.get("run") == "python -m pip install uv" for step in steps)
    assert any("npm ci --prefix pi-ext/factory-watch" in step.get("run", "") for step in steps)
    assert any(step.get("run") == "uv sync --locked" for step in steps)


@pytest.mark.skipif(os.name == "nt" or shutil.which("bash") is None, reason="requires Ubuntu bash")
def test_workflow_executes_install_commands_in_order_against_the_expected_tools(tmp_path):
    repo_root = Path(__file__).resolve().parents[2]
    fake_bin = tmp_path / "bin"
    marker = tmp_path / "install-marker"
    fake_bin.mkdir()
    for tool in ("python", "npm", "uv"):
        script = fake_bin / tool
        script.write_text(
            "#!/usr/bin/env bash\n"
            f"printf '%s %s\\n' {tool} \"$*\" >> \"$INSTALL_MARKER\"\n",
            encoding="utf-8",
        )
        script.chmod(0o755)
    env = dict(
        os.environ,
        INSTALL_MARKER=str(marker),
        PATH=f"{fake_bin}{os.pathsep}{os.environ['PATH']}",
    )
    steps = _workflow_steps(repo_root)
    for name in (
        "Install uv",
        "Install extension dependencies",
        "Sync Python dependencies (uv.lock, dev group included)",
    ):
        subprocess.run(
            ["bash", "-euo", "pipefail", "-c", _workflow_step(steps, name)["run"]],
            cwd=repo_root,
            env=env,
            check=True,
        )
    assert marker.read_text(encoding="utf-8").splitlines() == [
        "python -m pip install uv",
        "npm ci --prefix pi-ext/factory-watch",
        "uv sync --locked",
    ]


@pytest.mark.skipif(os.name == "nt" or shutil.which("bash") is None, reason="requires Ubuntu bash")
def test_workflow_puts_the_synced_venv_on_github_path(tmp_path):
    repo_root = Path(__file__).resolve().parents[2]
    path_file = tmp_path / "github-path"
    env = dict(os.environ, GITHUB_PATH=str(path_file))
    subprocess.run(
        [
            "bash",
            "-euo",
            "pipefail",
            "-c",
            _workflow_step(_workflow_steps(repo_root), "Put the synced venv on PATH")["run"],
        ],
        cwd=repo_root,
        env=env,
        check=True,
    )
    assert path_file.read_text(encoding="utf-8") == f"{repo_root}/.venv/bin\n"


def _run_workflow_gate_loop(
    tmp_path, repo_root: Path, label: str, commands: list[str], exits: dict[str, int]
):
    case_root = tmp_path / label
    runner_temp = case_root / "runner-temp"
    fake_bin = case_root / "bin"
    marker = case_root / "marker"
    runner_temp.mkdir(parents=True)
    fake_bin.mkdir()
    (runner_temp / "required-gates.txt").write_text("\n".join(commands) + "\n", encoding="utf-8")
    by_executable: dict[str, list[tuple[list[str], str, int]]] = {}
    for command, exit_code in exits.items():
        argv = shlex.split(command)
        by_executable.setdefault(argv[0], []).append((argv[1:], command, exit_code))
    for executable, cases in by_executable.items():
        lines = ["#!/usr/bin/env bash"]
        for args, command, exit_code in cases:
            expected_args = shlex.quote(" ".join(args))
            lines.extend(
                [
                    f"if [ \"$*\" = {expected_args} ]; then",
                    f"  echo {shlex.quote(command)} >> \"$GATE_MARKER\"",
                    f"  exit {exit_code}",
                    "fi",
                ]
            )
        lines.append("exit 0")
        script = fake_bin / executable
        script.write_text("\n".join(lines) + "\n", encoding="utf-8")
        script.chmod(0o755)
    env = dict(
        os.environ,
        RUNNER_TEMP=str(runner_temp),
        GATE_MARKER=str(marker),
        PATH=f"{fake_bin}{os.pathsep}{os.environ['PATH']}",
    )
    return subprocess.run(
        [
            "bash",
            "-euo",
            "pipefail",
            "-c",
            _workflow_step(_workflow_steps(repo_root), "Run every required gate")["run"],
        ],
        cwd=repo_root,
        env=env,
        capture_output=True,
        text=True,
    ), marker


@pytest.mark.skipif(os.name == "nt" or shutil.which("bash") is None, reason="requires Ubuntu bash")
def test_workflow_gate_loop_runs_every_resolved_command_in_order(tmp_path):
    repo_root = Path(__file__).resolve().parents[2]
    first = "python -m pytest -m unit -q --ignore=tests/gates/test_all_gate.py"
    second = "python -m ruff check ."
    result, marker = _run_workflow_gate_loop(
        tmp_path,
        repo_root,
        "ordered",
        [first, second],
        {first: 0, second: 0},
    )
    assert result.returncode == 0
    assert marker.read_text(encoding="utf-8").splitlines() == [first, second]


@pytest.mark.skipif(os.name == "nt" or shutil.which("bash") is None, reason="requires Ubuntu bash")
def test_workflow_gate_loop_tolerates_exit_5_only_for_pytest(tmp_path):
    repo_root = Path(__file__).resolve().parents[2]
    pytest_command = "python -m pytest -m unit -q --ignore=tests/gates/test_all_gate.py"
    non_pytest_command = "python -m ruff check pytest-config"
    pytest_result, _ = _run_workflow_gate_loop(
        tmp_path, repo_root, "pytest-exit-5", [pytest_command], {pytest_command: 5}
    )
    other_result, _ = _run_workflow_gate_loop(
        tmp_path,
        repo_root,
        "other-exit-5",
        [non_pytest_command],
        {non_pytest_command: 5},
    )
    assert pytest_result.returncode == 0
    assert other_result.returncode == 5


@pytest.mark.skipif(os.name == "nt" or shutil.which("bash") is None, reason="requires Ubuntu bash")
def test_workflow_gate_loop_stops_on_pytest_exit_1(tmp_path):
    repo_root = Path(__file__).resolve().parents[2]
    failed = "python -m pytest -m unit -q --ignore=tests/gates/test_all_gate.py"
    not_reached = "python -m ruff check ."
    result, marker = _run_workflow_gate_loop(
        tmp_path,
        repo_root,
        "stop-on-failure",
        [failed, not_reached],
        {failed: 1, not_reached: 0},
    )
    assert result.returncode == 1
    assert marker.read_text(encoding="utf-8").splitlines() == [failed]
```

- [ ] **Step 2: Run the test to verify it fails or passes for the right reason.**

Run: `rtk proxy uv run python -m pytest tests/integration/test_ci_workflow_dry_run.py -v -m integration`
Expected: PASS once Increment 2B and Task 2 of this plan are both merged (this repo's own
`.factory/factory.yaml` already declares `unit`/`sim`/`integration`/`full` gates, confirmed
earlier in this plan's research). This test resolving successfully says nothing about whether the
resolved commands would all currently pass if run — see "Known risk" above.

- [ ] **Step 3: Commit.**

```bash
git add tests/integration/test_ci_workflow_dry_run.py
git commit -m "test(ci): smoke-test required_ci_commands against this repo's real config"
```

---

## Increment 2C Acceptance

- `tasks/T-031-fix-report.md` no longer crashes `coherence register check` (Task 1).
- `coherence.policy.ci.required_ci_commands` returns every command backing a `blocking`
  `ci_verification` obligation compiled at the `project` scope, plus the fixed structural floor,
  and raises rather than returning an empty/partial list when no blocking obligation compiles.
- `.github/workflows/ci.yml` runs on push and pull request, independent of `/factory-run`,
  installs dependencies via `uv sync` (matching AGENTS.md, not a `pip install -e ".[dev]"` that
  would install nothing real), and its command list is generated from Task 2's module rather than
  hard-coded in the YAML. Its execution loop tolerates exit-5 "no tests collected" only for a
  command invoking pytest, and Task 2A either aligns `factory.orchestrator.backends` to that
  contract or documents the separate workflow/backend boundary. Exit 5 from any other command
  remains a workflow failure. The workflow test executes both branches.
- The backend helper and `tests/unit/orchestrator/test_backends.py` make the exit-5 choice
  executable: either backend normalization is pytest-only and aligned with CI, or the separate
  semantics and their non-pytest exit-5 consequence are explicitly documented and tested.
- Task 4's smoke test proves `required_ci_commands` resolves a non-empty, well-formed command list
  against this repo's own real config — not that a full CI run over this repo would currently pass
  (see "Known risk" above).
- A later increment that compiles a new `blocking` `ci_verification` obligation at the `project`
  scope (e.g. Increment 6's gate-requiredness work, if it adds a new project-scope gate) is picked
  up by `required_ci_commands` automatically — no edit to this plan's files required (D18). A
  `blocking` obligation of a different kind, or one compiled at a narrower `sr:`/`task:` scope
  (e.g. Increment 4's `verification_result`, Increment 6's `human_review`), is enforced by its own
  gate-protocol/audit mechanism, not by this CI workflow — see the Architecture section's scope
  note above.
- Known, accepted risk: the first real run of this workflow against `main` may fail on the
  pre-existing 62-gap `coherence trace check` backlog (see "Known risk" above) — this plan
  deliberately does not clear that backlog or soften the check to hide it.
