"""substrate must stay neutral: nothing under src/substrate may import
factory or coherence, in any form. Statically parsed with `ast` -- this must
catch a forbidden import even if the module itself never gets imported by
the test suite (a runtime-import-based check would miss dead code)."""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[3]
SUBSTRATE_ROOT = REPO_ROOT / "src" / "substrate"

FORBIDDEN_ROOTS = {"factory", "coherence"}


def _substrate_files() -> list[Path]:
    return sorted(SUBSTRATE_ROOT.rglob("*.py"))


def _forbidden_imports(path: Path) -> list[str]:
    """Return offending import statements (source text) in `path`, if any."""
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))
    offenders: list[str] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".", 1)[0]
                if root in FORBIDDEN_ROOTS:
                    offenders.append(f"import {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            root = module.split(".", 1)[0]
            if root in FORBIDDEN_ROOTS:
                names = ", ".join(alias.name for alias in node.names)
                dots = "." * node.level
                offenders.append(f"from {dots}{module} import {names}")

    return offenders


def test_substrate_has_python_files_to_check():
    # Guards against the glob silently matching nothing (e.g. a bad root),
    # which would make every parametrized case below vacuously pass.
    assert _substrate_files()


@pytest.mark.parametrize(
    "path",
    _substrate_files(),
    ids=lambda p: str(p.relative_to(SUBSTRATE_ROOT)),
)
def test_substrate_file_imports_no_factory_or_coherence(path: Path):
    offenders = _forbidden_imports(path)
    assert not offenders, (
        f"{path}: forbidden import(s) of factory/coherence found:\n"
        + "\n".join(f"  {line}" for line in offenders)
    )
