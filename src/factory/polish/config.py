from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import yaml

from factory.polish.devserver import DevServerPlayground
from factory.polish.playground import Playground
from factory.polish.reference import ScenarioReplayPlayground
from factory.validation.harness import Harness
from factory.validation.sim_harness import SimTestbenchHarness

PLAYGROUND_TYPES: dict[str, Callable[[dict, Path], Playground]] = {
    "dev-server": DevServerPlayground.from_config,
    "scenario-replay": ScenarioReplayPlayground.from_config,
}
HARNESS_TYPES: dict[str, Callable[[dict, Path], Harness]] = {
    "sim-testbench": SimTestbenchHarness.from_config,
}


class UnknownTypeError(ValueError):
    pass


@dataclass
class FactoryConfig:
    playgrounds: dict[str, Playground]
    harnesses: dict[str, Harness]


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
        return FactoryConfig({}, {})
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    playgrounds = {
        n: _build(PLAYGROUND_TYPES, n, s, project_root)
        for n, s in (data.get("playgrounds") or {}).items()
    }
    harnesses = {
        n: _build(HARNESS_TYPES, n, s, project_root)
        for n, s in (data.get("harnesses") or {}).items()
    }
    return FactoryConfig(playgrounds, harnesses)
