from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace

import pytest

from factory.trace.validation_status import requirement_validation


pytestmark = pytest.mark.unit

ROOT = Path(__file__).parents[3]


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def test_trace_validation_uses_structural_state_and_has_no_goal_dependency():
    validation_path = ROOT / "src" / "factory" / "trace" / "validation_status.py"

    assert requirement_validation([SimpleNamespace(state="REACHED")]) == "VALIDATED"
    assert not any(name == "factory.goals.schema" for name in _imports(validation_path))


def test_trace_graph_uses_the_substrate_adr_parser():
    graph_path = ROOT / "src" / "factory" / "trace" / "graph.py"
    imports = _imports(graph_path)

    assert "substrate.documents.adr" in imports
    assert "factory.system" not in imports
