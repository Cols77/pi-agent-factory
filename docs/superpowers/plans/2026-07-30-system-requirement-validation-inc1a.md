# System-Requirement Validation — Increment 1A (Python spine) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up the Python core of the system-requirement layer — a parseable requirement register, an assertion evaluator, a preemption metric extractor, a fixture-backed sim-testbench harness, a validation runner that emits `validation-report.json`, `satisfies:` on tasks, and a `factory requirements` CLI — proven end-to-end on the drone case study `SR-001`.

**Architecture:** Pure, independently-testable units. A requirement is a `SR-###.md` file (EARS statement + acceptance `binding`) parsed into a `Requirement`/`Binding`. A `Harness` runs a binding and returns a `HarnessResult`; the Increment-1 `SimTestbenchHarness` reads a static recorded **trace fixture** (list of trials of frames) and scores it with a metric extractor. A validation runner walks a task's `satisfies: [SR-###]`, runs each binding, and writes `validation-report.json`. No LLM and no pipeline rewiring in this increment — that is Increment 1B.

**Tech Stack:** Python 3.11–3.12, stdlib (`dataclasses`, `hashlib`, `json`, `argparse`), `python-frontmatter` (already a dep), `pytest` (`-m unit`).

## Global Constraints

- Python `>=3.11,<3.13`; every new module starts with `from __future__ import annotations`.
- Ruff `line-length = 100`.
- All tests are unit tests: put `pytestmark = pytest.mark.unit` at module top; the suite runs with `uv run pytest` (default `addopts = -m unit`).
- Prefer `@dataclass(frozen=True)` for value types.
- **No new dependencies** — stdlib + existing `python-frontmatter` only.
- New source under `src/factory/`; new tests under `tests/unit/`.
- Frontmatter uses PyYAML, so a nested `binding:` block parses to a `dict`; the YAML key `assert` is stored on the dataclass as `assert_expr`.
- This plan is **Increment 1A** in the factory repo (`pi-agent-factory`) except **Task 8**, which adds case-study artifacts to the drone repo (`cool_physical_ai_project`). Follow-on plans: **1B** (REQ_REVIEW role + `review-guide.json` extension), **1C** (TS review surfaces). Do not build those here.

---

### Task 1: Requirement register model, parse, and checksum

**Files:**
- Create: `src/factory/requirements/__init__.py` (empty)
- Create: `src/factory/requirements/register.py`
- Test: `tests/unit/requirements/__init__.py` (empty), `tests/unit/requirements/test_register.py`

**Interfaces:**
- Produces:
  - `Binding(harness: str, experiment: str, metric: str, assert_expr: str, trials: int = 1, window: dict | None = None)` (frozen dataclass)
  - `Requirement(id, title, statement, domain, upstream: list[str], binding: Binding, body: str, path: Path, checksum: str | None = None)` (frozen dataclass)
  - `parse_requirement(path: Path) -> Requirement`
  - `content_checksum(req: Requirement) -> str` → `"sha256:<hex>"`
  - `is_checksum_current(req: Requirement) -> bool`
  - `load_register(requirements_dir: Path) -> list[Requirement]` (sorted by id, glob `SR-*.md`)
  - `get_requirement(reqs: list[Requirement], req_id: str) -> Requirement | None`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/requirements/__init__.py` (empty) and `tests/unit/requirements/test_register.py`:

```python
from pathlib import Path

import pytest
from factory.requirements.register import (
    Binding,
    content_checksum,
    get_requirement,
    is_checksum_current,
    load_register,
    parse_requirement,
)

pytestmark = pytest.mark.unit

_SR = """---
id: SR-001
title: "Nav preempts patrol for in-zone shark"
statement: "When a shark is detected inside a swim zone, the navigation system shall preempt patrol."
domain: behavioral
upstream: [BR-002]
binding:
  harness: sim-testbench
  experiment: shark_warning
  metric: preemption_success_rate
  trials: 20
  assert: ">= 0.90"
  window: {after_event: shark_detected, within_s: 5}
checksum: null
---
Rationale here.
"""


def _write(dir_: Path, name: str, text: str) -> Path:
    p = dir_ / name
    p.write_text(text, encoding="utf-8")
    return p


def test_parse_requirement_reads_binding(tmp_path):
    req = parse_requirement(_write(tmp_path, "SR-001.md", _SR))
    assert req.id == "SR-001"
    assert req.domain == "behavioral"
    assert req.upstream == ["BR-002"]
    assert isinstance(req.binding, Binding)
    assert req.binding.harness == "sim-testbench"
    assert req.binding.experiment == "shark_warning"
    assert req.binding.metric == "preemption_success_rate"
    assert req.binding.trials == 20
    assert req.binding.assert_expr == ">= 0.90"
    assert req.binding.window == {"after_event": "shark_detected", "within_s": 5}


def test_checksum_is_stable_and_detects_change(tmp_path):
    req = parse_requirement(_write(tmp_path, "SR-001.md", _SR))
    c1 = content_checksum(req)
    assert c1.startswith("sha256:")
    # Same content → same checksum
    req2 = parse_requirement(_write(tmp_path, "SR-001.md", _SR))
    assert content_checksum(req2) == c1
    # Changed statement → different checksum
    changed = _SR.replace("preempt patrol", "preempt patrol IMMEDIATELY")
    req3 = parse_requirement(_write(tmp_path, "SR-001.md", changed))
    assert content_checksum(req3) != c1


def test_is_checksum_current(tmp_path):
    # File with checksum: null is never "current"
    req = parse_requirement(_write(tmp_path, "SR-001.md", _SR))
    assert is_checksum_current(req) is False
    # File whose stored checksum matches its content is "current"
    stamped = _SR.replace("checksum: null", f"checksum: {content_checksum(req)}")
    req2 = parse_requirement(_write(tmp_path, "SR-001.md", stamped))
    assert is_checksum_current(req2) is True


def test_load_register_and_get(tmp_path):
    _write(tmp_path, "SR-001.md", _SR)
    _write(tmp_path, "SR-002.md", _SR.replace("SR-001", "SR-002"))
    reqs = load_register(tmp_path)
    assert [r.id for r in reqs] == ["SR-001", "SR-002"]
    assert get_requirement(reqs, "SR-002").id == "SR-002"
    assert get_requirement(reqs, "SR-999") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/requirements/test_register.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'factory.requirements'`.

- [ ] **Step 3: Write minimal implementation**

Create `src/factory/requirements/__init__.py` (empty). Create `src/factory/requirements/register.py`:

```python
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

import frontmatter

_REQUIRED = ("id", "title", "statement", "domain", "binding")


@dataclass(frozen=True)
class Binding:
    harness: str
    experiment: str
    metric: str
    assert_expr: str
    trials: int = 1
    window: dict | None = None


@dataclass(frozen=True)
class Requirement:
    id: str
    title: str
    statement: str
    domain: str
    upstream: list[str]
    binding: Binding
    body: str
    path: Path
    checksum: str | None = None


def _parse_binding(raw: dict) -> Binding:
    return Binding(
        harness=str(raw["harness"]),
        experiment=str(raw["experiment"]),
        metric=str(raw["metric"]),
        assert_expr=str(raw["assert"]),
        trials=int(raw.get("trials", 1)),
        window=raw.get("window"),
    )


def parse_requirement(path: Path) -> Requirement:
    post = frontmatter.load(str(path))
    meta = post.metadata
    missing = [k for k in _REQUIRED if k not in meta]
    if missing:
        raise ValueError(f"{path.name}: missing required field(s): {missing}")
    upstream = meta.get("upstream") or []
    if isinstance(upstream, str):
        upstream = [upstream]
    checksum = meta.get("checksum")
    return Requirement(
        id=str(meta["id"]),
        title=str(meta["title"]),
        statement=str(meta["statement"]),
        domain=str(meta["domain"]),
        upstream=[str(u) for u in upstream],
        binding=_parse_binding(meta["binding"]),
        body=post.content,
        path=path,
        checksum=str(checksum) if checksum else None,
    )


def content_checksum(req: Requirement) -> str:
    b = req.binding
    canonical = "\n".join(
        [
            req.statement.strip(),
            b.harness,
            b.experiment,
            b.metric,
            b.assert_expr,
            str(b.trials),
            repr(b.window),
        ]
    )
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def is_checksum_current(req: Requirement) -> bool:
    return req.checksum is not None and req.checksum == content_checksum(req)


def load_register(requirements_dir: Path) -> list[Requirement]:
    if not requirements_dir.exists():
        return []
    return sorted(
        (parse_requirement(p) for p in requirements_dir.glob("SR-*.md")),
        key=lambda r: r.id,
    )


def get_requirement(reqs: list[Requirement], req_id: str) -> Requirement | None:
    return next((r for r in reqs if r.id == req_id), None)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/requirements/test_register.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add src/factory/requirements/__init__.py src/factory/requirements/register.py tests/unit/requirements/
git commit -m "feat(requirements): SR register model, parse, and content checksum"
```

---

### Task 2: Assertion evaluator

**Files:**
- Create: `src/factory/validation/assertions.py`
- Test: `tests/unit/validation/__init__.py` (empty), `tests/unit/validation/test_assertions.py`

**Interfaces:**
- Produces: `evaluate_assertion(value: float, expr: str) -> bool` — supports `>=`, `<=`, `>`, `<`, `==`; raises `ValueError` on an unparseable expr.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/validation/__init__.py` (empty) and `tests/unit/validation/test_assertions.py`:

```python
import pytest
from factory.validation.assertions import evaluate_assertion

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "value,expr,expected",
    [
        (0.90, ">= 0.90", True),
        (0.89, ">= 0.90", False),
        (0.91, "> 0.90", True),
        (0.90, "> 0.90", False),
        (0.5, "<= 0.5", True),
        (0.4, "< 0.5", True),
        (1.0, "== 1.0", True),
        (0.80, ">=0.80", True),  # no space
    ],
)
def test_evaluate_assertion(value, expr, expected):
    assert evaluate_assertion(value, expr) is expected


def test_bad_expr_raises():
    with pytest.raises(ValueError):
        evaluate_assertion(1.0, "roughly 0.9")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/validation/test_assertions.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'factory.validation.assertions'`.

- [ ] **Step 3: Write minimal implementation**

Create `src/factory/validation/assertions.py`:

```python
from __future__ import annotations

import operator
import re

_OPS = {
    ">=": operator.ge,
    "<=": operator.le,
    "==": operator.eq,
    ">": operator.gt,
    "<": operator.lt,
}
# Longest operators first so ">=" wins over ">".
_PATTERN = re.compile(r"^\s*(>=|<=|==|>|<)\s*(-?\d+(?:\.\d+)?)\s*$")


def evaluate_assertion(value: float, expr: str) -> bool:
    m = _PATTERN.match(expr)
    if m is None:
        raise ValueError(f"unparseable assertion: {expr!r}")
    op, threshold = m.group(1), float(m.group(2))
    return bool(_OPS[op](value, threshold))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/validation/test_assertions.py -v`
Expected: PASS (9 passed).

- [ ] **Step 5: Commit**

```bash
git add src/factory/validation/assertions.py tests/unit/validation/__init__.py tests/unit/validation/test_assertions.py
git commit -m "feat(validation): assertion expression evaluator"
```

---

### Task 3: Preemption metric extractor

**Files:**
- Create: `src/factory/validation/metrics/__init__.py` (empty)
- Create: `src/factory/validation/metrics/preemption.py`
- Test: `tests/unit/validation/test_preemption.py`

**Interfaces:**
- A **frame** is a `dict` with keys `mission_clock: float`, `active_directive: {"kind": str, ...}`, `detections: list[{"label": str, "confidence": float}]`.
- A **trial** is `list[frame]`.
- Produces:
  - `trial_preempted(frames: list[dict], window: dict | None, trigger_label: str = "shark") -> bool`
  - `preemption_success_rate(trials: list[list[dict]], window: dict | None, trigger_label: str = "shark") -> float`
- Semantics: a trial passes when — after the first frame containing a `trigger_label` detection — a non-`patrol` directive fires within `window["within_s"]` seconds (the preemption), AND some later frame returns to `kind == "patrol"` (resume). No trigger ⇒ `False`. `window=None` ⇒ no time bound (any later preemption counts).

- [ ] **Step 1: Write the failing test**

Create `tests/unit/validation/test_preemption.py`:

```python
import pytest
from factory.validation.metrics.preemption import (
    preemption_success_rate,
    trial_preempted,
)

pytestmark = pytest.mark.unit


def _f(t, kind, sharks=()):
    return {
        "mission_clock": t,
        "active_directive": {"kind": kind},
        "detections": [{"label": "shark", "confidence": c} for c in sharks],
    }


WINDOW = {"after_event": "shark_detected", "within_s": 5}

GOOD = [_f(0, "patrol"), _f(15, "patrol", (0.45,)), _f(17, "override", (0.8,)), _f(40, "patrol")]
LATE = [_f(0, "patrol"), _f(15, "patrol", (0.45,)), _f(30, "override"), _f(40, "patrol")]
NO_RESUME = [_f(0, "patrol"), _f(15, "patrol", (0.45,)), _f(17, "override")]
NO_TRIGGER = [_f(0, "patrol"), _f(20, "patrol")]


def test_good_trial_passes():
    assert trial_preempted(GOOD, WINDOW) is True


def test_late_preemption_fails_window():
    assert trial_preempted(LATE, WINDOW) is False


def test_no_resume_fails():
    assert trial_preempted(NO_RESUME, WINDOW) is False


def test_no_trigger_fails():
    assert trial_preempted(NO_TRIGGER, WINDOW) is False


def test_rate_over_trials():
    assert preemption_success_rate([GOOD, GOOD, LATE, NO_TRIGGER], WINDOW) == 0.5
    assert preemption_success_rate([], WINDOW) == 0.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/validation/test_preemption.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'factory.validation.metrics'`.

- [ ] **Step 3: Write minimal implementation**

Create `src/factory/validation/metrics/__init__.py` (empty). Create `src/factory/validation/metrics/preemption.py`:

```python
from __future__ import annotations

_PATROL = "patrol"


def _trigger_time(frames: list[dict], trigger_label: str) -> float | None:
    for f in frames:
        for d in f.get("detections", []):
            if d.get("label") == trigger_label:
                return float(f["mission_clock"])
    return None


def trial_preempted(
    frames: list[dict], window: dict | None, trigger_label: str = "shark"
) -> bool:
    t0 = _trigger_time(frames, trigger_label)
    if t0 is None:
        return False
    within = None if window is None else float(window["within_s"])
    preempt_time: float | None = None
    for f in frames:
        clock = float(f["mission_clock"])
        if clock < t0:
            continue
        kind = f.get("active_directive", {}).get("kind")
        if kind is not None and kind != _PATROL:
            if within is None or clock - t0 <= within:
                preempt_time = clock
                break
    if preempt_time is None:
        return False
    # Resume: a later frame returns to patrol.
    return any(
        float(f["mission_clock"]) > preempt_time
        and f.get("active_directive", {}).get("kind") == _PATROL
        for f in frames
    )


def preemption_success_rate(
    trials: list[list[dict]], window: dict | None, trigger_label: str = "shark"
) -> float:
    if not trials:
        return 0.0
    passed = sum(1 for t in trials if trial_preempted(t, window, trigger_label))
    return passed / len(trials)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/validation/test_preemption.py -v`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add src/factory/validation/metrics/ tests/unit/validation/test_preemption.py
git commit -m "feat(validation): preemption_success_rate metric extractor"
```

---

### Task 4: Harness contract + fixture-backed SimTestbenchHarness

**Files:**
- Create: `src/factory/validation/harness.py`
- Create: `src/factory/validation/sim_harness.py`
- Test: `tests/unit/validation/test_sim_harness.py`

**Interfaces:**
- Consumes: `Binding` (Task 1); `preemption_success_rate` (Task 3); `evaluate_assertion` (Task 2).
- Produces (`harness.py`):
  - `TrialResult(seed: int, passed: bool, detail: str = "")` (frozen)
  - `HarnessResult(metric_value: float, passed: bool, trials: list[TrialResult], artifacts: list[Path], raw: dict)` (frozen)
  - `Harness(Protocol)` with `run(self, binding: Binding, workdir: Path) -> HarnessResult`
- Produces (`sim_harness.py`):
  - `SimTestbenchHarness(traces_dir: Path)`; `run(binding, workdir)` loads `traces_dir / f"{binding.experiment}.json"` shaped `{"trials": [{"seed": int, "frames": [...]}, ...]}`, scores each trial with the extractor named by `binding.metric`, aggregates to a rate, and asserts.
  - `UnknownMetricError(ValueError)`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/validation/test_sim_harness.py`:

```python
import json
from pathlib import Path

import pytest
from factory.requirements.register import Binding
from factory.validation.harness import HarnessResult
from factory.validation.sim_harness import SimTestbenchHarness, UnknownMetricError

pytestmark = pytest.mark.unit


def _f(t, kind, sharks=()):
    return {
        "mission_clock": t,
        "active_directive": {"kind": kind},
        "detections": [{"label": "shark", "confidence": c} for c in sharks],
    }


GOOD = [_f(0, "patrol"), _f(15, "patrol", (0.45,)), _f(17, "override", (0.8,)), _f(40, "patrol")]
BAD = [_f(0, "patrol"), _f(20, "patrol")]  # no trigger → fail


def _binding(**kw):
    base = dict(
        harness="sim-testbench",
        experiment="shark_warning",
        metric="preemption_success_rate",
        assert_expr=">= 0.90",
        trials=4,
        window={"after_event": "shark_detected", "within_s": 5},
    )
    base.update(kw)
    return Binding(**base)


def _write_trace(dir_: Path, name: str, trials: list[list[dict]]) -> None:
    (dir_ / f"{name}.json").write_text(
        json.dumps({"trials": [{"seed": i, "frames": fr} for i, fr in enumerate(trials)]}),
        encoding="utf-8",
    )


def test_all_good_passes(tmp_path):
    _write_trace(tmp_path, "shark_warning", [GOOD, GOOD, GOOD, GOOD])
    res = SimTestbenchHarness(tmp_path).run(_binding(), tmp_path)
    assert isinstance(res, HarnessResult)
    assert res.metric_value == 1.0
    assert res.passed is True
    assert len(res.trials) == 4
    assert all(t.passed for t in res.trials)


def test_below_threshold_fails(tmp_path):
    _write_trace(tmp_path, "shark_warning", [GOOD, GOOD, GOOD, BAD])  # 0.75
    res = SimTestbenchHarness(tmp_path).run(_binding(), tmp_path)
    assert res.metric_value == 0.75
    assert res.passed is False
    assert res.trials[3].passed is False


def test_unknown_metric_raises(tmp_path):
    _write_trace(tmp_path, "shark_warning", [GOOD])
    with pytest.raises(UnknownMetricError):
        SimTestbenchHarness(tmp_path).run(_binding(metric="mystery"), tmp_path)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/validation/test_sim_harness.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'factory.validation.harness'`.

- [ ] **Step 3: Write minimal implementation**

Create `src/factory/validation/harness.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from factory.requirements.register import Binding


@dataclass(frozen=True)
class TrialResult:
    seed: int
    passed: bool
    detail: str = ""


@dataclass(frozen=True)
class HarnessResult:
    metric_value: float
    passed: bool
    trials: list[TrialResult]
    artifacts: list[Path]
    raw: dict


class Harness(Protocol):
    def run(self, binding: Binding, workdir: Path) -> HarnessResult: ...
```

Create `src/factory/validation/sim_harness.py`:

```python
from __future__ import annotations

import json
from pathlib import Path

from factory.requirements.register import Binding
from factory.validation.assertions import evaluate_assertion
from factory.validation.harness import HarnessResult, TrialResult
from factory.validation.metrics.preemption import trial_preempted

# Per-trial scorers: (frames, window) -> bool. Rate = mean of the booleans.
_TRIAL_SCORERS = {
    "preemption_success_rate": trial_preempted,
}


class UnknownMetricError(ValueError):
    pass


class SimTestbenchHarness:
    """Increment-1 harness: score a static recorded trace fixture.

    Reads ``traces_dir / f"{binding.experiment}.json"`` shaped
    ``{"trials": [{"seed": int, "frames": [frame, ...]}, ...]}``.
    """

    def __init__(self, traces_dir: Path) -> None:
        self._traces_dir = traces_dir

    def run(self, binding: Binding, workdir: Path) -> HarnessResult:
        scorer = _TRIAL_SCORERS.get(binding.metric)
        if scorer is None:
            raise UnknownMetricError(f"no trial scorer for metric {binding.metric!r}")
        path = self._traces_dir / f"{binding.experiment}.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        trials_raw = data["trials"]
        results: list[TrialResult] = []
        for tr in trials_raw:
            ok = scorer(tr["frames"], binding.window)
            results.append(TrialResult(seed=int(tr.get("seed", 0)), passed=bool(ok)))
        rate = (sum(1 for r in results if r.passed) / len(results)) if results else 0.0
        return HarnessResult(
            metric_value=rate,
            passed=evaluate_assertion(rate, binding.assert_expr),
            trials=results,
            artifacts=[],
            raw={"trace": str(path), "trials": len(results)},
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/validation/test_sim_harness.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add src/factory/validation/harness.py src/factory/validation/sim_harness.py tests/unit/validation/test_sim_harness.py
git commit -m "feat(validation): harness contract + fixture-backed SimTestbenchHarness"
```

---

### Task 5: Requirement-validation runner → validation-report.json

**Files:**
- Create: `src/factory/validation/report.py`
- Test: `tests/unit/validation/test_report.py`

**Interfaces:**
- Consumes: `Requirement`/`Binding`, `load_register`/`get_requirement`, `is_checksum_current` (Task 1); `Harness`/`HarnessResult` (Task 4).
- Produces:
  - `run_requirement_validation(satisfies: list[str], reqs: list[Requirement], harness_for: Callable[[str], Harness], workdir: Path) -> dict`
  - `write_validation_report(path: Path, report: dict) -> None` (atomic write, best-effort like `review_guide.write_review_guide`)
  - `default_harness_for(traces_dir: Path) -> Callable[[str], Harness]` mapping `"sim-testbench"` → `SimTestbenchHarness(traces_dir)`; unknown harness name raises `ValueError`.
- Report shape:
  ```json
  {"requirements": [
    {"id": "SR-001", "domain": "behavioral", "metric": "preemption_success_rate",
     "value": 1.0, "assert": ">= 0.90", "passed": true, "trials": 4, "stale": false,
     "artifacts": []}
  ]}
  ```
  A `satisfies` id absent from the register yields `{"id": id, "error": "unknown requirement"}`.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/validation/test_report.py`:

```python
import json
from pathlib import Path

import pytest
from factory.requirements.register import content_checksum, load_register, parse_requirement
from factory.validation.report import (
    default_harness_for,
    run_requirement_validation,
    write_validation_report,
)

pytestmark = pytest.mark.unit

_SR = """---
id: SR-001
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
  window: {after_event: shark_detected, within_s: 5}
checksum: {ck}
---
body
"""


def _f(t, kind, sharks=()):
    return {"mission_clock": t, "active_directive": {"kind": kind},
            "detections": [{"label": "shark", "confidence": c} for c in sharks]}


GOOD = [_f(0, "patrol"), _f(15, "patrol", (0.45,)), _f(17, "override"), _f(40, "patrol")]


def _setup(tmp_path):
    req_dir = tmp_path / "requirements"
    req_dir.mkdir()
    stub = req_dir / "SR-001.md"
    stub.write_text(_SR.format(ck="null"), encoding="utf-8")
    ck = content_checksum(parse_requirement(stub))
    stub.write_text(_SR.format(ck=ck), encoding="utf-8")  # stamp current checksum
    traces = tmp_path / "traces"
    traces.mkdir()
    (traces / "shark_warning.json").write_text(
        json.dumps({"trials": [{"seed": 0, "frames": GOOD}, {"seed": 1, "frames": GOOD}]}),
        encoding="utf-8",
    )
    return req_dir, traces


def test_run_and_report(tmp_path):
    req_dir, traces = _setup(tmp_path)
    reqs = load_register(req_dir)
    report = run_requirement_validation(
        ["SR-001"], reqs, default_harness_for(traces), tmp_path
    )
    entry = report["requirements"][0]
    assert entry["id"] == "SR-001"
    assert entry["value"] == 1.0
    assert entry["passed"] is True
    assert entry["trials"] == 2
    assert entry["stale"] is False


def test_unknown_requirement(tmp_path):
    req_dir, traces = _setup(tmp_path)
    reqs = load_register(req_dir)
    report = run_requirement_validation(["SR-404"], reqs, default_harness_for(traces), tmp_path)
    assert report["requirements"][0] == {"id": "SR-404", "error": "unknown requirement"}


def test_write_report_roundtrip(tmp_path):
    out = tmp_path / "sub" / "validation-report.json"
    write_validation_report(out, {"requirements": []})
    assert json.loads(out.read_text(encoding="utf-8")) == {"requirements": []}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/validation/test_report.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'factory.validation.report'`.

- [ ] **Step 3: Write minimal implementation**

Create `src/factory/validation/report.py`:

```python
from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

from factory.requirements.register import (
    Requirement,
    get_requirement,
    is_checksum_current,
)
from factory.validation.harness import Harness
from factory.validation.sim_harness import SimTestbenchHarness

HarnessFor = Callable[[str], Harness]


def default_harness_for(traces_dir: Path) -> HarnessFor:
    def _factory(harness_name: str) -> Harness:
        if harness_name == "sim-testbench":
            return SimTestbenchHarness(traces_dir)
        raise ValueError(f"unknown harness: {harness_name}")

    return _factory


def run_requirement_validation(
    satisfies: list[str],
    reqs: list[Requirement],
    harness_for: HarnessFor,
    workdir: Path,
) -> dict:
    entries: list[dict] = []
    for req_id in satisfies:
        req = get_requirement(reqs, req_id)
        if req is None:
            entries.append({"id": req_id, "error": "unknown requirement"})
            continue
        harness = harness_for(req.binding.harness)
        result = harness.run(req.binding, workdir)
        entries.append(
            {
                "id": req.id,
                "domain": req.domain,
                "metric": req.binding.metric,
                "value": result.metric_value,
                "assert": req.binding.assert_expr,
                "passed": result.passed,
                "trials": len(result.trials),
                "stale": not is_checksum_current(req),
                "artifacts": [str(a) for a in result.artifacts],
            }
        )
    return {"requirements": entries}


def write_validation_report(path: Path, report: dict) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(json.dumps(report, indent=2), encoding="utf-8")
        tmp.replace(path)
    except OSError:
        pass  # best-effort, mirrors review_guide.write_review_guide
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/validation/test_report.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add src/factory/validation/report.py tests/unit/validation/test_report.py
git commit -m "feat(validation): requirement-validation runner emits validation-report.json"
```

---

### Task 6: `satisfies:` on Task

**Files:**
- Modify: `src/factory/orchestrator/ledger.py:11-40` (the `Task` dataclass and `_parse`)
- Test: `tests/unit/orchestrator/test_ledger_satisfies.py`

**Interfaces:**
- Produces: `Task.satisfies: list[str]` (default `[]`), parsed from an optional `satisfies:` frontmatter key (scalar string wrapped to a one-element list; absent ⇒ `[]`). All existing `Task(...)` call sites are unaffected because `satisfies` has a default.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/orchestrator/test_ledger_satisfies.py`:

```python
import pytest
from factory.orchestrator.ledger import load_tasks

pytestmark = pytest.mark.unit


def _write(tmp_path, name, extra=""):
    (tmp_path / name).write_text(
        f"---\nid: {name[:-3]}\ntitle: t\nstatus: todo\ndod:\n  - x\n{extra}---\nbody\n",
        encoding="utf-8",
    )


def test_satisfies_absent_defaults_empty(tmp_path):
    _write(tmp_path, "T-001.md")
    assert load_tasks(tmp_path)[0].satisfies == []


def test_satisfies_list(tmp_path):
    _write(tmp_path, "T-002.md", extra="satisfies:\n  - SR-001\n  - SR-002\n")
    assert load_tasks(tmp_path)[0].satisfies == ["SR-001", "SR-002"]


def test_satisfies_scalar_wrapped(tmp_path):
    _write(tmp_path, "T-003.md", extra="satisfies: SR-001\n")
    assert load_tasks(tmp_path)[0].satisfies == ["SR-001"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/orchestrator/test_ledger_satisfies.py -v`
Expected: FAIL with `AttributeError: 'Task' object has no attribute 'satisfies'`.

- [ ] **Step 3: Write minimal implementation**

In `src/factory/orchestrator/ledger.py`, add the field to the `Task` dataclass (after `path`):

```python
@dataclass
class Task:
    id: str
    title: str
    status: str
    dod: list[str]
    body: str
    path: Path
    satisfies: list[str] = field(default_factory=list)
```

Add `field` to the dataclass import at the top:

```python
from dataclasses import dataclass, field
```

In `_parse`, before the `return Task(...)`, derive `satisfies`:

```python
    satisfies_value = meta.get("satisfies") or []
    if isinstance(satisfies_value, str):
        satisfies = [satisfies_value]
    else:
        satisfies = [str(s) for s in satisfies_value]
```

and pass it in the `Task(...)` constructor:

```python
    return Task(
        id=str(meta["id"]),
        title=str(meta["title"]),
        status=str(meta["status"]),
        dod=dod,
        body=post.content,
        path=path,
        satisfies=satisfies,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/orchestrator/test_ledger_satisfies.py tests/unit/orchestrator/test_ledger.py -v`
Expected: PASS (existing ledger tests still green; 3 new pass).

- [ ] **Step 5: Commit**

```bash
git add src/factory/orchestrator/ledger.py tests/unit/orchestrator/test_ledger_satisfies.py
git commit -m "feat(ledger): optional satisfies: list on Task frontmatter"
```

---

### Task 7: `factory requirements` CLI (new / index / status / show)

**Files:**
- Create: `src/factory/requirements/cli.py`
- Create: `src/factory/requirements/__main__.py`
- Test: `tests/unit/requirements/test_cli.py`

**Interfaces:**
- Consumes: `load_register`, `parse_requirement`, `content_checksum`, `is_checksum_current` (Task 1).
- Produces:
  - `cmd_new(requirements_dir: Path, title: str, domain: str) -> Path` — allocates the next `SR-###` id (max existing + 1, zero-padded to 3, starting at `SR-001`), writes a template file with `checksum: null`.
  - `cmd_index(requirements_dir: Path) -> dict` — restamps each file's `checksum:` with its current `content_checksum`, returns `{"requirements": [{"id","checksum","stale":false}...]}`, and writes `requirements/index.json`.
  - `cmd_status(requirements_dir: Path, stale_only: bool = False) -> str` — one line per requirement: `SR-001  [current|STALE]  <title>`.
  - `cmd_show(requirements_dir: Path, req_id: str) -> str` — the statement + binding + checksum state, or `f"not found: {req_id}"`.
  - `main(argv: list[str] | None = None) -> int` — argparse dispatch over subcommands `new|index|status|show`, with `--requirements-dir` (default `requirements`).

- [ ] **Step 1: Write the failing test**

Create `tests/unit/requirements/test_cli.py`:

```python
import json
from pathlib import Path

import pytest
from factory.requirements.cli import cmd_index, cmd_new, cmd_show, cmd_status, main

pytestmark = pytest.mark.unit


def test_new_allocates_sequential_ids(tmp_path):
    p1 = cmd_new(tmp_path, "First req", "behavioral")
    p2 = cmd_new(tmp_path, "Second req", "perception")
    assert p1.name == "SR-001.md"
    assert p2.name == "SR-002.md"
    assert "First req" in p1.read_text(encoding="utf-8")


def test_index_stamps_checksums_and_writes_index(tmp_path):
    cmd_new(tmp_path, "First", "behavioral")
    result = cmd_index(tmp_path)
    assert result["requirements"][0]["id"] == "SR-001"
    assert result["requirements"][0]["checksum"].startswith("sha256:")
    assert result["requirements"][0]["stale"] is False
    assert json.loads((tmp_path / "index.json").read_text(encoding="utf-8")) == result


def test_status_flags_stale_after_edit(tmp_path):
    path = cmd_new(tmp_path, "First", "behavioral")
    cmd_index(tmp_path)
    assert "current" in cmd_status(tmp_path)
    # Mutate the statement so the stored checksum no longer matches.
    text = path.read_text(encoding="utf-8").replace("First", "First CHANGED")
    path.write_text(text, encoding="utf-8")
    assert "STALE" in cmd_status(tmp_path)
    assert "SR-001" in cmd_status(tmp_path, stale_only=True)


def test_show(tmp_path):
    cmd_new(tmp_path, "First", "behavioral")
    assert "SR-001" in cmd_show(tmp_path, "SR-001")
    assert "not found" in cmd_show(tmp_path, "SR-999")


def test_main_status_exit_code(tmp_path, capsys):
    cmd_new(tmp_path, "First", "behavioral")
    rc = main(["status", "--requirements-dir", str(tmp_path)])
    assert rc == 0
    assert "SR-001" in capsys.readouterr().out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/requirements/test_cli.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'factory.requirements.cli'`.

- [ ] **Step 3: Write minimal implementation**

Create `src/factory/requirements/cli.py`:

```python
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import frontmatter

from factory.requirements.register import (
    content_checksum,
    is_checksum_current,
    load_register,
    parse_requirement,
)

_ID_RE = re.compile(r"SR-(\d+)")

_TEMPLATE = """---
id: {id}
title: "{title}"
statement: "TODO: EARS statement — When <trigger>, the <system> shall <response>."
domain: {domain}
upstream: []
binding:
  harness: sim-testbench
  experiment: TODO_experiment
  metric: preemption_success_rate
  trials: 20
  assert: ">= 0.90"
  window: {{after_event: shark_detected, within_s: 5}}
checksum: null
---

## Rationale
TODO
"""


def _next_id(requirements_dir: Path) -> str:
    nums = [
        int(m.group(1))
        for p in requirements_dir.glob("SR-*.md")
        if (m := _ID_RE.search(p.name))
    ]
    return f"SR-{(max(nums) + 1) if nums else 1:03d}"


def cmd_new(requirements_dir: Path, title: str, domain: str) -> Path:
    requirements_dir.mkdir(parents=True, exist_ok=True)
    req_id = _next_id(requirements_dir)
    path = requirements_dir / f"{req_id}.md"
    path.write_text(_TEMPLATE.format(id=req_id, title=title, domain=domain), encoding="utf-8")
    return path


def cmd_index(requirements_dir: Path) -> dict:
    out: list[dict] = []
    for req in load_register(requirements_dir):
        checksum = content_checksum(req)
        post = frontmatter.load(str(req.path))
        post["checksum"] = checksum
        req.path.write_text(frontmatter.dumps(post), encoding="utf-8")
        out.append({"id": req.id, "checksum": checksum, "stale": False})
    result = {"requirements": out}
    (requirements_dir / "index.json").write_text(
        json.dumps(result, indent=2), encoding="utf-8"
    )
    return result


def cmd_status(requirements_dir: Path, stale_only: bool = False) -> str:
    lines: list[str] = []
    for req in load_register(requirements_dir):
        current = is_checksum_current(req)
        if stale_only and current:
            continue
        lines.append(f"{req.id}  [{'current' if current else 'STALE'}]  {req.title}")
    return "\n".join(lines) if lines else "no requirements"


def cmd_show(requirements_dir: Path, req_id: str) -> str:
    path = requirements_dir / f"{req_id}.md"
    if not path.exists():
        return f"not found: {req_id}"
    req = parse_requirement(path)
    b = req.binding
    return (
        f"{req.id}  {req.title}\n"
        f"statement: {req.statement}\n"
        f"binding: {b.harness}/{b.experiment} {b.metric} {b.assert_expr} (trials={b.trials})\n"
        f"checksum: {'current' if is_checksum_current(req) else 'STALE'}"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="factory-requirements")
    parser.add_argument("--requirements-dir", default="requirements", type=Path)
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_new = sub.add_parser("new")
    p_new.add_argument("title")
    p_new.add_argument("--domain", default="behavioral")
    sub.add_parser("index")
    p_status = sub.add_parser("status")
    p_status.add_argument("--stale", action="store_true")
    p_show = sub.add_parser("show")
    p_show.add_argument("id")
    args = parser.parse_args(argv)

    if args.cmd == "new":
        print(cmd_new(args.requirements_dir, args.title, args.domain))
    elif args.cmd == "index":
        print(json.dumps(cmd_index(args.requirements_dir), indent=2))
    elif args.cmd == "status":
        print(cmd_status(args.requirements_dir, stale_only=args.stale))
    elif args.cmd == "show":
        print(cmd_show(args.requirements_dir, args.id))
    return 0
```

Create `src/factory/requirements/__main__.py`:

```python
from __future__ import annotations

import sys

from factory.requirements.cli import main

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/requirements/test_cli.py -v`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add src/factory/requirements/cli.py src/factory/requirements/__main__.py tests/unit/requirements/test_cli.py
git commit -m "feat(requirements): factory requirements CLI (new/index/status/show)"
```

---

### Task 8: Case-study wiring — SR-001 + trace fixture in the drone repo

**Files (in the drone repo `cool_physical_ai_project`, NOT the factory repo):**
- Create: `requirements/SR-001.md`
- Create: `validation/traces/shark_warning.json`
- Create: `scripts/validate_requirements.py`

**Interfaces:**
- Consumes the factory package (installed globally as `pif`, so `import factory...` resolves): `load_register`, `run_requirement_validation`, `default_harness_for`, `write_validation_report` (Tasks 1 & 5).
- This task has no unit test in the factory suite; it is verified by running the script and observing `SR-001` pass. It demonstrates the whole 1A spine on the real case study.

- [ ] **Step 1: Author the requirement**

In the **drone repo**, create `requirements/SR-001.md`:

```markdown
---
id: SR-001
title: "Navigation preempts patrol for an in-zone shark"
statement: "When a shark is detected inside or adjacent to an active swim zone, the navigation system shall preempt the current patrol and investigate before resuming patrol."
domain: behavioral
upstream: [BR-002]
binding:
  harness: sim-testbench
  experiment: shark_warning
  metric: preemption_success_rate
  trials: 3
  assert: ">= 0.90"
  window: {after_event: shark_detected, within_s: 5}
checksum: null
---

## Rationale
Swimmer safety: an unconfirmed shark near a swim zone must interrupt routine
patrol (patrol -> investigate -> confirm -> warn -> resume). Ground-truth
detections are supplied by the sim testbench; no CV in the loop for this SR.
```

- [ ] **Step 2: Add the recorded trace fixture**

Create `validation/traces/shark_warning.json` (3 trials that all preempt correctly, so the rate is 1.0 ≥ 0.90):

```json
{
  "trials": [
    {"seed": 0, "frames": [
      {"mission_clock": 0.0,  "active_directive": {"kind": "patrol"},   "detections": []},
      {"mission_clock": 15.0, "active_directive": {"kind": "patrol"},   "detections": [{"label": "shark", "confidence": 0.45}]},
      {"mission_clock": 17.0, "active_directive": {"kind": "override"}, "detections": [{"label": "shark", "confidence": 0.80}]},
      {"mission_clock": 40.0, "active_directive": {"kind": "patrol"},   "detections": []}
    ]},
    {"seed": 1, "frames": [
      {"mission_clock": 0.0,  "active_directive": {"kind": "patrol"},   "detections": []},
      {"mission_clock": 16.0, "active_directive": {"kind": "patrol"},   "detections": [{"label": "shark", "confidence": 0.50}]},
      {"mission_clock": 18.5, "active_directive": {"kind": "override"}, "detections": [{"label": "shark", "confidence": 0.85}]},
      {"mission_clock": 42.0, "active_directive": {"kind": "patrol"},   "detections": []}
    ]},
    {"seed": 2, "frames": [
      {"mission_clock": 0.0,  "active_directive": {"kind": "patrol"},   "detections": []},
      {"mission_clock": 14.5, "active_directive": {"kind": "patrol"},   "detections": [{"label": "shark", "confidence": 0.42}]},
      {"mission_clock": 16.0, "active_directive": {"kind": "override"}, "detections": [{"label": "shark", "confidence": 0.78}]},
      {"mission_clock": 38.0, "active_directive": {"kind": "patrol"},   "detections": []}
    ]}
  ]
}
```

- [ ] **Step 3: Add the demonstration script**

Create `scripts/validate_requirements.py`:

```python
from __future__ import annotations

import json
import sys
from pathlib import Path

from factory.orchestrator.ledger import load_tasks
from factory.requirements.register import load_register
from factory.validation.report import (
    default_harness_for,
    run_requirement_validation,
    write_validation_report,
)

REPO = Path(__file__).resolve().parent.parent


def main() -> int:
    reqs = load_register(REPO / "requirements")
    # Collect every SR referenced by a task's satisfies:, plus SR-001 directly
    # so the demo works before any task links it.
    satisfies: list[str] = ["SR-001"]
    if (REPO / "tasks").exists():
        for t in load_tasks(REPO / "tasks"):
            satisfies.extend(t.satisfies)
    satisfies = list(dict.fromkeys(satisfies))
    harness_for = default_harness_for(REPO / "validation" / "traces")
    report = run_requirement_validation(satisfies, reqs, harness_for, REPO)
    out = REPO / "validation" / "validation-report.json"
    write_validation_report(out, report)
    print(json.dumps(report, indent=2))
    failed = [e for e in report["requirements"] if not e.get("passed")]
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Stamp the checksum and run the demonstration**

Run (in the drone repo):

```bash
python -m factory.requirements index --requirements-dir requirements
python scripts/validate_requirements.py
```

Expected: `SR-001` prints with `"value": 1.0`, `"passed": true`, `"stale": false`; the script exits 0; `validation/validation-report.json` is written.

- [ ] **Step 5: Commit (in the drone repo)**

```bash
git add requirements/SR-001.md validation/traces/shark_warning.json scripts/validate_requirements.py validation/validation-report.json requirements/index.json
git commit -m "feat: SR-001 nav-preemption requirement + trace fixture + validation demo"
```

---

## Final verification

- [ ] Run the full factory unit suite: `uv run pytest -q` — expected: all green, including the new `tests/unit/requirements/` and `tests/unit/validation/` modules.
- [ ] Lint + types: `uv run ruff check src tests` and `uv run pyright src` — expected: clean.
- [ ] Confirm the drone-repo demo (`python scripts/validate_requirements.py`) exits 0 with `SR-001` passing.

## Self-review notes (coverage against the spec, Increment 1A slice)

- Register + checksum staleness (spec §5.1–5.2) → Tasks 1, 7.
- Harness contract + two-domain shape, behavioral path (spec §7.1) → Task 4 (`Harness`, `SimTestbenchHarness`); perception harness is Increment 3.
- Preemption metric + stochastic pass-rate over N trials (spec §5.1, §7.2) → Task 3.
- `validation-report.json` (spec §7.3) → Task 5.
- `satisfies:` traceability edge (spec §6) → Task 6.
- Requirements CLI new/index/status/show (spec §5.3) → Task 7.
- Case study SR-001 against a static recorded trace fixture (spec §13, §14 Increment 1) → Task 8.
- **Deferred to 1B/1C (out of this plan, by design):** activating the VALIDATION role to call this runner inside the pipeline, the `REQ_REVIEW` role, folding `validation-report.json` into `review-guide.json`, and the TUI/web review surfaces (spec §7 wiring, §8, §9). The 1A units are pure and independently testable, so 1B wiring consumes them without change.
