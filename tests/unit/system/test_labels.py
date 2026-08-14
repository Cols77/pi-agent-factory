from pathlib import Path

import pytest

from factory.system.labels import build_alias_map, normalize_ref

from . import _fixtures

# Required: pyproject.toml:31 sets addopts = "-m unit". Without this marker
# every test here is deselected and pytest exits 5.
pytestmark = pytest.mark.unit


def test_normalize_bare_task_id(tmp_path: Path) -> None:
    _fixtures.write_task(tmp_path / "tasks", "T-060", title="Wire the governor")
    assert normalize_ref(tmp_path, "T-060") == "task:T-060"


def test_normalize_prefixed_task_ref_is_idempotent(tmp_path: Path) -> None:
    _fixtures.write_task(tmp_path / "tasks", "T-060", title="Wire the governor")
    assert normalize_ref(tmp_path, "task:T-060") == "task:T-060"


def test_normalize_spec_basename_resolves_to_path_form(tmp_path: Path) -> None:
    _fixtures.write_spec(tmp_path, "2026-07-16-foo-design.md", title="Foo")
    canonical = "spec:docs/superpowers/specs/2026-07-16-foo-design.md"
    assert normalize_ref(tmp_path, "spec:2026-07-16-foo-design.md") == canonical
    assert normalize_ref(tmp_path, canonical) == canonical


def test_normalize_unresolvable_returns_none(tmp_path: Path) -> None:
    assert normalize_ref(tmp_path, "T-999") is None
    assert normalize_ref(tmp_path, "nonsense") is None


def test_alias_map_contains_basename_and_bare_forms(tmp_path: Path) -> None:
    _fixtures.write_spec(tmp_path, "2026-07-16-foo-design.md", title="Foo")
    _fixtures.write_task(tmp_path / "tasks", "T-060", title="Wire the governor")
    aliases = build_alias_map(tmp_path)
    assert aliases["spec:2026-07-16-foo-design.md"] == (
        "spec:docs/superpowers/specs/2026-07-16-foo-design.md"
    )
    assert aliases["T-060"] == "task:T-060"
