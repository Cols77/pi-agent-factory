from __future__ import annotations

import importlib.util
from pathlib import Path

from factory.polish.playground import Playground


def load_playgrounds(project_root: Path) -> dict[str, Playground]:
    reg = project_root / ".factory" / "registry.py"
    if not reg.exists():
        return {}
    spec = importlib.util.spec_from_file_location("_factory_project_registry", reg)
    if spec is None or spec.loader is None:
        return {}
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return dict(getattr(module, "PLAYGROUNDS", {}))
