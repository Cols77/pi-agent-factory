"""Legacy/canonical parity tests for Coherence Increment 1C, Task 1: the
durable code map moves from factory.codeindex to substrate.codemap.

factory.codeindex.{__init__,model,build,sigs,store,cli} become warn-and-
re-export shims (one release compatibility, matching the Increment 1B house
style -- see tests/unit/substrate/test_legacy_import_matrix.py and
test_compatibility_paths.py). factory.codeindex.substrate -- the
freshness-guard composition adapter (register_code_map_adapter et al.) --
stays factory-side and now imports substrate.codemap directly; it is
composition, not a moved module (like factory.config), so importing it must
stay silent. That file's own deep behavioral coverage lives in
tests/unit/substrate/test_codemap_resolver.py and is unchanged here.

This file covers two things:
  1. Every old factory.codeindex import path warns exactly once, naming its
     substrate.codemap home.
  2. substrate.codemap's ensure_fresh/load_latest/render_index_slice behave
     identically to the (still-working) factory.codeindex equivalents across
     the fixtures that matter: a source change rebuilds, a parser-engine
     change rebuilds, a matching fingerprint/engine reuses the stored index,
     and an empty source set returns the same empty CodeIndex result.
"""
from __future__ import annotations

import importlib
import sys
import warnings
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit


def _import_fresh(module_name: str):
    sys.modules.pop(module_name, None)
    return importlib.import_module(module_name)


def _import_fresh_leaf(module_name: str):
    # `factory.codeindex` (the package) is itself a whole-module shim with its
    # own single warning. Import it first (uncleared) so it is already cached
    # -- Python always imports a submodule's parent package first, and without
    # this the parent's warning would double-count into every leaf case,
    # regardless of test collection order.
    importlib.import_module("factory.codeindex")
    sys.modules.pop(module_name, None)
    return importlib.import_module(module_name)


def _deprecations(caught: list[warnings.WarningMessage]) -> list[warnings.WarningMessage]:
    return [item for item in caught if item.category is DeprecationWarning]


def _tree(root: Path) -> Path:
    root.mkdir(parents=True)
    (root / "src").mkdir()
    (root / "src" / "mod.py").write_text(
        '"""Module doc."""\n\ndef alpha(value):\n    return value\n',
        encoding="utf-8",
    )
    return root


# -- 1. Deprecation-shim matrix: each old import path warns exactly once. ---

WHOLE_MODULE_SHIMS = [
    ("factory.codeindex", "factory.codeindex is deprecated; import substrate.codemap"),
    (
        "factory.codeindex.model",
        "factory.codeindex.model is deprecated; import substrate.codemap.model",
    ),
    (
        "factory.codeindex.build",
        "factory.codeindex.build is deprecated; import substrate.codemap.build",
    ),
    (
        "factory.codeindex.sigs",
        "factory.codeindex.sigs is deprecated; import substrate.codemap.sigs",
    ),
    (
        "factory.codeindex.store",
        "factory.codeindex.store is deprecated; import substrate.codemap.store",
    ),
    (
        "factory.codeindex.cli",
        "factory.codeindex.cli is deprecated; import substrate.codemap.cli",
    ),
]


@pytest.mark.parametrize("module_name,expected_message", WHOLE_MODULE_SHIMS)
def test_whole_module_shim_warns_exactly_once_naming_substrate_codemap(
    module_name: str, expected_message: str
):
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", DeprecationWarning)
        if module_name == "factory.codeindex":
            _import_fresh(module_name)
        else:
            _import_fresh_leaf(module_name)

    deprecation = _deprecations(caught)
    assert len(deprecation) == 1
    assert str(deprecation[0].message) == expected_message


def test_substrate_codemap_package_imports_without_deprecation_warning():
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", DeprecationWarning)
        _import_fresh("substrate.codemap")

    assert _deprecations(caught) == []


def test_factory_codeindex_substrate_composition_adapter_imports_silently():
    # register_code_map_adapter/CODEMAP_RECIPE compose the substrate freshness
    # guard around substrate.codemap -- genuine factory-side glue (same
    # category as factory.config), not a moved module. Nothing public left
    # this file, so importing/using it must never warn.
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", DeprecationWarning)
        adapter = _import_fresh("factory.codeindex.substrate")

    assert _deprecations(caught) == []
    assert callable(adapter.register_code_map_adapter)


# -- 2. Legacy/canonical behavioral parity across the freshness fixtures. ---


def _old_and_new():
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        old = _import_fresh("factory.codeindex")
    new = importlib.import_module("substrate.codemap")
    return old, new


def test_source_change_rebuilds_index_identically_old_and_new(tmp_path):
    old, new = _old_and_new()
    old_root = _tree(tmp_path / "old")
    new_root = _tree(tmp_path / "new")
    files = ["src/mod.py"]

    old_first = old.ensure_fresh(old_root, files=files)
    new_first = new.ensure_fresh(new_root, files=files)
    assert old_first.fingerprint == new_first.fingerprint
    assert old_first.engine == new_first.engine

    for root in (old_root, new_root):
        (root / "src" / "mod.py").write_text(
            '"""Changed."""\n\ndef beta(value):\n    return value + 1\n', encoding="utf-8"
        )

    old_rebuilt = old.ensure_fresh(old_root, files=files)
    new_rebuilt = new.ensure_fresh(new_root, files=files)

    assert old_rebuilt.fingerprint != old_first.fingerprint
    assert new_rebuilt.fingerprint != new_first.fingerprint
    assert old_rebuilt.fingerprint == new_rebuilt.fingerprint
    old_names = {s["name"] for s in old.file_signatures(old_rebuilt, "src/mod.py") or []}
    new_names = {s["name"] for s in new.file_signatures(new_rebuilt, "src/mod.py") or []}
    assert old_names == new_names == {"beta"}


def test_parser_engine_change_rebuilds_identically_old_and_new(tmp_path):
    old, new = _old_and_new()
    old_root = _tree(tmp_path / "old")
    new_root = _tree(tmp_path / "new")
    files = ["src/mod.py"]

    # Simulate an index persisted under a stale engine label -- ensure_fresh
    # must rebuild toward whatever engine is actually available now, even
    # though the source content (and therefore fingerprint) did not change.
    old_stored = old.build_index(old_root, files=files, engine_note="stdlib-ast")
    old.save_index(old_stored, old_root)
    new_stored = new.build_index(new_root, files=files, engine_note="stdlib-ast")
    new.save_index(new_stored, new_root)

    old_fresh = old.ensure_fresh(old_root, files=files)
    new_fresh = new.ensure_fresh(new_root, files=files)

    assert old_fresh.fingerprint == old_stored.fingerprint  # code did not change
    assert new_fresh.fingerprint == new_stored.fingerprint
    assert old_fresh.engine == new_fresh.engine == old.preferred_engine() == new.preferred_engine()
    if old.preferred_engine() == "tree-sitter":
        # The stale "stdlib-ast" label forced a rebuild toward the available
        # engine identically on both sides.
        assert old_fresh.engine == "tree-sitter"
        assert new_fresh.engine == "tree-sitter"


def test_matching_fingerprint_and_engine_reuses_stored_index_identically(tmp_path):
    old, new = _old_and_new()
    old_root = _tree(tmp_path / "old")
    new_root = _tree(tmp_path / "new")
    files = ["src/mod.py"]

    old_first = old.ensure_fresh(old_root, files=files)
    old_second = old.ensure_fresh(old_root, files=files)
    new_first = new.ensure_fresh(new_root, files=files)
    new_second = new.ensure_fresh(new_root, files=files)

    # Same fingerprint AND engine -> reused, not rebuilt (identical timestamp).
    assert old_second.generated_at == old_first.generated_at
    assert new_second.generated_at == new_first.generated_at
    assert old_second.fingerprint == new_second.fingerprint == old_first.fingerprint

    old_loaded = old.load_latest(old_root)
    new_loaded = new.load_latest(new_root)
    assert old_loaded is not None and new_loaded is not None
    assert old_loaded.fingerprint == new_loaded.fingerprint
    assert set(old_loaded.files) == set(new_loaded.files) == {"src/mod.py"}


def test_no_files_returns_matching_empty_codeindex_old_and_new(tmp_path):
    old, new = _old_and_new()
    old_root = tmp_path / "old"
    new_root = tmp_path / "new"
    old_root.mkdir()
    new_root.mkdir()

    old_empty = old.ensure_fresh(old_root, files=[])
    new_empty = new.ensure_fresh(new_root, files=[])

    assert old_empty.fingerprint == new_empty.fingerprint == "no-files"
    assert old_empty.files == new_empty.files == {}
    # The empty-index short-circuit never touches disk.
    assert not (old_root / ".factory").exists()
    assert not (new_root / ".factory").exists()


def test_render_index_slice_matches_old_and_new(tmp_path):
    old, new = _old_and_new()
    old_root = _tree(tmp_path / "old")
    new_root = _tree(tmp_path / "new")
    files = ["src/mod.py"]

    old_index = old.build_index(old_root, files=files)
    new_index = new.build_index(new_root, files=files)

    assert old.render_index_slice(old_index, files) == new.render_index_slice(new_index, files)
