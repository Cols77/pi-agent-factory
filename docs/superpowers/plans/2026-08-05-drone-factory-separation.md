# Drone/Factory Separation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move the drone implementation, its product specs/plans and its 24 tasks out of `pi-agent-factory` and into `cool_physical_ai_project`, leaving the factory containing only the factory.

**Architecture:** The factory is the base; the drone is a plug. Gate resolution becomes project-relative so a repo that provides no `sim` gate is handled rather than failing, then the drone artifacts are copied into the drone repo with a provenance commit and removed from the factory with a matching one. No history is rewritten, so the operation is inspectable and abortable until the final removal commit.

**Tech Stack:** Python 3.11-3.12, pytest, ruff, pyright, git.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-08-05-drone-factory-separation-design.md`
- **Two repositories.** Factory `C:/coding/pi-agent-factory`, drone `C:/coding/cool_physical_ai_project`. Both must be clean before starting and green at the end.
- **No history rewriting.** Copy in, `git rm` out, one provenance commit each side citing the other's SHA.
- **Nothing moves before Task 1 lands.** Three of the factory's gates are defined entirely by drone tests — `sim`, `agent` (3 files, all `tests/agent/`) and `integration` (1 file). Without project-relative resolution, removing them makes `run_validation` report "sim tests failed" on every task and makes `all.py` fail on an empty `agent` selection.
- Factory tests: `uv run pytest -m unit`, `uv run ruff check .`, `uv run pyright`.
- Every test module needs `pytestmark = pytest.mark.unit` — `addopts = "-m unit"` means unmarked tests silently do not run.
- The drone repo already provides the plug: `scripts/gates/sim_smoke.py`, `SIM_CMD`, and a `sim` pytest marker. Do not recreate them.

---

### Task 1: Project-relative gate resolution

**Files:**
- Modify: `src/factory/orchestrator/backends.py` (`SubprocessGateRunner`)
- Modify: `src/factory/orchestrator/nodes.py` (`run_validation`)
- Modify: `scripts/gates/_proc.py` (`run_and_propagate`)
- Test: `tests/unit/orchestrator/test_backends.py`
- Test: `tests/unit/orchestrator/test_nodes_val_review.py`
- Test: `tests/gates/test_proc.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `GateRunner.run(name) -> int` gains a third outcome. `SubprocessGateRunner.run` returns `GATE_NOT_APPLICABLE` (a module-level `int` sentinel, `-1`); `run_validation` treats it as skip, not failure.
- **"Nothing to run" is not-applicable in two forms**: the gate's script is absent, or pytest exits `5` (no tests collected). A gate that runs and fails still returns its real non-zero code — absence and failure must never be conflated.
- **Both gate paths must learn this.** `SubprocessGateRunner` serves `factory-run`; `scripts/gates/_proc.run_and_propagate` serves `all.py`. Fixing only one leaves `all.py` failing on the emptied `agent` gate.

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/orchestrator/test_backends.py`:

```python
def test_subprocess_gate_reports_not_applicable_when_the_project_has_no_such_gate(tmp_path):
    # The factory has no sim tests once the drone leaves. A gate the project does
    # not provide must be distinguishable from a gate that ran and failed.
    from factory.orchestrator.backends import GATE_NOT_APPLICABLE, SubprocessGateRunner

    runner = SubprocessGateRunner(tmp_path)  # empty repo: no scripts/gates at all

    assert runner.run("sim") == GATE_NOT_APPLICABLE


def test_subprocess_gate_runs_a_script_the_project_does_provide(tmp_path):
    from factory.orchestrator.backends import GATE_NOT_APPLICABLE, SubprocessGateRunner

    gates = tmp_path / "scripts" / "gates"
    gates.mkdir(parents=True)
    (gates / "sim_smoke.py").write_text("import sys\nsys.exit(0)\n", encoding="utf-8")

    result = SubprocessGateRunner(tmp_path).run("sim")

    assert result == 0
    assert result != GATE_NOT_APPLICABLE


def test_a_provided_gate_that_fails_still_reports_its_failure(tmp_path):
    from factory.orchestrator.backends import GATE_NOT_APPLICABLE, SubprocessGateRunner

    gates = tmp_path / "scripts" / "gates"
    gates.mkdir(parents=True)
    (gates / "sim_smoke.py").write_text("import sys\nsys.exit(3)\n", encoding="utf-8")

    result = SubprocessGateRunner(tmp_path).run("sim")

    assert result == 3
    assert result != GATE_NOT_APPLICABLE


def test_a_gate_that_collects_no_tests_is_not_applicable(tmp_path):
    # pytest exits 5 when nothing is collected. After the drone leaves, the
    # integration gate runs against an empty directory -- that is "the project
    # has no integration suite", not "integration failed".
    from factory.orchestrator.backends import GATE_NOT_APPLICABLE, SubprocessGateRunner

    gates = tmp_path / "scripts" / "gates"
    gates.mkdir(parents=True)
    (gates / "sim_smoke.py").write_text("import sys\nsys.exit(5)\n", encoding="utf-8")

    assert SubprocessGateRunner(tmp_path).run("sim") == GATE_NOT_APPLICABLE


def test_integration_gate_on_an_empty_repo_is_not_applicable(tmp_path):
    from factory.orchestrator.backends import GATE_NOT_APPLICABLE, SubprocessGateRunner

    assert SubprocessGateRunner(tmp_path).run("integration") == GATE_NOT_APPLICABLE
```

Append to `tests/gates/test_proc.py`:

```python
def test_run_and_propagate_treats_no_tests_collected_as_success(tmp_path):
    # all.py runs AGENT_CMD; every agent-marked test is a drone test, so after
    # the split that selection is empty and pytest exits 5. The gate pipeline
    # must not read "this project has no agent tests" as a failure.
    import importlib.util
    import sys

    spec = importlib.util.spec_from_file_location("_proc", "scripts/gates/_proc.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    assert mod.run_and_propagate([sys.executable, "-c", "import sys; sys.exit(5)"]) == 0
    assert mod.run_and_propagate([sys.executable, "-c", "import sys; sys.exit(1)"]) == 1
    assert mod.run_and_propagate([sys.executable, "-c", "import sys; sys.exit(0)"]) == 0
```

Append to `tests/unit/orchestrator/test_nodes_val_review.py`:

```python
def test_validation_passes_when_a_gate_is_not_applicable():
    # Absence of a sim suite is not a validation failure. Before this, deleting
    # the factory's sim gate made run_validation report "sim tests failed" on
    # every task, blaming drone tests that no longer existed.
    from factory.orchestrator.backends import GATE_NOT_APPLICABLE

    gates = FakeGateRunner({"sim": [GATE_NOT_APPLICABLE], "integration": [0]})

    assert run_validation(gates)[0] == NodeOutcome.PASS


def test_validation_still_fails_on_a_gate_that_ran_and_failed():
    gates = FakeGateRunner({"sim": [1]})

    assert run_validation(gates)[0] == NodeOutcome.FAIL
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/orchestrator/test_backends.py tests/unit/orchestrator/test_nodes_val_review.py -q`
Expected: FAIL — `ImportError: cannot import name 'GATE_NOT_APPLICABLE'`

- [ ] **Step 3: Implement in `backends.py`**

Add above `class SubprocessGateRunner`:

```python
# A gate the project does not provide. Distinct from 0 (ran, passed) and from any
# positive code (ran, failed) -- absence must never be reported as failure.
GATE_NOT_APPLICABLE = -1
# pytest's exit code for "no tests were collected", which for a gate means the
# project has no such suite rather than that the suite failed.
PYTEST_NO_TESTS_COLLECTED = 5
```

Replace `SubprocessGateRunner.run`'s command selection so absence is detected
before the subprocess runs, and translate pytest's empty-selection code after it:

```python
    def run(self, name: str) -> int:
        script = self._SCRIPTS[name]
        if name == "integration":
            if not (self._repo_root / "tests" / "integration").is_dir():
                return GATE_NOT_APPLICABLE
            cmd = [sys.executable, "-m", "pytest", "tests/integration/", "-q", "-m", "integration"]
        else:
            if not (self._repo_root / script).is_file():
                return GATE_NOT_APPLICABLE
            cmd = [sys.executable, script]
```

and, at each of the two `return` points at the end of the method, map the code:

```python
        code = subprocess.run(cmd, cwd=self._repo_root).returncode
        return GATE_NOT_APPLICABLE if code == PYTEST_NO_TESTS_COLLECTED else code
```

```python
        return (
            GATE_NOT_APPLICABLE
            if proc.returncode == PYTEST_NO_TESTS_COLLECTED
            else proc.returncode
        )
```

- [ ] **Step 4: Implement in `nodes.py`**

In `run_validation`, replace the two gate checks so a not-applicable gate is
skipped rather than treated as a failure:

```python
    sim_result = gates.run("sim")
    if sim_result != GATE_NOT_APPLICABLE and sim_result != 0:
        status.report(
            task_id=task_id,
            node="validation",
            node_state="fail",
            attempt=1,
            max_attempts=1,
            handoff="sim tests failed",
        )
        return NodeOutcome.FAIL, NodeEvent("validation", "fail")
    integration_result = gates.run("integration")
    if integration_result != GATE_NOT_APPLICABLE and integration_result != 0:
```

with the existing integration-failure body following unchanged, and add the import:

```python
from factory.orchestrator.backends import GATE_NOT_APPLICABLE
```

- [ ] **Step 4b: Implement in `scripts/gates/_proc.py`**

`all.py` does not go through `SubprocessGateRunner`, so it needs the same rule.
Replace `run_and_propagate`:

```python
# pytest exits 5 when nothing is collected. For a gate that means the project has
# no such suite -- not that the suite failed. all.py runs AGENT_CMD, and after the
# drone leaves there are no agent-marked tests here.
PYTEST_NO_TESTS_COLLECTED = 5


def run_and_propagate(cmd: list[str]) -> int:
    """Run cmd, stream its output, return its exit code. No parsing of stdout."""
    code = subprocess.run(cmd, check=False).returncode
    return 0 if code == PYTEST_NO_TESTS_COLLECTED else code
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/unit/orchestrator/ -q`
Expected: PASS — all orchestrator tests, including the five new ones.

- [ ] **Step 6: Verify the whole factory suite is still green**

Run: `uv run pytest -m unit -q --ignore=tests/gates`
Expected: PASS, no regressions.

- [ ] **Step 7: Commit**

```bash
git add src/factory/orchestrator/backends.py src/factory/orchestrator/nodes.py tests/unit/orchestrator/
git commit -m "feat(orchestrator): report a gate the project does not provide as not-applicable

A gate whose script is absent returned a subprocess failure indistinguishable
from a real one, so a repo with no sim suite failed every task at validation.
Absence and failure are now separate outcomes.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 2: Import the drone artifacts into the drone repo

**Files (in `C:/coding/cool_physical_ai_project`):**
- Create: `src/drone/**` (16 files, overwriting the existing `fake_flight_controller.py`)
- Create: `src/sim/**` (13), `tests/sim/**` (12), `scenarios/**` (5)
- Create: `tests/agent/**` (3 — every `agent`-marked test), `tests/integration/test_mission_loop.py` (the only `integration`-marked test)
- Create: `docs/superpowers/specs/2026-07-21-mission-agent-navigation-design.md`, `docs/superpowers/specs/2026-07-30-sim-testbench-design.md`
- Create: `docs/superpowers/plans/2026-07-21-mission-agent-navigation.md`, `docs/superpowers/plans/2026-07-30-sim-testbench.md`
- Create: `tasks/T-029…T-052` (the 24 listed in spec §3.3)
- Modify: `pyproject.toml` (add `pygame`, `matplotlib`)

**Interfaces:**
- Consumes: the factory tree at the SHA recorded in the commit message.
- Produces: a drone repo containing the implementation, its ledger, and its planning artifacts.

- [ ] **Step 1: Confirm both repos are clean**

Run: `git -C C:/coding/pi-agent-factory status --porcelain` and `git -C C:/coding/cool_physical_ai_project status --porcelain`
Expected: both print nothing. If not, stop — the split must start from a clean state.

Record the factory SHA for the commit message: `git -C C:/coding/pi-agent-factory rev-parse --short HEAD`

- [ ] **Step 2: Copy code and assets**

```bash
FACTORY=C:/coding/pi-agent-factory
DRONE=C:/coding/cool_physical_ai_project
for p in src/drone src/sim tests/sim tests/agent scenarios; do
  mkdir -p "$DRONE/$(dirname $p)"
  cp -r "$FACTORY/$p" "$DRONE/$(dirname $p)/"
done
mkdir -p "$DRONE/tests/integration"
cp "$FACTORY/tests/integration/test_mission_loop.py" "$DRONE/tests/integration/"
find "$DRONE" -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null || true
```

- [ ] **Step 3: Copy planning artifacts and the task ledger**

```bash
mkdir -p "$DRONE/docs/superpowers/specs" "$DRONE/docs/superpowers/plans" "$DRONE/tasks"
cp "$FACTORY/docs/superpowers/specs/2026-07-21-mission-agent-navigation-design.md" \
   "$FACTORY/docs/superpowers/specs/2026-07-30-sim-testbench-design.md" \
   "$DRONE/docs/superpowers/specs/"
cp "$FACTORY/docs/superpowers/plans/2026-07-21-mission-agent-navigation.md" \
   "$FACTORY/docs/superpowers/plans/2026-07-30-sim-testbench.md" \
   "$DRONE/docs/superpowers/plans/"
for t in 029 030 031 032 033 034 035 036 037 038 039 040 041 042 043 044 045 046 047 048 049 050 051 052; do
  cp "$FACTORY"/tasks/T-$t-*.md "$DRONE/tasks/"
done
ls "$DRONE"/tasks/T-*.md | wc -l   # expect 25: the 24 moved + the pre-existing T-001-example
```

- [ ] **Step 4: Add the sim dependencies**

In `$DRONE/pyproject.toml`, extend `dependencies` with the two entries the sim
testbench needs, keeping the existing three:

```toml
dependencies = [
  "numpy>=2.2",
  "gym-pybullet-drones @ git+https://github.com/utiasDSL/gym-pybullet-drones.git@e712698a05a80728b06572819dcf044596707754",
  # gym-pybullet-drones' BaseControl imports pkg_resources at runtime, which
  # setuptools removed in 82.0.0 (Feb 2026). Pin below that until upstream drops it.
  "setuptools<82",
  "pygame>=2.6.1",
  "matplotlib>=3.11.1",
]
```

The `sim` marker and `scripts/gates/sim_smoke.py` already exist here — do not add
them. But the incoming `tests/agent/` and `tests/integration/` carry markers this
repo does not declare, and an unregistered marker means those tests never run.
Extend `[tool.pytest.ini_options]`:

```toml
markers = [
  "unit: fast deterministic tests",
  "sim: pybullet simulation tests",
  "agent: agent decision tests with mocked LLM",
  "integration: cross-component tests",
]
```

- [ ] **Step 5: Verify the drone repo runs its own suite**

Run: `cd C:/coding/cool_physical_ai_project && uv run pytest -m unit -q`
Expected: PASS. If imports fail, fix the import paths in the copied modules — they
referenced the factory's layout and both repos use `src/` layout, so this should be
a no-op; investigate any failure rather than deleting the test.

Run: `uv run ruff check .`
Expected: `All checks passed!`

- [ ] **Step 6: Commit in the drone repo**

```bash
cd C:/coding/cool_physical_ai_project
git add -A
git commit -m "feat: import drone implementation from pi-agent-factory@<SHA>

The drone simulation testbench, mission agent, navigation stack, scenarios and
their task ledger were built inside pi-agent-factory after the factory was
extracted from this repo. They belong beside the requirement they satisfy.

Per-file history remains readable in pi-agent-factory at the SHA above; this is
a deliberate import rather than a history rewrite.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

Record the resulting SHA for Task 3's commit message.

---

### Task 3: Remove the drone artifacts from the factory

**Files (in `C:/coding/pi-agent-factory`):**
- Delete: `src/drone/`, `src/sim/`, `tests/sim/`, `scenarios/`
- Delete: `scripts/gates/sim_smoke.py`
- Delete: `docs/superpowers/specs/2026-07-21-mission-agent-navigation-design.md`, `…/2026-07-30-sim-testbench-design.md`
- Delete: `docs/superpowers/plans/2026-07-21-mission-agent-navigation.md`, `…/2026-07-30-sim-testbench.md`
- Delete: `tasks/T-029…T-052` (the 24)
- Modify: `pyproject.toml` (drop `pygame`, `matplotlib`, drop the `sim` marker)

**Interfaces:**
- Consumes: Task 1's `GATE_NOT_APPLICABLE`, which is what allows the sim gate to disappear safely.
- Produces: a factory containing only the factory.

- [ ] **Step 1: Remove the paths**

```bash
cd C:/coding/pi-agent-factory
git rm -r -q src/drone src/sim tests/sim tests/agent scenarios scripts/gates/sim_smoke.py
git rm -q tests/integration/test_mission_loop.py
git rm -q docs/superpowers/specs/2026-07-21-mission-agent-navigation-design.md \
          docs/superpowers/specs/2026-07-30-sim-testbench-design.md \
          docs/superpowers/plans/2026-07-21-mission-agent-navigation.md \
          docs/superpowers/plans/2026-07-30-sim-testbench.md
for t in 029 030 031 032 033 034 035 036 037 038 039 040 041 042 043 044 045 046 047 048 049 050 051 052; do
  git rm -q tasks/T-$t-*.md
done
ls tasks/T-*.md | wc -l   # expect 21
```

- [ ] **Step 2: Drop the sim dependencies and marker**

In `pyproject.toml`, remove these two lines from `dependencies`:

```toml
  "pygame>=2.6.1",
  "matplotlib>=3.11.1",
```

and remove the `sim` and `agent` markers from `[tool.pytest.ini_options]` — every
test carrying either is a drone test — leaving:

```toml
markers = [
  "unit: fast deterministic tests",
]
```

- [ ] **Step 3: Find anything still referencing the drone**

Run:

```bash
grep -rn "src/sim\|src/drone\|tests/sim\|scenarios/\|pygame\|matplotlib" \
  --include="*.py" --include="*.toml" --include="*.ts" \
  src tests scripts pi-ext/factory-watch/src pyproject.toml | grep -v node_modules
```
Expected: no hits. Every hit is live code or config still pointing at the drone and
must be resolved before committing — a hit in `docs/` or `kb/` is historical prose
and is fine, which is why they are excluded from this grep.

- [ ] **Step 4: Verify the factory is green**

Run: `uv run pytest -m unit -q --ignore=tests/gates`
Expected: PASS.

Run: `uv run ruff check .` and `uv run pyright`
Expected: clean.

Run: `uv run pytest tests/gates -q`
Expected: PASS — the gate scripts must still work with `sim_smoke.py` gone.

- [ ] **Step 5: Prove the not-applicable path against the real repo**

Run:

```bash
uv run python -c "
from pathlib import Path
from factory.orchestrator.backends import GATE_NOT_APPLICABLE, SubprocessGateRunner
r = SubprocessGateRunner(Path('.')).run('sim')
print('sim gate ->', r, '(GATE_NOT_APPLICABLE)' if r == GATE_NOT_APPLICABLE else '(RAN)')
assert r == GATE_NOT_APPLICABLE
"
```
Expected: `sim gate -> -1 (GATE_NOT_APPLICABLE)`. This is the check that the factory
can still run a task after the drone left; without it, validation would fail every task.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "refactor: move the drone implementation out to cool_physical_ai_project

The drone simulation testbench, mission agent, navigation stack, scenarios, their
two product specs and plans, and their 24 tasks now live in the product repo at
<DRONE-SHA>, beside the requirement they satisfy.

The factory keeps the mechanism: lint/typecheck/unit/agent gates, the orchestrator
and the extension. It no longer declares a sim marker, ships a sim gate, or depends
on pygame/matplotlib. A project that provides no sim gate is now reported as
not-applicable rather than failing validation.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 4: Verify the separation end to end

**Files:** none — verification only.

**Interfaces:**
- Consumes: both repositories at their new HEADs.

- [ ] **Step 1: Factory contains only the factory**

Run: `ls src/` in the factory.
Expected: `factory/` and the egg-info only — no `drone/`, no `sim/`.

Run: `uv run python -m factory.trace status | head -8`
Expected: a graph with 21 tasks and no drone artifacts. `task->plan` may now be
below 21/21 if a moved plan was some remaining task's `source_plan`; if so, those
gaps are real and belong to `/trace-fix`, not to this plan.

- [ ] **Step 2: Drone repo holds the product and its ledger**

Run: `cd C:/coding/cool_physical_ai_project && uv run pytest -m unit -q`
Expected: PASS.

Run: `uv run python -m factory.trace status --project-root C:/coding/cool_physical_ai_project`

(from the factory checkout, since `factory.trace` is factory code)
Expected: a graph containing the 24 moved tasks, the 2 moved plans, the 2 moved
specs and `SR-001`, with `task->SR` near zero — the true state, and the reason the
doctor pass exists.

- [ ] **Step 3: The extension still passes**

Run: `npm test --prefix pi-ext/factory-watch` and `npm run typecheck --prefix pi-ext/factory-watch`
Expected: PASS and clean.

- [ ] **Step 4: Record the outcome**

Report both repos' gate results and both `factory trace status` outputs verbatim.
Do not describe the split as complete unless every command above passed; if any
did not, say which and stop.

---

## What this plan deliberately does not do

- **The doctor pass.** Inferring requirements per behaviour from specs is the next
  spec; this plan only makes it safe to run by ensuring drone specs live in the
  drone repo.
- **Making the drone repo a full factory target.** Vendoring `.pi/skills/`,
  authoring `.factory/factory.yaml`, and implementing the `HARNESSES`/`PLAYGROUNDS`
  registry from `2026-07-31-polish-workflow-and-validation-node-design.md` §3
  remain open.
- **Fixing `factory requirements new`'s drone-specific binding template**, which
  still hardcodes `sim-testbench`, `preemption_success_rate` and `shark_detected`.
- **Resolving `SR-001`'s dangling `upstream: [BR-002]`.**
