from __future__ import annotations

from dataclasses import dataclass, field
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
    "GovernedExecutionConfig",
    "GovernedExecutionConfigError",
    "UnknownTypeError",
    "load_config",
    "require_gates",
    "require_governed_execution",
]


class UnknownTypeError(ValueError):
    pass


class GovernedExecutionConfigError(ValueError):
    """``governed_execution`` is absent, malformed, or unusable for a dispatch."""


@dataclass(frozen=True)
class GovernedExecutionConfig:
    """SR-034's project-wide governed-execution settings.

    ``max_fixer_iterations`` is the single fixer budget for *every* governed
    task in this project. It is deliberately project-wide rather than
    task-local: decision 3 (2026-09-11) recorded one human-decided budget
    (``2``) for the whole execution graph, so there is exactly one field here
    and no task dimension a task could override.

    ``None`` means "the project did not declare a budget"; a governed dispatch
    must fail closed on that (see :func:`require_governed_execution`) rather
    than guess one.
    """

    max_fixer_iterations: int | None = None

    def __post_init__(self) -> None:
        value = self.max_fixer_iterations
        if value is None:
            return
        if isinstance(value, bool) or not isinstance(value, int):
            raise GovernedExecutionConfigError(
                "governed_execution.max_fixer_iterations must be an integer, "
                f"not {type(value).__name__} ({value!r})"
            )
        if value < 1:
            raise GovernedExecutionConfigError(
                f"governed_execution.max_fixer_iterations must be >= 1, got {value!r}"
            )


@dataclass
class FactoryConfig:
    playgrounds: dict[str, Any]
    harnesses: dict[str, Any]
    gates: GateDeclarations
    governed_execution: GovernedExecutionConfig = field(
        default_factory=GovernedExecutionConfig
    )


def load_governed_execution(data: dict, context: str) -> GovernedExecutionConfig:
    """Parse ``governed_execution`` from a factory.yaml mapping.

    An absent section or key is an *unset* budget (``None``), not a parse
    error: only a governed dispatch needs the value, and it fails closed on
    ``None`` via :func:`require_governed_execution`. A present but malformed
    value is rejected here, where the file and key are still known.
    """
    section = data.get("governed_execution")
    if section is None:
        return GovernedExecutionConfig()
    if not isinstance(section, dict):
        raise GovernedExecutionConfigError(
            f"{context}: governed_execution must be a mapping, not {type(section).__name__}"
        )
    if "max_fixer_iterations" not in section:
        return GovernedExecutionConfig()
    try:
        return GovernedExecutionConfig(
            max_fixer_iterations=section["max_fixer_iterations"]
        )
    except GovernedExecutionConfigError as exc:
        raise GovernedExecutionConfigError(f"{context}: {exc}") from exc



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
    context = str(path)
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
    return FactoryConfig(
        playgrounds,
        harnesses,
        load_gate_declarations(data),
        load_governed_execution(data, context),
    )


def require_gates(cfg: FactoryConfig, project_root: Path) -> GateDeclarations:
    """Gates for a project that must have them, else raise.

    'This project has no sim' and 'this project never said what to check' are
    different statements. An individual gate may be omitted -- it skips -- but a
    project with no gates at all would validate nothing while reporting green.
    """
    context = str(project_root / ".factory" / "factory.yaml")
    return _require_gate_declarations(cfg.gates, context)


def require_governed_execution(
    cfg: FactoryConfig, project_root: Path, *, task_id: str | None = None
) -> GovernedExecutionConfig:
    """The governed-execution settings a dispatch needs, else raise.

    A governed dispatch must fail closed when the project never declared a
    fixer budget: "the human decided 2 for this project" and "this project
    never said" are different statements, and a driver that invented a budget
    would spend human-decided iterations nobody authorised.

    ``task_id`` is accepted only to make the intent explicit and can never
    change the answer -- the budget is project-wide by decision 3
    (2026-09-11). It is ignored on purpose, so a caller cannot turn this into
    a task-local lookup.
    """
    del task_id  # project-wide by design: no task-local override exists.
    context = str(project_root / ".factory" / "factory.yaml")
    settings = cfg.governed_execution
    if settings.max_fixer_iterations is None:
        raise GovernedExecutionConfigError(
            f"{context}: governed_execution.max_fixer_iterations is unset; "
            "a governed dispatch fails closed without a project-wide fixer budget "
            "(SR-034 decision 3, 2026-09-11, recorded 2)"
        )
    return settings

