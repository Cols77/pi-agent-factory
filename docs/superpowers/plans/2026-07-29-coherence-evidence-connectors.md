# Coherence Evidence Connectors Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the context-gather gate's LLM self-attestation (`coherence.proven`/`pass`) with a two-layer, factory-verified gate: a deliverable-derived coverage floor plus an extensible connector framework that re-executes the agent's declared checks.

**Architecture:** A new `factory/evidence/` package provides a `Connector` protocol, an `EvidenceContext` source-bundle, and a `Registry`. Built-in connectors verify filesystem facts and (via the trusted `GateRunner`) baseline test results. `validate_manifest` derives `proven` from a `Modify:`-deliverable coverage check plus connector results, instead of trusting the agent's booleans.

**Tech Stack:** Python 3, `jsonschema` (Draft 2020-12), `pytest`, stdlib `ast`/`re`. Package import root is `factory` (e.g. `from factory.evidence.registry import Registry`).

## Global Constraints

- **Test marker:** every test module sets `pytestmark = pytest.mark.unit` (mirror existing `tests/unit/`).
- **Run tests with:** `uv run pytest <path> -v`.
- **Trust boundary:** connector *code* is trusted; connector *args* are untrusted agent data. A connector maps args to fixed operations and MUST NOT interpolate them into a shell or `eval`. No connector runs a shell.
- **`bash="deny"` for the context-gatherer is preserved** — dynamic checks run only via the existing `GateRunner`, never via the agent.
- **Style:** `from __future__ import annotations` at the top of every new module; type every function signature; match the terse docstring style in `src/factory/`.
- **Coverage floor is `Modify:`-only** — `Create:`/`Test:` deliverables are brought into existence and are excluded (see `deliverables.py`).

---

### Task 1: `modified_deliverables` helper

**Files:**
- Modify: `src/factory/orchestrator/deliverables.py`
- Test: `tests/unit/orchestrator/test_deliverables.py`

**Interfaces:**
- Consumes: existing `_parse(task_body, pattern)` in the same module.
- Produces: `modified_deliverables(task_body: str) -> list[str]` — the `Modify:` paths only, in order, de-duplicated.

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/orchestrator/test_deliverables.py`:

```python
def test_modified_deliverables_only_modify_lines():
    from factory.orchestrator.deliverables import modified_deliverables
    body = "- Create: `src/a.py`\n- Modify: `src/b.py`\n- Test: `tests/test_a.py`\n- Modify: `src/b.py`"
    # Create:/Test: excluded; Modify: kept and de-duplicated.
    assert modified_deliverables(body) == ["src/b.py"]


def test_modified_deliverables_empty_when_none():
    from factory.orchestrator.deliverables import modified_deliverables
    assert modified_deliverables("- Create: `src/a.py`\njust prose") == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/orchestrator/test_deliverables.py::test_modified_deliverables_only_modify_lines -v`
Expected: FAIL with `ImportError: cannot import name 'modified_deliverables'`.

- [ ] **Step 3: Write minimal implementation**

In `src/factory/orchestrator/deliverables.py`, add after `_CREATED_LINE`:

```python
# Only the MODIFY lines -- pre-existing files the task will change. These are
# the paths that MUST already exist and be gathered into context (unlike
# Create:/Test:, which the task brings into existence).
_MODIFIED_LINE = re.compile(r"^\s*[-*]?\s*modify\s*:\s*`([^`]+)`", re.IGNORECASE)
```

And add after `created_deliverables`:

```python
def modified_deliverables(task_body: str) -> list[str]:
    """Paths the task declares it will MODIFY (Modify: lines only) -- pre-existing
    files that must be gathered into context. Create:/Test: are excluded (the task
    brings those into existence)."""
    return _parse(task_body, _MODIFIED_LINE)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/orchestrator/test_deliverables.py -v`
Expected: PASS (all tests in file).

- [ ] **Step 5: Commit**

```bash
git add src/factory/orchestrator/deliverables.py tests/unit/orchestrator/test_deliverables.py
git commit -m "feat: modified_deliverables helper (Modify:-only paths)"
```

---

### Task 2: Evidence core — types, registry, schema helper

**Files:**
- Create: `src/factory/evidence/__init__.py`
- Create: `src/factory/evidence/types.py`
- Create: `src/factory/evidence/registry.py`
- Modify: `src/factory/validation/schema_validator.py`
- Test: `tests/unit/evidence/__init__.py`
- Test: `tests/unit/evidence/test_registry.py`
- Test: `tests/unit/test_schema_validator.py`

**Interfaces:**
- Consumes: `Draft202012Validator` (already used in `schema_validator.py`); `GateRunner` protocol from `factory.orchestrator.backends`.
- Produces:
  - `CheckResult(passed: bool, evidence: str)` — frozen dataclass.
  - `EvidenceContext(repo_root: Path, gates: GateRunner | None = None, kb_dir: Path | None = None)` — dataclass.
  - `Connector` — `typing.Protocol` with attributes `kind: str`, `args_schema: dict`, `side_effect_free: bool` and method `evaluate(self, args: dict, ctx: EvidenceContext) -> CheckResult`.
  - `Registry` — `register(connector) -> None` (raises `ValueError` on duplicate `kind`), `get(kind) -> Connector | None`, `evaluate_checks(checks: list[dict], ctx: EvidenceContext) -> list[str]` (error strings; empty = all passed).
  - `schema_validator.validate_against(instance, schema: dict) -> list[str]`.

- [ ] **Step 1: Write the failing test for `validate_against`**

Append to `tests/unit/test_schema_validator.py`:

```python
def test_validate_against_accepts_dict_schema():
    from factory.validation.schema_validator import validate_against
    schema = {"type": "object", "required": ["x"], "properties": {"x": {"type": "string"}}}
    assert validate_against({"x": "ok"}, schema) == []
    errs = validate_against({}, schema)
    assert errs and any("x" in e for e in errs)
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/unit/test_schema_validator.py::test_validate_against_accepts_dict_schema -v`
Expected: FAIL with `ImportError: cannot import name 'validate_against'`.

- [ ] **Step 3: Implement `validate_against`**

In `src/factory/validation/schema_validator.py`, add (and refactor `validate` to reuse it):

```python
def validate_against(instance: dict, schema: dict) -> list[str]:
    """Validate `instance` against an in-memory JSON `schema` dict.

    Returns a list of human-readable error strings; empty means valid.
    """
    validator = Draft202012Validator(schema, format_checker=Draft202012Validator.FORMAT_CHECKER)
    errors = sorted(validator.iter_errors(instance), key=lambda e: list(e.path))
    return [f"{'/'.join(str(p) for p in e.path) or '<root>'}: {e.message}" for e in errors]


def validate(instance: dict, schema_path: Path | str) -> list[str]:
    """Validate `instance` against the JSON schema at `schema_path`."""
    schema = json.loads(Path(schema_path).read_text(encoding="utf-8"))
    return validate_against(instance, schema)
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/unit/test_schema_validator.py -v`
Expected: PASS.

- [ ] **Step 5: Create the evidence package types**

Create `src/factory/evidence/__init__.py`:

```python
```

(empty file)

Create `src/factory/evidence/types.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable

from factory.orchestrator.backends import GateRunner


@dataclass(frozen=True)
class CheckResult:
    passed: bool
    evidence: str


@dataclass
class EvidenceContext:
    """Bundle of evidence sources a connector may read. A connector touches only
    the sources it needs; new sources are added here without changing existing
    connectors."""
    repo_root: Path
    gates: GateRunner | None = None
    kb_dir: Path | None = None


@runtime_checkable
class Connector(Protocol):
    kind: str
    args_schema: dict
    side_effect_free: bool

    def evaluate(self, args: dict, ctx: EvidenceContext) -> CheckResult: ...
```

- [ ] **Step 6: Write the failing registry test**

Create `tests/unit/evidence/__init__.py` (empty), then `tests/unit/evidence/test_registry.py`:

```python
from __future__ import annotations

from pathlib import Path

import pytest

from factory.evidence.types import CheckResult, EvidenceContext
from factory.evidence.registry import Registry

pytestmark = pytest.mark.unit


class _AlwaysConnector:
    kind = "always"
    args_schema = {"type": "object", "required": ["ok"], "properties": {"ok": {"type": "boolean"}},
                   "additionalProperties": False}
    side_effect_free = True

    def evaluate(self, args, ctx):
        return CheckResult(passed=bool(args["ok"]), evidence=f"ok={args['ok']}")


class _BoomConnector:
    kind = "boom"
    args_schema = {"type": "object"}
    side_effect_free = True

    def evaluate(self, args, ctx):
        raise RuntimeError("kaboom")


def _ctx(tmp_path):
    return EvidenceContext(repo_root=tmp_path)


def test_register_and_evaluate_pass(tmp_path):
    r = Registry()
    r.register(_AlwaysConnector())
    assert r.evaluate_checks([{"name": "c1", "kind": "always", "args": {"ok": True}}], _ctx(tmp_path)) == []


def test_failed_check_reports_error(tmp_path):
    r = Registry()
    r.register(_AlwaysConnector())
    errs = r.evaluate_checks([{"name": "c1", "kind": "always", "args": {"ok": False}}], _ctx(tmp_path))
    assert errs and "c1" in errs[0] and "ok=False" in errs[0]


def test_unknown_kind_is_error(tmp_path):
    r = Registry()
    errs = r.evaluate_checks([{"name": "c1", "kind": "nope", "args": {}}], _ctx(tmp_path))
    assert errs and "unknown kind" in errs[0] and "nope" in errs[0]


def test_bad_args_is_error(tmp_path):
    r = Registry()
    r.register(_AlwaysConnector())
    errs = r.evaluate_checks([{"name": "c1", "kind": "always", "args": {}}], _ctx(tmp_path))
    assert errs and "c1" in errs[0]


def test_connector_exception_becomes_failed_check(tmp_path):
    r = Registry()
    r.register(_BoomConnector())
    errs = r.evaluate_checks([{"name": "c1", "kind": "boom", "args": {}}], _ctx(tmp_path))
    assert errs and "boom errored" in errs[0] and "kaboom" in errs[0]


def test_duplicate_registration_raises():
    r = Registry()
    r.register(_AlwaysConnector())
    with pytest.raises(ValueError):
        r.register(_AlwaysConnector())
```

- [ ] **Step 7: Run to verify it fails**

Run: `uv run pytest tests/unit/evidence/test_registry.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'factory.evidence.registry'`.

- [ ] **Step 8: Implement the registry**

Create `src/factory/evidence/registry.py`:

```python
from __future__ import annotations

from factory.evidence.types import Connector, EvidenceContext
from factory.validation.schema_validator import validate_against


class Registry:
    """Maps a check `kind` to a Connector and evaluates declared checks. Connector
    code is trusted; check `args` are untrusted agent data validated against each
    connector's `args_schema` before evaluation."""

    def __init__(self) -> None:
        self._by_kind: dict[str, Connector] = {}

    def register(self, connector: Connector) -> None:
        if connector.kind in self._by_kind:
            raise ValueError(f"connector already registered for kind: {connector.kind}")
        self._by_kind[connector.kind] = connector

    def get(self, kind: str) -> Connector | None:
        return self._by_kind.get(kind)

    def evaluate_checks(self, checks: list[dict], ctx: EvidenceContext) -> list[str]:
        """Return a list of error strings (empty = every check passed). Unknown
        kind, invalid args, a failed check, or a connector exception each yield an
        error; nothing here raises."""
        errors: list[str] = []
        for check in checks:
            name = check.get("name", "<unnamed>")
            kind = check.get("kind", "")
            args = check.get("args", {})
            connector = self._by_kind.get(kind)
            if connector is None:
                errors.append(f"check '{name}': unknown kind '{kind}'")
                continue
            arg_errors = validate_against(args, connector.args_schema)
            if arg_errors:
                errors.append(f"check '{name}': invalid args: {'; '.join(arg_errors)}")
                continue
            try:
                result = connector.evaluate(args, ctx)
            except Exception as exc:  # connector bug or unreadable input -> failed check
                errors.append(f"check '{name}': {kind} errored: {exc}")
                continue
            if not result.passed:
                errors.append(f"check '{name}' failed: {result.evidence}")
        return errors
```

- [ ] **Step 9: Run to verify it passes**

Run: `uv run pytest tests/unit/evidence/test_registry.py tests/unit/test_schema_validator.py -v`
Expected: PASS.

- [ ] **Step 10: Commit**

```bash
git add src/factory/evidence/__init__.py src/factory/evidence/types.py src/factory/evidence/registry.py src/factory/validation/schema_validator.py tests/unit/evidence/__init__.py tests/unit/evidence/test_registry.py tests/unit/test_schema_validator.py
git commit -m "feat: evidence connector framework (types + registry)"
```

---

### Task 3: Static connectors

**Files:**
- Create: `src/factory/evidence/connectors.py`
- Test: `tests/unit/evidence/test_connectors_static.py`

**Interfaces:**
- Consumes: `CheckResult`, `EvidenceContext` (Task 2); `Registry` (Task 2).
- Produces:
  - Connector classes `FilesExist`, `FileContains`, `SymbolDefined`, `AnchorResolves` with `kind` values `"files_exist"`, `"file_contains"`, `"symbol_defined"`, `"anchor_resolves"`.
  - Module-level helper `symbol_in_file(path: Path, symbol: str) -> bool`.
  - Module-level `DEFAULT_REGISTRY: Registry` with all connectors registered (dynamic connector added in Task 4).

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/evidence/test_connectors_static.py`:

```python
from __future__ import annotations

import pytest

from factory.evidence.types import EvidenceContext
from factory.evidence.connectors import (
    FilesExist, FileContains, SymbolDefined, AnchorResolves, symbol_in_file,
)

pytestmark = pytest.mark.unit


def _ctx(tmp_path):
    return EvidenceContext(repo_root=tmp_path)


def test_files_exist_pass_and_fail(tmp_path):
    (tmp_path / "a.py").write_text("x", encoding="utf-8")
    assert FilesExist().evaluate({"paths": ["a.py"]}, _ctx(tmp_path)).passed is True
    res = FilesExist().evaluate({"paths": ["a.py", "missing.py"]}, _ctx(tmp_path))
    assert res.passed is False and "missing.py" in res.evidence


def test_file_contains_literal_and_regex(tmp_path):
    (tmp_path / "f.txt").write_text("hello world 42", encoding="utf-8")
    assert FileContains().evaluate({"path": "f.txt", "pattern": "world", "mode": "literal"}, _ctx(tmp_path)).passed
    assert FileContains().evaluate({"path": "f.txt", "pattern": r"\d+", "mode": "regex"}, _ctx(tmp_path)).passed
    assert not FileContains().evaluate({"path": "f.txt", "pattern": "nope", "mode": "literal"}, _ctx(tmp_path)).passed


def test_file_contains_missing_file_fails(tmp_path):
    res = FileContains().evaluate({"path": "no.txt", "pattern": "x", "mode": "literal"}, _ctx(tmp_path))
    assert res.passed is False and "not found" in res.evidence


def test_symbol_in_file_python(tmp_path):
    (tmp_path / "m.py").write_text("class Foo:\n    pass\n\ndef bar():\n    return 1\n", encoding="utf-8")
    assert symbol_in_file(tmp_path / "m.py", "Foo") is True
    assert symbol_in_file(tmp_path / "m.py", "bar") is True
    assert symbol_in_file(tmp_path / "m.py", "Baz") is False


def test_symbol_in_file_markdown_heading(tmp_path):
    (tmp_path / "d.md").write_text("# Title\n\n## Design Notes\n\ntext\n", encoding="utf-8")
    assert symbol_in_file(tmp_path / "d.md", "Design Notes") is True
    assert symbol_in_file(tmp_path / "d.md", "Absent") is False


def test_symbol_defined_connector(tmp_path):
    (tmp_path / "m.py").write_text("def bar():\n    return 1\n", encoding="utf-8")
    assert SymbolDefined().evaluate({"path": "m.py", "symbol": "bar"}, _ctx(tmp_path)).passed
    assert not SymbolDefined().evaluate({"path": "m.py", "symbol": "nope"}, _ctx(tmp_path)).passed


def test_anchor_resolves(tmp_path):
    (tmp_path / "m.py").write_text("class Foo:\n    pass\n", encoding="utf-8")
    assert AnchorResolves().evaluate({"ref": "m.py#Foo"}, _ctx(tmp_path)).passed
    assert not AnchorResolves().evaluate({"ref": "m.py#Bar"}, _ctx(tmp_path)).passed
    # No anchor -> existence only.
    assert AnchorResolves().evaluate({"ref": "m.py"}, _ctx(tmp_path)).passed
    assert not AnchorResolves().evaluate({"ref": "missing.py"}, _ctx(tmp_path)).passed
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/unit/evidence/test_connectors_static.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'factory.evidence.connectors'`.

- [ ] **Step 3: Implement the static connectors**

Create `src/factory/evidence/connectors.py`:

```python
from __future__ import annotations

import ast
import re
from pathlib import Path

from factory.evidence.registry import Registry
from factory.evidence.types import CheckResult, EvidenceContext

_MD_SUFFIXES = {".md", ".markdown"}


def symbol_in_file(path: Path, symbol: str) -> bool:
    """True if `symbol` is defined in `path`. Python files are parsed with `ast`
    (top-level or nested def/class/assignment names); markdown matches a heading
    whose text contains the symbol; any other file falls back to a word-boundary
    regex search."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    suffix = path.suffix.lower()
    if suffix == ".py":
        try:
            tree = ast.parse(text)
        except SyntaxError:
            return bool(re.search(rf"\b{re.escape(symbol)}\b", text))
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.name == symbol:
                return True
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store) and node.id == symbol:
                return True
        return False
    if suffix in _MD_SUFFIXES:
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("#") and symbol in stripped.lstrip("#").strip():
                return True
        return False
    return bool(re.search(rf"\b{re.escape(symbol)}\b", text))


class FilesExist:
    kind = "files_exist"
    side_effect_free = True
    args_schema = {
        "type": "object", "required": ["paths"], "additionalProperties": False,
        "properties": {"paths": {"type": "array", "items": {"type": "string"}, "minItems": 1}},
    }

    def evaluate(self, args: dict, ctx: EvidenceContext) -> CheckResult:
        missing = [p for p in args["paths"] if not (ctx.repo_root / p).exists()]
        if missing:
            return CheckResult(False, f"missing: {', '.join(missing)}")
        return CheckResult(True, f"all present: {', '.join(args['paths'])}")


class FileContains:
    kind = "file_contains"
    side_effect_free = True
    args_schema = {
        "type": "object", "required": ["path", "pattern", "mode"], "additionalProperties": False,
        "properties": {
            "path": {"type": "string"},
            "pattern": {"type": "string"},
            "mode": {"enum": ["regex", "literal"]},
        },
    }

    def evaluate(self, args: dict, ctx: EvidenceContext) -> CheckResult:
        target = ctx.repo_root / args["path"]
        if not target.exists():
            return CheckResult(False, f"file not found: {args['path']}")
        text = target.read_text(encoding="utf-8", errors="replace")
        pattern, mode = args["pattern"], args["mode"]
        found = (pattern in text) if mode == "literal" else bool(re.search(pattern, text))
        if found:
            return CheckResult(True, f"{args['path']} matches {mode} /{pattern}/")
        return CheckResult(False, f"{args['path']} does not match {mode} /{pattern}/")


class SymbolDefined:
    kind = "symbol_defined"
    side_effect_free = True
    args_schema = {
        "type": "object", "required": ["path", "symbol"], "additionalProperties": False,
        "properties": {"path": {"type": "string"}, "symbol": {"type": "string"}},
    }

    def evaluate(self, args: dict, ctx: EvidenceContext) -> CheckResult:
        target = ctx.repo_root / args["path"]
        if not target.exists():
            return CheckResult(False, f"file not found: {args['path']}")
        if symbol_in_file(target, args["symbol"]):
            return CheckResult(True, f"{args['symbol']} defined in {args['path']}")
        return CheckResult(False, f"{args['symbol']} not defined in {args['path']}")


class AnchorResolves:
    kind = "anchor_resolves"
    side_effect_free = True
    args_schema = {
        "type": "object", "required": ["ref"], "additionalProperties": False,
        "properties": {"ref": {"type": "string"}},
    }

    def evaluate(self, args: dict, ctx: EvidenceContext) -> CheckResult:
        ref = args["ref"]
        path_part, _, anchor = ref.partition("#")
        target = ctx.repo_root / path_part
        if not target.exists():
            return CheckResult(False, f"file not found: {path_part}")
        if not anchor:
            return CheckResult(True, f"{path_part} exists")
        if symbol_in_file(target, anchor):
            return CheckResult(True, f"{anchor} resolves in {path_part}")
        return CheckResult(False, f"anchor '{anchor}' not found in {path_part}")


DEFAULT_REGISTRY = Registry()
for _connector in (FilesExist(), FileContains(), SymbolDefined(), AnchorResolves()):
    DEFAULT_REGISTRY.register(_connector)
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/unit/evidence/test_connectors_static.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/factory/evidence/connectors.py tests/unit/evidence/test_connectors_static.py
git commit -m "feat: static evidence connectors (fs/symbol/anchor)"
```

---

### Task 4: Dynamic connector `test_result`

**Files:**
- Modify: `src/factory/evidence/connectors.py`
- Test: `tests/unit/evidence/test_connectors_dynamic.py`

**Interfaces:**
- Consumes: `FakeGateRunner` from `factory.orchestrator.backends` (test-only); `EvidenceContext.gates`.
- Produces: `TestResult` connector, `kind = "test_result"`, registered into `DEFAULT_REGISTRY`.

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/evidence/test_connectors_dynamic.py`:

```python
from __future__ import annotations

import pytest

from factory.orchestrator.backends import FakeGateRunner
from factory.evidence.types import EvidenceContext
from factory.evidence.connectors import TestResult

pytestmark = pytest.mark.unit


def _ctx(tmp_path, gate_rc):
    return EvidenceContext(repo_root=tmp_path, gates=FakeGateRunner({"unit": [gate_rc]}))


def test_expected_pass_when_gate_green(tmp_path):
    res = TestResult().evaluate({"gate": "unit", "expected": "pass"}, _ctx(tmp_path, 0))
    assert res.passed is True


def test_expected_pass_fails_when_gate_red(tmp_path):
    res = TestResult().evaluate({"gate": "unit", "expected": "pass"}, _ctx(tmp_path, 1))
    assert res.passed is False and "exit=1" in res.evidence


def test_expected_fail_passes_when_gate_red(tmp_path):
    # Bug-repro baseline: the suite is expected to FAIL right now.
    res = TestResult().evaluate({"gate": "unit", "expected": "fail"}, _ctx(tmp_path, 1))
    assert res.passed is True


def test_missing_gate_runner_is_failed_check(tmp_path):
    res = TestResult().evaluate({"gate": "unit", "expected": "pass"}, EvidenceContext(repo_root=tmp_path))
    assert res.passed is False and "gate runner" in res.evidence
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/unit/evidence/test_connectors_dynamic.py -v`
Expected: FAIL with `ImportError: cannot import name 'TestResult'`.

- [ ] **Step 3: Implement `TestResult` and register it**

In `src/factory/evidence/connectors.py`, add the class before the `DEFAULT_REGISTRY` block:

```python
class TestResult:
    """Baseline test/regression check, executed via the trusted GateRunner (the
    agent never runs anything). `expected: pass` = a regression safety net exists;
    `expected: fail` = the bug reproduces at baseline."""
    kind = "test_result"
    side_effect_free = False
    args_schema = {
        "type": "object", "required": ["gate", "expected"], "additionalProperties": False,
        "properties": {
            "gate": {"enum": ["unit", "sim", "full"]},
            "expected": {"enum": ["pass", "fail"]},
        },
    }

    def evaluate(self, args: dict, ctx: EvidenceContext) -> CheckResult:
        if ctx.gates is None:
            return CheckResult(False, "test_result requires a gate runner but none is available")
        rc = ctx.gates.run(args["gate"])
        actual_pass = rc == 0
        want_pass = args["expected"] == "pass"
        passed = actual_pass == want_pass
        return CheckResult(
            passed,
            f"gate {args['gate']} exit={rc} (expected {args['expected']})",
        )
```

Then update the registration loop to include it:

```python
DEFAULT_REGISTRY = Registry()
for _connector in (FilesExist(), FileContains(), SymbolDefined(), AnchorResolves(), TestResult()):
    DEFAULT_REGISTRY.register(_connector)
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/unit/evidence/ -v`
Expected: PASS (all evidence tests).

- [ ] **Step 5: Commit**

```bash
git add src/factory/evidence/connectors.py tests/unit/evidence/test_connectors_dynamic.py
git commit -m "feat: test_result dynamic connector (baseline gate check)"
```

---

### Task 5: Coverage floor

**Files:**
- Create: `src/factory/evidence/coverage.py`
- Test: `tests/unit/evidence/test_coverage.py`

**Interfaces:**
- Consumes: `modified_deliverables` (Task 1).
- Produces: `coverage_errors(task_body: str, context: dict, repo_root: Path) -> list[str]` — one error per `Modify:` deliverable that is not gathered into `context` or does not resolve on disk.

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/evidence/test_coverage.py`:

```python
from __future__ import annotations

import pytest

from factory.evidence.coverage import coverage_errors

pytestmark = pytest.mark.unit

BODY = "- Modify: `src/b.py`\n- Create: `src/a.py`\n- Test: `tests/test_a.py`"


def test_passes_when_modify_gathered_and_exists(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "b.py").write_text("x", encoding="utf-8")
    context = {"source_files": ["src/b.py"], "spec": [], "plan": []}
    assert coverage_errors(BODY, context, tmp_path) == []


def test_error_when_modify_not_gathered(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "b.py").write_text("x", encoding="utf-8")
    context = {"source_files": [], "spec": [], "plan": []}
    errs = coverage_errors(BODY, context, tmp_path)
    assert errs and "src/b.py" in errs[0] and "not gathered" in errs[0]


def test_error_when_gathered_but_missing_on_disk(tmp_path):
    context = {"source_files": ["src/b.py"], "spec": [], "plan": []}
    errs = coverage_errors(BODY, context, tmp_path)
    assert errs and "src/b.py" in errs[0] and "missing on disk" in errs[0]


def test_anchor_in_gathered_ref_is_stripped(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "b.py").write_text("x", encoding="utf-8")
    context = {"source_files": ["src/b.py#Foo"], "spec": [], "plan": []}
    assert coverage_errors(BODY, context, tmp_path) == []


def test_no_modify_deliverables_is_clean(tmp_path):
    context = {"source_files": [], "spec": [], "plan": []}
    assert coverage_errors("- Create: `src/a.py`", context, tmp_path) == []
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/unit/evidence/test_coverage.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'factory.evidence.coverage'`.

- [ ] **Step 3: Implement coverage**

Create `src/factory/evidence/coverage.py`:

```python
from __future__ import annotations

from pathlib import Path

from factory.orchestrator.deliverables import modified_deliverables


def _gathered_refs(context: dict) -> set[str]:
    """All paths the manifest gathered, anchor-stripped: source_files + spec + plan."""
    refs: set[str] = set()
    for key in ("source_files", "spec", "plan"):
        for ref in context.get(key, []) or []:
            refs.add(str(ref).split("#", 1)[0])
    return refs


def coverage_errors(task_body: str, context: dict, repo_root: Path) -> list[str]:
    """Factory-derived coverage floor (agent-independent): every `Modify:`
    deliverable the task declares must be gathered into context AND resolve on
    disk. Create:/Test: are excluded (the task brings those into existence)."""
    gathered = _gathered_refs(context)
    errors: list[str] = []
    for path in modified_deliverables(task_body):
        if path not in gathered:
            errors.append(f"deliverable not gathered into context: {path} (declared Modify:)")
        elif not (repo_root / path).exists():
            errors.append(f"gathered deliverable missing on disk: {path}")
    return errors
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/unit/evidence/test_coverage.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/factory/evidence/coverage.py tests/unit/evidence/test_coverage.py
git commit -m "feat: Modify:-deliverable coverage floor"
```

---

### Task 6: Schema change + `validate_manifest` rewrite

**Files:**
- Modify: `src/factory/schemas/context_manifest.schema.json`
- Modify: `src/factory/validation/manifest_validator.py`
- Test: `tests/unit/test_manifest_validator.py`

**Interfaces:**
- Consumes: `DEFAULT_REGISTRY` (Task 3/4), `coverage_errors` (Task 5), `EvidenceContext` (Task 2), `Task` (`factory.orchestrator.ledger`).
- Produces: `validate_manifest(manifest: dict, repo_root: Path, *, task: Task | None = None, ctx: EvidenceContext | None = None) -> list[str]`. `proven` is derived (no errors ⇒ proven); agent-supplied `pass`/`proven` are schema-rejected.

- [ ] **Step 1: Update the schema**

In `src/factory/schemas/context_manifest.schema.json`, replace the `coherence` block so `proven` is gone and checks are typed:

```json
    "coherence": {
      "type": "object",
      "required": ["checks"],
      "additionalProperties": false,
      "properties": {
        "checks": {
          "type": "array",
          "items": {
            "type": "object",
            "required": ["name", "kind", "args"],
            "additionalProperties": false,
            "properties": {
              "name": {"type": "string"},
              "kind": {"type": "string"},
              "args": {"type": "object"}
            }
          }
        }
      }
    },
```

- [ ] **Step 2: Rewrite the failing tests**

Replace the body of `tests/unit/test_manifest_validator.py` with:

```python
import pytest
from factory.validation.manifest_validator import validate_manifest

pytestmark = pytest.mark.unit


def _manifest(tmp_path, checks=None, **ctx):
    (tmp_path / "tasks").mkdir(exist_ok=True)
    (tmp_path / "tasks" / "T-001.md").write_text("dod", encoding="utf-8")
    base = {
        "task_id": "T-001",
        "generated_by": "context-gatherer",
        "generated_at": "2026-07-16T14:32:10Z",
        "coherence": {"checks": checks if checks is not None else []},
        "context": {"task": "tasks/T-001.md", "source_files": [], "skills": []},
        "reject": None,
    }
    base["context"].update(ctx)
    return base


def test_valid_manifest_no_checks(tmp_path):
    assert validate_manifest(_manifest(tmp_path), tmp_path) == []


def test_missing_source_file_reports_error(tmp_path):
    m = _manifest(tmp_path, source_files=["src/does_not_exist.py"])
    errors = validate_manifest(m, tmp_path)
    assert any("does_not_exist" in e for e in errors)


def test_anchor_is_stripped_before_existence_check(tmp_path):
    (tmp_path / "spec.md").write_text("x", encoding="utf-8")
    m = _manifest(tmp_path, spec=["spec.md#section"])
    assert validate_manifest(m, tmp_path) == []


def test_legacy_pass_field_is_schema_rejected(tmp_path):
    m = _manifest(tmp_path)
    m["coherence"]["checks"] = [{"name": "x", "kind": "files_exist", "args": {"paths": ["a"]}, "pass": True}]
    errors = validate_manifest(m, tmp_path)
    assert errors  # additionalProperties:false rejects the stray `pass`


def test_legacy_proven_field_is_schema_rejected(tmp_path):
    m = _manifest(tmp_path)
    m["coherence"]["proven"] = True
    errors = validate_manifest(m, tmp_path)
    assert errors  # coherence.additionalProperties:false rejects `proven`


def test_connector_check_evaluated_pass(tmp_path):
    (tmp_path / "real.py").write_text("x", encoding="utf-8")
    m = _manifest(tmp_path, checks=[{"name": "c", "kind": "files_exist", "args": {"paths": ["real.py"]}}])
    assert validate_manifest(m, tmp_path) == []


def test_connector_check_evaluated_fail(tmp_path):
    m = _manifest(tmp_path, checks=[{"name": "c", "kind": "files_exist", "args": {"paths": ["ghost.py"]}}])
    errors = validate_manifest(m, tmp_path)
    assert any("ghost.py" in e for e in errors)


def test_unknown_kind_rejected(tmp_path):
    m = _manifest(tmp_path, checks=[{"name": "c", "kind": "made_up", "args": {}}])
    errors = validate_manifest(m, tmp_path)
    assert any("unknown kind" in e for e in errors)


def test_coverage_floor_requires_modify_deliverable(tmp_path):
    from factory.orchestrator.ledger import Task
    from pathlib import Path
    task = Task(id="T-001", title="t", status="todo", dod=["done"],
                body="- Modify: `src/b.py`", path=Path("x"))
    # Manifest gathered nothing; the Modify: deliverable is uncovered even though
    # every declared check passes -> still an error (honest-but-hollow).
    m = _manifest(tmp_path)
    errors = validate_manifest(m, tmp_path, task=task)
    assert any("src/b.py" in e and "not gathered" in e for e in errors)
```

- [ ] **Step 3: Run to verify tests fail**

Run: `uv run pytest tests/unit/test_manifest_validator.py -v`
Expected: FAIL (old validator still enforces `proven`/`pass`; new tests reference behavior not yet implemented).

- [ ] **Step 4: Rewrite `validate_manifest`**

Replace `src/factory/validation/manifest_validator.py` with:

```python
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from factory.evidence.connectors import DEFAULT_REGISTRY
from factory.evidence.coverage import coverage_errors
from factory.evidence.types import EvidenceContext
from factory.validation.schema_validator import SCHEMA_DIR, validate

if TYPE_CHECKING:
    from factory.orchestrator.ledger import Task

_SCHEMA = SCHEMA_DIR / "context_manifest.schema.json"


def _strip_anchor(ref: str) -> str:
    return ref.split("#", 1)[0]


def _context_ref_errors(manifest: dict, repo_root: Path) -> list[str]:
    ctx = manifest.get("context", {})
    refs: list[str] = []
    if ctx.get("task"):
        refs.append(ctx["task"])
    if ctx.get("prior_session"):
        refs.append(ctx["prior_session"])
    for key in ("source_files", "spec", "plan"):
        refs.extend(ctx.get(key, []))
    missing: list[str] = []
    for ref in refs:
        rel = _strip_anchor(ref)
        if not (repo_root / rel).exists():
            missing.append(f"context path missing: {rel}")
    return missing


def validate_manifest(
    manifest: dict,
    repo_root: Path,
    *,
    task: "Task | None" = None,
    ctx: EvidenceContext | None = None,
) -> list[str]:
    """Two-layer coherence gate. `coherence.proven` is DERIVED: the manifest
    passes iff this returns []. Agent-supplied `proven`/`pass` are schema-rejected.

    Layer 1 (coverage) runs only when `task` is supplied. Layer 2 (connectors)
    always runs; `ctx` defaults to a repo-root-only context (dynamic connectors
    needing a gate runner then fail with a clear message)."""
    errors = validate(manifest, _SCHEMA)
    if errors:
        return errors

    if ctx is None:
        ctx = EvidenceContext(repo_root=repo_root, gates=None, kb_dir=repo_root / "kb")

    out: list[str] = []
    if task is not None:
        out += coverage_errors(task.body, manifest.get("context", {}), repo_root)
    checks = manifest.get("coherence", {}).get("checks", [])
    out += DEFAULT_REGISTRY.evaluate_checks(checks, ctx)
    out += _context_ref_errors(manifest, repo_root)
    return out
```

- [ ] **Step 5: Run to verify tests pass**

Run: `uv run pytest tests/unit/test_manifest_validator.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/factory/schemas/context_manifest.schema.json src/factory/validation/manifest_validator.py tests/unit/test_manifest_validator.py
git commit -m "feat: two-layer validate_manifest (coverage + connectors), derive proven"
```

---

### Task 7: Wire into the context-gather node

**Files:**
- Modify: `src/factory/orchestrator/nodes.py`
- Modify: `src/factory/orchestrator/runner.py:72-74`
- Test: `tests/agent/test_nodes_context.py` (create if absent; otherwise add to the existing context-gather node test)

**Interfaces:**
- Consumes: `validate_manifest(..., task=, ctx=)` (Task 6); `EvidenceContext` (Task 2); `GateRunner`/`FakeGateRunner` (`factory.orchestrator.backends`).
- Produces: `run_context_gatherer(backend, task, repo_root, max_attempts=2, transcript_dir=None, status=..., gates=None)` — now builds an `EvidenceContext` and passes `task`+`ctx`; PASS condition becomes "validate returned no errors".

- [ ] **Step 1: Locate the current call and PASS condition**

In `src/factory/orchestrator/nodes.py`, the context-gather node currently does (around lines 114–124):

```python
        errors = validate_manifest(manifest, repo_root)
        if not errors and manifest.get("coherence", {}).get("proven"):
```

- [ ] **Step 2: Write the failing test**

Create `tests/agent/test_nodes_context.py`:

```python
from __future__ import annotations

import pytest

from factory.orchestrator.backends import FakeAgentBackend, FakeGateRunner
from factory.orchestrator.ledger import Task
from factory.orchestrator.nodes import run_context_gatherer
from factory.orchestrator.types import AgentResult, AgentRole, NodeOutcome

pytestmark = pytest.mark.agent


def _task(tmp_path):
    (tmp_path / "tasks").mkdir(exist_ok=True)
    p = tmp_path / "tasks" / "T-001.md"
    p.write_text("- Modify: `src/b.py`", encoding="utf-8")
    return Task(id="T-001", title="t", status="todo", dod=["done"],
                body="- Modify: `src/b.py`", path=p)


def _manifest_output(checks):
    return {
        "task_id": "T-001", "generated_by": "context-gatherer",
        "generated_at": "2026-07-16T14:32:10Z",
        "coherence": {"checks": checks},
        "context": {"task": "tasks/T-001.md", "source_files": ["src/b.py"], "skills": []},
        "reject": None,
    }


def _backend(manifest):
    return FakeAgentBackend({AgentRole.CONTEXT_GATHERER: [
        AgentResult(output=manifest, raw="", ok=True, session_id="s1"),
    ]})


def test_passes_with_covered_modify_and_passing_check(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "b.py").write_text("x", encoding="utf-8")
    task = _task(tmp_path)
    manifest = _manifest_output([{"name": "c", "kind": "files_exist", "args": {"paths": ["src/b.py"]}}])
    outcome, m, ev = run_context_gatherer(
        _backend(manifest), task, tmp_path, gates=FakeGateRunner(),
    )
    assert outcome == NodeOutcome.PASS
    assert m is not None


def test_rejects_when_modify_uncovered(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "b.py").write_text("x", encoding="utf-8")
    task = _task(tmp_path)
    # source_files omits the Modify: deliverable -> coverage floor fails every attempt.
    manifest = _manifest_output([])
    manifest["context"]["source_files"] = []
    outcome, m, ev = run_context_gatherer(
        _backend_two(manifest), task, tmp_path, gates=FakeGateRunner(),
    )
    assert outcome == NodeOutcome.REJECT


def _backend_two(manifest):
    # context-gather retries up to max_attempts=2 -> supply the scripted result twice.
    return FakeAgentBackend({AgentRole.CONTEXT_GATHERER: [
        AgentResult(output=manifest, raw="", ok=True, session_id="s1"),
        AgentResult(output=manifest, raw="", ok=True, session_id="s1"),
    ]})
```

> `AgentResult` is `AgentResult(ok: bool, output: dict, raw: str = "",
> session_id: str | None = None)` (verified in `types.py`); the kwargs above match.

- [ ] **Step 3: Run to verify it fails**

Run: `uv run pytest tests/agent/test_nodes_context.py -v`
Expected: FAIL (`run_context_gatherer` has no `gates` param / still checks `proven`).

- [ ] **Step 4: Update `run_context_gatherer`**

In `src/factory/orchestrator/nodes.py`:

1. Add the `EvidenceContext` import near the top (the module already imports
   `AgentBackend` and `GateRunner` from `factory.orchestrator.backends` — leave
   that line as-is):

```python
from factory.evidence.types import EvidenceContext
```

2. Add `gates: GateRunner | None = None` to the `run_context_gatherer` signature (after `status`).

3. Replace the validate call + PASS condition:

```python
        ctx = EvidenceContext(repo_root=repo_root, gates=gates, kb_dir=repo_root / "kb")
        errors = validate_manifest(manifest, repo_root, task=task, ctx=ctx)
        if not errors:
```

(Everything inside that `if` block — the PASS `status.report` and `return NodeOutcome.PASS` — stays unchanged.)

- [ ] **Step 5: Pass `gates` from `run_task`**

In `src/factory/orchestrator/runner.py`, update the context-gatherer call (currently lines 72–74):

```python
    c_outcome, manifest, c_ev = run_context_gatherer(
        backend, task, repo_root, transcript_dir=transcript_dir, status=status, gates=gates,
    )
```

- [ ] **Step 6: Run to verify node tests pass**

Run: `uv run pytest tests/agent/test_nodes_context.py -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/factory/orchestrator/nodes.py src/factory/orchestrator/runner.py tests/agent/test_nodes_context.py
git commit -m "feat: context-gather node uses two-layer gate (coverage + connectors)"
```

---

### Task 8: Update the context-gatherer prompt

**Files:**
- Modify: `src/factory/orchestrator/roles.py:63-74`
- Test: `tests/unit/orchestrator/test_roles_prompt.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: an updated `ROLE_PROMPTS[AgentRole.CONTEXT_GATHERER]` string describing the typed-check vocabulary and coverage requirement.

- [ ] **Step 1: Write the failing guard test**

Create `tests/unit/orchestrator/test_roles_prompt.py`:

```python
from __future__ import annotations

import pytest

from factory.orchestrator.roles import ROLE_PROMPTS
from factory.orchestrator.types import AgentRole

pytestmark = pytest.mark.unit


def test_context_gatherer_prompt_documents_typed_checks():
    prompt = ROLE_PROMPTS[AgentRole.CONTEXT_GATHERER]
    # The vocabulary the factory re-runs must be named so the agent emits it.
    for kind in ("files_exist", "file_contains", "symbol_defined", "anchor_resolves", "test_result"):
        assert kind in prompt
    # Self-attestation is gone: no proven/pass booleans to set.
    assert "proven" not in prompt
    # Coverage requirement is stated.
    assert "Modify:" in prompt
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/unit/orchestrator/test_roles_prompt.py -v`
Expected: FAIL (current prompt says "set coherence.proven=false" and names no kinds).

- [ ] **Step 3: Replace the prompt**

In `src/factory/orchestrator/roles.py`, replace the `AgentRole.CONTEXT_GATHERER` value in `ROLE_PROMPTS` with:

```python
    AgentRole.CONTEXT_GATHERER: (
        "You verify that spec, plan, prior session, and this task are coherent and "
        "that context is complete. Emit ONLY a context manifest as a fenced ```json block "
        "matching the context_manifest schema.\n"
        "Coherence is proven by DECLARED, MACHINE-VERIFIABLE checks -- the factory RE-RUNS "
        "every check you list, so a hollow or trivially-true check buys you nothing. Do NOT "
        "set any 'proven' or 'pass' field; the factory derives the verdict. Populate "
        "coherence.checks with entries of the form {\"name\": <str>, \"kind\": <str>, "
        "\"args\": {...}} drawn ONLY from this vocabulary:\n"
        "  - files_exist   {\"paths\": [<path>, ...]}\n"
        "  - file_contains {\"path\": <path>, \"pattern\": <str>, \"mode\": \"regex\"|\"literal\"}\n"
        "  - symbol_defined {\"path\": <path>, \"symbol\": <name>}\n"
        "  - anchor_resolves {\"ref\": \"<path>#<symbol-or-heading>\"}\n"
        "  - test_result   {\"gate\": \"unit\"|\"sim\"|\"full\", \"expected\": \"pass\"|\"fail\"}\n"
        "test_result is a BASELINE check (it runs before any work): expected=pass means a "
        "regression net exists; expected=fail means the bug reproduces now. Every file this "
        "task declares with a `Modify:` line MUST appear in context.source_files (it is a "
        "pre-existing file you must gather). If you cannot ground coherence in such checks, "
        "populate reject instead.\n"
        "FIRST, before anything else: check whether this task's deliverables (the "
        "`Create:`/`Modify:`/`Test:` paths in the task body) already exist and satisfy "
        "the Definition of Done. Read files with the read/view tool -- NOT with bash "
        "(bash is disabled for your role). If the work already appears complete, add "
        '"already_done": true and a one-line "already_done_reason" to the manifest '
        "JSON; coherence checks need not be provided in that case."
    ),
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/unit/orchestrator/test_roles_prompt.py -v`
Expected: PASS.

- [ ] **Step 5: Full suite + commit**

Run the whole suite to confirm nothing regressed:

Run: `uv run pytest -q`
Expected: PASS (no failures).

```bash
git add src/factory/orchestrator/roles.py tests/unit/orchestrator/test_roles_prompt.py
git commit -m "feat: context-gatherer prompt emits typed, re-runnable coherence checks"
```

---

## Self-Review

**Spec coverage:**
- Two-layer gate (coverage + connectors) → Tasks 5, 6.
- Connector framework (protocol/registry/context) → Task 2.
- Static vocabulary (`files_exist`/`file_contains`/`symbol_defined`/`anchor_resolves`) → Task 3.
- Dynamic `test_result{gate, expected}` baseline incl. `expected: fail` bug-repro → Task 4.
- `Modify:`-only coverage floor (corrected from spec's Modify+Test) → Tasks 1, 5.
- Schema removes agent `proven`/`pass`; `proven` derived → Task 6.
- `validate_manifest` gains optional `task`/`ctx`; CLI caller unaffected → Task 6.
- Node wiring + PASS-condition change + `gates` threading → Task 7.
- Prompt rewrite → Task 8.
- Trust boundary / no-shell / `bash="deny"` preserved → Global Constraints + Task 4 (`test_result` via `GateRunner` only).
- Error handling (unknown kind, bad args, connector exception → failed check) → Task 2 tests.
- Deferred (KB connectors, user connector discovery, post-work reuse) → intentionally absent; `EvidenceContext.kb_dir` leaves room without building them.

**Placeholder scan:** every code step contains complete code; no TBD/TODO. The one advisory note (Task 7 Step 2) tells the implementer to confirm `AgentResult` field names against `types.py` before running — a verification instruction, not a code placeholder.

**Type consistency:** `CheckResult(passed, evidence)`, `EvidenceContext(repo_root, gates, kb_dir)`, `Connector.evaluate(args, ctx)`, `Registry.evaluate_checks(checks, ctx) -> list[str]`, `coverage_errors(task_body, context, repo_root) -> list[str]`, `validate_manifest(manifest, repo_root, *, task=None, ctx=None)`, `modified_deliverables(task_body) -> list[str]` — names/signatures used identically across Tasks 2–8. Connector `kind` strings match between `connectors.py`, the prompt vocabulary, and the guard test.
