# Requirement Doctor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let an agent propose system requirements from prose specs, have a human accept them one at a time, and record them honestly in a register that can now hold a requirement whose measurement is not yet decided.

**Architecture:** Three layers land in order. First the *scorer seam*: `sim-testbench` resolves its metric scorers from a module the target repo declares in `.factory/factory.yaml`, so drone vocabulary leaves the factory. Then the *proposed state*: `binding:` becomes optional in the register, and its absence — not a `status:` field — is what makes a requirement proposed. Then the *doctor CLI and skill*: deterministic commands for the register state, id assignment, frontmatter writing and the scorer lookup, with every judgement left to the agent.

**Tech Stack:** Python 3.11–3.12, `python-frontmatter`, `pyyaml`, `argparse`, pytest. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-08-06-requirement-doctor-design.md`

## Global Constraints

- Python `>=3.11,<3.13`. Type hints use `from __future__ import annotations`.
- `ruff` line-length **100**. Run `uv run ruff check .` before every commit.
- `pyright` `typeCheckingMode = "standard"` over `src` and `scripts`. Must stay clean.
- Unit tests run with `uv run pytest -m unit`. The `unit` marker is the default via `addopts`.
- **No new dependencies.** Everything needed is already in `pyproject.toml`.
- CLIs are invoked as `python -m factory.<package>` and use an argparse `prog` of `factory-<package>`, matching `factory-trace` and `factory-requirements`.
- Never write a `status:` field on a requirement. The presence or absence of `binding:` is the only representation of proposed vs. active.
- `build_graph` and everything it calls must never load `.factory/factory.yaml` and never import target-repo code.

---

### Task 1: Resolve sim-testbench scorers from config

Today `sim_harness.py:12` hardcodes a single drone metric as a module-level constant, so no other metric can ever validate. This task makes the scorer map come from the target repository.

**Files:**
- Create: `src/factory/validation/scorer_registry.py`
- Modify: `src/factory/validation/sim_harness.py`
- Test: `tests/unit/validation/test_scorer_registry.py`
- Test: `tests/unit/validation/test_sim_harness.py`

**Interfaces:**
- Produces: `load_scorers(module_name: str | None, project_root: Path) -> dict[str, Callable[..., bool]]`, `ScorerModuleError(ValueError)`.
- Produces: `SimTestbenchHarness(traces_dir: Path, scorers: dict[str, Callable[..., bool]] | None = None)`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/validation/test_scorer_registry.py
import pytest

from factory.validation.scorer_registry import ScorerModuleError, load_scorers


def _write_module(tmp_path, body: str) -> None:
    pkg = tmp_path / "src" / "demoproj"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "scorers.py").write_text(body, encoding="utf-8")


def test_absent_module_name_is_an_empty_map(tmp_path):
    assert load_scorers(None, tmp_path) == {}
    assert load_scorers("", tmp_path) == {}


def test_scorers_are_read_from_the_targets_src_tree(tmp_path):
    _write_module(tmp_path, "SCORERS = {'always_true': lambda frames, window: True}\n")
    scorers = load_scorers("demoproj.scorers", tmp_path)
    assert sorted(scorers) == ["always_true"]
    assert scorers["always_true"]([], None) is True


def test_a_module_without_SCORERS_is_reported_not_guessed(tmp_path):
    _write_module(tmp_path, "def trial_thing(frames, window):\n    return True\n")
    with pytest.raises(ScorerModuleError, match="SCORERS"):
        load_scorers("demoproj.scorers", tmp_path)


def test_an_unimportable_module_names_itself(tmp_path):
    with pytest.raises(ScorerModuleError, match="demoproj.missing"):
        load_scorers("demoproj.missing", tmp_path)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/unit/validation/test_scorer_registry.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'factory.validation.scorer_registry'`

- [ ] **Step 3: Implement the registry**

```python
# src/factory/validation/scorer_registry.py
from __future__ import annotations

import importlib
import sys
from collections.abc import Callable
from pathlib import Path

Scorer = Callable[..., bool]


class ScorerModuleError(ValueError):
    pass


def load_scorers(module_name: str | None, project_root: Path) -> dict[str, Scorer]:
    """Import the target repo's scorer module and return its SCORERS mapping.

    A missing name is an empty map, not an error: a project that declares no
    scorers has no implemented metrics yet, which the register can now say
    honestly. Importing target-repo code is the same trust posture the gate
    steps already carry -- see the design's section 4.1.
    """
    if not module_name:
        return {}
    # Both this repo and its targets use a src/ layout (pyproject
    # `[tool.setuptools.packages.find] where = ["src"]`), and the factory runs
    # from its own interpreter, so the target's src/ is not importable by default.
    src = project_root / "src"
    added = str(src) if src.is_dir() and str(src) not in sys.path else None
    if added:
        sys.path.insert(0, added)
    try:
        module = importlib.import_module(module_name)
    except Exception as exc:
        raise ScorerModuleError(f"cannot import scorer module {module_name!r}: {exc}") from exc
    finally:
        if added:
            sys.path.remove(added)

    registry = getattr(module, "SCORERS", None)
    if not isinstance(registry, dict):
        raise ScorerModuleError(
            f"{module_name!r} must define a SCORERS dict of metric name -> callable"
        )
    return {str(k): v for k, v in registry.items()}
```

- [ ] **Step 4: Run the registry tests to verify they pass**

Run: `uv run pytest tests/unit/validation/test_scorer_registry.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Point the harness at the registry**

Replace the module-level constant and `from_config` in `src/factory/validation/sim_harness.py`. Delete the `_TRIAL_SCORERS` dict and the `trial_preempted` import entirely.

```python
# src/factory/validation/sim_harness.py -- changed regions only
from collections.abc import Callable

from factory.validation.scorer_registry import load_scorers

# (delete: from factory.validation.metrics.preemption import trial_preempted)
# (delete: _TRIAL_SCORERS = {...})


class SimTestbenchHarness:
    def __init__(
        self, traces_dir: Path, scorers: dict[str, Callable[..., bool]] | None = None
    ) -> None:
        self._traces_dir = traces_dir
        self._scorers = scorers if scorers is not None else {}

    @classmethod
    def from_config(cls, params: dict, project_root: Path) -> "SimTestbenchHarness":
        return cls(
            project_root / params["traces_dir"],
            load_scorers(params.get("scorers"), project_root),
        )

    def run(self, binding: Binding, workdir: Path) -> HarnessResult:
        scorer = self._scorers.get(binding.metric)
        if scorer is None:
            raise UnknownMetricError(f"no trial scorer for metric {binding.metric!r}")
        # ... rest of run() unchanged
```

- [ ] **Step 6: Give `default_harness_for` a scorer map**

`report.py`'s helper builds the harness for the tests, so it must be able to supply scorers or every test using it starts raising `UnknownMetricError`.

```python
# src/factory/validation/report.py -- replace default_harness_for
def default_harness_for(
    traces_dir: Path, scorers: dict[str, Callable[..., bool]] | None = None
) -> HarnessFor:
    def _factory(harness_name: str) -> Harness:
        if harness_name == "sim-testbench":
            return SimTestbenchHarness(traces_dir, scorers)
        raise ValueError(f"unknown harness: {harness_name}")

    return _factory
```

Add `from collections.abc import Callable` to that file's imports.

- [ ] **Step 7: Replace `tests/unit/validation/test_sim_harness.py` in full**

The existing fixtures are drone-shaped (`"shark"`, `"patrol"`, `active_directive`). The factory no longer owns that vocabulary, so the harness's own test uses a neutral scorer. Every assertion keeps its exact meaning: 4/4 → 1.0 pass, 3/4 → 0.75 fail, unknown metric raises.

```python
import json
from pathlib import Path

import pytest
from factory.requirements.register import Binding
from factory.validation.harness import HarnessResult
from factory.validation.sim_harness import SimTestbenchHarness, UnknownMetricError

pytestmark = pytest.mark.unit


def _scored(frames: list[dict], window: dict | None) -> bool:
    """Stand-in scorer. The factory owns no real metric; targets declare their own."""
    return any(f.get("ok") for f in frames)


SCORERS = {"demo_rate": _scored}

GOOD = [{"tick": 0}, {"tick": 1, "ok": True}]
BAD = [{"tick": 0}, {"tick": 1, "ok": False}]


def _binding(**kw):
    base = dict(
        harness="sim-testbench",
        experiment="demo_experiment",
        metric="demo_rate",
        assert_expr=">= 0.90",
        trials=4,
        window=None,
    )
    base.update(kw)
    return Binding(**base)


def _write_trace(dir_: Path, name: str, trials: list[list[dict]]) -> None:
    (dir_ / f"{name}.json").write_text(
        json.dumps({"trials": [{"seed": i, "frames": fr} for i, fr in enumerate(trials)]}),
        encoding="utf-8",
    )


def test_all_good_passes(tmp_path):
    _write_trace(tmp_path, "demo_experiment", [GOOD, GOOD, GOOD, GOOD])
    res = SimTestbenchHarness(tmp_path, SCORERS).run(_binding(), tmp_path)
    assert isinstance(res, HarnessResult)
    assert res.metric_value == 1.0
    assert res.passed is True
    assert len(res.trials) == 4
    assert all(t.passed for t in res.trials)


def test_below_threshold_fails(tmp_path):
    _write_trace(tmp_path, "demo_experiment", [GOOD, GOOD, GOOD, BAD])  # 0.75
    res = SimTestbenchHarness(tmp_path, SCORERS).run(_binding(), tmp_path)
    assert res.metric_value == 0.75
    assert res.passed is False
    assert res.trials[3].passed is False


def test_unknown_metric_raises(tmp_path):
    _write_trace(tmp_path, "demo_experiment", [GOOD])
    with pytest.raises(UnknownMetricError):
        SimTestbenchHarness(tmp_path, SCORERS).run(_binding(metric="mystery"), tmp_path)


def test_a_project_declaring_no_scorers_implements_nothing(tmp_path):
    _write_trace(tmp_path, "demo_experiment", [GOOD])
    harness = SimTestbenchHarness.from_config({"traces_dir": "."}, tmp_path)
    with pytest.raises(UnknownMetricError):
        harness.run(_binding(), tmp_path)
```

- [ ] **Step 8: Give `test_report.py` a local scorer**

That file's fixtures stay as they are — test data may name a shark; only `src/factory` may not. It needs one helper and four one-word call changes.

```python
# tests/unit/validation/test_report.py -- add after the GOOD fixture
def _preempted(frames, window):
    return any(f["active_directive"]["kind"] != "patrol" for f in frames)


_SCORERS = {"preemption_success_rate": _preempted}
```

Then change all four `default_harness_for(traces)` calls (lines 62, 74, 90, 121) to `default_harness_for(traces, _SCORERS)`.

- [ ] **Step 9: Run the full unit suite**

Run: `uv run pytest -m unit`
Expected: PASS

- [ ] **Step 10: Lint, typecheck and commit**

```bash
uv run ruff check . && uv run pyright
git add src/factory/validation/scorer_registry.py src/factory/validation/sim_harness.py src/factory/validation/report.py tests/unit/validation/
git commit -m "feat(validation): resolve sim-testbench scorers from the target repo's declared module"
```

---

### Task 2: Move the preemption metric out of the factory

`metrics/preemption.py` hardcodes `"shark"`, `"patrol"` and the drone's frame schema. Under the boundary rule it belongs to the drone.

**Files:**
- Delete: `src/factory/validation/metrics/preemption.py`
- Delete: `src/factory/validation/metrics/__init__.py` (the package becomes empty)
- Delete: `tests/unit/validation/test_preemption.py`
- Create (in `C:/coding/cool_physical_ai_project`): `src/drone/validation/__init__.py`, `src/drone/validation/scorers.py`, `tests/unit/drone/test_scorers.py`, `.factory/factory.yaml`
- Modify: `tests/unit/validation/test_sim_harness.py`, `tests/unit/validation/test_pipeline.py`, `tests/unit/validation/test_report.py`
- Create: `tests/unit/validation/test_no_drone_vocabulary.py`

**Interfaces:**
- Consumes: `load_scorers` from Task 1.
- Produces: in the drone repo, `SCORERS = {"preemption_success_rate": trial_preempted}`.

- [ ] **Step 1: Write the migration guard test**

```python
# tests/unit/validation/test_no_drone_vocabulary.py
from pathlib import Path

_SRC = Path(__file__).resolve().parents[3] / "src" / "factory"


def test_the_factory_ships_no_drone_metric_module():
    assert not (_SRC / "validation" / "metrics").exists()


def test_no_factory_source_mentions_the_drone_trigger_label():
    offenders = [
        path.relative_to(_SRC).as_posix()
        for path in _SRC.rglob("*.py")
        if "shark" in path.read_text(encoding="utf-8").lower()
    ]
    assert offenders == []
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/unit/validation/test_no_drone_vocabulary.py -v`
Expected: FAIL — the metrics package still exists and `preemption.py` contains `"shark"`.

- [ ] **Step 3: Create the scorer module in the drone repo**

Create `C:/coding/cool_physical_ai_project/src/drone/validation/__init__.py` (empty), then `src/drone/validation/scorers.py` with the **exact** body of the factory's `metrics/preemption.py` (both functions, unchanged), plus this registry at the end:

```python
SCORERS = {"preemption_success_rate": trial_preempted}
```

Copy `tests/unit/validation/test_preemption.py` to `C:/coding/cool_physical_ai_project/tests/unit/drone/test_scorers.py`, changing only the import to `from drone.validation.scorers import preemption_success_rate, trial_preempted`, and add:

```python
def test_the_registry_exposes_the_metric_by_its_binding_name():
    from drone.validation.scorers import SCORERS

    assert SCORERS["preemption_success_rate"] is trial_preempted
```

- [ ] **Step 4: Create the drone's factory config**

Create `C:/coding/cool_physical_ai_project/.factory/factory.yaml`:

```yaml
harnesses:
  sim-testbench:
    type: sim-testbench
    traces_dir: validation/traces
    scorers: drone.validation.scorers

gates:
  unit:
    - { cmd: "{python} -m pytest -m unit -q" }
  full:
    - { cmd: "{python} -m ruff check ." }
    - { cmd: "{python} -m pytest -m unit -q" }
```

The `gates:` section is required — `factory.config` treats a config with no gates as a hard error (configurable-gates design §4).

- [ ] **Step 5: Delete the factory-side metric and its tests**

```bash
git rm -r src/factory/validation/metrics tests/unit/validation/test_preemption.py
```

Nothing else needs editing: Task 1 already replaced `test_sim_harness.py` with a neutral scorer and gave `test_report.py` its own local one, and `sim_harness.py` no longer imports the metrics package. `grep -rn "metrics.preemption" src tests` must come back empty before moving on.

- [ ] **Step 6: Run both suites**

Run in the factory: `uv run pytest -m unit`
Expected: PASS, including `test_no_drone_vocabulary.py`.

Run in the drone repo: `uv run pytest -m unit`
Expected: PASS — the moved scorer tests pass there.

- [ ] **Step 7: Commit both repositories**

```bash
# factory
uv run ruff check . && uv run pyright
git add -A src/factory/validation tests/unit/validation
git commit -m "refactor(validation): move the preemption metric to the drone repo"
```

```bash
# cool_physical_ai_project
git add src/drone/validation tests/unit/drone/test_scorers.py .factory/factory.yaml
git commit -m "feat(validation): own the preemption scorer and declare the sim-testbench harness"
```

---

### Task 3: Let the register hold a requirement with no binding

**Files:**
- Modify: `src/factory/requirements/register.py`
- Test: `tests/unit/requirements/test_register.py`

**Interfaces:**
- Produces: `Requirement.binding: Binding | None`, `Requirement.source: str | None`.
- Produces: `content_checksum` raises `ValueError` for a proposed requirement; `is_checksum_current` returns `True` for one.

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/requirements/test_register.py -- append
import pytest

from factory.requirements.register import (
    content_checksum,
    is_checksum_current,
    parse_requirement,
)

_PROPOSED = """---
id: SR-009
title: Investigate is abandoned when the zone clears
statement: When the swim zone becomes empty during an investigate directive, the
  navigation system shall abandon the investigation and resume patrol.
domain: behavioral
source: docs/superpowers/specs/2026-07-21-mission-agent-navigation-design.md
---

## Rationale
Zone-clear must not strand the drone in investigate.
"""


def _write(tmp_path, name: str, text: str):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def test_a_requirement_with_no_binding_parses(tmp_path):
    req = parse_requirement(_write(tmp_path, "SR-009.md", _PROPOSED))
    assert req.binding is None
    assert req.id == "SR-009"
    assert req.source.endswith("mission-agent-navigation-design.md")


def test_a_proposed_requirement_is_never_stale(tmp_path):
    req = parse_requirement(_write(tmp_path, "SR-009.md", _PROPOSED))
    assert is_checksum_current(req) is True


def test_checksumming_a_proposed_requirement_is_refused(tmp_path):
    req = parse_requirement(_write(tmp_path, "SR-009.md", _PROPOSED))
    with pytest.raises(ValueError, match="no binding"):
        content_checksum(req)


def test_a_bound_requirement_is_unaffected(tmp_path):
    # SR_TEXT is the existing bound fixture at the top of this file.
    req = parse_requirement(_write(tmp_path, "SR-001.md", SR_TEXT))
    assert req.binding is not None
    assert req.binding.metric == "preemption_success_rate"
    assert req.source is None
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/unit/requirements/test_register.py -v`
Expected: FAIL — `ValueError: SR-009.md: missing required field(s): ['binding']`

- [ ] **Step 3: Implement**

```python
# src/factory/requirements/register.py -- changed regions only
_REQUIRED = ("id", "title", "statement", "domain")


@dataclass(frozen=True)
class Requirement:
    id: str
    title: str
    statement: str
    domain: str
    upstream: list[str]
    binding: Binding | None
    body: str
    path: Path
    checksum: str | None = None
    source: str | None = None


def parse_requirement(path: Path) -> Requirement:
    # ... unchanged up to the return
    source = meta.get("source")
    return Requirement(
        id=str(meta["id"]),
        title=str(meta["title"]),
        statement=str(meta["statement"]),
        domain=str(meta["domain"]),
        upstream=[str(u) for u in upstream],  # type: ignore[union-attr]
        binding=_parse_binding(meta["binding"]) if "binding" in meta else None,  # type: ignore[arg-type]
        body=post.content,
        path=path,
        checksum=str(checksum) if checksum else None,
        source=str(source) if source else None,
    )


def content_checksum(req: Requirement) -> str:
    # cadence is intentionally excluded: it is scheduling (how often the SR runs),
    # not a metric input, so changing it must not stale the requirement.
    b = req.binding
    if b is None:
        raise ValueError(f"{req.id}: proposed requirement has no binding to checksum")
    # ... rest unchanged


def is_checksum_current(req: Requirement) -> bool:
    # A proposed requirement has no binding, so there is nothing for a checksum to
    # go stale against. Returning False here would print STALE forever.
    if req.binding is None:
        return True
    return req.checksum is not None and req.checksum == content_checksum(req)
```

- [ ] **Step 4: Run to verify they pass**

Run: `uv run pytest tests/unit/requirements/ -v`
Expected: PASS — including every pre-existing bound-requirement test.

- [ ] **Step 5: Commit**

```bash
uv run ruff check . && uv run pyright
git add src/factory/requirements/register.py tests/unit/requirements/test_register.py
git commit -m "feat(requirements): a requirement may exist without a binding"
```

---

### Task 4: Teach the requirements CLI about proposed requirements

`cmd_index` would crash checksumming a proposed requirement; `cmd_status` would call it "current"; `_TEMPLATE` still mints the hardcoded drone binding the separation design flagged.

**Files:**
- Modify: `src/factory/requirements/cli.py`
- Test: `tests/unit/requirements/test_requirements_cli.py`

**Interfaces:**
- Consumes: `Requirement.binding`, `is_checksum_current` from Task 3.

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/requirements/test_requirements_cli.py -- append
from factory.requirements.cli import cmd_index, cmd_new, cmd_show, cmd_status


def test_index_leaves_a_proposed_requirement_untouched(tmp_path):
    path = tmp_path / "SR-009.md"
    path.write_text(_PROPOSED, encoding="utf-8")  # fixture from test_register.py
    before = path.read_text(encoding="utf-8")
    result = cmd_index(tmp_path)
    assert path.read_text(encoding="utf-8") == before
    assert result["requirements"] == [{"id": "SR-009", "checksum": None, "proposed": True}]


def test_status_says_proposed_not_current(tmp_path):
    (tmp_path / "SR-009.md").write_text(_PROPOSED, encoding="utf-8")
    assert "[proposed]" in cmd_status(tmp_path)
    assert "current" not in cmd_status(tmp_path)


def test_show_reports_no_binding(tmp_path):
    (tmp_path / "SR-009.md").write_text(_PROPOSED, encoding="utf-8")
    assert "not yet measurable" in cmd_show(tmp_path, "SR-009")


def test_new_mints_a_proposed_requirement(tmp_path):
    path = cmd_new(tmp_path, "Zone clear abandons investigate", "behavioral")
    text = path.read_text(encoding="utf-8")
    assert "binding:" not in text
    assert "preemption_success_rate" not in text
    assert "sim-testbench" not in text
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/unit/requirements/test_requirements_cli.py -v`
Expected: FAIL — `cmd_index` raises `ValueError: SR-009: proposed requirement has no binding to checksum`.

- [ ] **Step 3: Implement**

```python
# src/factory/requirements/cli.py -- changed regions only
_TEMPLATE = """---
id: {id}
title: "{title}"
statement: "TODO: EARS statement — When <trigger>, the <system> shall <response>."
domain: {domain}
upstream: []
---

## Rationale
TODO
"""


def cmd_index(requirements_dir: Path) -> dict:
    out: list[dict] = []
    for req in load_register(requirements_dir):
        if req.binding is None:
            # Proposed: nothing to checksum, and rewriting the file would only
            # churn its formatting.
            out.append({"id": req.id, "checksum": None, "proposed": True})
            continue
        checksum = content_checksum(req)
        post = frontmatter.load(str(req.path))
        post["checksum"] = checksum
        req.path.write_text(frontmatter.dumps(post), encoding="utf-8")
        out.append({"id": req.id, "checksum": checksum, "stale": False})
    result = {"requirements": out}
    (requirements_dir / "index.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def cmd_status(requirements_dir: Path, stale_only: bool = False) -> str:
    lines: list[str] = []
    for req in load_register(requirements_dir):
        if req.binding is None:
            if not stale_only:
                lines.append(f"{req.id}  [proposed]  {req.title}")
            continue
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
    if req.binding is None:
        return (
            f"{req.id}  {req.title}\n"
            f"statement: {req.statement}\n"
            f"binding: (proposed — not yet measurable)\n"
            f"source: {req.source or '(none)'}"
        )
    b = req.binding
    return (
        f"{req.id}  {req.title}\n"
        f"statement: {req.statement}\n"
        f"binding: {b.harness}/{b.experiment} {b.metric} {b.assert_expr} (trials={b.trials})\n"
        f"checksum: {'current' if is_checksum_current(req) else 'STALE'}"
    )
```

- [ ] **Step 4: Run to verify they pass**

Run: `uv run pytest tests/unit/requirements/ -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
uv run ruff check . && uv run pyright
git add src/factory/requirements/cli.py tests/unit/requirements/test_requirements_cli.py
git commit -m "feat(requirements): CLI reports proposed requirements and mints them unbound"
```

---

### Task 5: Keep proposed requirements out of validation

**Files:**
- Modify: `src/factory/validation/pipeline.py`
- Modify: `src/factory/validation/report.py`
- Test: `tests/unit/validation/test_pipeline.py`
- Test: `tests/unit/validation/test_report.py`

**Interfaces:**
- Consumes: `Requirement.binding` from Task 3.

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/validation/test_pipeline.py -- append
from factory.validation.pipeline import select_requirement_ids


def test_a_proposed_requirement_is_never_selected(proposed_req, bound_req):
    ids = select_requirement_ids([proposed_req, bound_req], satisfies=[], full_sweep=True)
    assert ids == [bound_req.id]


def test_a_proposed_requirement_named_by_a_task_is_still_not_run(proposed_req, bound_req):
    ids = select_requirement_ids([proposed_req, bound_req], satisfies=[proposed_req.id])
    assert proposed_req.id not in ids
```

```python
# tests/unit/validation/test_report.py -- append
from factory.validation.report import run_requirement_validation


def test_a_proposed_requirement_reports_an_error_not_a_crash(proposed_req):
    report = run_requirement_validation(
        [proposed_req.id], [proposed_req], lambda name: None, Path(".")
    )
    entry = report["requirements"][0]
    assert entry["id"] == proposed_req.id
    assert "proposed" in entry["error"]
    assert "passed" not in entry
```

Add a shared fixture in `tests/unit/validation/conftest.py`:

```python
import pytest

from factory.requirements.register import Binding, Requirement


@pytest.fixture
def proposed_req(tmp_path):
    return Requirement(
        id="SR-009", title="t", statement="s", domain="behavioral",
        upstream=[], binding=None, body="", path=tmp_path / "SR-009.md",
    )


@pytest.fixture
def bound_req(tmp_path):
    return Requirement(
        id="SR-001", title="t", statement="s", domain="behavioral", upstream=[],
        binding=Binding(
            harness="sim-testbench", experiment="e", metric="m", assert_expr=">= 0.9"
        ),
        body="", path=tmp_path / "SR-001.md",
    )
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/unit/validation/test_pipeline.py tests/unit/validation/test_report.py -v`
Expected: FAIL — the proposed id is selected, and `run_requirement_validation` raises `AttributeError: 'NoneType' object has no attribute 'harness'`.

- [ ] **Step 3: Implement**

```python
# src/factory/validation/pipeline.py
def select_requirement_ids(
    reqs: list[Requirement], satisfies: list[str], *, full_sweep: bool = False
) -> list[str]:
    # A proposed requirement has no binding, so there is nothing to run -- not even
    # when a task names it directly.
    runnable = {r.id for r in reqs if r.binding is not None}
    ids: list[str] = []
    for r in reqs:
        if r.binding is None:
            continue
        if full_sweep or r.binding.cadence == "every_iteration":
            ids.append(r.id)
    for sid in satisfies:  # a task's own SRs always run, even if periodic
        if sid in runnable and sid not in ids:
            ids.append(sid)
    return ids
```

```python
# src/factory/validation/report.py -- inside the loop, right after the None check
        if req.binding is None:
            entries.append(
                {"id": req.id, "error": "proposed requirement: no binding to validate"}
            )
            continue
```

- [ ] **Step 4: Run to verify they pass**

Run: `uv run pytest -m unit`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
uv run ruff check . && uv run pyright
git add src/factory/validation/pipeline.py src/factory/validation/report.py tests/unit/validation/
git commit -m "feat(validation): proposed requirements are skipped, and reported honestly if named"
```

---

### Task 6: Record proposed-ness on the trace node

`build_graph` must not load config or import target code, so the graph learns proposed-ness the same way it learns `trace_exempt` — from frontmatter, degrading rather than crashing.

**Files:**
- Modify: `src/factory/trace/model.py`
- Test: `tests/unit/trace/test_model.py`

**Interfaces:**
- Produces: `Node.proposed: bool` — `True` only for an `sr` node whose frontmatter has no `binding` key.

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/trace/test_model.py -- append
from factory.trace.model import load_nodes


def _sr(tmp_path, name: str, body: str):
    d = tmp_path / "requirements"
    d.mkdir(exist_ok=True)
    (d / name).write_text(body, encoding="utf-8")


def test_a_requirement_without_a_binding_is_proposed(tmp_path):
    _sr(tmp_path, "SR-009.md", "---\nid: SR-009\ntitle: t\n---\nbody\n")
    node = next(n for n in load_nodes(tmp_path) if n.id == "SR-009")
    assert node.proposed is True


def test_a_bound_requirement_is_not_proposed(tmp_path):
    _sr(
        tmp_path,
        "SR-001.md",
        "---\nid: SR-001\ntitle: t\nbinding:\n  harness: sim-testbench\n---\nbody\n",
    )
    node = next(n for n in load_nodes(tmp_path) if n.id == "SR-001")
    assert node.proposed is False


def test_a_task_is_never_proposed(tmp_path):
    d = tmp_path / "tasks"
    d.mkdir()
    (d / "T-001.md").write_text("---\nid: T-001\ntitle: t\n---\nbody\n", encoding="utf-8")
    assert all(n.proposed is False for n in load_nodes(tmp_path) if n.kind == "task")


def test_a_malformed_requirement_still_degrades_to_a_filename_node(tmp_path):
    _sr(tmp_path, "SR-bad.md", "---\nid: [unclosed\n---\n")
    node = next(n for n in load_nodes(tmp_path) if n.path.name == "SR-bad.md")
    assert node.id == "SR-bad.md"
    assert node.proposed is False
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/unit/trace/test_model.py -v`
Expected: FAIL — `AttributeError: 'Node' object has no attribute 'proposed'`

- [ ] **Step 3: Implement**

```python
# src/factory/trace/model.py -- changed regions only
@dataclass(frozen=True)
class Node:
    id: str
    kind: NodeKind
    title: str
    path: Path
    exempt: bool = False
    deferred: str | None = None
    proposed: bool = False


def _id_node(path: Path, kind: NodeKind) -> Node:
    post = _load_post(path)
    if post is None or "id" not in post.metadata:
        return Node(id=path.name, kind=kind, title=path.name, path=path)
    exempt, deferred = _disposition(post.metadata)
    return Node(
        id=str(post.metadata["id"]),
        kind=kind,
        title=str(post.metadata.get("title", path.name)),
        path=path,
        exempt=exempt,
        deferred=deferred,
        # The absence of a binding IS the proposed state -- there is no status field
        # to disagree with the content.
        proposed=kind == "sr" and "binding" not in post.metadata,
    )
```

- [ ] **Step 4: Run to verify they pass**

Run: `uv run pytest tests/unit/trace/ -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
uv run ruff check . && uv run pyright
git add src/factory/trace/model.py tests/unit/trace/test_model.py
git commit -m "feat(trace): nodes record whether a requirement is proposed"
```

---

### Task 7: Split `sr_unvalidated` into three honest states

**Files:**
- Modify: `src/factory/trace/gaps.py`
- Test: `tests/unit/trace/test_gaps.py`

**Interfaces:**
- Consumes: `Node.proposed` (Task 6), `SrStatus.state`/`SrStatus.error` (existing).
- Produces: gap kinds `sr_proposed` and `sr_unvalidatable` alongside `sr_unvalidated`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/trace/test_gaps.py -- append
from factory.trace.gaps import find_gaps
from factory.trace.model import Node
from factory.trace.validation_status import SrStatus


def _sr_node(tmp_path, proposed: bool) -> Node:
    return Node(id="SR-001", kind="sr", title="t", path=tmp_path / "SR-001.md", proposed=proposed)


def _kinds(gaps) -> set[str]:
    return {g.kind for g in gaps}


def test_a_proposed_requirement_reports_sr_proposed_and_is_deferred(tmp_path):
    gaps = find_gaps([_sr_node(tmp_path, True)], [], {})
    assert "sr_proposed" in _kinds(gaps)
    assert "sr_unvalidated" not in _kinds(gaps)
    proposed = next(g for g in gaps if g.kind == "sr_proposed")
    assert proposed.disposition == "deferred"


def test_an_errored_requirement_is_unvalidatable_and_carries_the_reason(tmp_path):
    status = {"SR-001": SrStatus(id="SR-001", state="error", error="no harness 'sim-testbench'")}
    gaps = find_gaps([_sr_node(tmp_path, False)], [], status)
    gap = next(g for g in gaps if g.kind == "sr_unvalidatable")
    assert "no harness" in gap.detail
    assert gap.disposition == "pending"


def test_a_bound_requirement_with_no_report_is_unvalidated_not_unvalidatable(tmp_path):
    gaps = find_gaps([_sr_node(tmp_path, False)], [], {})
    assert "sr_unvalidated" in _kinds(gaps)
    assert "sr_unvalidatable" not in _kinds(gaps)


def test_a_proposed_requirement_still_needs_a_satisfying_task(tmp_path):
    assert "sr_unsatisfied" in _kinds(find_gaps([_sr_node(tmp_path, True)], [], {}))
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/unit/trace/test_gaps.py -v`
Expected: FAIL — `KeyError: 'sr_proposed'` in `_KIND_ORDER`, and no `sr_unvalidatable` kind exists.

- [ ] **Step 3: Implement**

```python
# src/factory/trace/gaps.py -- changed regions only
GapKind = Literal[
    "task_no_sr",
    "task_no_plan",
    "task_plan_missing",
    "plan_no_spec",
    "dangling_upstream",
    "sr_unsatisfied",
    "sr_proposed",
    "sr_unvalidatable",
    "sr_unvalidated",
    "sr_stale",
]

_KIND_ORDER: dict[str, int] = {
    "task_no_sr": 0,
    "task_no_plan": 1,
    "plan_no_spec": 2,
    "sr_unsatisfied": 3,
    "sr_proposed": 4,
    "sr_unvalidatable": 5,
    "sr_unvalidated": 6,
    "sr_stale": 7,
    "dangling_upstream": 8,
    "task_plan_missing": 9,
}


def find_gaps(
    nodes: list[Node], edges: list[Edge], validation: dict[str, SrStatus]
) -> list[Gap]:
    by_id = {n.id: n for n in nodes}
    gaps: list[Gap] = []

    def add(
        node: Node, kind: GapKind, detail: str, disposition: Disposition | None = None
    ) -> None:
        derived, note = _disposition_of(node)
        gaps.append(
            Gap(node.id, kind, f"{detail} ({note})" if note else detail, disposition or derived)
        )
    # ... task and plan branches unchanged ...
        elif node.kind == "sr":
            if node.id not in satisfied_srs:
                add(node, "sr_unsatisfied", "no task declares satisfies for this SR")
            if node.proposed:
                # Accepted in substance, measurement undecided. Deferred rather than
                # pending: the human accepted it knowing the binding was open, which
                # is exactly "discussed, still open". Pending would red-gate the repo
                # the moment the doctor is used.
                add(node, "sr_proposed", "binding not yet decided", disposition="deferred")
            else:
                status = validation.get(node.id)
                if status is None or status.state == "never_validated":
                    add(node, "sr_unvalidated", "absent from validation report")
                elif status.state == "error":
                    # Read from the report, never from config: keeping this out of
                    # the trace path is what stops `trace status` importing target
                    # code. Design section 8.1.
                    add(node, "sr_unvalidatable", status.error or "validation could not run")
                elif status.stale:
                    add(node, "sr_stale", "result predates a change to statement or binding")
```

- [ ] **Step 4: Run to verify they pass**

Run: `uv run pytest tests/unit/trace/ -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
uv run ruff check . && uv run pyright
git add src/factory/trace/gaps.py tests/unit/trace/test_gaps.py
git commit -m "feat(trace): distinguish proposed, unvalidatable and unvalidated requirements"
```

---

### Task 8: Report proposed requirements in health without punishing the score

**Files:**
- Modify: `src/factory/trace/health.py`
- Modify: `src/factory/trace/graph.py`
- Modify: `src/factory/trace/cli.py`
- Test: `tests/unit/trace/test_health.py`

**Interfaces:**
- Produces: `Health.proposed: int`.
- Consumes: gap kinds from Task 7.

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/trace/test_health.py -- append
from factory.trace.gaps import Gap
from factory.trace.health import compute_health
from factory.trace.model import Node


def _sr(node_id: str, proposed: bool, tmp_path) -> Node:
    return Node(id=node_id, kind="sr", title="t", path=tmp_path / f"{node_id}.md",
                proposed=proposed)


def test_a_proposed_requirement_leaves_the_validated_denominator(tmp_path):
    nodes = [_sr("SR-009", True, tmp_path)]
    gaps = [
        Gap("SR-009", "sr_unsatisfied", "d", "pending"),
        Gap("SR-009", "sr_proposed", "d", "deferred"),
    ]
    health = compute_health(nodes, gaps)
    validated = next(c for c in health.classes if c.name == "SR validated")
    assert validated.expected == 0
    assert health.proposed == 1


def test_a_proposed_requirement_stays_in_the_satisfied_denominator(tmp_path):
    nodes = [_sr("SR-009", True, tmp_path)]
    gaps = [
        Gap("SR-009", "sr_unsatisfied", "d", "pending"),
        Gap("SR-009", "sr_proposed", "d", "deferred"),
    ]
    satisfied = next(c for c in compute_health(nodes, gaps).classes if c.name == "SR satisfied")
    assert satisfied.expected == 1
    assert satisfied.satisfied == 0


def test_an_unvalidatable_requirement_counts_as_unfilled(tmp_path):
    nodes = [_sr("SR-001", False, tmp_path)]
    gaps = [Gap("SR-001", "sr_unvalidatable", "no harness", "pending")]
    validated = next(c for c in compute_health(nodes, gaps).classes if c.name == "SR validated")
    assert validated.expected == 1
    assert validated.satisfied == 0


def test_proposed_is_not_double_counted_as_deferred(tmp_path):
    nodes = [_sr("SR-009", True, tmp_path)]
    gaps = [Gap("SR-009", "sr_proposed", "d", "deferred")]
    assert compute_health(nodes, gaps).deferred == 0
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/unit/trace/test_health.py -v`
Expected: FAIL — `AttributeError: 'Health' object has no attribute 'proposed'`

- [ ] **Step 3: Implement**

```python
# src/factory/trace/health.py -- changed regions only
_SLOT_OF_GAP: dict[str, str] = {
    "task_no_sr": "task->SR",
    "task_no_plan": "task->plan",
    "plan_no_spec": "plan->spec",
    "sr_unsatisfied": "SR satisfied",
    "sr_unvalidatable": "SR validated",
    "sr_unvalidated": "SR validated",
}


@dataclass(frozen=True)
class Health:
    classes: list[ClassHealth]
    satisfied: int
    expected: int
    dangling: int
    deferred: int
    proposed: int = 0
    # ... percent property unchanged


def compute_health(nodes: list[Node], gaps: list[Gap]) -> Health:
    # ... expected/unfilled/exempt setup unchanged
    dangling = 0
    deferred = 0
    proposed = 0
    for gap in gaps:
        if gap.kind in ("dangling_upstream", "task_plan_missing"):
            dangling += 1
            continue
        if gap.kind == "sr_proposed":
            # Nobody has yet claimed this requirement is measurable, so counting it
            # as an unfilled validation slot would punish the doctor for recording a
            # real state. It keeps its SR-satisfied slot: a requirement with no task
            # is a gap whether or not its binding is decided.
            proposed += 1
            expected["SR validated"] -= 1
            continue
        if gap.disposition == "deferred":
            deferred += 1
        # ... remainder of the loop unchanged
    # ... sr_stale pass unchanged
    return Health(
        classes=classes,
        satisfied=sum(c.satisfied for c in classes),
        expected=sum(c.expected for c in classes),
        dangling=dangling,
        deferred=deferred,
        proposed=proposed,
    )
```

```python
# src/factory/trace/graph.py -- inside graph_to_dict's "health" dict
            "deferred": graph.health.deferred,
            "proposed": graph.health.proposed,
```

```python
# src/factory/trace/cli.py -- inside cmd_status, after the deferred line
    lines.append(f"  proposed       {health.proposed}")
```

- [ ] **Step 4: Run to verify they pass**

Run: `uv run pytest -m unit`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
uv run ruff check . && uv run pyright
git add src/factory/trace/health.py src/factory/trace/graph.py src/factory/trace/cli.py tests/unit/trace/test_health.py
git commit -m "feat(trace): report proposed requirements separately from the health score"
```

---

### Task 9: `factory doctor context`

The agent's field of view: the register state and the scorer inventory — everything the agent cannot cheaply derive, and nothing that filters, ranks or excerpts the specs.

**Files:**
- Create: `src/factory/doctor/__init__.py`, `src/factory/doctor/__main__.py`, `src/factory/doctor/context.py`, `src/factory/doctor/cli.py`
- Test: `tests/unit/doctor/test_context.py`

**Interfaces:**
- Consumes: `load_register` (Task 3), `load_config` (`factory.config`), `load_scorers` (Task 1).
- Produces: `gather_context(project_root: Path) -> dict` and `format_context(ctx: dict) -> str`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/doctor/test_context.py
from pathlib import Path

from factory.doctor.context import format_context, gather_context


def _repo(tmp_path) -> Path:
    (tmp_path / "requirements").mkdir()
    (tmp_path / "docs" / "superpowers" / "specs").mkdir(parents=True)
    (tmp_path / "docs" / "superpowers" / "specs" / "2026-01-01-a-design.md").write_text(
        "# A\n", encoding="utf-8"
    )
    (tmp_path / "requirements" / "SR-009.md").write_text(
        "---\nid: SR-009\ntitle: t\nstatement: s\ndomain: behavioral\n"
        "source: docs/superpowers/specs/2026-01-01-a-design.md\n---\nbody\n",
        encoding="utf-8",
    )
    return tmp_path


def test_context_lists_specs_and_register_state(tmp_path):
    ctx = gather_context(_repo(tmp_path))
    assert ctx["specs"] == ["docs/superpowers/specs/2026-01-01-a-design.md"]
    entry = ctx["requirements"][0]
    assert entry["id"] == "SR-009"
    assert entry["state"] == "proposed"
    assert entry["source"].endswith("a-design.md")
    assert entry["binding"] is None


def test_a_repo_with_no_factory_config_says_so_rather_than_failing(tmp_path):
    ctx = gather_context(_repo(tmp_path))
    assert ctx["config"] == {"present": False, "harnesses": {}}


def test_context_never_emits_spec_text(tmp_path):
    rendered = format_context(gather_context(_repo(tmp_path)))
    assert "2026-01-01-a-design.md" in rendered
    assert "read these files yourself" in rendered.lower()
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/unit/doctor/test_context.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'factory.doctor'`

- [ ] **Step 3: Implement**

```python
# src/factory/doctor/context.py
from __future__ import annotations

from pathlib import Path

from factory.requirements.register import load_register
from factory.validation.scorer_registry import ScorerModuleError, load_scorers

_SPECS = ("docs", "superpowers", "specs")


def _harness_inventory(project_root: Path) -> dict:
    path = project_root / ".factory" / "factory.yaml"
    if not path.exists():
        return {"present": False, "harnesses": {}}
    import yaml

    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    harnesses: dict[str, dict] = {}
    for name, spec in (data.get("harnesses") or {}).items():
        module = (spec or {}).get("scorers")
        try:
            metrics = sorted(load_scorers(module, project_root))
            error = None
        except ScorerModuleError as exc:
            metrics, error = [], str(exc)
        harnesses[name] = {"scorers_module": module, "metrics": metrics, "error": error}
    return {"present": True, "harnesses": harnesses}


def gather_context(project_root: Path) -> dict:
    specs_dir = project_root.joinpath(*_SPECS)
    specs = (
        [p.relative_to(project_root).as_posix() for p in sorted(specs_dir.glob("*.md"))]
        if specs_dir.is_dir()
        else []
    )
    requirements = []
    for req in load_register(project_root / "requirements"):
        b = req.binding
        requirements.append(
            {
                "id": req.id,
                "title": req.title,
                "statement": req.statement,
                "domain": req.domain,
                "source": req.source,
                "state": "proposed" if b is None else "active",
                "binding": None
                if b is None
                else {
                    "harness": b.harness,
                    "experiment": b.experiment,
                    "metric": b.metric,
                    "assert": b.assert_expr,
                },
            }
        )
    return {"specs": specs, "requirements": requirements, "config": _harness_inventory(project_root)}


def format_context(ctx: dict) -> str:
    lines = [
        f"Specs ({len(ctx['specs'])}) — read these files yourself; this command does not",
        "summarise, rank or excerpt them:",
        *[f"  {p}" for p in ctx["specs"]],
        "",
        f"Register ({len(ctx['requirements'])}):",
    ]
    for req in ctx["requirements"] or []:
        lines.append(f"  {req['id']}  [{req['state']}]  {req['title']}")
        lines.append(f"      {req['statement']}")
        lines.append(f"      source: {req['source'] or '(none)'}")
        if req["binding"]:
            b = req["binding"]
            lines.append(f"      binding: {b['harness']}/{b['experiment']} {b['metric']}")
    if not ctx["requirements"]:
        lines.append("  (empty)")
    lines.append("")
    config = ctx["config"]
    if not config["present"]:
        lines.append("No .factory/factory.yaml — no harness is declared and no metric is")
        lines.append("implemented. Requirements can still be proposed and accepted.")
        return "\n".join(lines)
    lines.append("Declared harnesses:")
    for name, info in config["harnesses"].items():
        detail = info["error"] or (", ".join(info["metrics"]) or "(no metrics implemented)")
        lines.append(f"  {name}  scorers={info['scorers_module'] or '(none)'}  -> {detail}")
    return "\n".join(lines)
```

```python
# src/factory/doctor/__main__.py
from factory.doctor.cli import main

raise SystemExit(main())
```

```python
# src/factory/doctor/cli.py
from __future__ import annotations

import argparse
import json
from pathlib import Path

from factory.doctor.context import format_context, gather_context


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="factory-doctor")
    sub = parser.add_subparsers(dest="cmd", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--project-root", default=Path("."), type=Path)

    p_context = sub.add_parser("context", parents=[common])
    p_context.add_argument("--json", action="store_true")

    args = parser.parse_args(argv)
    if args.cmd == "context":
        ctx = gather_context(args.project_root)
        print(json.dumps(ctx, indent=2) if args.json else format_context(ctx))
    return 0
```

Create empty `src/factory/doctor/__init__.py` and `tests/unit/doctor/__init__.py` if the test layout requires it (match the sibling `tests/unit/trace/` layout).

- [ ] **Step 4: Run to verify they pass**

Run: `uv run pytest tests/unit/doctor/ -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
uv run ruff check . && uv run pyright
git add src/factory/doctor tests/unit/doctor
git commit -m "feat(doctor): factory doctor context reports the register and scorer inventory"
```

---

### Task 10: `factory doctor mint`

**Files:**
- Create: `src/factory/doctor/write.py`
- Modify: `src/factory/doctor/cli.py`
- Test: `tests/unit/doctor/test_write.py`

**Interfaces:**
- Produces: `mint(project_root: Path, source: str, title: str, statement: str, domain: str) -> Path`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/doctor/test_write.py
import pytest

from factory.doctor.write import mint
from factory.requirements.register import parse_requirement


def _repo(tmp_path):
    (tmp_path / "docs" / "superpowers" / "specs").mkdir(parents=True)
    (tmp_path / "docs" / "superpowers" / "specs" / "a.md").write_text("# A\n", encoding="utf-8")
    return tmp_path


def test_mint_writes_a_parseable_proposed_requirement(tmp_path):
    path = mint(
        _repo(tmp_path),
        source="docs/superpowers/specs/a.md",
        title="Zone clear abandons investigate",
        statement="When the zone clears, the system shall resume patrol.",
        domain="behavioral",
    )
    req = parse_requirement(path)
    assert req.id == "SR-001"
    assert req.binding is None
    assert req.source == "docs/superpowers/specs/a.md"
    assert req.statement.startswith("When the zone clears")


def test_mint_assigns_consecutive_ids(tmp_path):
    repo = _repo(tmp_path)
    first = mint(repo, "docs/superpowers/specs/a.md", "one", "s", "behavioral")
    second = mint(repo, "docs/superpowers/specs/a.md", "two", "s", "behavioral")
    assert (first.name, second.name) == ("SR-001.md", "SR-002.md")


def test_mint_refuses_a_source_that_does_not_exist(tmp_path):
    with pytest.raises(ValueError, match="no such source"):
        mint(_repo(tmp_path), "docs/superpowers/specs/missing.md", "t", "s", "behavioral")
    assert not (tmp_path / "requirements").exists()
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/unit/doctor/test_write.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'factory.doctor.write'`

- [ ] **Step 3: Implement**

```python
# src/factory/doctor/write.py
from __future__ import annotations

from pathlib import Path

import frontmatter

from factory.requirements.cli import _next_id


def mint(
    project_root: Path, source: str, title: str, statement: str, domain: str = "behavioral"
) -> Path:
    """Write an accepted candidate as a proposed requirement.

    Refusing a non-existent source mirrors link_satisfies refusing a non-existent
    target: a provenance pointer that dangles is worse than none.
    """
    if not (project_root / source).is_file():
        raise ValueError(f"no such source: {source}")
    requirements_dir = project_root / "requirements"
    requirements_dir.mkdir(parents=True, exist_ok=True)
    req_id = _next_id(requirements_dir)
    post = frontmatter.Post(
        "\n## Rationale\n",
        id=req_id,
        title=title,
        statement=statement,
        domain=domain,
        upstream=[],
        source=source,
    )
    path = requirements_dir / f"{req_id}.md"
    path.write_text(frontmatter.dumps(post), encoding="utf-8")
    return path
```

Note the ordering: the source check runs before `requirements_dir.mkdir`, so a refused mint leaves no directory behind — which the third test asserts.

Add to `cli.py`:

```python
    p_mint = sub.add_parser("mint", parents=[common])
    p_mint.add_argument("--source", required=True)
    p_mint.add_argument("--title", required=True)
    p_mint.add_argument("--statement", required=True)
    p_mint.add_argument("--domain", default="behavioral")
```

```python
    elif args.cmd == "mint":
        path = mint(args.project_root, args.source, args.title, args.statement, args.domain)
        print(f"minted {path.stem} at {path}")
```

- [ ] **Step 4: Run to verify they pass**

Run: `uv run pytest tests/unit/doctor/ -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
uv run ruff check . && uv run pyright
git add src/factory/doctor tests/unit/doctor/test_write.py
git commit -m "feat(doctor): mint an accepted candidate as a proposed requirement"
```

---

### Task 11: `factory doctor promote`

**Files:**
- Modify: `src/factory/doctor/write.py`, `src/factory/doctor/cli.py`
- Test: `tests/unit/doctor/test_promote.py`

**Interfaces:**
- Produces: `promote(project_root, req_id, harness, experiment, metric, assert_expr, trials=1, window=None) -> tuple[Path, bool]` — the bool is `True` when the metric is present in the harness's declared scorers module.

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/doctor/test_promote.py
import pytest

from factory.doctor.write import mint, promote
from factory.requirements.register import is_checksum_current, parse_requirement


def _repo(tmp_path):
    specs = tmp_path / "docs" / "superpowers" / "specs"
    specs.mkdir(parents=True)
    (specs / "a.md").write_text("# A\n", encoding="utf-8")
    mint(tmp_path, "docs/superpowers/specs/a.md", "t", "s", "behavioral")
    return tmp_path


def test_promote_binds_the_requirement_and_writes_a_current_checksum(tmp_path):
    path, implemented = promote(
        _repo(tmp_path), "SR-001", "sim-testbench", "shark_warning",
        "preemption_success_rate", ">= 0.90", trials=20,
    )
    req = parse_requirement(path)
    assert req.binding is not None
    assert req.binding.trials == 20
    assert is_checksum_current(req) is True
    assert implemented is False  # no .factory/factory.yaml in this repo


def test_promote_reports_an_implemented_metric(tmp_path):
    repo = _repo(tmp_path)
    pkg = repo / "src" / "demoproj"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "scorers.py").write_text(
        "SCORERS = {'preemption_success_rate': lambda f, w: True}\n", encoding="utf-8"
    )
    (repo / ".factory").mkdir()
    (repo / ".factory" / "factory.yaml").write_text(
        "harnesses:\n  sim-testbench:\n    type: sim-testbench\n"
        "    traces_dir: validation/traces\n    scorers: demoproj.scorers\n"
        "gates:\n  unit:\n    - { cmd: \"true\" }\n",
        encoding="utf-8",
    )
    _, implemented = promote(
        repo, "SR-001", "sim-testbench", "shark_warning",
        "preemption_success_rate", ">= 0.90",
    )
    assert implemented is True


def test_promote_does_not_refuse_an_unimplemented_metric(tmp_path):
    path, implemented = promote(
        _repo(tmp_path), "SR-001", "sim-testbench", "e", "not_built_yet", ">= 0.9"
    )
    assert implemented is False
    assert parse_requirement(path).binding.metric == "not_built_yet"


def test_promote_refuses_an_unknown_requirement(tmp_path):
    with pytest.raises(ValueError, match="SR-404"):
        promote(_repo(tmp_path), "SR-404", "sim-testbench", "e", "m", ">= 0.9")
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/unit/doctor/test_promote.py -v`
Expected: FAIL — `ImportError: cannot import name 'promote'`

- [ ] **Step 3: Implement**

```python
# src/factory/doctor/write.py -- append
from factory.doctor.context import gather_context
from factory.requirements.register import content_checksum, parse_requirement


def promote(
    project_root: Path,
    req_id: str,
    harness: str,
    experiment: str,
    metric: str,
    assert_expr: str,
    trials: int = 1,
    window: dict | None = None,
) -> tuple[Path, bool]:
    """Fill a proposed requirement's binding, and report whether the metric exists.

    Deliberately does NOT refuse an unimplemented metric: "bound, and we know it
    cannot run yet" is a state the register can now hold honestly, and refusing
    would push that state back into prose.
    """
    path = project_root / "requirements" / f"{req_id}.md"
    if not path.is_file():
        raise ValueError(f"no such requirement: {req_id}")
    binding: dict = {
        "harness": harness,
        "experiment": experiment,
        "metric": metric,
        "assert": assert_expr,
        "trials": trials,
    }
    if window is not None:
        binding["window"] = window
    post = frontmatter.load(str(path))
    post["binding"] = binding
    path.write_text(frontmatter.dumps(post), encoding="utf-8")

    post = frontmatter.load(str(path))
    post["checksum"] = content_checksum(parse_requirement(path))
    path.write_text(frontmatter.dumps(post), encoding="utf-8")

    declared = gather_context(project_root)["config"]["harnesses"].get(harness, {})
    return path, metric in declared.get("metrics", [])
```

Add to `cli.py`:

```python
    p_promote = sub.add_parser("promote", parents=[common])
    p_promote.add_argument("id")
    p_promote.add_argument("--harness", required=True)
    p_promote.add_argument("--experiment", required=True)
    p_promote.add_argument("--metric", required=True)
    p_promote.add_argument("--assert", dest="assert_expr", required=True)
    p_promote.add_argument("--trials", type=int, default=1)
    # JSON, not k=v: the window carries typed values (within_s is a number,
    # after_event a string) that a flat key-value syntax cannot express.
    p_promote.add_argument("--window-json", dest="window_json", default=None)
```

```python
    elif args.cmd == "promote":
        window = json.loads(args.window_json) if args.window_json else None
        path, implemented = promote(
            args.project_root, args.id, args.harness, args.experiment,
            args.metric, args.assert_expr, args.trials, window,
        )
        print(f"promoted {args.id} at {path}")
        print(
            f"metric {args.metric!r}: "
            + ("implemented" if implemented else "NOT implemented in the declared scorers module")
        )
```

- [ ] **Step 4: Run to verify they pass**

Run: `uv run pytest tests/unit/doctor/ -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
uv run ruff check . && uv run pyright
git add src/factory/doctor tests/unit/doctor/test_promote.py
git commit -m "feat(doctor): promote a requirement and report whether its metric exists"
```

---

### Task 12: `factory doctor task`

**Files:**
- Modify: `src/factory/doctor/write.py`, `src/factory/doctor/cli.py`
- Test: `tests/unit/doctor/test_task.py`

**Interfaces:**
- Produces: `emit_task(project_root: Path, satisfies: str, title: str, dod: list[str], body: str = "") -> Path`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/doctor/test_task.py
import frontmatter
import pytest

from factory.doctor.write import emit_task, mint


def _repo(tmp_path):
    specs = tmp_path / "docs" / "superpowers" / "specs"
    specs.mkdir(parents=True)
    (specs / "a.md").write_text("# A\n", encoding="utf-8")
    mint(tmp_path, "docs/superpowers/specs/a.md", "t", "s", "behavioral")
    return tmp_path


def test_emit_task_links_the_requirement(tmp_path):
    path = emit_task(
        _repo(tmp_path), "SR-001",
        "Implement the zone_clear_resume_rate scorer",
        ["SCORERS exposes zone_clear_resume_rate", "unit test covers pass and fail trials"],
        body="Add the scorer to src/drone/validation/scorers.py.",
    )
    post = frontmatter.load(str(path))
    assert post["id"] == "T-001"
    assert post["satisfies"] == ["SR-001"]
    assert post["status"] == "todo"
    assert len(post["dod"]) == 2
    assert "src/drone/validation/scorers.py" in post.content


def test_emit_task_assigns_consecutive_ids(tmp_path):
    repo = _repo(tmp_path)
    first = emit_task(repo, "SR-001", "one", ["d"])
    second = emit_task(repo, "SR-001", "two", ["d"])
    assert (first.name, second.name) == ("T-001.md", "T-002.md")


def test_emit_task_refuses_an_unknown_requirement(tmp_path):
    with pytest.raises(ValueError, match="SR-404"):
        emit_task(_repo(tmp_path), "SR-404", "t", ["d"])


def test_emit_task_refuses_an_empty_dod(tmp_path):
    with pytest.raises(ValueError, match="dod"):
        emit_task(_repo(tmp_path), "SR-001", "t", [])
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/unit/doctor/test_task.py -v`
Expected: FAIL — `ImportError: cannot import name 'emit_task'`

- [ ] **Step 3: Implement**

```python
# src/factory/doctor/write.py -- append
import re

_TASK_ID_RE = re.compile(r"T-(\d+)")


def _next_task_id(tasks_dir: Path) -> str:
    nums = [int(m.group(1)) for p in tasks_dir.glob("T-*.md") if (m := _TASK_ID_RE.search(p.name))]
    return f"T-{(max(nums) + 1) if nums else 1:03d}"


def emit_task(
    project_root: Path, satisfies: str, title: str, dod: list[str], body: str = ""
) -> Path:
    """Write an agent-authored task, linked to the requirement it serves.

    Same division as polish/routing.py: the payload is judgement, the id,
    frontmatter and write are not.
    """
    if not (project_root / "requirements" / f"{satisfies}.md").is_file():
        raise ValueError(f"no such requirement: {satisfies}")
    if not dod:
        raise ValueError("a task needs at least one dod entry")
    tasks_dir = project_root / "tasks"
    tasks_dir.mkdir(parents=True, exist_ok=True)
    task_id = _next_task_id(tasks_dir)
    post = frontmatter.Post(
        body, id=task_id, title=title, status="todo", dod=list(dod), satisfies=[satisfies]
    )
    path = tasks_dir / f"{task_id}.md"
    path.write_text(frontmatter.dumps(post), encoding="utf-8")
    return path
```

Add to `cli.py`:

```python
    p_task = sub.add_parser("task", parents=[common])
    p_task.add_argument("--satisfies", required=True)
    p_task.add_argument("--title", required=True)
    p_task.add_argument("--dod", action="append", required=True)
    p_task.add_argument("--body", default="")
```

```python
    elif args.cmd == "task":
        path = emit_task(
            args.project_root, args.satisfies, args.title, args.dod, args.body
        )
        print(f"wrote {path.stem} at {path}")
```

- [ ] **Step 4: Run the whole suite**

Run: `uv run pytest -m unit`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
uv run ruff check . && uv run pyright
git add src/factory/doctor tests/unit/doctor/test_task.py
git commit -m "feat(doctor): emit an agent-authored task linked to its requirement"
```

---

### Task 13: The doctor skill

**Files:**
- Create: `.pi/skills/doctor/SKILL.md`
- Test: `tests/unit/doctor/test_skill_contract.py`

**Interfaces:**
- Consumes: every command from Tasks 9–12.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/doctor/test_skill_contract.py
from pathlib import Path

_SKILL = Path(__file__).resolve().parents[3] / ".pi" / "skills" / "doctor" / "SKILL.md"


def test_the_skill_exists_and_names_every_command():
    text = _SKILL.read_text(encoding="utf-8")
    for command in ("factory doctor context", "factory doctor mint",
                    "factory doctor promote", "factory doctor task"):
        assert command in text


def test_the_skill_gives_completion_to_the_agent_not_the_tools():
    text = _SKILL.read_text(encoding="utf-8").lower()
    assert "you decide when the pass is complete" in text
    # The inverse claim belongs to trace-fix, whose gap set is finite. Copying it
    # here would be the mistake the design's section 2.1 records.
    assert "the tools own enumeration" not in text


def test_the_skill_forbids_batching_approvals():
    assert "one proposal, one confirmation" in _SKILL.read_text(encoding="utf-8").lower()
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/unit/doctor/test_skill_contract.py -v`
Expected: FAIL — `FileNotFoundError: .pi/skills/doctor/SKILL.md`

- [ ] **Step 3: Write the skill**

```markdown
---
name: doctor
description: Turn prose specs into system requirements — read the specs, judge which claims are falsifiable requirements, propose them one at a time, and let the doctor tools perform every write.
---

# Doctor

Use this when a project's behaviour is described in specs but not recorded in its
requirements register — a new project being onboarded, or an existing one whose
specs have moved ahead of its requirements.

## What you own, and what you do not

You own **the judgement**: which claims in the prose are requirements, how many
are in a passage, whether the register already covers one, how a statement should
read, when the pass is done, and what a metric task says.

You do **not** own id assignment, frontmatter, or the scorer lookup. Those are
mechanical, and they fail silently when done by hand — a colliding `SR-004`, or
YAML the register rejects long after you wrote it.

This split is narrower than the one in `\trace-fix`, and deliberately so. That
loop works over a finite gap set on disk, so its tools can tell it when the work
is finished. Yours works over prose, where "have we captured every behaviour" is
not computable. **You decide when the pass is complete**, and you say what you
based that on.

## Steps

1. **Get the register state.** Call `factory doctor context`. It gives you every
   requirement with its statement, source and state, the declared harnesses, and
   which metrics are actually implemented. It does not summarise the specs.
2. **Read the specs yourself**, in full, with your own file tools. The context
   command lists their paths and deliberately does not excerpt them.
3. **Judge.** A requirement is a claim a measurement could contradict. "The
   navigation system shall preempt patrol within 5s of a shark detection" is one.
   "The system should be responsive" is not. A single heading may hold three
   requirements or none — the register, not the document structure, tells you
   what is already covered.
4. **Propose one.** Give the human the statement you would record, the passage it
   came from, and why you read it as falsifiable. If an existing requirement
   already covers the ground, say so instead of minting a near-duplicate.
5. **Wait.** One proposal, one confirmation. Never batch approvals, and do not
   call a write tool before they answer.
6. **On accept**, `factory doctor mint --source <spec path> --title ...
   --statement ... --domain ...`. Return to step 4.
7. **When the human wants a requirement bound**, `factory doctor promote SR-NNN
   --harness ... --experiment ... --metric ... --assert ...`. Propose the
   harness, experiment and metric name; let the human choose the threshold. It is
   their product decision, not yours.
8. **If promote reports the metric is NOT implemented**, propose a task that
   implements it in the target repo's scorers module, with a real definition of
   done. On accept, `factory doctor task --satisfies SR-NNN --title ... --dod ...`.
9. **Say when you believe the pass is complete**, and what you based it on — which
   specs you read, and what you deliberately did not record as a requirement.

## Rules

- **Never hand-write a requirement or task file.** `mint` and `promote` produce
  frontmatter the register can parse; hand-authored YAML is discovered as broken
  much later, by something else.
- **Never invent an assertion threshold.** Propose the metric, ask for the number.
- **A proposed requirement is not a failure.** Recording one whose measurement is
  undecided is the honest state; it does not block the gate.
- **Do not link tasks to requirements here.** `\trace-fix` already does that, with
  ranked candidates. This skill only mints what does not yet exist.
- **Step 9 is a claim, not a gate.** `factory trace check` remains the gate and
  re-derives everything from disk.
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/unit/doctor/ -v`
Expected: PASS

- [ ] **Step 5: Full gate and commit**

```bash
uv run pytest -m unit && uv run ruff check . && uv run pyright
git add .pi/skills/doctor/SKILL.md tests/unit/doctor/test_skill_contract.py
git commit -m "feat(doctor): the doctor skill"
```

---

## Verification

The plan is done when, from a clean tree:

- `uv run pytest -m unit` passes in the factory
- `uv run ruff check .` and `uv run pyright` are clean
- `uv run pytest -m unit` passes in `cool_physical_ai_project`
- `python -m factory.doctor context --project-root ../../cool_physical_ai_project`
  lists both drone specs, reports `SR-001` as active, and reports
  `sim-testbench -> preemption_success_rate` as implemented
- `python -m factory.trace status --project-root ../../cool_physical_ai_project`
  runs without importing any drone code, and shows a `proposed` line
