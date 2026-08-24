from __future__ import annotations

import importlib
import sys
from collections.abc import Callable
from pathlib import Path

__all__ = ["Scorer", "ScorerModuleError", "load_scorers"]

Scorer = Callable[..., bool]


class ScorerModuleError(ValueError):
    pass


def load_scorers(module_name: str | None, project_root: Path) -> dict[str, Scorer]:
    """Import the target repo's scorer module and return its SCORERS mapping.

    A missing name is an empty map, not an error: a project that declares no
    scorers has implemented no metrics yet, which the register can now say
    honestly rather than crashing. Importing target-repo code is the same trust
    posture the gate steps already carry -- see the design's section 4.1.
    """
    if not module_name:
        return {}
    # Both this repo and its targets use a src/ layout (pyproject
    # `[tool.setuptools.packages.find] where = ["src"]`), and the factory runs from
    # its own interpreter, so the target's src/ is not importable by default.
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
