from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from factory.polish.playground import Playground


def load_playgrounds(project_root: Path) -> dict[str, Playground]:
    """Return the project's ``PLAYGROUNDS`` registry, or ``{}`` if absent.

    This EXECUTES ``<project_root>/.factory/registry.py`` as arbitrary Python —
    the same trust level as running the repo's own tooling/``conftest.py``. Only
    run the factory against repos you trust.
    """
    reg = project_root / ".factory" / "registry.py"
    if not reg.exists():
        return {}
    spec = importlib.util.spec_from_file_location("_factory_project_registry", reg)
    if spec is None or spec.loader is None:
        return {}
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # so the module can reference its own definitions
    spec.loader.exec_module(module)
    return dict(getattr(module, "PLAYGROUNDS", {}))
