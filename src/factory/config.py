from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


class UnknownTypeError(ValueError):
    pass


class GateConfigError(ValueError):
    pass


@dataclass(frozen=True)
class GateStep:
    cmd: str
    cwd: str | None = None


@dataclass
class FactoryConfig:
    playgrounds: dict[str, Any]
    harnesses: dict[str, Any]
    gates: dict[str, list[GateStep]]


def _build(types: dict, name: str, spec: dict, project_root: Path):
    spec = dict(spec)
    type_name = spec.pop("type", None)
    ctor = types.get(type_name)
    if ctor is None:
        raise UnknownTypeError(f"{name!r}: unknown type {type_name!r} (have {sorted(types)})")
    return ctor(spec, project_root)


def _parse_gates(data: dict) -> dict[str, list[GateStep]]:
    """Absent 'gates:' is {} -- NOT an error. Callers that require gates say so
    themselves (see require_gates); load_config is used by polish and validation
    on repos that declare only playgrounds."""
    gates: dict[str, list[GateStep]] = {}
    for name, steps in (data.get("gates") or {}).items():
        if not isinstance(steps, list):
            raise GateConfigError(
                f"gate {name!r}: expected a list of steps, got {type(steps).__name__}"
            )
        parsed: list[GateStep] = []
        for i, step in enumerate(steps):
            if not isinstance(step, dict) or "cmd" not in step:
                raise GateConfigError(f"gate {name!r} step {i}: each step needs a 'cmd'")
            parsed.append(GateStep(cmd=str(step["cmd"]), cwd=step.get("cwd")))
        gates[name] = parsed
    return gates


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
    return FactoryConfig(playgrounds, harnesses, _parse_gates(data))
