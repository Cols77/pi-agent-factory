from __future__ import annotations

from pathlib import Path

import pytest

from coherence.register.relations import resolve_sr_relations

pytestmark = pytest.mark.unit

# SR-050/AC-1: "Each requirement an implementation slice changes carries
# typed implementation and validation references whose repository-relative
# paths resolve inside the project and whose symbol or pytest node
# identifiers resolve to real definitions, with no line number used as
# identity."


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _write_prod(root: Path) -> None:
    _write(
        root / "src" / "widgets" / "feature.py",
        "def feature_context():\n"
        "    return 1\n"
        "\n"
        "\n"
        "class Widget:\n"
        "    def render(self):\n"
        "        return 2\n",
    )


def _write_test_file(root: Path) -> None:
    _write(
        root / "tests" / "unit" / "test_feature.py",
        "def test_feature_context():\n"
        "    assert True\n"
        "\n"
        "\n"
        "class TestWidget:\n"
        "    def test_render(self):\n"
        "        assert True\n",
    )


@pytest.mark.sr("SR-050")
def test_a_symbol_resolving_to_a_real_definition_produces_no_issue(tmp_path: Path):
    _write_prod(tmp_path)
    meta = {
        "implemented_by": [
            {"path": "src/widgets/feature.py", "symbol": "widgets.feature:feature_context"}
        ]
    }
    resolution = resolve_sr_relations(tmp_path, meta)
    assert resolution.ok
    assert resolution.issues == ()


@pytest.mark.sr("SR-050")
def test_a_symbol_with_no_matching_definition_is_a_reference_issue(tmp_path: Path):
    _write_prod(tmp_path)
    meta = {
        "implemented_by": [
            {"path": "src/widgets/feature.py", "symbol": "widgets.feature:does_not_exist"}
        ]
    }
    resolution = resolve_sr_relations(tmp_path, meta)
    assert not resolution.ok
    assert resolution.issues[0].field == "implemented_by"
    assert "does not resolve" in resolution.issues[0].detail


@pytest.mark.sr("SR-050")
def test_a_symbol_module_mismatched_with_its_declared_path_is_an_issue(tmp_path: Path):
    _write_prod(tmp_path)
    meta = {
        "implemented_by": [
            # symbol claims a different module than the declared path.
            {"path": "src/widgets/feature.py", "symbol": "some.other.module:feature_context"}
        ]
    }
    resolution = resolve_sr_relations(tmp_path, meta)
    assert not resolution.ok
    assert "module does not match" in resolution.issues[0].detail


@pytest.mark.sr("SR-050")
def test_a_pytest_node_resolving_to_a_real_test_produces_no_issue(tmp_path: Path):
    _write_test_file(tmp_path)
    meta = {
        "verified_by": [
            {
                "path": "tests/unit/test_feature.py",
                "test": "tests/unit/test_feature.py::test_feature_context",
            }
        ]
    }
    resolution = resolve_sr_relations(tmp_path, meta)
    assert resolution.ok


@pytest.mark.sr("SR-050")
def test_a_class_scoped_pytest_node_resolving_to_a_real_method_produces_no_issue(tmp_path: Path):
    _write_test_file(tmp_path)
    meta = {
        "verified_by": [
            {
                "path": "tests/unit/test_feature.py",
                "test": "tests/unit/test_feature.py::TestWidget::test_render",
            }
        ]
    }
    resolution = resolve_sr_relations(tmp_path, meta)
    assert resolution.ok


@pytest.mark.sr("SR-050")
def test_a_pytest_node_with_no_matching_test_is_a_reference_issue(tmp_path: Path):
    _write_test_file(tmp_path)
    meta = {
        "verified_by": [
            {
                "path": "tests/unit/test_feature.py",
                "test": "tests/unit/test_feature.py::test_does_not_exist",
            }
        ]
    }
    resolution = resolve_sr_relations(tmp_path, meta)
    assert not resolution.ok
    assert resolution.issues[0].field == "verified_by"
    assert "does not resolve" in resolution.issues[0].detail


@pytest.mark.sr("SR-050")
def test_an_absolute_path_is_rejected_without_touching_the_filesystem(tmp_path: Path):
    meta = {
        "implemented_by": [
            {"path": "/etc/passwd", "symbol": "etc.passwd:root"}
        ]
    }
    resolution = resolve_sr_relations(tmp_path, meta)
    assert not resolution.ok
    assert "does not resolve inside the project" in resolution.issues[0].detail


@pytest.mark.sr("SR-050")
def test_a_dot_dot_escaping_path_is_rejected(tmp_path: Path):
    # Root confinement: matches the convention in coherence.navigate.snapshots
    # and coherence.policy.compiler -- candidate.is_absolute() or ".." in parts.
    outside = tmp_path.parent / "outside.py"
    outside.write_text("def x():\n    pass\n", encoding="utf-8")
    meta = {
        "implemented_by": [
            {"path": "../outside.py", "symbol": "outside:x"}
        ]
    }
    resolution = resolve_sr_relations(tmp_path, meta)
    assert not resolution.ok
    assert "does not resolve inside the project" in resolution.issues[0].detail


@pytest.mark.sr("SR-050")
def test_a_path_that_does_not_exist_on_disk_is_rejected(tmp_path: Path):
    meta = {
        "implemented_by": [
            {"path": "src/widgets/missing.py", "symbol": "widgets.missing:thing"}
        ]
    }
    resolution = resolve_sr_relations(tmp_path, meta)
    assert not resolution.ok
    assert "does not resolve inside the project" in resolution.issues[0].detail


@pytest.mark.sr("SR-050")
def test_a_line_number_shaped_symbol_identity_is_rejected(tmp_path: Path):
    _write_prod(tmp_path)
    meta = {
        "implemented_by": [
            {"path": "src/widgets/feature.py", "symbol": "src/widgets/feature.py:5"}
        ]
    }
    resolution = resolve_sr_relations(tmp_path, meta)
    assert not resolution.ok
    assert "line number" in resolution.issues[0].detail


@pytest.mark.sr("SR-050")
def test_a_line_number_shaped_test_node_identity_is_rejected(tmp_path: Path):
    _write_test_file(tmp_path)
    meta = {
        "verified_by": [
            {
                "path": "tests/unit/test_feature.py",
                "test": "tests/unit/test_feature.py::113",
            }
        ]
    }
    resolution = resolve_sr_relations(tmp_path, meta)
    assert not resolution.ok
    assert "line number" in resolution.issues[0].detail


@pytest.mark.sr("SR-050")
def test_a_verified_by_entry_with_only_a_path_is_file_only_validation(tmp_path: Path):
    # The design allows file-only validation for non-pytest harnesses: no
    # `test` key means nothing further needs to resolve.
    _write_test_file(tmp_path)
    meta = {"verified_by": [{"path": "tests/unit/test_feature.py"}]}
    resolution = resolve_sr_relations(tmp_path, meta)
    assert resolution.ok


@pytest.mark.sr("SR-050")
def test_a_non_python_implemented_by_entry_needs_no_symbol(tmp_path: Path):
    # A produced artifact that is not Python source -- a gate config, a JSON
    # schema, a hook script -- has no symbol to name, so requiring one made it
    # permanently undeclarable. Since SR-049's claim reconciliation reports
    # every claimed-but-undeclared path as a blocking finding, that was not a
    # cosmetic gap: it made the claim gate unsatisfiable for any commit that
    # touched configuration alongside code.
    _write(tmp_path / ".factory" / "factory.yaml", "gates: {}\n")
    meta = {"implemented_by": [{"path": ".factory/factory.yaml"}]}
    resolution = resolve_sr_relations(tmp_path, meta)
    assert resolution.ok


@pytest.mark.sr("SR-050")
def test_a_python_implemented_by_entry_still_requires_its_symbol(tmp_path: Path):
    # The carve-out above is scoped to non-Python artifacts precisely so this
    # keeps its teeth: Python source is exactly where a symbol exists to name,
    # and naming it is what makes the relation canonical rather than file-level.
    _write_prod(tmp_path)
    meta = {"implemented_by": [{"path": "src/widgets/feature.py"}]}
    resolution = resolve_sr_relations(tmp_path, meta)
    assert not resolution.ok
    assert "symbol" in resolution.issues[0].detail


@pytest.mark.sr("SR-050")
def test_legacy_plain_string_verified_by_entries_are_not_this_resolvers_concern(tmp_path: Path):
    # verified_by: [T-001] is the pre-existing string-list graph edge
    # (coherence.trace.model._verified_by_edges), not the SR-050 structured
    # relation -- a non-dict entry is silently skipped here.
    meta = {"verified_by": ["T-001"]}
    resolution = resolve_sr_relations(tmp_path, meta)
    assert resolution.ok


@pytest.mark.sr("SR-050")
def test_no_declared_relations_at_all_resolves_ok(tmp_path: Path):
    assert resolve_sr_relations(tmp_path, {}).ok


@pytest.mark.sr("SR-050")
def test_multiple_entries_report_one_issue_per_failing_entry(tmp_path: Path):
    _write_prod(tmp_path)
    meta = {
        "implemented_by": [
            {"path": "src/widgets/feature.py", "symbol": "widgets.feature:feature_context"},
            {"path": "src/widgets/feature.py", "symbol": "widgets.feature:nope"},
        ]
    }
    resolution = resolve_sr_relations(tmp_path, meta)
    assert len(resolution.issues) == 1
    assert resolution.issues[0].index == 1


@pytest.mark.sr("SR-050")
def test_a_duplicate_implemented_by_entry_is_a_reference_issue(tmp_path: Path):
    _write_prod(tmp_path)
    meta = {
        "implemented_by": [
            {"path": "src/widgets/feature.py", "symbol": "widgets.feature:feature_context"},
            {"path": "src/widgets/feature.py", "symbol": "widgets.feature:feature_context"},
        ]
    }
    resolution = resolve_sr_relations(tmp_path, meta)
    assert not resolution.ok
    assert len(resolution.issues) == 1
    assert resolution.issues[0].index == 1
    assert "duplicate" in resolution.issues[0].detail


@pytest.mark.sr("SR-050")
def test_a_duplicate_verified_by_entry_is_a_reference_issue(tmp_path: Path):
    _write_test_file(tmp_path)
    entry = {
        "path": "tests/unit/test_feature.py",
        "test": "tests/unit/test_feature.py::test_feature_context",
    }
    meta = {"verified_by": [dict(entry), dict(entry)]}
    resolution = resolve_sr_relations(tmp_path, meta)
    assert not resolution.ok
    assert len(resolution.issues) == 1
    assert resolution.issues[0].index == 1
    assert "duplicate" in resolution.issues[0].detail


@pytest.mark.sr("SR-050")
def test_the_same_path_across_different_symbols_is_not_a_duplicate(tmp_path: Path):
    _write_prod(tmp_path)
    meta = {
        "implemented_by": [
            {"path": "src/widgets/feature.py", "symbol": "widgets.feature:feature_context"},
            {"path": "src/widgets/feature.py", "symbol": "widgets.feature:Widget.render"},
        ]
    }
    resolution = resolve_sr_relations(tmp_path, meta)
    assert resolution.ok
