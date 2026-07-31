# System-Requirement Validation — 1B (automated face in factory-run) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire the automated requirement-validation face into `factory-run`: after the sim/integration gates pass, `run_validation` runs the **full SR suite** (from `.factory/factory.yaml` harnesses + the `requirements/` register), writes `validation-report.json`, **fails the node on ANY red SR** (strict standing gate), and folds a `requirements[]` block into `review-guide.json`. Plus a `binding.trials` declared-vs-actual guard and a `factory validate --all` full-sweep CLI.

**Architecture:** Additive and backward-compatible. `run_validation` gains optional `repo_root`/`satisfies`/`transcript_dir`; when `repo_root` is None (existing tests/callers) it behaves exactly as today. When given, it calls a new `factory.validation.pipeline.validate_task_requirements`, which loads harnesses via P2's config (`factory.polish.config.load_config`) + the register, selects the SRs to run (all `cadence: every_iteration` SRs + the task's `satisfies:`, or everything on a full sweep), runs them through the existing `run_requirement_validation`, and reports pass/fail. A repo with no register/config runs zero SRs → PASS.

**Tech Stack:** Python 3.11–3.12, stdlib, `pyyaml`/`python-frontmatter` (existing), `pytest` (`-m unit`).

## Global Constraints

- Python `>=3.11,<3.13`; every new module starts with `from __future__ import annotations`.
- Ruff `line-length = 100`; run `uv run ruff format <files>` before committing (format-check must pass).
- Unit tests: `pytestmark = pytest.mark.unit`; run with `uv run pytest` (default `-m unit`).
- No new dependencies.
- **Backward compatibility is binding:** existing `run_validation(gates, task_id, status=...)` call sites and tests MUST keep working — the new params are keyword-only with defaults, and `repo_root=None` skips all requirement work.
- Source under `src/factory/`; tests under `tests/unit/`.
- **Work in the isolated worktree** `C:/coding/pi-agent-factory-wt/b1` on branch `feat/req-validation-1b`. Prefix commands with `cd /c/coding/pi-agent-factory-wt/b1 &&`. Commit only each task's files; revert `uv.lock` churn before committing.
- Base contains 1A (`src/factory/{requirements,validation}/…`) and P2 (`src/factory/polish/config.py` with `load_config`).
- **REQ_REVIEW LLM role is OUT of scope** (a later increment).

---

### Task 1: Requirement data — `Binding.cadence` + declared-vs-actual trials

**Files:**
- Modify: `src/factory/requirements/register.py` (`Binding` + `_parse_binding`)
- Modify: `src/factory/validation/report.py` (`run_requirement_validation` entry)
- Test: `tests/unit/requirements/test_register.py` (extend), `tests/unit/validation/test_report.py` (extend)

**Interfaces:**
- `Binding` gains `cadence: str = "every_iteration"` (values `"every_iteration"` | `"periodic"`), parsed from `binding.cadence` (default `"every_iteration"`).
- `run_requirement_validation` entry gains `declared_trials: int` (= `binding.trials`) and its `passed` becomes `result.passed AND len(result.trials) >= binding.trials` — so an SR scored on fewer trials than it declares is NOT passed.

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/requirements/test_register.py`:

```python
def test_binding_cadence_defaults_and_parses(tmp_path):
    from factory.requirements.register import parse_requirement

    base = _SR  # existing module-level template with a full binding
    p = tmp_path / "SR-009.md"
    p.write_text(base.replace("SR-001", "SR-009"), encoding="utf-8")
    assert parse_requirement(p).binding.cadence == "every_iteration"  # default

    p2 = tmp_path / "SR-010.md"
    p2.write_text(base.replace("SR-001", "SR-010").replace(
        'assert: ">= 0.90"', 'assert: ">= 0.90"\n  cadence: periodic'), encoding="utf-8")
    assert parse_requirement(p2).binding.cadence == "periodic"
```

Append to `tests/unit/validation/test_report.py`:

```python
def test_report_flags_trials_shortfall(tmp_path):
    # SR declares trials: 5 but the fixture has only the 2 GOOD trials → not passed.
    req_dir = tmp_path / "requirements"
    req_dir.mkdir()
    stub = req_dir / "SR-001.md"
    text = _SR.format(ck="null").replace("trials: 2", "trials: 5")
    stub.write_text(text, encoding="utf-8")
    from factory.requirements.register import content_checksum, load_register, parse_requirement
    ck = content_checksum(parse_requirement(stub))
    stub.write_text(text.replace("checksum: null", f"checksum: {ck}"), encoding="utf-8")
    traces = tmp_path / "traces"
    traces.mkdir()
    (traces / "shark_warning.json").write_text(
        json.dumps({"trials": [{"seed": 0, "frames": GOOD}, {"seed": 1, "frames": GOOD}]}),
        encoding="utf-8",
    )
    reqs = load_register(req_dir)
    report = run_requirement_validation(["SR-001"], reqs, default_harness_for(traces), tmp_path)
    entry = report["requirements"][0]
    assert entry["declared_trials"] == 5
    assert entry["trials"] == 2
    assert entry["passed"] is False   # metric passed but too few trials
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /c/coding/pi-agent-factory-wt/b1 && uv run pytest tests/unit/requirements/test_register.py tests/unit/validation/test_report.py -q`
Expected: FAIL — `Binding` has no `cadence`; report entry has no `declared_trials` and `passed` is True.

- [ ] **Step 3: Implement**

In `src/factory/requirements/register.py`, add the field to `Binding` (after `window`):

```python
@dataclass(frozen=True)
class Binding:
    harness: str
    experiment: str
    metric: str
    assert_expr: str
    trials: int = 1
    window: dict | None = None
    cadence: str = "every_iteration"
```

In `_parse_binding`, pass it:

```python
        window=raw.get("window"),
        cadence=str(raw.get("cadence", "every_iteration")),
    )
```

In `src/factory/validation/report.py`, update the entry dict inside `run_requirement_validation`:

```python
        actual_trials = len(result.trials)
        entries.append(
            {
                "id": req.id,
                "domain": req.domain,
                "metric": req.binding.metric,
                "value": result.metric_value,
                "assert": req.binding.assert_expr,
                "passed": result.passed and actual_trials >= req.binding.trials,
                "trials": actual_trials,
                "declared_trials": req.binding.trials,
                "stale": not is_checksum_current(req),
                "artifacts": [str(a) for a in result.artifacts],
            }
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /c/coding/pi-agent-factory-wt/b1 && uv run pytest tests/unit/requirements tests/unit/validation -q`
Expected: PASS (new tests green; existing register/report tests still green — the default cadence and the extra field don't break them).

- [ ] **Step 5: Format + commit**

```bash
cd /c/coding/pi-agent-factory-wt/b1
uv run ruff format src/factory/requirements/register.py src/factory/validation/report.py tests/unit/requirements/test_register.py tests/unit/validation/test_report.py
git checkout -- uv.lock 2>/dev/null || true
git add src/factory/requirements/register.py src/factory/validation/report.py tests/unit/requirements/test_register.py tests/unit/validation/test_report.py
git commit -m "feat(validation): Binding.cadence + declared-vs-actual trials guard in the report"
```

---

### Task 2: `validation/pipeline.py` — SR selection + suite run

**Files:**
- Create: `src/factory/validation/pipeline.py`
- Test: `tests/unit/validation/test_pipeline.py`

**Interfaces:**
- Consumes: `factory.requirements.register.load_register`, `factory.polish.config.load_config` (P2), `factory.validation.report.run_requirement_validation` (Task 1).
- Produces:
  - `select_requirement_ids(reqs, satisfies, *, full_sweep=False) -> list[str]` — all reqs with `binding.cadence == "every_iteration"` (or all reqs when `full_sweep`), plus every id in `satisfies` (deduped, order-stable).
  - `validate_task_requirements(repo_root, satisfies, *, full_sweep=False) -> tuple[dict, bool]` — loads the register (`repo_root/requirements`) and the config harnesses; builds `harness_for` (raising a clear `ValueError` for a harness name absent from `.factory/factory.yaml`); runs `run_requirement_validation` over the selected ids; returns `(report, ok)` where `ok` is True iff every entry has `passed is True` (an `error` entry or a failed SR ⇒ not ok). Empty selection ⇒ `({"requirements": []}, True)`.
- **Note (layering):** `load_config` currently lives in `factory.polish.config`; importing it here is acceptable (no import cycle — `polish.config` does not import this module), but flag that config is really a project-level concern that could move to `factory.config` later.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/validation/test_pipeline.py`:

```python
import json

import pytest
from factory.requirements.register import content_checksum, load_register, parse_requirement
from factory.validation.pipeline import select_requirement_ids, validate_task_requirements

pytestmark = pytest.mark.unit

_SR = """---
id: {id}
title: "t"
statement: "When a shark is detected in a swim zone, nav shall preempt patrol."
domain: behavioral
upstream: []
binding:
  harness: sim-testbench
  experiment: shark_warning
  metric: preemption_success_rate
  trials: 2
  assert: ">= 0.90"
  window: {{after_event: shark_detected, within_s: 5}}
  cadence: {cadence}
checksum: {ck}
---
body
"""

_CONFIG = """
harnesses:
  sim:
    type: sim-testbench
    traces_dir: traces
"""


def _f(t, kind, sharks=()):
    return {"mission_clock": t, "active_directive": {"kind": kind},
            "detections": [{"label": "shark", "confidence": c} for c in sharks]}


GOOD = [_f(0, "patrol"), _f(15, "patrol", (0.45,)), _f(17, "override"), _f(40, "patrol")]


def _write_sr(req_dir, sr_id, cadence):
    stub = req_dir / f"{sr_id}.md"
    stub.write_text(_SR.format(id=sr_id, cadence=cadence, ck="null"), encoding="utf-8")
    ck = content_checksum(parse_requirement(stub))
    stub.write_text(_SR.format(id=sr_id, cadence=cadence, ck=ck), encoding="utf-8")


def _project(tmp_path):
    req = tmp_path / "requirements"
    req.mkdir()
    _write_sr(req, "SR-001", "every_iteration")
    _write_sr(req, "SR-002", "periodic")
    fac = tmp_path / ".factory"
    fac.mkdir()
    (fac / "factory.yaml").write_text(_CONFIG, encoding="utf-8")
    traces = tmp_path / "traces"
    traces.mkdir()
    (traces / "shark_warning.json").write_text(
        json.dumps({"trials": [{"seed": 0, "frames": GOOD}, {"seed": 1, "frames": GOOD}]}),
        encoding="utf-8",
    )
    return tmp_path


def test_select_every_iteration_plus_satisfies(tmp_path):
    _project(tmp_path)
    reqs = load_register(tmp_path / "requirements")
    assert select_requirement_ids(reqs, []) == ["SR-001"]                 # periodic excluded
    assert select_requirement_ids(reqs, ["SR-002"]) == ["SR-001", "SR-002"]  # satisfies pulls it in
    assert sorted(select_requirement_ids(reqs, [], full_sweep=True)) == ["SR-001", "SR-002"]


def test_validate_task_requirements_ok(tmp_path):
    _project(tmp_path)
    report, ok = validate_task_requirements(tmp_path, ["SR-001"])
    assert ok is True
    assert [e["id"] for e in report["requirements"]] == ["SR-001"]


def test_validate_empty_when_no_register(tmp_path):
    report, ok = validate_task_requirements(tmp_path, [])
    assert report == {"requirements": []} and ok is True


def test_unknown_harness_makes_it_not_ok(tmp_path):
    _project(tmp_path)
    (tmp_path / ".factory" / "factory.yaml").write_text("harnesses: {}\n", encoding="utf-8")
    report, ok = validate_task_requirements(tmp_path, ["SR-001"])
    assert ok is False
    assert "error" in report["requirements"][0]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /c/coding/pi-agent-factory-wt/b1 && uv run pytest tests/unit/validation/test_pipeline.py -q`
Expected: FAIL — `No module named 'factory.validation.pipeline'`.

- [ ] **Step 3: Implement**

Create `src/factory/validation/pipeline.py`:

```python
from __future__ import annotations

from pathlib import Path

from factory.polish.config import load_config
from factory.requirements.register import Requirement, load_register
from factory.validation.harness import Harness
from factory.validation.report import run_requirement_validation


def select_requirement_ids(
    reqs: list[Requirement], satisfies: list[str], *, full_sweep: bool = False
) -> list[str]:
    ids: list[str] = []
    for r in reqs:
        if full_sweep or r.binding.cadence == "every_iteration":
            ids.append(r.id)
    for sid in satisfies:  # a task's own SRs always run, even if periodic
        if sid not in ids:
            ids.append(sid)
    return ids


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

    ids = select_requirement_ids(reqs, satisfies, full_sweep=full_sweep)
    report = run_requirement_validation(ids, reqs, harness_for, repo_root)
    ok = all(e.get("passed") is True for e in report["requirements"])
    return report, ok
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /c/coding/pi-agent-factory-wt/b1 && uv run pytest tests/unit/validation/test_pipeline.py -q`
Expected: PASS (4 passed).

- [ ] **Step 5: Format + commit**

```bash
cd /c/coding/pi-agent-factory-wt/b1
uv run ruff format src/factory/validation/pipeline.py tests/unit/validation/test_pipeline.py
git checkout -- uv.lock 2>/dev/null || true
git add src/factory/validation/pipeline.py tests/unit/validation/test_pipeline.py
git commit -m "feat(validation): pipeline SR selection + validate_task_requirements (config-driven harnesses)"
```

---

### Task 3: Extend `run_validation` to run the SR suite

**Files:**
- Modify: `src/factory/orchestrator/nodes.py` (`run_validation`)
- Test: `tests/unit/orchestrator/test_nodes_requirement_validation.py`

**Interfaces:**
- `run_validation(gates, task_id="", status=NullStatusReporter(), *, repo_root: Path | None = None, satisfies: list[str] | None = None, transcript_dir: Path | None = None) -> tuple[NodeOutcome, NodeEvent]` — after the existing sim+integration gates pass, if `repo_root is not None` it calls `validate_task_requirements(repo_root, satisfies or [])`, writes `validation-report.json` to `transcript_dir` (when given), and returns `NodeOutcome.FAIL` (event `extra={"failed_requirements": [...ids]}`) if any SR is red, else PASS. `repo_root=None` ⇒ unchanged behavior.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/orchestrator/test_nodes_requirement_validation.py`:

```python
import json

import pytest
from factory.orchestrator.nodes import run_validation
from factory.orchestrator.types import NodeOutcome

pytestmark = pytest.mark.unit


class _Gates:
    def run(self, name):
        return 0  # all gates green


def _f(t, kind, sharks=()):
    return {"mission_clock": t, "active_directive": {"kind": kind},
            "detections": [{"label": "shark", "confidence": c} for c in sharks]}


GOOD = [_f(0, "patrol"), _f(15, "patrol", (0.45,)), _f(17, "override"), _f(40, "patrol")]
BAD = [_f(0, "patrol"), _f(20, "patrol")]  # no trigger → preemption fails

_SR = """---
id: SR-001
title: t
statement: "When a shark is detected in a swim zone, nav shall preempt patrol."
domain: behavioral
upstream: []
binding:
  harness: sim-testbench
  experiment: shark_warning
  metric: preemption_success_rate
  trials: 2
  assert: ">= 0.90"
  window: {{after_event: shark_detected, within_s: 5}}
checksum: {ck}
---
body
"""

_CONFIG = "harnesses:\n  sim:\n    type: sim-testbench\n    traces_dir: traces\n"


def _project(tmp_path, trials):
    from factory.requirements.register import content_checksum, parse_requirement

    req = tmp_path / "requirements"
    req.mkdir()
    stub = req / "SR-001.md"
    stub.write_text(_SR.format(ck="null"), encoding="utf-8")
    ck = content_checksum(parse_requirement(stub))
    stub.write_text(_SR.format(ck=ck), encoding="utf-8")
    (tmp_path / ".factory").mkdir()
    (tmp_path / ".factory" / "factory.yaml").write_text(_CONFIG, encoding="utf-8")
    traces = tmp_path / "traces"
    traces.mkdir()
    (traces / "shark_warning.json").write_text(
        json.dumps({"trials": [{"seed": i, "frames": fr} for i, fr in enumerate(trials)]}),
        encoding="utf-8",
    )
    return tmp_path


def test_backward_compatible_without_repo_root():
    outcome, ev = run_validation(_Gates(), "T-1")
    assert outcome == NodeOutcome.PASS   # no requirement work when repo_root is None


def test_passes_when_sr_green(tmp_path):
    _project(tmp_path, [GOOD, GOOD])
    td = tmp_path / "td"
    td.mkdir()
    outcome, ev = run_validation(_Gates(), "T-1", repo_root=tmp_path,
                                 satisfies=["SR-001"], transcript_dir=td)
    assert outcome == NodeOutcome.PASS
    report = json.loads((td / "validation-report.json").read_text(encoding="utf-8"))
    assert report["requirements"][0]["passed"] is True


def test_fails_when_sr_red(tmp_path):
    _project(tmp_path, [GOOD, BAD])  # rate 0.5 < 0.90
    outcome, ev = run_validation(_Gates(), "T-1", repo_root=tmp_path, satisfies=["SR-001"])
    assert outcome == NodeOutcome.FAIL
    assert ev.extra["failed_requirements"] == ["SR-001"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /c/coding/pi-agent-factory-wt/b1 && uv run pytest tests/unit/orchestrator/test_nodes_requirement_validation.py -q`
Expected: FAIL — `run_validation` doesn't accept `repo_root`.

- [ ] **Step 3: Implement**

In `src/factory/orchestrator/nodes.py`, add imports near the top:

```python
from factory.validation.pipeline import validate_task_requirements
from factory.validation.report import write_validation_report
```

Replace the `run_validation` function with:

```python
def run_validation(
    gates: GateRunner,
    task_id: str = "",
    status: StatusReporter = NullStatusReporter(),
    *,
    repo_root: Path | None = None,
    satisfies: list[str] | None = None,
    transcript_dir: Path | None = None,
) -> tuple[NodeOutcome, NodeEvent]:
    status.report(task_id=task_id, node="validation", node_state="running", attempt=1, max_attempts=1,
                 handoff="running sim + integration gates")
    if gates.run("sim") != 0:
        status.report(task_id=task_id, node="validation", node_state="fail", attempt=1, max_attempts=1,
                     handoff="sim tests failed")
        return NodeOutcome.FAIL, NodeEvent("validation", "fail")
    if gates.run("integration") != 0:
        status.report(task_id=task_id, node="validation", node_state="fail", attempt=1, max_attempts=1,
                     handoff="integration tests failed")
        return NodeOutcome.FAIL, NodeEvent("validation", "fail")

    if repo_root is not None:
        report, ok = validate_task_requirements(repo_root, satisfies or [])
        if transcript_dir is not None:
            write_validation_report(transcript_dir / "validation-report.json", report)
        if not ok:
            reds = [e["id"] for e in report["requirements"] if e.get("passed") is not True]
            status.report(task_id=task_id, node="validation", node_state="fail", attempt=1, max_attempts=1,
                         handoff=f"requirements failed: {', '.join(reds)}")
            return NodeOutcome.FAIL, NodeEvent("validation", "fail", 1, {"failed_requirements": reds})

    status.report(task_id=task_id, node="validation", node_state="pass", attempt=1, max_attempts=1,
                 handoff="→ review: sim + integration + requirements green")
    return NodeOutcome.PASS, NodeEvent("validation", "pass")
```

Ensure `from pathlib import Path` is imported in `nodes.py` (it already is — verify).

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /c/coding/pi-agent-factory-wt/b1 && uv run pytest tests/unit/orchestrator/test_nodes_requirement_validation.py tests/unit/orchestrator/test_nodes_val_review.py -q`
Expected: PASS (new tests green; the existing `test_nodes_val_review.py` still green — backward compatible).

- [ ] **Step 5: Format + commit**

```bash
cd /c/coding/pi-agent-factory-wt/b1
uv run ruff format src/factory/orchestrator/nodes.py tests/unit/orchestrator/test_nodes_requirement_validation.py
git checkout -- uv.lock 2>/dev/null || true
git add src/factory/orchestrator/nodes.py tests/unit/orchestrator/test_nodes_requirement_validation.py
git commit -m "feat(orchestrator): run_validation runs the SR suite + fails on any red requirement"
```

---

### Task 4: Wire into `runner.py` + fold `requirements[]` into `review-guide.json`

**Files:**
- Modify: `src/factory/orchestrator/runner.py` (the `run_validation` call + feedback + guide build)
- Modify: `src/factory/orchestrator/review_guide.py` (add `read_requirements_report`)
- Test: `tests/unit/orchestrator/test_review_guide.py` (extend, for the new reader)

**Interfaces:**
- `review_guide.read_requirements_report(transcript_dir: Path) -> list[dict]` — returns the `requirements` array from `transcript_dir/validation-report.json`, or `[]` if the file is missing/unreadable.
- `runner.run_task` passes `repo_root=repo_root, satisfies=task.satisfies, transcript_dir=transcript_dir` to `run_validation`; on FAIL, its `feedback` names the failed requirements when present; the review-guide dict gains `"requirements": read_requirements_report(transcript_dir)`.

- [ ] **Step 1: Write the failing test** (append to `tests/unit/orchestrator/test_review_guide.py`)

```python
def test_read_requirements_report(tmp_path):
    import json

    from factory.orchestrator.review_guide import read_requirements_report

    assert read_requirements_report(tmp_path) == []  # missing file → []
    (tmp_path / "validation-report.json").write_text(
        json.dumps({"requirements": [{"id": "SR-001", "passed": True}]}), encoding="utf-8"
    )
    got = read_requirements_report(tmp_path)
    assert got == [{"id": "SR-001", "passed": True}]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /c/coding/pi-agent-factory-wt/b1 && uv run pytest tests/unit/orchestrator/test_review_guide.py -q`
Expected: FAIL — `read_requirements_report` doesn't exist.

- [ ] **Step 3: Implement**

In `src/factory/orchestrator/review_guide.py`, add:

```python
def read_requirements_report(transcript_dir: Path) -> list[dict]:
    path = transcript_dir / "validation-report.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    reqs = data.get("requirements", [])
    return reqs if isinstance(reqs, list) else []
```

In `src/factory/orchestrator/runner.py`:

Update the import from `review_guide` to include the new reader:

```python
from factory.orchestrator.review_guide import (
    read_requirements_report,
    read_validation,
    write_review_guide,
)
```

Change the `run_validation` call (currently `v_outcome, v_ev = run_validation(gates, task.id, status=status)`) to:

```python
            v_outcome, v_ev = run_validation(
                gates, task.id, status=status,
                repo_root=repo_root, satisfies=task.satisfies, transcript_dir=transcript_dir,
            )
```

Change the FAIL feedback (currently `feedback = "functional/sim tests failed"`) to name failed requirements when present:

```python
            if v_outcome == NodeOutcome.FAIL:
                reds = v_ev.extra.get("failed_requirements")
                feedback = (
                    "requirements failed: " + ", ".join(reds)
                    if reds else "functional/sim tests failed"
                )
                continue
```

Add `requirements` to the guide dict:

```python
            guide = {
                "confidence": r_ev.extra.get("confidence") if r_ev is not None else None,
                "verify": r_ev.extra.get("verify", []) if r_ev is not None else [],
                "validation": read_validation(transcript_dir),
                "requirements": read_requirements_report(transcript_dir),
                "addressed": list(dict.fromkeys(addressed)),  # dedup, keep order
            }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /c/coding/pi-agent-factory-wt/b1 && uv run pytest tests/unit/orchestrator/test_review_guide.py tests/unit/orchestrator/test_runner_e2e.py tests/unit/orchestrator/test_run_next.py -q`
Expected: PASS — new reader test green; existing runner tests still green (the extra `run_validation` kwargs and the extra guide key don't break them; if a runner test constructs a repo without `requirements/`, the SR suite is empty → PASS, unchanged).

- [ ] **Step 5: Format + commit**

```bash
cd /c/coding/pi-agent-factory-wt/b1
uv run ruff format src/factory/orchestrator/runner.py src/factory/orchestrator/review_guide.py tests/unit/orchestrator/test_review_guide.py
git checkout -- uv.lock 2>/dev/null || true
git add src/factory/orchestrator/runner.py src/factory/orchestrator/review_guide.py tests/unit/orchestrator/test_review_guide.py
git commit -m "feat(orchestrator): thread SR validation through run_task + fold requirements[] into review-guide.json"
```

---

### Task 5: `factory validate --all` full-sweep CLI

**Files:**
- Create: `src/factory/validation/cli.py`
- Create: `src/factory/validation/__main__.py`
- Test: `tests/unit/validation/test_validation_cli.py`

**Interfaces:**
- `cmd_validate(project_root: Path, *, full_sweep: bool, satisfies: list[str] | None = None) -> tuple[dict, bool]` — runs `validate_task_requirements`, writes `project_root/validation/validation-report.json` (via `write_validation_report`), returns `(report, ok)`.
- `main(argv: list[str] | None = None) -> int` — argparse; subcommand `run` with `--project-root` (default `.`), `--all` (full sweep), and repeatable `--satisfies SR-###`. Prints the report JSON; returns `0` when ok else `1`.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/validation/test_validation_cli.py`:

```python
import json

import pytest
from factory.requirements.register import content_checksum, parse_requirement
from factory.validation.cli import cmd_validate, main

pytestmark = pytest.mark.unit

_SR = """---
id: SR-001
title: t
statement: "When a shark is detected in a swim zone, nav shall preempt patrol."
domain: behavioral
upstream: []
binding:
  harness: sim-testbench
  experiment: shark_warning
  metric: preemption_success_rate
  trials: 2
  assert: ">= 0.90"
  window: {{after_event: shark_detected, within_s: 5}}
checksum: {ck}
---
body
"""


def _f(t, kind, sharks=()):
    return {"mission_clock": t, "active_directive": {"kind": kind},
            "detections": [{"label": "shark", "confidence": c} for c in sharks]}


GOOD = [_f(0, "patrol"), _f(15, "patrol", (0.45,)), _f(17, "override"), _f(40, "patrol")]


def _project(tmp_path):
    req = tmp_path / "requirements"
    req.mkdir()
    stub = req / "SR-001.md"
    stub.write_text(_SR.format(ck="null"), encoding="utf-8")
    ck = content_checksum(parse_requirement(stub))
    stub.write_text(_SR.format(ck=ck), encoding="utf-8")
    (tmp_path / ".factory").mkdir()
    (tmp_path / ".factory" / "factory.yaml").write_text(
        "harnesses:\n  sim:\n    type: sim-testbench\n    traces_dir: traces\n", encoding="utf-8")
    traces = tmp_path / "traces"
    traces.mkdir()
    (traces / "shark_warning.json").write_text(
        json.dumps({"trials": [{"seed": 0, "frames": GOOD}, {"seed": 1, "frames": GOOD}]}),
        encoding="utf-8",
    )
    return tmp_path


def test_cmd_validate_all_writes_report(tmp_path):
    _project(tmp_path)
    report, ok = cmd_validate(tmp_path, full_sweep=True)
    assert ok is True
    assert [e["id"] for e in report["requirements"]] == ["SR-001"]
    on_disk = json.loads((tmp_path / "validation" / "validation-report.json").read_text(encoding="utf-8"))
    assert on_disk == report


def test_main_returns_exit_code(tmp_path, capsys):
    _project(tmp_path)
    rc = main(["run", "--project-root", str(tmp_path), "--all"])
    assert rc == 0
    assert "SR-001" in capsys.readouterr().out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /c/coding/pi-agent-factory-wt/b1 && uv run pytest tests/unit/validation/test_validation_cli.py -q`
Expected: FAIL — `No module named 'factory.validation.cli'`.

- [ ] **Step 3: Implement**

Create `src/factory/validation/cli.py`:

```python
from __future__ import annotations

import argparse
import json
from pathlib import Path

from factory.validation.pipeline import validate_task_requirements
from factory.validation.report import write_validation_report


def cmd_validate(
    project_root: Path, *, full_sweep: bool, satisfies: list[str] | None = None
) -> tuple[dict, bool]:
    report, ok = validate_task_requirements(project_root, satisfies or [], full_sweep=full_sweep)
    write_validation_report(project_root / "validation" / "validation-report.json", report)
    return report, ok


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="factory-validate")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_run = sub.add_parser("run")
    p_run.add_argument("--project-root", default=Path("."), type=Path)
    p_run.add_argument("--all", action="store_true", help="full sweep (include periodic SRs)")
    p_run.add_argument("--satisfies", action="append", default=[], metavar="SR-###")
    args = parser.parse_args(argv)

    report, ok = cmd_validate(args.project_root, full_sweep=args.all, satisfies=args.satisfies)
    print(json.dumps(report, indent=2))
    return 0 if ok else 1
```

Create `src/factory/validation/__main__.py`:

```python
from __future__ import annotations

import sys

from factory.validation.cli import main

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /c/coding/pi-agent-factory-wt/b1 && uv run pytest tests/unit/validation/test_validation_cli.py -q`
Expected: PASS (2 passed).

- [ ] **Step 5: Format + commit**

```bash
cd /c/coding/pi-agent-factory-wt/b1
uv run ruff format src/factory/validation/cli.py src/factory/validation/__main__.py tests/unit/validation/test_validation_cli.py
git checkout -- uv.lock 2>/dev/null || true
git add src/factory/validation/cli.py src/factory/validation/__main__.py tests/unit/validation/test_validation_cli.py
git commit -m "feat(validation): factory validate --all full-sweep CLI"
```

---

## Final verification

- [ ] Full unit suite: `cd /c/coding/pi-agent-factory-wt/b1 && uv run pytest -q --ignore=tests/gates` — all green (new tests + existing orchestrator/validation/requirements untouched-in-behavior).
- [ ] Lint + types: `uv run ruff check src/factory tests/unit/validation tests/unit/orchestrator/test_nodes_requirement_validation.py` , `uv run ruff format --check` on the changed files, `uv run pyright src/factory/validation/pipeline.py src/factory/validation/cli.py`.

## Self-review notes (coverage vs. decisions)

- Strict standing gate — ANY red SR fails the node (user decision) → Task 3 (`ok` requires every entry passed; FAIL names reds).
- Full-suite every iteration + `cadence: periodic` opt-out → Tasks 1 (cadence field) + 2 (selection).
- `binding.trials` declared-vs-actual guard → Task 1.
- `validation-report.json` written in-pipeline + folded into `review-guide.json` → Tasks 3 + 4.
- Config-driven harnesses (P2) as the harness source → Task 2 (`load_config`).
- `factory validate --all` on-demand full sweep → Task 5.
- Backward compatible (no register/config → PASS) → Tasks 2/3.
- **Deferred (out of scope):** `REQ_REVIEW` LLM role; migrating the drone repo's `validate_requirements.py`/SR-001 to a `.factory/factory.yaml` sim-testbench harness (a drone-repo change — required for the drone's SRs to validate in-pipeline, but not a factory change); moving `load_config` out of `factory.polish` to a neutral `factory.config` (layering); the TS rendering of the `requirements[]` review-guide block (**1C**).
```
