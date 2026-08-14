# Factory Init Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make a repository able to become a factory target: one extension-registration point, a recorded validation choice, an onboarding skill plus mechanical CLI, and the discoverability fixes that let any of it work from outside the factory's own checkout.

**Architecture:** A `Registry` seeded with the factory's built-in harness and playground types, then extended by one module the target repo names in `.factory/factory.yaml`. `load_config` builds it and resolves every `type:` through it. A new `factory.init` package mirrors `factory.doctor`'s shape — `context.py` reports, `write.py` writes, `cli.py` dispatches — and a vendored `init` skill drives the conversation. Three separate defects that hide the factory from a target repo are fixed alongside, because init is useless without them.

**Tech Stack:** Python 3.11-3.12, pytest (`-m unit`), ruff, pyright, pyyaml (reading), ruamel.yaml (comment-preserving writes), frontmatter; TypeScript + vitest for the pi extension.

## Global Constraints

- **Spec:** `docs/superpowers/specs/2026-08-06-factory-init-design.md`. Every decision below traces to it.
- **CLI output is ASCII only.** cp1252 cannot encode an em dash. Comments and docs may use one; anything reaching `print()` may not. See `doctor/context.py:format_context`'s comment.
- **`from __future__ import annotations`** at the top of every new Python module, matching every existing one.
- **Every new test module starts `pytestmark = pytest.mark.unit`.** The default addopts is `-m unit`; an unmarked test never runs.
- **Line length 100** (ruff), **pyright standard mode** over `src` and `scripts`.
- **Gate names are the fixed vocabulary** `unit`, `sim`, `integration`, `full`. Never invent one.
- **No fallback paths.** When this plan says a key is deleted, it is deleted — the gates design's decision 3. A compatibility shim is a plan violation.
- **Commit after every task**, message in the repo's style (`feat(scope): lowercase summary`), ending with:
  `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`
- **Run `uv run pytest -m unit -q` before every commit.** A task is not done if the suite is red.

## Deviation from the spec, decided while planning

The spec (§6) says `validation:` is "required iff `requirements/` holds no `SR-*.md`". Enforcing *required* inside `load_config` would raise for the factory's own config, for `cool_physical_ai_project`, and for roughly every temp-dir fixture in the existing suite — punishing every consumer of `load_config` for an onboarding gap.

This plan uses the pattern the codebase already established for exactly this shape of problem, `require_gates` (`config.py:88-102`):

- **`load_config` enforces the *forbidden* rule** — a declared `validation:` above a non-empty register is a content disagreement and is always wrong, so it raises everywhere.
- **`validation_state(cfg, project_root)` reports the *required* rule** — returning `"active" | "none" | "pending" | "undeclared"`. `init context` and `trace status` consume it. `"undeclared"` is reported, not raised.

Net effect matches the spec's intent (the ambiguity is recorded and visible) without a blast radius the spec did not price in.

## File Structure

**Create**

| path | responsibility |
|---|---|
| `src/factory/registry.py` | `Registry`, its errors, built-in seeding, extension-module loading |
| `src/factory/init/__init__.py` | empty package marker |
| `src/factory/init/__main__.py` | `python -m factory.init` entry |
| `src/factory/init/cli.py` | argparse dispatch for `context`/`config`/`gate`/`harness`/`playground` |
| `src/factory/init/context.py` | what PIF offers + what this repo has |
| `src/factory/init/write.py` | comment-preserving `.factory/factory.yaml` writes |
| `.pi/skills/init/SKILL.md` | the onboarding skill |
| `tests/unit/test_registry.py` | registry behaviour |
| `tests/unit/init/test_context.py` | context reporting |
| `tests/unit/init/test_write.py` | write verbs, idempotency, comment survival |
| `tests/unit/test_install_pif.py` | shim generation guard |

**Modify**

| path | change |
|---|---|
| `src/factory/config.py` | registry wiring; `validation` field + forbidden rule; `validation_state` |
| `src/factory/polish/config.py` | `PLAYGROUND_TYPES`/`HARNESS_TYPES` become the registry's seed |
| `src/factory/validation/sim_harness.py` | scorers arrive from the registry |
| `src/factory/validation/playwright_harness.py` | `from_config` signature |
| `src/factory/polish/devserver.py`, `reference.py` | `from_config` signature |
| `src/factory/doctor/context.py` | metrics from the registry, not `load_scorers` |
| `src/factory/orchestrator/skills.py` | search path rather than one dir + one fallback |
| `src/factory/trace/cli.py` | `cmd_status` reports the validation state |
| `scripts/install-pif.sh` | no `cd`; passes `--skill`; honours `PIF_BIN_DIR` |
| `pi-ext/factory-watch/src/factory-skills.ts` | `resolveSkillBlocks`, skill-name constants |
| `pi-ext/factory-watch/src/index.ts` | `/plan` and `/trace-fix` both use `resolveSkillBlocks` |
| `pi-ext/factory-watch/test/factory-skills.test.ts` | covers `resolveSkillBlocks` |
| `pyproject.toml` | `ruamel.yaml` dependency |
| `tests/unit/test_config.py` | `FactoryConfig` gained a field |

**Delete**

| path | why |
|---|---|
| `src/factory/validation/scorer_registry.py` | scorers arrive via `r.scorers({...})`; a second importer is dead weight |
| `tests/unit/validation/test_scorer_registry.py` (if present) | with it |

---

### Task 1: The Registry

**Files:**
- Create: `src/factory/registry.py`
- Test: `tests/unit/test_registry.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `Registry` with `.harness(name: str, factory: TypeFactory) -> None`, `.playground(name: str, factory: TypeFactory) -> None`, `.scorers(mapping: dict[str, Scorer]) -> None`, `.skills(path: Path) -> None`
  - read-only views `.harnesses -> dict[str, TypeFactory]`, `.playgrounds -> dict[str, TypeFactory]`, `.scorer_map -> dict[str, Scorer]`, `.skill_dirs -> list[Path]`
  - `TypeFactory = Callable[[dict, Path, "Registry"], Any]`
  - `Scorer = Callable[..., bool]`
  - `ExtensionError(ValueError)`, `ExtensionModuleError(ExtensionError)`, `ExtensionConflictError(ExtensionError)`
  - `built_in_registry() -> Registry`
  - `load_extensions(module_name: str | None, project_root: Path, registry: Registry) -> Registry`

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_registry.py`:

```python
from pathlib import Path

import pytest

from factory.registry import (
    ExtensionConflictError,
    ExtensionModuleError,
    Registry,
    built_in_registry,
    load_extensions,
)

pytestmark = pytest.mark.unit


def _fake_factory(params: dict, project_root: Path, registry: Registry):
    return ("built", params)


def test_built_in_registry_has_the_factory_types():
    r = built_in_registry()
    assert "sim-testbench" in r.harnesses
    assert "playwright-e2e" in r.harnesses
    assert "dev-server" in r.playgrounds
    assert "scenario-replay" in r.playgrounds


def test_registering_a_harness_makes_it_resolvable():
    r = Registry()
    r.harness("my-bench", _fake_factory)
    assert r.harnesses["my-bench"] is _fake_factory


def test_registering_over_an_existing_name_is_a_hard_error():
    # Silently shadowing sim-testbench would be a silent failure, which is the
    # class of bug this whole seam exists to remove.
    r = built_in_registry()
    with pytest.raises(ExtensionConflictError, match="sim-testbench"):
        r.harness("sim-testbench", _fake_factory)


def test_scorer_names_may_not_collide():
    r = Registry()
    r.scorers({"latency_p95": lambda *a: True})
    with pytest.raises(ExtensionConflictError, match="latency_p95"):
        r.scorers({"latency_p95": lambda *a: False})


def test_skills_dir_is_appended_not_substituted(tmp_path):
    r = Registry()
    r.skills(tmp_path)
    assert r.skill_dirs == [tmp_path]


def test_a_skill_name_present_twice_is_a_hard_error(tmp_path):
    # paths.py exists because deriving skills from the target repo caused three
    # separate silent failures. A project must not be able to reinstate that.
    first = tmp_path / "a"
    second = tmp_path / "b"
    for root in (first, second):
        (root / "polish").mkdir(parents=True)
        (root / "polish" / "SKILL.md").write_text("---\nname: polish\n---\nx\n", encoding="utf-8")
    r = Registry()
    r.skills(first)
    with pytest.raises(ExtensionConflictError, match="polish"):
        r.skills(second)


def test_no_module_declared_leaves_the_registry_untouched(tmp_path):
    r = built_in_registry()
    assert load_extensions(None, tmp_path, r) is r
    assert "sim-testbench" in r.harnesses


def test_a_module_registers_into_the_registry(tmp_path):
    src = tmp_path / "src" / "proj"
    src.mkdir(parents=True)
    (src / "__init__.py").write_text("", encoding="utf-8")
    (src / "ext.py").write_text(
        "def register(r):\n"
        "    r.harness('my-bench', lambda p, root, reg: 'BENCH')\n"
        "    r.scorers({'latency_p95': lambda *a: True})\n",
        encoding="utf-8",
    )
    r = load_extensions("proj.ext", tmp_path, built_in_registry())
    assert r.harnesses["my-bench"]({}, tmp_path, r) == "BENCH"
    assert "latency_p95" in r.scorer_map


def test_a_module_that_cannot_be_imported_says_so(tmp_path):
    # An empty registry would present later as UnknownTypeError on a type the
    # project DID register -- the wrong error, at the wrong moment.
    with pytest.raises(ExtensionModuleError, match="proj.missing"):
        load_extensions("proj.missing", tmp_path, built_in_registry())


def test_a_module_without_register_says_so(tmp_path):
    src = tmp_path / "src" / "proj"
    src.mkdir(parents=True)
    (src / "__init__.py").write_text("", encoding="utf-8")
    (src / "ext.py").write_text("VALUE = 1\n", encoding="utf-8")
    with pytest.raises(ExtensionModuleError, match="register"):
        load_extensions("proj.ext", tmp_path, built_in_registry())
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/unit/test_registry.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'factory.registry'`

- [ ] **Step 3: Implement the registry**

Create `src/factory/registry.py`:

```python
"""The one point at which a project extends the factory.

Before this, each subsystem that needed extending added its own config key
(`harnesses.*.scorers` for metrics, a factory-side map for `type:`). The cost was
not the keys: it was that `type:` read differently depending on whose type it was,
and that the next subsystem would add a fifth key. Here a project names one
module, and extending a new subsystem adds a method rather than a schema.
"""
from __future__ import annotations

import importlib
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import frontmatter

Scorer = Callable[..., bool]
TypeFactory = Callable[[dict, Path, "Registry"], Any]


class ExtensionError(ValueError):
    pass


class ExtensionModuleError(ExtensionError):
    pass


class ExtensionConflictError(ExtensionError):
    pass


class Registry:
    def __init__(self) -> None:
        self._harnesses: dict[str, TypeFactory] = {}
        self._playgrounds: dict[str, TypeFactory] = {}
        self._scorers: dict[str, Scorer] = {}
        self._skill_dirs: list[Path] = []
        self._skill_names: dict[str, Path] = {}

    @property
    def harnesses(self) -> dict[str, TypeFactory]:
        return dict(self._harnesses)

    @property
    def playgrounds(self) -> dict[str, TypeFactory]:
        return dict(self._playgrounds)

    @property
    def scorer_map(self) -> dict[str, Scorer]:
        return dict(self._scorers)

    @property
    def skill_dirs(self) -> list[Path]:
        return list(self._skill_dirs)

    def harness(self, name: str, factory: TypeFactory) -> None:
        self._claim(self._harnesses, "harness type", name)
        self._harnesses[name] = factory

    def playground(self, name: str, factory: TypeFactory) -> None:
        self._claim(self._playgrounds, "playground type", name)
        self._playgrounds[name] = factory

    def scorers(self, mapping: dict[str, Scorer]) -> None:
        for name in mapping:
            self._claim(self._scorers, "metric", name)
        self._scorers.update(mapping)

    def skills(self, path: Path) -> None:
        """Append a skills directory. It is never substituted for the factory's own.

        A name present in two directories is a hard error rather than a silent
        override: pi's own loader warns and keeps the first found, but this
        registry is ours and can be strict.
        """
        for skill_md in sorted(path.glob("*/SKILL.md")):
            name = _skill_name(skill_md)
            existing = self._skill_names.get(name)
            if existing is not None:
                raise ExtensionConflictError(
                    f"skill {name!r} is registered twice: {existing} and {skill_md}. "
                    "Rename one; a project cannot override a factory skill by name."
                )
            self._skill_names[name] = skill_md
        self._skill_dirs.append(path)

    @staticmethod
    def _claim(target: dict, kind: str, name: str) -> None:
        if name in target:
            raise ExtensionConflictError(f"{kind} {name!r} is already registered")


def _skill_name(skill_md: Path) -> str:
    meta = frontmatter.load(str(skill_md)).metadata
    return str(meta.get("name") or skill_md.parent.name)


def built_in_registry() -> Registry:
    """A registry holding the factory's own types.

    Imported inside the function, not at module level: the orchestrator imports
    this module, and a module-level import of factory.polish would point the core
    package back at a consumer -- the same inversion load_config already avoids.
    """
    from factory.polish.config import HARNESS_TYPES, PLAYGROUND_TYPES

    registry = Registry()
    for name, factory in HARNESS_TYPES.items():
        registry.harness(name, factory)
    for name, factory in PLAYGROUND_TYPES.items():
        registry.playground(name, factory)
    return registry


def load_extensions(module_name: str | None, project_root: Path, registry: Registry) -> Registry:
    """Import the project's extension module and let it register into *registry*.

    Both this repo and its targets use a src/ layout, and the factory runs from
    its own interpreter, so the target's src/ is not importable by default.
    Importing target-repo code is the same trust posture the gate steps carry.
    """
    if not module_name:
        return registry
    src = project_root / "src"
    added = str(src) if src.is_dir() and str(src) not in sys.path else None
    if added:
        sys.path.insert(0, added)
    try:
        module = importlib.import_module(module_name)
    except Exception as exc:
        raise ExtensionModuleError(
            f"cannot import extension module {module_name!r}: {exc}"
        ) from exc
    finally:
        if added:
            sys.path.remove(added)

    register = getattr(module, "register", None)
    if not callable(register):
        raise ExtensionModuleError(
            f"{module_name!r} must define register(registry) -> None"
        )
    register(registry)
    return registry
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/unit/test_registry.py -q`
Expected: PASS, 10 tests. `built_in_registry` currently seeds `Callable[[dict, Path], ...]` factories — that mismatch is fixed in Task 2 and pyright is not yet expected to be clean on this file.

- [ ] **Step 5: Commit**

```bash
git add src/factory/registry.py tests/unit/test_registry.py
git commit -m "feat(registry): one point at which a project extends the factory

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 2: Resolve every `type:` through the registry, and delete `scorers:`

**Files:**
- Modify: `src/factory/config.py` (`_build`, `load_config`, `FactoryConfig`)
- Modify: `src/factory/polish/config.py`
- Modify: `src/factory/validation/sim_harness.py:33-37`
- Modify: `src/factory/validation/playwright_harness.py` (`from_config`)
- Modify: `src/factory/polish/devserver.py`, `src/factory/polish/reference.py` (`from_config`)
- Modify: `src/factory/doctor/context.py:_harness_inventory`
- Delete: `src/factory/validation/scorer_registry.py`
- Test: `tests/unit/test_config.py` (extend), `tests/unit/doctor/test_context.py` (adjust if it asserts on `scorers`)

**Interfaces:**
- Consumes: `Registry`, `built_in_registry`, `load_extensions` from Task 1.
- Produces:
  - `FactoryConfig(playgrounds, harnesses, gates, registry)` — a fourth field holding the built registry.
  - Every `from_config` classmethod becomes `from_config(cls, params: dict, project_root: Path, registry: Registry)`.
  - `SimTestbenchHarness(traces_dir: Path, scorers: dict[str, Scorer])` takes its scorers from `registry.scorer_map`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_config.py`:

```python
def test_a_project_type_resolves_through_the_extension_module(tmp_path):
    src = tmp_path / "src" / "proj"
    src.mkdir(parents=True)
    (src / "__init__.py").write_text("", encoding="utf-8")
    (src / "ext.py").write_text(
        "def register(r):\n"
        "    r.playground('my-sandbox', lambda p, root, reg: ('SANDBOX', p))\n",
        encoding="utf-8",
    )
    root = _write(tmp_path, """
extensions: proj.ext
playgrounds:
  sandbox:
    type: my-sandbox
    port: 8080
""")
    cfg = load_config(root)
    assert cfg.playgrounds["sandbox"] == ("SANDBOX", {"port": 8080})


def test_unknown_type_names_both_built_in_and_project_types(tmp_path):
    from factory.config import UnknownTypeError

    root = _write(tmp_path, "harnesses:\n  h:\n    type: nope\n")
    with pytest.raises(UnknownTypeError) as exc:
        load_config(root)
    assert "sim-testbench" in str(exc.value)


def test_the_scorers_key_is_gone_and_says_where_it_went(tmp_path):
    # Silently ignoring it would leave the project with no metrics and no clue.
    root = _write(tmp_path, """
harnesses:
  sim-testbench:
    type: sim-testbench
    traces_dir: t
    scorers: proj.scorers
""")
    with pytest.raises(GateConfigError, match="extensions"):
        load_config(root)


def test_sim_harness_scorers_come_from_the_registry(tmp_path):
    src = tmp_path / "src" / "proj"
    src.mkdir(parents=True)
    (src / "__init__.py").write_text("", encoding="utf-8")
    (src / "ext.py").write_text(
        "def register(r):\n    r.scorers({'always': lambda frames, window: True})\n",
        encoding="utf-8",
    )
    (tmp_path / "t").mkdir()
    root = _write(tmp_path, """
extensions: proj.ext
harnesses:
  sim-testbench:
    type: sim-testbench
    traces_dir: t
""")
    cfg = load_config(root)
    assert "always" in cfg.harnesses["sim-testbench"]._scorers
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/unit/test_config.py -q`
Expected: FAIL — `TypeError` on `_build` arity, and no `extensions` handling.

- [ ] **Step 3: Implement**

In `src/factory/polish/config.py`, keep the two maps but retype them:

```python
from factory.registry import Registry, TypeFactory

PLAYGROUND_TYPES: dict[str, TypeFactory] = {
    "dev-server": DevServerPlayground.from_config,
    "scenario-replay": ScenarioReplayPlayground.from_config,
}
HARNESS_TYPES: dict[str, TypeFactory] = {
    "sim-testbench": SimTestbenchHarness.from_config,
    "playwright-e2e": PlaywrightE2EHarness.from_config,
}
```

Add `Registry` to that module's `__all__` alongside the existing re-exports.

In `src/factory/config.py`:

```python
from factory.registry import Registry, built_in_registry, load_extensions


@dataclass
class FactoryConfig:
    playgrounds: dict[str, Any]
    harnesses: dict[str, Any]
    gates: dict[str, list[GateStep]]
    registry: Registry | None = None


def _build(types: dict, name: str, spec: dict, project_root: Path, registry: Registry):
    spec = dict(spec)
    type_name = spec.pop("type", None)
    ctor = types.get(type_name)
    if ctor is None:
        raise UnknownTypeError(f"{name!r}: unknown type {type_name!r} (have {sorted(types)})")
    return ctor(spec, project_root, registry)


def _reject_removed_keys(data: dict) -> None:
    """`scorers:` moved into the extension module. Ignoring it silently would
    leave a project with no metrics and no explanation."""
    for name, spec in (data.get("harnesses") or {}).items():
        if isinstance(spec, dict) and "scorers" in spec:
            raise GateConfigError(
                f"harness {name!r}: 'scorers:' has been removed. Declare "
                "'extensions: <module>' at the top level and register metrics "
                "with r.scorers({...}) in that module's register(r)."
            )
```

`load_config` becomes:

```python
def load_config(project_root: Path) -> FactoryConfig:
    path = project_root / ".factory" / "factory.yaml"
    if not path.exists():
        return FactoryConfig({}, {}, {}, built_in_registry())
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    _reject_removed_keys(data)
    registry = load_extensions(data.get("extensions"), project_root, built_in_registry())
    playgrounds = {
        n: _build(registry.playgrounds, n, s, project_root, registry)
        for n, s in (data.get("playgrounds") or {}).items()
    }
    harnesses = {
        n: _build(registry.harnesses, n, s, project_root, registry)
        for n, s in (data.get("harnesses") or {}).items()
    }
    return FactoryConfig(playgrounds, harnesses, _parse_gates(data), registry)
```

Delete the old in-function `from factory.polish.config import HARNESS_TYPES, PLAYGROUND_TYPES` import and its comment — `built_in_registry` now carries that reasoning.

`SimTestbenchHarness.from_config`:

```python
    @classmethod
    def from_config(cls, params: dict, project_root: Path, registry) -> "SimTestbenchHarness":
        # Scorers come from the extension module the registry already imported;
        # a second importer for the same code was dead weight.
        return cls(project_root / params["traces_dir"], registry.scorer_map)
```

Remove `from factory.validation.scorer_registry import load_scorers` from that file and `git rm src/factory/validation/scorer_registry.py`.

Give `PlaywrightE2EHarness.from_config`, `DevServerPlayground.from_config` and `ScenarioReplayPlayground.from_config` the same third parameter, unused, named `registry` — uniform signatures are what let a project's own type be constructed identically to a built-in.

In `src/factory/doctor/context.py`, rewrite `_harness_inventory` to keep its output shape (`doctor/write.py:promote` reads `["metrics"]`) while sourcing metrics from the registry:

```python
def _harness_inventory(project_root: Path) -> dict:
    path = project_root / ".factory" / "factory.yaml"
    if not path.exists():
        return {"present": False, "harnesses": {}}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    module = data.get("extensions")
    try:
        metrics = sorted(load_extensions(module, project_root, built_in_registry()).scorer_map)
        error = None
    except ExtensionError as exc:
        # A project that cannot load its extensions still has a register worth
        # reading. Report the reason instead of failing the whole command.
        metrics, error = [], str(exc)
    harnesses = {
        name: {"extensions_module": module, "metrics": metrics, "error": error}
        for name in (data.get("harnesses") or {})
    }
    return {"present": True, "harnesses": harnesses}
```

Update `format_context`'s harness line to print `extensions=` rather than `scorers=`.

- [ ] **Step 4: Run the whole suite**

Run: `uv run pytest -m unit -q && uv run ruff check . && uv run pyright`
Expected: PASS. `tests/unit/test_config.py`'s `FactoryConfig({}, {}, {})` equality assertions now need a fourth field — change them to compare `.playgrounds`, `.harnesses` and `.gates` individually rather than the whole dataclass, since `Registry` has no `__eq__`.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat(registry): resolve every type through the registry, drop scorers:

harnesses.*.scorers is deleted rather than deprecated -- one code path,
per the gates design's decision 3. from_config takes the registry so a
project's own type is constructed exactly like a built-in.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 3: The `validation:` key

**Files:**
- Modify: `src/factory/config.py`
- Test: `tests/unit/test_config.py`

**Interfaces:**
- Consumes: `FactoryConfig` from Task 2.
- Produces:
  - `FactoryConfig.validation: str | None`
  - `ValidationDeclarationError(ValueError)`
  - `validation_state(cfg: FactoryConfig, project_root: Path) -> str` returning one of `"active"`, `"none"`, `"pending"`, `"undeclared"`

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_config.py`:

```python
def _with_sr(root: Path) -> Path:
    (root / "requirements").mkdir(parents=True, exist_ok=True)
    (root / "requirements" / "SR-001.md").write_text(
        "---\nid: SR-001\ntitle: t\nstatement: s\ndomain: behavioral\n---\n", encoding="utf-8"
    )
    return root


def test_validation_none_and_pending_are_accepted_with_an_empty_register(tmp_path):
    for value in ("none", "pending"):
        root = _write(tmp_path, f"validation: {value}\n")
        assert load_config(root).validation == value


def test_an_unknown_validation_value_is_rejected(tmp_path):
    from factory.config import ValidationDeclarationError

    root = _write(tmp_path, "validation: maybe\n")
    with pytest.raises(ValidationDeclarationError, match="maybe"):
        load_config(root)


def test_declaring_validation_above_a_non_empty_register_raises(tmp_path):
    # The register's rule: state is derived, never declared. A non-empty register
    # IS the active state, so `validation: none` above it is a content
    # disagreement -- the thing the absent status: field exists to prevent.
    from factory.config import ValidationDeclarationError

    root = _with_sr(_write(tmp_path, "validation: none\n"))
    with pytest.raises(ValidationDeclarationError, match="SR-001"):
        load_config(root)


def test_validation_state_derives_active_from_a_non_empty_register(tmp_path):
    from factory.config import validation_state

    root = _with_sr(_write(tmp_path, "gates:\n  unit:\n    - { cmd: 'x' }\n"))
    assert validation_state(load_config(root), root) == "active"


def test_validation_state_reports_undeclared_rather_than_raising(tmp_path):
    # Required-iff-empty is reported by the commands that care, not enforced by
    # load_config -- see require_gates for the same split.
    from factory.config import validation_state

    root = _write(tmp_path, "gates:\n  unit:\n    - { cmd: 'x' }\n")
    assert validation_state(load_config(root), root) == "undeclared"


def test_validation_state_passes_through_none_and_pending(tmp_path):
    from factory.config import validation_state

    for value in ("none", "pending"):
        root = _write(tmp_path, f"validation: {value}\n")
        assert validation_state(load_config(root), root) == value
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/unit/test_config.py -q`
Expected: FAIL — `ImportError: cannot import name 'ValidationDeclarationError'`

- [ ] **Step 3: Implement**

In `src/factory/config.py`:

```python
_VALIDATION_VALUES = ("none", "pending")


class ValidationDeclarationError(ValueError):
    pass


def _has_requirements(project_root: Path) -> bool:
    return any((project_root / "requirements").glob("SR-*.md"))


def _parse_validation(data: dict, project_root: Path) -> str | None:
    """`validation:` records only what a register cannot derive.

    A non-empty register IS the active state, so the key exists solely to tell a
    deliberately empty one ("none") from an owed one ("pending"). Declaring it
    above a non-empty register is a content disagreement, and raises -- the same
    rule that keeps a status: field out of the requirement frontmatter.
    Required-iff-empty is NOT enforced here: see validation_state.
    """
    value = data.get("validation")
    if value is None:
        return None
    value = str(value)
    if value not in _VALIDATION_VALUES:
        raise ValidationDeclarationError(
            f"validation: {value!r} is not one of {list(_VALIDATION_VALUES)}"
        )
    if _has_requirements(project_root):
        existing = sorted(p.stem for p in (project_root / "requirements").glob("SR-*.md"))
        raise ValidationDeclarationError(
            f"validation: {value!r} is declared, but the register holds {existing}. "
            "A non-empty register is the active state; remove the key."
        )
    return value


def validation_state(cfg: FactoryConfig, project_root: Path) -> str:
    """active | none | pending | undeclared -- reported, never raised.

    Enforcing "required when the register is empty" inside load_config would
    raise for every consumer over an onboarding gap. require_gates draws the
    same line: load_config parses, callers that need a thing say so.
    """
    if _has_requirements(project_root):
        return "active"
    return cfg.validation or "undeclared"
```

Add `validation` to the `FactoryConfig` dataclass (`str | None = None`, after `gates`, before `registry`; keep `registry` last so positional construction in tests stays readable), set it in both `load_config` return paths, and call `_parse_validation(data, project_root)`.

- [ ] **Step 4: Run**

Run: `uv run pytest -m unit -q && uv run ruff check . && uv run pyright`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat(config): record the validation choice a register cannot derive

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 4: `trace status` reports the validation state

**Files:**
- Modify: `src/factory/trace/cli.py:22-40` (`cmd_status`)
- Test: `tests/unit/trace/test_status_validation.py` (create)

**Interfaces:**
- Consumes: `validation_state`, `load_config` from Task 3.
- Produces: no new API; `cmd_status`'s first line gains a validation line beneath the health percentage.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/trace/test_status_validation.py`:

```python
from pathlib import Path

import pytest

from factory.trace.cli import cmd_status

pytestmark = pytest.mark.unit


def _repo(tmp_path: Path, config: str) -> Path:
    (tmp_path / ".factory").mkdir(parents=True)
    (tmp_path / ".factory" / "factory.yaml").write_text(config, encoding="utf-8")
    return tmp_path


def test_opted_out_reads_as_a_choice_not_a_zero(tmp_path):
    out = cmd_status(_repo(tmp_path, "validation: none\n"))
    assert "opted out" in out


def test_pending_reads_as_owed(tmp_path):
    out = cmd_status(_repo(tmp_path, "validation: pending\n"))
    assert "SR pass not yet run" in out


def test_undeclared_says_so(tmp_path):
    out = cmd_status(_repo(tmp_path, "gates:\n  unit:\n    - { cmd: 'x' }\n"))
    assert "not declared" in out


def test_a_repo_with_requirements_shows_no_opt_out_line(tmp_path):
    root = _repo(tmp_path, "gates:\n  unit:\n    - { cmd: 'x' }\n")
    (root / "requirements").mkdir()
    (root / "requirements" / "SR-001.md").write_text(
        "---\nid: SR-001\ntitle: t\nstatement: s\ndomain: behavioral\n---\n", encoding="utf-8"
    )
    out = cmd_status(root)
    assert "opted out" not in out
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/unit/trace/test_status_validation.py -q`
Expected: FAIL — none of those strings appear.

- [ ] **Step 3: Implement**

In `src/factory/trace/cli.py`, import `load_config` and `validation_state` from `factory.config`, and insert after the health-percentage line in `cmd_status`:

```python
    state = validation_state(load_config(root), root)
    if state != "active":
        # ASCII only: this is printed.
        note = {
            "none": "system validation: opted out (validation: none)",
            "pending": "system validation: 0% -- SR pass not yet run (validation: pending)",
            "undeclared": "system validation: not declared -- run the init skill",
        }[state]
        lines.append(note)
```

- [ ] **Step 4: Run**

Run: `uv run pytest -m unit -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat(trace): status distinguishes opted out from owed

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 5: Skills resolve along a search path

**Files:**
- Modify: `src/factory/orchestrator/skills.py`
- Test: `tests/unit/orchestrator/test_skills.py` (extend, or create if absent)

**Interfaces:**
- Consumes: `Registry.skill_dirs` from Task 1.
- Produces: `load_skill_block(skills_dir: Path, name: str, extra_dirs: list[Path] | None = None) -> str` — search order is `skills_dir`, then `extra_dirs` in registration order, then `factory_skills_dir()`.

- [ ] **Step 1: Write the failing tests**

Create or extend `tests/unit/orchestrator/test_skills.py`:

```python
from pathlib import Path

import pytest

from factory.orchestrator.skills import factory_skills_dir, load_skill_block

pytestmark = pytest.mark.unit


def _skill(root: Path, name: str, body: str) -> Path:
    d = root / name
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text(f"---\nname: {name}\n---\n{body}\n", encoding="utf-8")
    return d


def test_the_factory_remains_the_base_of_the_search_path(tmp_path):
    # paths.py: anything shipping with the factory resolves from there and never
    # from the repo being worked on.
    block = load_skill_block(tmp_path, "polish")
    assert str(factory_skills_dir()) in block


def test_a_registered_dir_is_searched_after_the_target_repo(tmp_path):
    target = tmp_path / "target"
    target.mkdir()
    extra = tmp_path / "extra"
    _skill(extra, "house-style", "EXTRA BODY")
    block = load_skill_block(target, "house-style", extra_dirs=[extra])
    assert "EXTRA BODY" in block


def test_the_target_repo_still_wins_over_a_registered_dir(tmp_path):
    target = tmp_path / "target"
    _skill(target, "house-style", "TARGET BODY")
    extra = tmp_path / "extra"
    _skill(extra, "house-style", "EXTRA BODY")
    block = load_skill_block(target, "house-style", extra_dirs=[extra])
    assert "TARGET BODY" in block


def test_a_name_in_no_directory_names_every_place_looked(tmp_path):
    extra = tmp_path / "extra"
    extra.mkdir()
    with pytest.raises(FileNotFoundError) as exc:
        load_skill_block(tmp_path, "no-such-skill", extra_dirs=[extra])
    assert str(extra) in str(exc.value)
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/unit/orchestrator/test_skills.py -q`
Expected: FAIL — `load_skill_block() got an unexpected keyword argument 'extra_dirs'`

- [ ] **Step 3: Implement**

Replace `load_skill_block`'s body, keeping the whole existing docstring and extending it with the search-path sentence:

```python
def load_skill_block(
    skills_dir: Path, name: str, extra_dirs: list[Path] | None = None
) -> str:
    candidates = [skills_dir, *(extra_dirs or []), factory_skills_dir()]
    for base in candidates:
        path = base / name / "SKILL.md"
        if path.exists():
            post = frontmatter.load(str(path))
            return f'<skill name="{name}" location="{path}">\n{post.content.strip()}\n</skill>'
    raise FileNotFoundError(
        f"skill not found: {name} (looked in "
        + ", ".join(str(c) for c in candidates)
        + ")"
    )
```

- [ ] **Step 4: Run**

Run: `uv run pytest -m unit -q && uv run pyright`
Expected: PASS. `prompts.py:compose_prompt` calls this positionally and is unaffected.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat(skills): resolve along a search path, factory last

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 6: `factory init context`

**Files:**
- Create: `src/factory/init/__init__.py` (empty), `src/factory/init/__main__.py`, `src/factory/init/context.py`, `src/factory/init/cli.py`
- Test: `tests/unit/init/test_context.py`

**Interfaces:**
- Consumes: `built_in_registry`, `load_extensions`, `ExtensionError` (Task 1); `load_config`, `validation_state` (Tasks 2-3); `factory_skills_dir` (Task 5).
- Produces:
  - `gather_context(project_root: Path) -> dict` with top-level keys `pif` and `repo`
  - `format_context(ctx: dict) -> str`
  - `probe_factory_import(interpreter: Path) -> bool`
  - `main(argv: list[str] | None = None) -> int` in `cli.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/init/test_context.py`:

```python
import sys
from pathlib import Path

import pytest

from factory.init.context import format_context, gather_context, probe_factory_import

pytestmark = pytest.mark.unit


def _repo(tmp_path: Path, config: str | None = None) -> Path:
    if config is not None:
        (tmp_path / ".factory").mkdir(parents=True)
        (tmp_path / ".factory" / "factory.yaml").write_text(config, encoding="utf-8")
    return tmp_path


def test_reports_what_pif_offers(tmp_path):
    pif = gather_context(_repo(tmp_path))["pif"]
    assert pif["gates"] == ["unit", "sim", "integration", "full"]
    assert "sim-testbench" in pif["harness_types"]
    assert "dev-server" in pif["playground_types"]
    assert any(s["name"] == "doctor" for s in pif["skills"])
    assert "factory-run" in pif["commands"]


def test_reports_raw_repo_facts_without_concluding(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        '[tool.pytest.ini_options]\nmarkers = ["unit: fast", "sim: slow"]\n', encoding="utf-8"
    )
    (tmp_path / "package.json").write_text('{"scripts": {"test": "vitest run"}}', encoding="utf-8")
    repo = gather_context(_repo(tmp_path))["repo"]
    assert repo["pytest_markers"] == ["unit", "sim"]
    assert repo["npm_scripts"] == ["test"]
    # No conclusion about what kind of project this is.
    assert "project_type" not in repo


def test_reports_an_unimportable_extension_module_distinguishably(tmp_path):
    repo = gather_context(_repo(tmp_path, "extensions: proj.missing\n"))["repo"]
    assert repo["extensions"]["declared"] == "proj.missing"
    assert repo["extensions"]["error"] is not None
    assert repo["extensions"]["registered"] == {}


def test_reports_an_undeclared_extension_module(tmp_path):
    repo = gather_context(_repo(tmp_path, "gates: {}\n"))["repo"]
    assert repo["extensions"]["declared"] is None
    assert repo["extensions"]["error"] is None


def test_reports_what_a_working_extension_module_registered(tmp_path):
    src = tmp_path / "src" / "proj"
    src.mkdir(parents=True)
    (src / "__init__.py").write_text("", encoding="utf-8")
    (src / "ext.py").write_text(
        "def register(r):\n"
        "    r.harness('my-bench', lambda p, root, reg: None)\n"
        "    r.scorers({'latency_p95': lambda *a: True})\n",
        encoding="utf-8",
    )
    repo = gather_context(_repo(tmp_path, "extensions: proj.ext\n"))["repo"]
    assert repo["extensions"]["registered"]["harnesses"] == ["my-bench"]
    assert repo["extensions"]["registered"]["metrics"] == ["latency_p95"]


def test_reports_the_validation_state(tmp_path):
    assert gather_context(_repo(tmp_path, "validation: none\n"))["repo"]["validation"] == "none"
    assert gather_context(_repo(tmp_path))["repo"]["validation"] == "undeclared"


def test_reports_a_type_that_no_longer_resolves(tmp_path):
    repo = gather_context(_repo(tmp_path, "harnesses:\n  h:\n    type: nope\n"))["repo"]
    assert repo["unresolved_types"] == ["harnesses.h: nope"]


def test_probe_reports_whether_an_interpreter_can_import_factory():
    assert probe_factory_import(Path(sys.executable)) is True
    assert probe_factory_import(Path("no-such-interpreter")) is False


def test_format_is_ascii_only(tmp_path):
    text = format_context(gather_context(_repo(tmp_path)))
    text.encode("cp1252")  # raises UnicodeEncodeError on an em dash
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/unit/init/test_context.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'factory.init'`

- [ ] **Step 3: Implement**

Create `src/factory/init/__init__.py` (empty file) and `src/factory/init/context.py`:

```python
"""The agent's field of view at onboarding: what PIF offers, and what this repo has.

Deliberately does NOT rank, filter, score or recommend. The reasoning is
propose.py's, applied to repo facts rather than trace gaps: a heuristic that
decided which facts reached the agent would cap what it can notice, and a repo
shape nobody anticipated is exactly the case onboarding must survive.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import tomllib
from pathlib import Path

import frontmatter
import yaml

from factory.config import load_config, validation_state
from factory.orchestrator.roles import ROLE_SKILLS
from factory.paths import factory_root, factory_skills_dir
from factory.registry import ExtensionError, built_in_registry, load_extensions

GATE_NAMES = ["unit", "sim", "integration", "full"]
GATE_NODES = {
    "unit": "dev",
    "sim": "validation",
    "integration": "validation",
    "full": "review",
}
_MAKE_TARGET = re.compile(r"^([A-Za-z0-9_.-]+):", re.MULTILINE)
_PI_COMMAND = re.compile(r'pi\.registerCommand\("([^"]+)"')
_CLIS = ["doctor", "trace", "requirements", "polish", "validation", "init"]
_INTERPRETERS = (
    Path(".venv") / "Scripts" / "python.exe",
    Path(".venv") / "bin" / "python",
)


def probe_factory_import(interpreter: Path) -> bool:
    """Whether *interpreter* can `import factory`. A fact, not a proxy for one."""
    try:
        proc = subprocess.run(
            [str(interpreter), "-c", "import factory"],
            capture_output=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return proc.returncode == 0


def _skills(base: Path) -> list[dict]:
    out = []
    for skill_md in sorted(base.glob("*/SKILL.md")):
        meta = frontmatter.load(str(skill_md)).metadata
        out.append(
            {
                "name": str(meta.get("name") or skill_md.parent.name),
                "description": str(meta.get("description") or ""),
            }
        )
    return out


def _pi_commands() -> list[str]:
    index = factory_root() / "pi-ext" / "factory-watch" / "src" / "index.ts"
    if not index.is_file():
        return []
    return sorted(set(_PI_COMMAND.findall(index.read_text(encoding="utf-8"))))


def _pif_half() -> dict:
    registry = built_in_registry()
    return {
        "gates": list(GATE_NAMES),
        "gate_nodes": dict(GATE_NODES),
        "harness_types": sorted(registry.harnesses),
        "playground_types": sorted(registry.playgrounds),
        "registry_slots": ["harness", "playground", "scorers", "skills"],
        "role_skills": {role.value: names for role, names in ROLE_SKILLS.items()},
        "skills": _skills(factory_skills_dir()),
        "commands": _pi_commands(),
        "clis": list(_CLIS),
    }


def _pytest_markers(project_root: Path) -> list[str]:
    path = project_root / "pyproject.toml"
    if not path.is_file():
        return []
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    raw = data.get("tool", {}).get("pytest", {}).get("ini_options", {}).get("markers", [])
    return [str(m).split(":")[0].strip() for m in raw]


def _npm_scripts(project_root: Path) -> list[str]:
    path = project_root / "package.json"
    if not path.is_file():
        return []
    try:
        return sorted(json.loads(path.read_text(encoding="utf-8")).get("scripts", {}))
    except json.JSONDecodeError:
        return []


def _make_targets(project_root: Path) -> list[str]:
    path = project_root / "Makefile"
    if not path.is_file():
        return []
    return sorted(set(_MAKE_TARGET.findall(path.read_text(encoding="utf-8"))))


def _extensions(data: dict, project_root: Path) -> dict:
    module = data.get("extensions")
    result: dict = {"declared": module, "error": None, "registered": {}}
    if not module:
        return result
    try:
        registry = load_extensions(module, project_root, built_in_registry())
    except ExtensionError as exc:
        result["error"] = str(exc)
        return result
    built_in = built_in_registry()
    result["registered"] = {
        "harnesses": sorted(set(registry.harnesses) - set(built_in.harnesses)),
        "playgrounds": sorted(set(registry.playgrounds) - set(built_in.playgrounds)),
        "metrics": sorted(registry.scorer_map),
        "skill_dirs": [str(p) for p in registry.skill_dirs],
    }
    return result


def _unresolved_types(data: dict, project_root: Path, extensions: dict) -> list[str]:
    registry = built_in_registry()
    if extensions["declared"] and extensions["error"] is None:
        registry = load_extensions(extensions["declared"], project_root, registry)
    known = {"harnesses": set(registry.harnesses), "playgrounds": set(registry.playgrounds)}
    out = []
    for section, names in known.items():
        for name, spec in (data.get(section) or {}).items():
            type_name = (spec or {}).get("type")
            if type_name not in names:
                out.append(f"{section}.{name}: {type_name}")
    return sorted(out)


def _skill_collisions(project_root: Path) -> list[str]:
    """pi warns and keeps the first skill found, so load order decides. Reported
    at onboarding rather than as a confusing prompt later."""
    ours = {s["name"] for s in _skills(factory_skills_dir())}
    theirs = {s["name"] for s in _skills(project_root / ".pi" / "skills")}
    return sorted(ours & theirs)


def _repo_half(project_root: Path) -> dict:
    path = project_root / ".factory" / "factory.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {} if path.is_file() else {}
    extensions = _extensions(data, project_root)
    interpreters = [
        {"path": str(project_root / rel), "imports_factory": probe_factory_import(project_root / rel)}
        for rel in _INTERPRETERS
        if (project_root / rel).is_file()
    ]
    return {
        "config_present": path.is_file(),
        "config": data,
        "gates_declared": sorted(data.get("gates") or {}),
        "harnesses_declared": sorted(data.get("harnesses") or {}),
        "playgrounds_declared": sorted(data.get("playgrounds") or {}),
        "extensions": extensions,
        "unresolved_types": _unresolved_types(data, project_root, extensions),
        "validation": validation_state(load_config(project_root), project_root)
        if not extensions["error"]
        else str(data.get("validation") or "undeclared"),
        "requirements": len(list((project_root / "requirements").glob("SR-*.md"))),
        "tasks": len(list((project_root / "tasks").glob("T-*.md"))),
        "pyproject": (project_root / "pyproject.toml").is_file(),
        "pytest_markers": _pytest_markers(project_root),
        "npm_scripts": _npm_scripts(project_root),
        "make_targets": _make_targets(project_root),
        "uv_lock": (project_root / "uv.lock").is_file(),
        "node_modules": (project_root / "node_modules").is_dir(),
        "interpreters": interpreters,
        "vendored_skills": [s["name"] for s in _skills(project_root / ".pi" / "skills")],
        "skill_collisions": _skill_collisions(project_root),
    }


def gather_context(project_root: Path) -> dict:
    return {"pif": _pif_half(project_root and project_root and None or None) if False else _pif_half(),
            "repo": _repo_half(project_root)}


def format_context(ctx: dict) -> str:
    pif, repo = ctx["pif"], ctx["repo"]
    lines = [
        "PIF offers",
        "  gates: " + ", ".join(f"{g} ({pif['gate_nodes'][g]} node)" for g in pif["gates"]),
        "  harness types:    " + ", ".join(pif["harness_types"]),
        "  playground types: " + ", ".join(pif["playground_types"]),
        "  registry slots:   " + ", ".join(pif["registry_slots"]),
        "  pi commands:      " + ", ".join(pif["commands"]),
        f"  skills ({len(pif['skills'])}):",
        *[f"    {s['name']}" for s in pif["skills"]],
        "",
        "This repo",
        f"  .factory/factory.yaml: {'present' if repo['config_present'] else 'absent'}",
        f"  gates declared:        {', '.join(repo['gates_declared']) or '(none)'}",
        f"  harnesses declared:    {', '.join(repo['harnesses_declared']) or '(none)'}",
        f"  validation:            {repo['validation']}",
        f"  requirements: {repo['requirements']}   tasks: {repo['tasks']}",
    ]
    ext = repo["extensions"]
    if ext["error"]:
        lines.append(f"  extensions: {ext['declared']} -- ERROR: {ext['error']}")
    elif ext["declared"]:
        reg = ext["registered"]
        lines.append(
            f"  extensions: {ext['declared']} -> harnesses={reg['harnesses'] or '[]'} "
            f"metrics={reg['metrics'] or '[]'}"
        )
    else:
        lines.append("  extensions: (none declared)")
    if repo["unresolved_types"]:
        lines.append("  UNRESOLVED types: " + "; ".join(repo["unresolved_types"]))
    if repo["skill_collisions"]:
        lines.append(
            "  skill name collisions (pi keeps the first found): "
            + ", ".join(repo["skill_collisions"])
        )
    lines.append("")
    lines.append("Raw build facts -- draw your own conclusions:")
    lines.append(f"  pyproject.toml: {repo['pyproject']}   uv.lock: {repo['uv_lock']}")
    lines.append(f"  pytest markers: {', '.join(repo['pytest_markers']) or '(none)'}")
    lines.append(f"  npm scripts:    {', '.join(repo['npm_scripts']) or '(none)'}")
    lines.append(f"  make targets:   {', '.join(repo['make_targets']) or '(none)'}")
    lines.append("")
    lines.append("Factory CLIs (invoked as <interpreter> -m factory.<name>):")
    lines.append("  " + ", ".join(pif["clis"]))
    if not repo["interpreters"]:
        lines.append("  no project interpreter found at .venv/ -- cannot confirm they are")
        lines.append("  reachable from this repo.")
    for interp in repo["interpreters"]:
        verdict = "can import factory" if interp["imports_factory"] else "CANNOT import factory"
        lines.append(f"  {interp['path']}: {verdict}")
    return "\n".join(lines)
```

Simplify `gather_context` to exactly:

```python
def gather_context(project_root: Path) -> dict:
    return {"pif": _pif_half(), "repo": _repo_half(project_root)}
```

Create `src/factory/init/cli.py`:

```python
from __future__ import annotations

import argparse
import json
from pathlib import Path

from factory.init.context import format_context, gather_context


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="factory-init")
    sub = parser.add_subparsers(dest="cmd", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--project-root", default=Path("."), type=Path)

    p_context = sub.add_parser("context", parents=[common])
    p_context.add_argument("--json", action="store_true", dest="as_json")

    args = parser.parse_args(argv)
    if args.cmd == "context":
        ctx = gather_context(args.project_root)
        print(json.dumps(ctx, indent=2, default=str) if args.as_json else format_context(ctx))
    return 0
```

Create `src/factory/init/__main__.py`:

```python
from factory.init.cli import main

raise SystemExit(main())
```

(Match `src/factory/doctor/__main__.py` exactly — read it first and copy its shape.)

- [ ] **Step 4: Run**

Run: `uv run pytest tests/unit/init -q && uv run python -m factory.init context`
Expected: PASS, and the command prints both halves against the factory's own repo.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat(init): report what PIF offers and what this repo has

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 7: The write verbs

**Files:**
- Create: `src/factory/init/write.py`
- Modify: `src/factory/init/cli.py`, `pyproject.toml`
- Test: `tests/unit/init/test_write.py`

**Interfaces:**
- Consumes: `built_in_registry`, `load_extensions` (Task 1); `GateStep` (Task 2).
- Produces:
  - `set_config(project_root, validation=None, extensions=None) -> tuple[Path, list[str]]`
  - `set_gate(project_root, name: str, steps: list[GateStep]) -> tuple[Path, list[str]]`
  - `set_typed(project_root, section: str, name: str, type_name: str, params: dict) -> tuple[Path, list[str]]` where `section` is `"harnesses"` or `"playgrounds"`
  - `InitWriteError(ValueError)`
  - Each returns the written path and a list of human-readable warnings.

- [ ] **Step 1: Add the dependency**

In `pyproject.toml`, add to `dependencies`:

```toml
  "ruamel.yaml>=0.18",
```

Run `uv sync`.

- [ ] **Step 2: Write the failing tests**

Create `tests/unit/init/test_write.py`:

```python
from pathlib import Path

import pytest

from factory.config import GateStep, load_config
from factory.init.write import InitWriteError, set_config, set_gate, set_typed

pytestmark = pytest.mark.unit


def _read(root: Path) -> str:
    return (root / ".factory" / "factory.yaml").read_text(encoding="utf-8")


def test_writes_a_gate_with_ordered_steps(tmp_path):
    set_gate(tmp_path, "unit", [GateStep("pytest -q", "backend"), GateStep("npm test", "frontend")])
    assert load_config(tmp_path).gates["unit"] == [
        GateStep(cmd="pytest -q", cwd="backend"),
        GateStep(cmd="npm test", cwd="frontend"),
    ]


def test_a_gate_name_outside_the_vocabulary_is_rejected(tmp_path):
    with pytest.raises(InitWriteError, match="integration"):
        set_gate(tmp_path, "lint", [GateStep("ruff check .", None)])


def test_comments_survive_a_rewrite(tmp_path):
    # Silently deleting a human's explanation of why a gate is written a certain
    # way is exactly the class of silent loss this repo keeps designing against.
    (tmp_path / ".factory").mkdir()
    (tmp_path / ".factory" / "factory.yaml").write_text(
        "# the sim gate is deliberately absent: no simulator yet\ngates:\n"
        "  unit:\n    - { cmd: 'pytest -q' }\n",
        encoding="utf-8",
    )
    set_gate(tmp_path, "full", [GateStep("ruff check .", None)])
    assert "deliberately absent" in _read(tmp_path)


def test_unknown_top_level_keys_survive_a_rewrite(tmp_path):
    (tmp_path / ".factory").mkdir()
    (tmp_path / ".factory" / "factory.yaml").write_text(
        "future_key: keep me\n", encoding="utf-8"
    )
    set_config(tmp_path, validation="pending")
    assert "future_key" in _read(tmp_path)


def test_running_the_same_verb_twice_changes_nothing(tmp_path):
    set_gate(tmp_path, "unit", [GateStep("pytest -q", None)])
    once = _read(tmp_path)
    set_gate(tmp_path, "unit", [GateStep("pytest -q", None)])
    assert _read(tmp_path) == once


def test_an_unknown_type_with_no_extensions_module_is_a_hard_error(tmp_path):
    # It can never resolve, so accepting it would only defer the failure.
    with pytest.raises(InitWriteError, match="my-bench"):
        set_typed(tmp_path, "harnesses", "bench", "my-bench", {})


def test_an_unknown_type_warns_when_an_extensions_module_is_declared(tmp_path):
    # A greenfield project legitimately declares the seam before writing the code.
    set_config(tmp_path, validation="pending", extensions="proj.ext")
    path, warnings = set_typed(tmp_path, "harnesses", "bench", "my-bench", {"fixtures": "f"})
    assert path.is_file()
    assert any("my-bench" in w for w in warnings)


def test_a_built_in_type_writes_without_warning(tmp_path):
    _, warnings = set_typed(tmp_path, "harnesses", "e2e", "playwright-e2e", {"project": "web"})
    assert warnings == []


def test_validation_value_is_checked(tmp_path):
    with pytest.raises(InitWriteError, match="maybe"):
        set_config(tmp_path, validation="maybe")
```

- [ ] **Step 3: Run to verify they fail**

Run: `uv run pytest tests/unit/init/test_write.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'factory.init.write'`

- [ ] **Step 4: Implement**

Create `src/factory/init/write.py`:

```python
"""Mechanical writes to .factory/factory.yaml.

The agent supplies values; this module constructs the file. Hand-authored YAML
is a silent-malformation hazard -- rejected long after it is written, by
something else. Comments are preserved because deleting a human's note about why
a gate reads the way it does is the same class of silent loss.
"""
from __future__ import annotations

import io
from pathlib import Path

from ruamel.yaml import YAML

from factory.config import GateStep
from factory.registry import ExtensionError, built_in_registry, load_extensions

GATE_NAMES = ("unit", "sim", "integration", "full")
VALIDATION_VALUES = ("none", "pending")
_SECTIONS = ("harnesses", "playgrounds")


class InitWriteError(ValueError):
    pass


def _yaml() -> YAML:
    y = YAML()
    y.preserve_quotes = True
    y.indent(mapping=2, sequence=4, offset=2)
    return y


def _path(project_root: Path) -> Path:
    return project_root / ".factory" / "factory.yaml"


def _load(project_root: Path):
    path = _path(project_root)
    if not path.is_file():
        return {}
    return _yaml().load(path.read_text(encoding="utf-8")) or {}


def _dump(project_root: Path, doc) -> Path:
    path = _path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    stream = io.StringIO()
    _yaml().dump(doc, stream)
    path.write_text(stream.getvalue(), encoding="utf-8")
    return path


def set_config(
    project_root: Path, validation: str | None = None, extensions: str | None = None
) -> tuple[Path, list[str]]:
    if validation is not None and validation not in VALIDATION_VALUES:
        raise InitWriteError(f"validation: {validation!r} is not one of {list(VALIDATION_VALUES)}")
    doc = _load(project_root)
    warnings: list[str] = []
    if validation is not None:
        doc["validation"] = validation
    if extensions is not None:
        doc["extensions"] = extensions
        try:
            load_extensions(extensions, project_root, built_in_registry())
        except ExtensionError as exc:
            warnings.append(
                f"{exc} -- expected at onboarding; the module is written later."
            )
    return _dump(project_root, doc), warnings


def set_gate(project_root: Path, name: str, steps: list[GateStep]) -> tuple[Path, list[str]]:
    if name not in GATE_NAMES:
        raise InitWriteError(
            f"gate {name!r} is not one of {list(GATE_NAMES)}. Projects do not invent gate names."
        )
    if not steps:
        raise InitWriteError(f"gate {name!r}: at least one step is required")
    doc = _load(project_root)
    doc.setdefault("gates", {})
    doc["gates"][name] = [
        {"cmd": s.cmd} if s.cwd is None else {"cmd": s.cmd, "cwd": s.cwd} for s in steps
    ]
    return _dump(project_root, doc), []


def set_typed(
    project_root: Path, section: str, name: str, type_name: str, params: dict
) -> tuple[Path, list[str]]:
    if section not in _SECTIONS:
        raise InitWriteError(f"section {section!r} is not one of {list(_SECTIONS)}")
    doc = _load(project_root)
    declared = doc.get("extensions")
    registry = built_in_registry()
    error = None
    if declared:
        try:
            registry = load_extensions(declared, project_root, registry)
        except ExtensionError as exc:
            error = str(exc)
    known = registry.harnesses if section == "harnesses" else registry.playgrounds
    warnings: list[str] = []
    if type_name not in known:
        if not declared:
            raise InitWriteError(
                f"unknown type {type_name!r} (have {sorted(known)}). No 'extensions:' module "
                "is declared, so this type can never resolve. Declare one first."
            )
        warnings.append(
            f"type {type_name!r} is not registered yet"
            + (f" ({error})" if error else "")
            + " -- it must be registered by "
            + f"{declared} before this {section[:-1]} can run."
        )
    entry = {"type": type_name}
    entry.update(params)
    doc.setdefault(section, {})
    doc[section][name] = entry
    return _dump(project_root, doc), warnings
```

Extend `src/factory/init/cli.py` with the four verbs:

```python
    p_config = sub.add_parser("config", parents=[common])
    p_config.add_argument("--validation", choices=["none", "pending"])
    p_config.add_argument("--extensions")

    p_gate = sub.add_parser("gate", parents=[common])
    p_gate.add_argument("name")
    p_gate.add_argument("--step", action="append", required=True, dest="steps")
    # One --cwd per --step, in the same order; omit with "" for a step that needs none.
    p_gate.add_argument("--cwd", action="append", default=[], dest="cwds")

    for verb in ("harness", "playground"):
        p = sub.add_parser(verb, parents=[common])
        p.add_argument("name")
        p.add_argument("--type", required=True, dest="type_name")
        # JSON, not k=v: params carry typed values a flat key-value syntax cannot express.
        p.add_argument("--params-json", dest="params_json", default="{}")
```

and dispatch:

```python
    warnings: list[str] = []
    if args.cmd == "config":
        path, warnings = set_config(args.project_root, args.validation, args.extensions)
        print(f"wrote {path}")
    elif args.cmd == "gate":
        cwds = list(args.cwds) + [""] * (len(args.steps) - len(args.cwds))
        steps = [GateStep(cmd=c, cwd=w or None) for c, w in zip(args.steps, cwds)]
        path, warnings = set_gate(args.project_root, args.name, steps)
        print(f"wrote {path}")
    elif args.cmd in ("harness", "playground"):
        section = "harnesses" if args.cmd == "harness" else "playgrounds"
        path, warnings = set_typed(
            args.project_root, section, args.name, args.type_name, json.loads(args.params_json)
        )
        print(f"wrote {path}")
    for warning in warnings:
        print(f"warning: {warning}")
```

Wrap the dispatch in `try: ... except (InitWriteError, ExtensionError) as exc: print(f"error: {exc}"); return 1`, matching `doctor/cli.py`'s error handling — read it first and copy its shape.

- [ ] **Step 5: Run**

Run: `uv run pytest -m unit -q && uv run ruff check . && uv run pyright`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "feat(init): mechanical, comment-preserving config writes

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 8: The `init` skill

**Files:**
- Create: `.pi/skills/init/SKILL.md`
- Test: `pi-ext/factory-watch/test/skill-prompt.test.ts` (extend)

**Interfaces:**
- Consumes: the CLI surface from Tasks 6-7.
- Produces: a vendored skill discoverable once Task 10 lands.

- [ ] **Step 1: Write the failing test**

Read `pi-ext/factory-watch/test/skill-prompt.test.ts` first and follow its shape. Append:

```typescript
describe("the init skill", () => {
  const body = readFileSync(
    join(factorySkillsDir(), "init", "SKILL.md"),
    "utf-8",
  );

  test("names the context command rather than describing it", () => {
    expect(body).toContain("factory init context");
  });

  test("offers every validation answer, including opting out entirely", () => {
    expect(body).toContain("none");
    expect(body).toContain("pending");
  });

  test("states that it does not choose a harness for a greenfield repo", () => {
    // A measuring apparatus cannot be chosen before the requirements that
    // define what it measures exist.
    expect(body.toLowerCase()).toContain("greenfield");
  });
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd pi-ext/factory-watch && npm test -- skill-prompt`
Expected: FAIL — ENOENT on `init/SKILL.md`.

- [ ] **Step 3: Write the skill**

Create `.pi/skills/init/SKILL.md`:

```markdown
---
name: init
description: Onboard a repository as a factory target -- read what PIF offers and what the repo already has, agree what it should declare, and let the init tools perform every write. Use when a project has no .factory/factory.yaml, or has one that predates the extension registry.
---

# Init

Use this when a repository should become a factory target: it has no
`.factory/factory.yaml`, or it has one written before the extension registry
existed.

## What you own, and what you do not

You own **the judgement**: what kind of project this is, what its gate commands
actually are, whether a built-in harness fits, whether it wants system
validation at all, and when onboarding is finished.

You do **not** own YAML construction, gate-name checking, or type resolution.
Hand-authored config fails silently -- rejected much later, by something else.

## Steps

1. **Get the picture.** Call `factory init context`. It gives you what PIF
   offers and every raw fact about this repo. It deliberately draws no
   conclusions -- "there is a `pyproject.toml` declaring a `unit` marker" is a
   fact; "this is a pytest project, so the unit gate is `pytest -m unit`" is
   your call.
2. **Read the repo yourself** with your own file tools where the facts are not
   enough. A build system nobody anticipated is exactly the case this must
   survive.
3. **Propose the gates.** One gate at a time, with the command you would write
   and why. Gate names are fixed: `unit`, `sim`, `integration`, `full`. An
   undeclared gate skips and passes, so propose only gates this repo really has
   -- an `exit 0` stub is worse than an honest absence.
4. **On accept**, `factory init gate <name> --step "<cmd>" [--cwd <dir>]`,
   repeating `--step` in order.
5. **Ask whether this project wants verified system requirements.** Three
   honest answers:
   - **yes** -> `factory init config --validation pending`, then offer to
     continue into the specification workflow in this session.
   - **not yet** -> `factory init config --validation pending`, and stop.
   - **never** -> `factory init config --validation none`, and stop. Do not
     raise requirements in this repo again.
   If the repo already has requirements, do not set this key at all; a
   non-empty register is already the active state, and the tools will refuse.
6. **If the project needs its own harness, playground, metric or skill**, it
   needs an extension module: `factory init config --extensions <module>`. The
   module exports `register(r)` and calls `r.harness(...)`, `r.playground(...)`,
   `r.scorers({...})`, `r.skills(path)`. Warning that the module does not import
   yet is expected at onboarding -- it is written later.
7. **Do not choose a harness for a greenfield repo.** A measuring apparatus
   cannot be picked before the requirements that define what it measures exist.
   Record a harness only when the repo already has one. Otherwise the
   specification workflow declares it, using the same
   `factory init harness` verb.
8. **Say when you believe onboarding is complete**, and what you based it on --
   which gates you declared, what you deliberately left undeclared, and what
   the project still owes.

## Rules

- **Never hand-write `.factory/factory.yaml`.** The `config`, `gate`, `harness`
  and `playground` verbs perform every write, and they preserve the comments and
  keys a human put there.
- **One proposal, one confirmation.** Never batch, and never call a write verb
  before the human answers.
- **Report warnings verbatim.** An unresolved type or an unimportable extension
  module is a real state; do not soften it into "should be fine".
- **`factory init context` reports; it does not recommend.** If you want a
  ranking, that is your judgement to produce and to defend.
```

- [ ] **Step 4: Run**

Run: `cd pi-ext/factory-watch && npm test -- skill-prompt`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat(init): the onboarding skill

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 9: `pif` stays in the caller's repo and carries the factory's skills

**Files:**
- Modify: `scripts/install-pif.sh`
- Test: `tests/unit/test_install_pif.py`

**Interfaces:**
- Consumes: nothing.
- Produces: three shims (`pif`, `pif.cmd`, `pif.ps1`) that do not `cd` and pass `--skill`; `PIF_BIN_DIR` overrides the npm prefix so the script is testable.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_install_pif.py`:

```python
import shutil
import subprocess
from pathlib import Path

import pytest

from factory.paths import factory_root

pytestmark = pytest.mark.unit

_SHIMS = ("pif", "pif.cmd", "pif.ps1")


@pytest.fixture
def installed(tmp_path: Path) -> Path:
    sh = shutil.which("sh") or shutil.which("bash")
    if sh is None:
        pytest.skip("no POSIX shell available")
    subprocess.run(
        [sh, str(factory_root() / "scripts" / "install-pif.sh")],
        env={"PIF_BIN_DIR": str(tmp_path), "PATH": "/usr/bin:/bin"},
        check=True,
        capture_output=True,
    )
    return tmp_path


def test_every_shim_is_generated(installed):
    for name in _SHIMS:
        assert (installed / name).is_file()


def test_no_shim_relocates_the_session_into_the_factory(installed):
    # The whole point of running pif from another repo. Before this, all three
    # shims cd'd into the factory checkout.
    for name in _SHIMS:
        body = (installed / name).read_text(encoding="utf-8")
        assert "cd " not in body
        assert "Set-Location" not in body


def test_every_shim_puts_the_factory_skills_on_pi_s_search_path(installed):
    # Pi searches <cwd>/.pi/skills, not the factory's, so without --skill none of
    # the factory's skills (the doctor included) is discoverable from a target repo.
    for name in _SHIMS:
        body = (installed / name).read_text(encoding="utf-8")
        assert "--skill" in body
        assert ".pi" in body and "skills" in body
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/unit/test_install_pif.py -q`
Expected: FAIL — the script calls `npm config get prefix` and the shims contain `cd`.

- [ ] **Step 3: Implement**

In `scripts/install-pif.sh`, replace the npm-prefix block's opening so `PIF_BIN_DIR` wins:

```sh
NPM_PREFIX_WIN="${PIF_BIN_DIR:-$(npm config get prefix)}"
```

and, when `PIF_BIN_DIR` is set, skip the `cygpath` conversion (it is already a usable path):

```sh
if [ -n "$PIF_BIN_DIR" ]; then
  NPM_BIN="$PIF_BIN_DIR"
elif command -v cygpath > /dev/null 2>&1; then
  NPM_BIN="$(cygpath -u "$NPM_PREFIX_WIN")"
else
  NPM_BIN="$NPM_PREFIX_WIN"
fi
```

Add the skills path next to the extension path:

```sh
EXT_PATH="$REPO_ROOT/pi-ext/factory-watch/src/index.ts"
SKILLS_PATH="$REPO_ROOT/.pi/skills"
```

Replace the three heredocs. The header comment must change too — it currently
promises the opposite behaviour:

```sh
# Installs a `pif` command into the npm global bin directory (the same
# directory `pi` itself already lives in, already on PATH) that launches
# `pi` with the factory-watch extension and the factory's skills loaded,
# IN THE DIRECTORY IT IS INVOKED FROM. It deliberately does not cd into
# this repo: the factory runs against other repositories, and relocating
# the session was making every command operate on the wrong one.
```

```sh
cat > "$NPM_BIN/pif" <<EOF
#!/bin/sh
exec pi --extension "$EXT_PATH" --skill "$SKILLS_PATH" "\$@"
EOF
chmod +x "$NPM_BIN/pif"

cat > "$NPM_BIN/pif.cmd" <<EOF
@echo off
pi --extension "$EXT_PATH" --skill "$SKILLS_PATH" %*
EOF

cat > "$NPM_BIN/pif.ps1" <<EOF
#!/usr/bin/env pwsh
& pi --extension "$EXT_PATH" --skill "$SKILLS_PATH" @args
exit \$LASTEXITCODE
EOF
```

Update the closing `echo` hint to a command that makes sense from another repo:

```sh
echo "Try from any repo:"
echo "  pif -p \"/skill:init\" --mode json"
```

Update `README.md`'s Setup section to say the shim runs in the current directory.

- [ ] **Step 4: Run**

Run: `uv run pytest tests/unit/test_install_pif.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "fix(pif): stay in the caller's repo and carry the factory's skills

The shims cd'd into the factory checkout, so running pif from another
repo gave you a session on the wrong one. Pi searches <cwd>/.pi/skills,
never the factory's, so no factory skill -- the doctor included -- was
discoverable from a target repo either.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 10: One skill resolver for every command

**Files:**
- Modify: `pi-ext/factory-watch/src/factory-skills.ts`
- Modify: `pi-ext/factory-watch/src/index.ts:593-628` (`/plan`), `:654-670` (`/trace-fix`)
- Test: `pi-ext/factory-watch/test/factory-skills.test.ts`

**Interfaces:**
- Consumes: existing `findSkillFile`.
- Produces, from `factory-skills.ts`:
  - `export const PLAN_SKILL_NAMES = ["brainstorming", "writing-plans"]`
  - `export const TRACE_FIX_SKILL_NAMES = ["trace-fix"]`
  - `export function resolveSkillBlocks(cwd: string, names: readonly string[]): { blocks: string[] } | { missing: string; lookedIn: string[] }`

- [ ] **Step 1: Write the failing tests**

Append to `pi-ext/factory-watch/test/factory-skills.test.ts`:

```typescript
import {
  PLAN_SKILL_NAMES,
  resolveSkillBlocks,
} from "../src/factory-skills.js";

describe("resolveSkillBlocks", () => {
  test("resolves /plan's skills from a cwd that vendors none", () => {
    // /plan used loadSkills({ skillPaths: [] }), so brainstorming and
    // writing-plans resolved only from the target repo or ~/.pi/agent --
    // meaning /plan failed in every repo where /trace-fix worked.
    const empty = mkdtempSync(join(tmpdir(), "empty-"));
    const result = resolveSkillBlocks(empty, PLAN_SKILL_NAMES);
    expect("blocks" in result).toBe(true);
    if ("blocks" in result) {
      expect(result.blocks).toHaveLength(2);
      expect(result.blocks[0]).toContain('<skill name="brainstorming"');
    }
  });

  test("prefers the target repo's copy", () => {
    const root = repoWithSkill("brainstorming");
    const result = resolveSkillBlocks(root, ["brainstorming"]);
    expect("blocks" in result && result.blocks[0]).toContain(
      join(root, ".pi", "skills", "brainstorming", "SKILL.md"),
    );
  });

  test("names the missing skill and every place it looked", () => {
    const empty = mkdtempSync(join(tmpdir(), "empty-"));
    const result = resolveSkillBlocks(empty, ["no-such-skill"]);
    expect("missing" in result).toBe(true);
    if ("missing" in result) {
      expect(result.missing).toBe("no-such-skill");
      expect(result.lookedIn.length).toBeGreaterThan(0);
    }
  });
});
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd pi-ext/factory-watch && npm test -- factory-skills`
Expected: FAIL — `resolveSkillBlocks` is not exported.

- [ ] **Step 3: Implement**

In `src/factory-skills.ts`, add:

```typescript
import { readFileSync } from "node:fs";
import { stripFrontmatter } from "@earendil-works/pi-coding-agent";
import { buildSkillBlock } from "./skill-prompt.js";

export const PLAN_SKILL_NAMES = ["brainstorming", "writing-plans"] as const;
export const TRACE_FIX_SKILL_NAMES = ["trace-fix"] as const;

/**
 * Resolve several skills to prompt blocks, target-repo copy first.
 *
 * Every command uses this. /plan previously used loadSkills({ skillPaths: [] }),
 * which searches only the target repo and ~/.pi/agent -- so it failed in exactly
 * the repos /trace-fix worked in. One resolver, one behaviour.
 */
export function resolveSkillBlocks(
  cwd: string,
  names: readonly string[],
): { blocks: string[] } | { missing: string; lookedIn: string[] } {
  const blocks: string[] = [];
  for (const name of names) {
    const filePath = findSkillFile(cwd, name);
    if (filePath === null) {
      return {
        missing: name,
        lookedIn: [join(cwd, ".pi", "skills"), factorySkillsDir()],
      };
    }
    const body = stripFrontmatter(readFileSync(filePath, "utf-8")).trim();
    blocks.push(buildSkillBlock({ name, location: filePath, body }));
  }
  return { blocks };
}
```

In `src/index.ts`:
- Delete the local `PLAN_SKILL_NAMES` and `TRACE_FIX_SKILL_NAMES` constants (lines 61-62) and import them from `./factory-skills.js` instead.
- Replace `/plan`'s `loadSkills` block with:

```typescript
      const resolved = resolveSkillBlocks(ctx.cwd, PLAN_SKILL_NAMES);
      if ("missing" in resolved) {
        ctx.ui.notify(
          `/plan: skill not found: ${resolved.missing} (looked in ${resolved.lookedIn.join(", ")})`,
          "error",
        );
        return;
      }
      const seedText = buildPlanSeedPrompt(topic, resolved.blocks);
```

- Replace `/trace-fix`'s per-name loop with the same call, keeping its `/trace-fix:` message prefix and its existing comment about `ctx.cwd`.
- Remove `loadSkills` from the `@earendil-works/pi-coding-agent` import if nothing else uses it; run `npm run typecheck` to confirm.

- [ ] **Step 4: Run**

Run: `cd pi-ext/factory-watch && npm test && npm run typecheck`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "fix(factory-watch): one skill resolver for every command

/plan resolved its skills only from the target repo or ~/.pi/agent, so it
failed in exactly the repos /trace-fix worked in.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 11: Migrate the drone repo to the extension registry

**Files (in `../cool_physical_ai_project`, a separate repository):**
- Create: `src/drone/factory_ext.py`
- Modify: `.factory/factory.yaml`
- Test: `tests/unit/test_factory_ext.py`

**Interfaces:**
- Consumes: `Registry` (Task 1); the `scorers:` rejection (Task 2).
- Produces: nothing the factory imports; this repo is the first consumer of the seam.

- [ ] **Step 1: Write the failing test**

In `cool_physical_ai_project`, create `tests/unit/test_factory_ext.py`:

```python
import pytest

from factory.registry import built_in_registry
from drone.factory_ext import register

pytestmark = pytest.mark.unit


def test_register_supplies_the_preemption_metric():
    r = built_in_registry()
    register(r)
    assert "preemption_success_rate" in r.scorer_map


def test_the_config_declares_the_extension_module_and_no_scorers_key():
    from pathlib import Path

    import yaml

    data = yaml.safe_load(Path(".factory/factory.yaml").read_text(encoding="utf-8"))
    assert data["extensions"] == "drone.factory_ext"
    assert all("scorers" not in (h or {}) for h in data["harnesses"].values())
```

- [ ] **Step 2: Run to verify it fails**

Run (from `cool_physical_ai_project`): `uv run pytest tests/unit/test_factory_ext.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'drone.factory_ext'`

- [ ] **Step 3: Implement**

Create `src/drone/factory_ext.py`:

```python
"""What this product adds to the factory.

The factory owns the mechanism; a project registers its plugs here. One module,
so a new kind of extension needs no new config key.
"""
from __future__ import annotations

from drone.validation.scorers import trial_preempted


def register(r) -> None:
    r.scorers({"preemption_success_rate": trial_preempted})
```

Edit `.factory/factory.yaml` to drop `scorers:` and declare the module, keeping the existing comments and rewriting the one that explains the old key:

```yaml
# What this repo adds to the factory: metrics, and later its own harness.
# The metric lives here because it scores this product's behaviour.
extensions: drone.factory_ext

harnesses:
  sim-testbench:
    type: sim-testbench
    traces_dir: validation/traces

gates:
  unit:
    - { cmd: "{python} -m pytest -m unit -q" }
  full:
    - { cmd: "{python} -m ruff check ." }
    - { cmd: "{python} -m pytest -m unit -q" }
```

- [ ] **Step 4: Verify end to end**

Run from `cool_physical_ai_project`:

```bash
uv run pytest -m unit -q
uv run python -m factory.doctor context
uv run python -m factory.trace status
uv run python -m factory.init context
```

Expected: tests pass; `doctor context` lists `preemption_success_rate` under the sim-testbench harness; `trace status` shows no opt-out line (the register holds SR-001); `init context` reports the extension module resolving with one metric registered.

- [ ] **Step 5: Commit (in the drone repo)**

```bash
git add -A
git commit -m "refactor(validation): register the preemption metric through the factory registry

harnesses.*.scorers is gone; one extension module supplies metrics, and
later this repo's own harness.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 12: Dogfood and document

**Files:**
- Modify: `.factory/factory.yaml` (the factory's own)
- Modify: `README.md`
- Test: `tests/unit/test_factory_own_gates.py` (extend)

**Interfaces:**
- Consumes: everything above.
- Produces: no API.

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_factory_own_gates.py`:

```python
def test_the_factory_declares_its_own_validation_choice():
    # The factory builds products; it has no system requirements of its own, and
    # saying so is different from never having been asked.
    from factory.config import load_config, validation_state
    from factory.paths import factory_root

    root = factory_root()
    assert validation_state(load_config(root), root) == "none"
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/unit/test_factory_own_gates.py -q`
Expected: FAIL — state is `undeclared`.

- [ ] **Step 3: Implement**

Add to the factory's own `.factory/factory.yaml`, above `gates:`:

```yaml
# The factory builds products; it has no system requirements of its own. Recorded
# rather than left blank so `trace status` reads "opted out" and not "0%".
validation: none
```

In `README.md`:
- Replace the "Declaring a project's gates" note about `scorers:` with the extension-module shape, showing `extensions:` and a `register(r)` example.
- Add an "Onboarding a project" section pointing at `/skill:init` and
  `python -m factory.init context`.
- Correct the Setup section: `pif` now runs in the current directory and loads
  the factory's skills, so every factory skill and command is available from any
  repo.

- [ ] **Step 4: Full verification**

Run:

```bash
uv run ruff check .
uv run pyright
uv run pytest -m unit -q
uv run pytest -m agent -q
cd pi-ext/factory-watch && npm test && npm run typecheck && cd ../..
cd pi-ext/scope-guard && npm test && npm run typecheck && cd ../..
uv run python -m factory.init context
uv run python -m factory.trace status
```

Expected: all green; `trace status` on the factory prints the opted-out line.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "docs: onboarding, the extension module, and the factory's own choice

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Self-Review

**Spec coverage**

| spec section | task |
|---|---|
| §3 skill/CLI split | 6, 7, 8 |
| §4 `init context`, both halves + CLI reachability | 6 |
| §5 registry, resolution, `scorers:` deleted | 1, 2 |
| §5.3 skills append-not-replace, collision is an error | 1, 5 |
| §6 `validation:` (with the documented deviation) | 3, 4 |
| §7 init declares no greenfield harness | 8 (skill step 7) |
| §8.1 `pif` does not `cd` | 9 |
| §8.2 `--skill` on the search path | 9 |
| §8.3 one skill resolver | 10 |
| §8.4 collisions reported | 6 |
| §8.5 CLI reachability reported | 6 |
| §9 CLI surface, `--params-json`, unknown-type rule | 7 |
| §10 idempotency, comments preserved | 7 |
| §11 components | all |
| §12 testing strategy | every task's tests; dogfood guard in 12 |
| §13 non-goals | nothing here scaffolds directories, publishes PIF, or touches the node graph |

**Type consistency checked:** `TypeFactory` is `(dict, Path, Registry)` in Task 1 and every `from_config` is changed to match in Task 2. `set_config`/`set_gate`/`set_typed` all return `tuple[Path, list[str]]` in Task 7 and the CLI unpacks two values. `validation_state` returns the same four strings in Tasks 3, 4 and 6. `resolveSkillBlocks`'s union return is destructured with `"missing" in result` in both Task 10 call sites.

**Known ordering constraint:** Task 2 is the only breaking change; Tasks 3-8 build on its `FactoryConfig` shape. Tasks 9 and 10 are independent of the Python work and could run in parallel with 1-8. Task 11 requires Task 2 (it fails against the old code) and Task 6 (its verification calls `init context`).
