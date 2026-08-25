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

Task 2 adds a third section, sharing this file's name because the plan's own
Task 2 Step 3 test command names this exact path: the structured import-edge
layer, substrate.codemap.imports (ImportEdge/ImportClosure/build_import_
closure), alongside the relocated compute_overlap/OverlapResult/
transitive_imports (moved verbatim from factory.coverage.imports, which is
now itself a warn-and-re-export shim, matching the pattern above). See
tests/unit/coverage/test_imports.py for the original, still-passing
compute_overlap/transitive_imports behavioral tests exercised through the
shim.
"""
from __future__ import annotations

import importlib
import sys
import warnings
from pathlib import Path

import pytest

from substrate.codemap.imports import (
    ImportClosure,
    ImportEdge,
    OverlapResult,
    ReachabilityResult,
    _load_edges,
    build_import_closure,
    compute_overlap,
    reachable_symbols,
)

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


# -- 3. Structured import-edge layer (substrate.codemap.imports), Task 2. ---


def _import_tree(root: Path) -> None:
    """Same shape as tests/unit/coverage/test_imports.py's _tree fixture, so
    the parity assertions below compare like for like."""
    (root / "src").mkdir(parents=True)
    (root / "tests").mkdir()
    (root / "src" / "drone").mkdir()
    (root / "src" / "drone" / "__init__.py").write_text("")
    (root / "src" / "drone" / "priority_filter.py").write_text(
        "def preempt():\n    return True\n"
    )
    (root / "tests" / "test_preempt.py").write_text(
        "from drone.priority_filter import preempt\n\ndef test_preempt():\n"
        "    assert preempt()\n"
    )


def _norm(p: Path) -> str:
    return p.as_posix().lstrip("./")


def _closure_overlap(root: Path, selection: str, changed_files: list[str]) -> tuple[str, ...]:
    """Convert a structured ImportClosure into the same shape as
    OverlapResult.overlap, for parity-checking against compute_overlap.
    build_import_closure includes the root itself in `files`;
    compute_overlap/transitive_imports never do, so the root is excluded
    before intersecting with changed_files."""
    if "::" in selection:
        selection = selection.split("::", 1)[0]
    closure = build_import_closure(root, [selection])
    changed = {_norm(Path(c)) for c in changed_files}
    reached = set(closure.files) - {selection}
    return tuple(sorted(reached & changed))


# -- 3a. build_import_closure: resolved / unresolved / unsupported status. --


def test_build_import_closure_resolved_includes_roots_and_reached(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_text("import b\n")
    (tmp_path / "src" / "b.py").write_text("X = 1\n")

    result = build_import_closure(tmp_path, ["src/a.py"])

    assert result.status == "resolved"
    assert result.files == ("src/a.py", "src/b.py")
    assert result.diagnostics == ()


def test_build_import_closure_missing_root_is_unresolved_selection_missing(tmp_path: Path) -> None:
    result = build_import_closure(tmp_path, ["src/does_not_exist.py"])

    assert result.status == "unresolved"
    assert result.files == ()
    assert result.diagnostics == ("selection missing: src/does_not_exist.py",)


def test_build_import_closure_missing_import_fixture_is_unresolved(tmp_path: Path) -> None:
    # A genuinely external, unresolvable import -- e.g. a third-party package
    # not vendored into the project.
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_text("import numpy\n")

    result = build_import_closure(tmp_path, ["src/a.py"])

    assert result.status == "unresolved"
    assert result.files == ("src/a.py",)
    assert any("numpy" in d for d in result.diagnostics)


def test_build_import_closure_renamed_binding_fixture_is_unresolved(tmp_path: Path) -> None:
    # An internal project import left pointing at a module that was since
    # renamed -- a dangling reference, distinct from a missing external
    # package, but resolution-wise it is the same "unresolved" outcome.
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "new_name.py").write_text("VALUE = 1\n")
    (tmp_path / "src" / "a.py").write_text("from src.old_name import VALUE\n")

    result = build_import_closure(tmp_path, ["src/a.py"])

    assert result.status == "unresolved"
    assert any("old_name" in d for d in result.diagnostics)
    assert "src/new_name.py" not in result.files  # nothing links to it


def test_build_import_closure_non_python_root_is_unsupported(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "widget.ts").write_text("import {x} from './y';\n")

    result = build_import_closure(tmp_path, ["src/widget.ts"])

    # Not "resolved" and not folded into "unresolved" -- a parser existing
    # elsewhere in the codebase (tree-sitter, for signatures) must not make
    # this layer claim a transitive closure it never walked.
    assert result.status == "unsupported"
    assert result.files == ("src/widget.ts",)
    assert any("unsupported source type" in d for d in result.diagnostics)


def test_build_import_closure_unsupported_root_takes_precedence_over_missing(
    tmp_path: Path,
) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "widget.ts").write_text("export const x = 1;\n")

    result = build_import_closure(tmp_path, ["src/widget.ts", "src/does_not_exist.py"])

    assert result.status == "unsupported"
    assert "selection missing: src/does_not_exist.py" in result.diagnostics
    assert "unsupported source type: src/widget.ts" in result.diagnostics


# -- 3b. compute_overlap: relocated, but the diagnostic split is unchanged. -


def test_compute_overlap_distinguishes_selection_missing_from_no_overlap(tmp_path: Path) -> None:
    _import_tree(tmp_path)

    missing = compute_overlap(
        tmp_path, "tests/does_not_exist.py", ["src/drone/priority_filter.py"]
    )
    assert missing.test_source is None  # the selection itself doesn't resolve

    no_overlap = compute_overlap(tmp_path, "tests/test_preempt.py", ["unrelated/file.py"])
    assert no_overlap.test_source is not None  # the selection resolved fine...
    assert no_overlap.overlap == ()  # ...it just doesn't touch the changed files
    assert not no_overlap.ok
    assert not missing.ok


# -- 3c. Parity: the new structured layer must not change old overlap answers.


@pytest.mark.parametrize(
    "selection,changed_files",
    [
        ("tests/test_preempt.py", ["src/drone/priority_filter.py"]),
        ("tests/test_preempt.py::test_preempt", ["src/drone/priority_filter.py"]),
        ("tests/test_preempt.py", ["src/drone/priority_filter.py", "tests/test_preempt.py"]),
        ("tests/test_preempt.py", ["unrelated/file.py"]),
    ],
)
def test_converted_codemap_overlap_matches_factory_coverage_imports_exactly(
    tmp_path: Path, selection: str, changed_files: list[str]
) -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        from factory.coverage.imports import compute_overlap as legacy_compute_overlap

    _import_tree(tmp_path)
    legacy = legacy_compute_overlap(tmp_path, selection, changed_files)
    converted = _closure_overlap(tmp_path, selection, changed_files)

    assert converted == legacy.overlap


def test_converted_codemap_overlap_matches_factory_coverage_imports_for_relative_imports(
    tmp_path: Path,
) -> None:
    """Parity for tests/unit/coverage/test_imports.py::test_relative_import_resolution's
    fixture (`from . import b`, level > 0) -- also the only exercise of
    kind="relative" edge classification via the parity path."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        from factory.coverage.imports import compute_overlap as legacy_compute_overlap

    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "__init__.py").write_text("")
    (tmp_path / "pkg" / "a.py").write_text("from . import b\n")
    (tmp_path / "pkg" / "b.py").write_text("X = 1\n")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_rel.py").write_text("from pkg.a import b\n")

    selection = "tests/test_rel.py"
    changed_files = ["pkg/a.py", "pkg/b.py"]

    legacy = legacy_compute_overlap(tmp_path, selection, changed_files)
    converted = _closure_overlap(tmp_path, selection, changed_files)

    assert converted == legacy.overlap == ("pkg/a.py", "pkg/b.py")


def test_converted_codemap_overlap_matches_factory_coverage_imports_for_no_imports(
    tmp_path: Path,
) -> None:
    """Parity for test_compute_overlap_false_when_imports_nothing's fixture
    (a test file with no imports at all)."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        from factory.coverage.imports import compute_overlap as legacy_compute_overlap

    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_empty.py").write_text(
        "def test_nothing():\n    assert True\n"
    )

    selection = "tests/test_empty.py"
    changed_files = ["src/drone/priority_filter.py"]

    legacy = legacy_compute_overlap(tmp_path, selection, changed_files)
    converted = _closure_overlap(tmp_path, selection, changed_files)

    assert converted == legacy.overlap == ()


def test_converted_codemap_overlap_matches_factory_coverage_imports_for_external_unresolved(
    tmp_path: Path,
) -> None:
    """Parity for test_unresolved_imports_are_honest's fixture (an import
    of a genuinely external, unresolvable package)."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        from factory.coverage.imports import compute_overlap as legacy_compute_overlap

    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_extern.py").write_text(
        "import numpy\n\ndef test():\n    pass\n"
    )

    selection = "tests/test_extern.py"
    changed_files = ["x.py"]

    legacy = legacy_compute_overlap(tmp_path, selection, changed_files)
    converted = _closure_overlap(tmp_path, selection, changed_files)

    assert converted == legacy.overlap == ()
    assert legacy.unresolved == ("numpy",)  # still honest through the shim


def test_build_import_closure_records_relative_edge_kind(tmp_path: Path) -> None:
    """Direct (non-parity) coverage of kind="relative" edge classification,
    complementing the parity test above."""
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "__init__.py").write_text("")
    (tmp_path / "pkg" / "a.py").write_text("from . import b\n")
    (tmp_path / "pkg" / "b.py").write_text("X = 1\n")

    result = build_import_closure(tmp_path, ["pkg/a.py"])

    assert result.status == "resolved"
    edges = _load_edges(tmp_path, list(result.files))
    assert edges is not None
    assert any(
        e.source == "pkg/a.py" and e.target == "pkg/b.py" and e.kind == "relative"
        for e in edges
    )


# -- 3d. Edge storage: beside the fingerprinted index, with a tolerant reader.


def test_build_import_closure_persists_edges_beside_fingerprinted_index(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_text("import b\n")
    (tmp_path / "src" / "b.py").write_text("X = 1\n")

    result = build_import_closure(tmp_path, ["src/a.py"])

    index_dir = tmp_path / ".factory" / "code-index"
    assert (index_dir / "imports-latest.json").exists()
    edge_files = list(index_dir.glob("*.imports.json"))
    assert len(edge_files) == 1

    loaded = _load_edges(tmp_path, list(result.files))
    assert loaded is not None
    assert any(e.source == "src/a.py" and e.target == "src/b.py" for e in loaded)


def test_load_edges_is_backward_compatible_with_pre_edge_index_dirs(tmp_path: Path) -> None:
    # Simulate an index directory written before edge storage existed: the
    # code-index dir exists (from substrate.codemap.build/store) but has no
    # *.imports.json sibling yet.
    index_dir = tmp_path / ".factory" / "code-index"
    index_dir.mkdir(parents=True)
    (index_dir / "latest.json").write_text("{}", encoding="utf-8")

    loaded = _load_edges(tmp_path, ["src/a.py", "src/b.py"])
    assert loaded is None  # missing edges file -> the reader tolerates it

    # build_import_closure still works fine in that same, pre-existing dir.
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_text("import b\n")
    (tmp_path / "src" / "b.py").write_text("X = 1\n")
    result = build_import_closure(tmp_path, ["src/a.py"])

    assert result.status == "resolved"
    assert result.files == ("src/a.py", "src/b.py")


# -- 3e. factory.coverage.imports is now a warn-and-re-export shim. ---------


def test_factory_coverage_imports_shim_warns_naming_substrate_codemap_imports() -> None:
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", DeprecationWarning)
        _import_fresh("factory.coverage.imports")

    deprecation = _deprecations(caught)
    assert len(deprecation) == 1
    assert str(deprecation[0].message) == (
        "factory.coverage.imports is deprecated; import substrate.codemap.imports"
    )


def test_factory_coverage_imports_reexports_edge_and_overlap_types() -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        shim = _import_fresh("factory.coverage.imports")

    assert shim.OverlapResult is OverlapResult
    assert shim.ImportEdge is ImportEdge
    assert shim.ImportClosure is ImportClosure
    assert shim.build_import_closure is build_import_closure
    assert shim.compute_overlap is compute_overlap


# -- 4. Canonical-qualified symbol reachability (Task 4). -------------------


def _symbol_tree(root: Path) -> None:
    """The 'moved symbol' fixture for Task 4.

    `factory.function` used to live in the edited file, then MOVED into
    `src/factory/module.py`. The edited file `client.py` reaches it through an
    import, so its canonical qualified name `factory.module.function` is still
    reachable from the changed file across the codemap import graph. KB scope
    lists that canonical name -- a file-glob on the edited file alone would
    never find it.
    """
    (root / "src" / "factory").mkdir(parents=True)
    (root / "src" / "factory" / "__init__.py").write_text("")
    (root / "src" / "factory" / "module.py").write_text(
        '"""The moved-to home of the symbol."""\n'
        "def function(value=1):\n"
        "    return value + 1\n"
    )
    (root / "src" / "factory" / "client.py").write_text(
        "from factory.module import function\n\n"
        "def call():\n"
        "    return function(2)\n"
    )


def _fresh_symbol_snapshot(root: Path) -> None:
    from substrate.codemap.store import ensure_fresh

    ensure_fresh(
        root,
        files=[
            "src/factory/__init__.py",
            "src/factory/module.py",
            "src/factory/client.py",
        ],
    )


def test_reachable_symbols_resolved_fields_the_moved_symbol(tmp_path: Path) -> None:
    _symbol_tree(tmp_path)
    _fresh_symbol_snapshot(tmp_path)

    result = reachable_symbols(tmp_path, ["src/factory/client.py"])

    assert result.status == "resolved"
    assert isinstance(result, ReachabilityResult)
    assert "factory.module.function" in result.symbols
    assert result.snapshot_ref is not None
    assert result.diagnostics == ()


def test_reachable_symbols_missing_snapshot_is_missing_with_diagnostic(tmp_path: Path) -> None:
    _symbol_tree(tmp_path)  # code exists, but no codemap snapshot has ever been built

    result = reachable_symbols(tmp_path, ["src/factory/client.py"])

    assert result.status == "missing"
    assert result.symbols == ()
    assert result.snapshot_ref is None
    assert any("missing" in d.lower() for d in result.diagnostics)


def test_reachable_symbols_stale_snapshot_is_stale_with_diagnostic(tmp_path: Path) -> None:
    _symbol_tree(tmp_path)
    _fresh_symbol_snapshot(tmp_path)
    # Edit a source file after the snapshot was built -> fingerprint mismatch.
    (tmp_path / "src" / "factory" / "module.py").write_text(
        "def renamed():\n    return 9\n"
    )

    result = reachable_symbols(tmp_path, ["src/factory/client.py"])

    assert result.status == "stale"
    assert result.symbols == ()  # never claim a symbol hit from a stale snapshot
    assert result.snapshot_ref is not None
    assert any("stale" in d.lower() for d in result.diagnostics)


def test_reachable_symbols_nonpython_changed_root_is_unsupported(tmp_path: Path) -> None:
    _symbol_tree(tmp_path)
    _fresh_symbol_snapshot(tmp_path)
    (tmp_path / "src" / "widget.ts").write_text("export const bone = 1;\n")

    result = reachable_symbols(tmp_path, ["src/widget.ts"])

    assert result.status == "unsupported"
    assert result.symbols == ()
    assert any("unsupported" in d.lower() for d in result.diagnostics)


def test_reachable_symbols_empty_changed_files_is_resolved_with_no_symbols(tmp_path: Path) -> None:
    _symbol_tree(tmp_path)
    _fresh_symbol_snapshot(tmp_path)

    result = reachable_symbols(tmp_path, [])

    assert result.status == "resolved"
    assert result.symbols == ()

