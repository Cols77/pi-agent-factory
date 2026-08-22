from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from substrate.config import (
    GateConfigError,
    GateDeclarations,
    GateStep,
    load_gate_declarations,
)
from substrate.config import require_gates as _require_gate_declarations

# GateConfigError, GateDeclarations, and GateStep are re-exported here rather
# than only kept internally: factory.polish.config, factory.orchestrator.backends,
# and existing tests import gate-config types from this module, and the split
# with substrate.config (Task 2) is an internal-composition change, not a public
# API move -- factory.config keeps its full surface, unchanged, on top of it.
__all__ = [
    "FactoryConfig",
    "GateConfigError",
    "GateDeclarations",
    "GateStep",
    "UnknownTypeError",
    "load_config",
    "require_gates",
]


class UnknownTypeError(ValueError):
    pass


@dataclass
class FactoryConfig:
    playgrounds: dict[str, Any]
    harnesses: dict[str, Any]
    gates: GateDeclarations


def _build(types: dict, name: str, spec: dict, project_root: Path):
    spec = dict(spec)
    type_name = spec.pop("type", None)
    ctor = types.get(type_name)
    if ctor is None:
        raise UnknownTypeError(f"{name!r}: unknown type {type_name!r} (have {sorted(types)})")
    return ctor(spec, project_root)


def load_config(project_root: Path) -> FactoryConfig:
    path = project_root / ".factory" / "factory.yaml"
    if not path.exists():
        return FactoryConfig({}, {}, {})
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    # Imported here, not at module level: the orchestrator imports this module,
    # and a module-level import of factory.polish would point the core package
    # back at a consumer -- the inversion this move exists to remove.
    from factory.polish.config import HARNESS_TYPES, PLAYGROUND_TYPES

    playgrounds = {
        n: _build(PLAYGROUND_TYPES, n, s, project_root)
        for n, s in (data.get("playgrounds") or {}).items()
    }
    harnesses = {
        n: _build(HARNESS_TYPES, n, s, project_root)
        for n, s in (data.get("harnesses") or {}).items()
    }
    return FactoryConfig(playgrounds, harnesses, load_gate_declarations(data))


def require_gates(cfg: FactoryConfig, project_root: Path) -> GateDeclarations:
    """Gates for a project that must have them, else raise.

    'This project has no sim' and 'this project never said what to check' are
    different statements. An individual gate may be omitted -- it skips -- but a
    project with no gates at all would validate nothing while reporting green.
    """
    context = str(project_root / ".factory" / "factory.yaml")
    return _require_gate_declarations(cfg.gates, context)
