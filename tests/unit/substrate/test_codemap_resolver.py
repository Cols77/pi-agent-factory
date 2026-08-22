from __future__ import annotations

from pathlib import Path

import pytest

from factory.codeindex import ensure_fresh, load_latest
from factory.codeindex import substrate as codeindex_substrate
from substrate.artifacts import SnapshotRef
from substrate.freshness.guard import GuardSession, guarded_read
from substrate.freshness.recipes import (
    FingerprinterRegistry,
    ResolverRegistry,
    compile_recipes,
)

pytestmark = pytest.mark.unit


def _tree(root: Path) -> Path:
    (root / "src").mkdir()
    (root / "src" / "mod.py").write_text(
        '"""Module doc."""\n\ndef alpha(value):\n    return value\n',
        encoding="utf-8",
    )
    return root


def _write_token_capped_source(path: Path) -> None:
    path.write_text(
        "def capped():\n    pass\n# " + ("x" * 200_001) + "\n",
        encoding="utf-8",
    )


def _guarded(root: Path, files: list[str] | None = None):
    fingerprinters = FingerprinterRegistry()
    resolvers = ResolverRegistry()
    inputs = codeindex_substrate.register_code_map_adapter(
        fingerprinters,
        resolvers,
        root,
        files=files,
    )
    compiled = compile_recipes(
        [codeindex_substrate.CODEMAP_RECIPE],
        fingerprinters=fingerprinters,
        resolvers=resolvers,
    )
    return inputs, compiled


def test_stale_code_map_resolves_once_with_snapshot_lineage(tmp_path, monkeypatch):
    root = _tree(tmp_path)
    ensure_fresh(root, files=["src/mod.py"])
    candidate = codeindex_substrate.load_code_map_candidate(root, files=["src/mod.py"])
    assert isinstance(candidate, SnapshotRef)

    (root / "src" / "mod.py").write_text(
        '"""Changed."""\n\ndef beta(value):\n    return value + 1\n',
        encoding="utf-8",
    )
    inputs, compiled = _guarded(root, files=["src/mod.py"])
    calls = 0
    original_ensure_fresh = codeindex_substrate.ensure_fresh

    def counting_ensure_fresh(repo_root: Path, files: list[str] | None = None):
        nonlocal calls
        calls += 1
        return original_ensure_fresh(repo_root, files=files)

    monkeypatch.setattr(codeindex_substrate, "ensure_fresh", counting_ensure_fresh)
    session = GuardSession()

    first = guarded_read(
        session,
        compiled,
        codeindex_substrate.CODEMAP_RECIPE,
        candidate,
        [inputs],
    )
    second = guarded_read(
        session,
        compiled,
        codeindex_substrate.CODEMAP_RECIPE,
        candidate,
        [inputs],
    )

    assert first is second
    assert first.stale is not None
    assert first.snapshot is not None
    assert first.current
    assert calls == 1
    assert first.snapshot.kind == "code-map"
    assert first.snapshot.ref == f"snapshot:code-map:{first.snapshot.fingerprint}"
    assert first.snapshot.fingerprint == first.stale.actual_fingerprint
    assert first.snapshot.supersedes == candidate.ref
    assert first.snapshot.producer.name == "factory.codeindex"
    assert first.snapshot.producer.version == 1
    assert first.snapshot.producer.engine in ("tree-sitter", "stdlib-ast")
    assert {item.ref.split(":", 1)[0] for item in first.snapshot.inputs} == {
        "source-set",
        "parser-engine",
    }
    assert not hasattr(first.snapshot, "files")
    persisted = load_latest(root)
    assert persisted is not None
    assert "src/mod.py" in persisted.files


def test_matching_code_map_is_current_without_resolution(tmp_path, monkeypatch):
    root = _tree(tmp_path)
    ensure_fresh(root, files=["src/mod.py"])
    candidate = codeindex_substrate.load_code_map_candidate(root, files=["src/mod.py"])
    inputs, compiled = _guarded(root, files=["src/mod.py"])

    def unexpected_ensure_fresh(repo_root: Path, files: list[str] | None = None):
        raise AssertionError("a matching code map must not resolve")

    monkeypatch.setattr(codeindex_substrate, "ensure_fresh", unexpected_ensure_fresh)
    session = GuardSession()
    result = guarded_read(
        session,
        compiled,
        codeindex_substrate.CODEMAP_RECIPE,
        candidate,
        [inputs],
    )

    assert result.current
    assert result.snapshot is candidate
    assert result.stale is None


def test_code_map_fingerprinter_includes_parser_engine(tmp_path, monkeypatch):
    root = _tree(tmp_path)
    inputs = codeindex_substrate.code_map_inputs(root, files=["src/mod.py"])

    monkeypatch.setattr(
        codeindex_substrate,
        "extract_signatures",
        lambda path, source: ("stdlib-ast", []),
    )
    stdlib_fingerprint = codeindex_substrate.code_map_fingerprinter(inputs)
    monkeypatch.setattr(
        codeindex_substrate,
        "extract_signatures",
        lambda path, source: ("tree-sitter", []),
    )
    tree_sitter_fingerprint = codeindex_substrate.code_map_fingerprinter(inputs)

    assert stdlib_fingerprint != tree_sitter_fingerprint


def test_token_capped_discovered_file_candidate_is_current_after_resolution(
    tmp_path, monkeypatch
):
    root = _tree(tmp_path)
    capped = root / "src" / "oversized.py"
    _write_token_capped_source(capped)

    persisted = ensure_fresh(root)
    assert "src/oversized.py" not in persisted.files
    candidate = codeindex_substrate.load_code_map_candidate(root)
    inputs, compiled = _guarded(root)
    (root / "src" / "mod.py").write_text(
        '"""Changed."""\n\ndef beta(value):\n    return value + 1\n',
        encoding="utf-8",
    )

    calls = 0
    original_ensure_fresh = codeindex_substrate.ensure_fresh

    def counting_ensure_fresh(repo_root: Path, files: list[str] | None = None):
        nonlocal calls
        calls += 1
        return original_ensure_fresh(repo_root, files=files)

    monkeypatch.setattr(codeindex_substrate, "ensure_fresh", counting_ensure_fresh)
    result = guarded_read(
        GuardSession(),
        compiled,
        codeindex_substrate.CODEMAP_RECIPE,
        candidate,
        [inputs],
    )

    assert result.current
    assert result.stale is not None
    assert result.snapshot is not None
    assert result.snapshot.fingerprint == result.stale.actual_fingerprint
    assert result.snapshot.supersedes == candidate.ref
    assert calls == 1
    refreshed = load_latest(root)
    assert refreshed is not None
    assert "src/oversized.py" not in refreshed.files

    fresh_candidate = codeindex_substrate.load_code_map_candidate(root)

    def unexpected_ensure_fresh(repo_root: Path, files: list[str] | None = None):
        raise AssertionError("a fresh candidate must not resolve")

    monkeypatch.setattr(codeindex_substrate, "ensure_fresh", unexpected_ensure_fresh)
    fresh_result = guarded_read(
        GuardSession(),
        compiled,
        codeindex_substrate.CODEMAP_RECIPE,
        fresh_candidate,
        [inputs],
    )

    assert fresh_result.current
    assert fresh_result.snapshot is fresh_candidate
    assert fresh_result.stale is None


def test_engine_fingerprint_matches_persisted_engine_for_mixed_source_set(
    tmp_path, monkeypatch
):
    root = _tree(tmp_path)
    (root / "src" / "notes.txt").write_text("not parsed\n", encoding="utf-8")
    files = ["src/notes.txt", "src/mod.py"]
    persisted = ensure_fresh(root, files=files)
    assert persisted.engine == "stdlib-ast"
    assert set(persisted.files) == set(files)

    monkeypatch.setattr(codeindex_substrate, "preferred_engine", lambda: "tree-sitter")
    candidate = codeindex_substrate.load_code_map_candidate(root, files=files)
    inputs, compiled = _guarded(root, files=files)

    def unexpected_ensure_fresh(repo_root: Path, files: list[str] | None = None):
        raise AssertionError("matching persisted parser engine must not resolve")

    monkeypatch.setattr(codeindex_substrate, "ensure_fresh", unexpected_ensure_fresh)
    result = guarded_read(
        GuardSession(),
        compiled,
        codeindex_substrate.CODEMAP_RECIPE,
        candidate,
        [inputs],
    )

    assert result.current
    assert result.snapshot is candidate
    assert result.stale is None


def test_removed_sources_resolve_old_map_to_no_files_snapshot(tmp_path):
    root = _tree(tmp_path)
    ensure_fresh(root)
    candidate = codeindex_substrate.load_code_map_candidate(root)
    (root / "src" / "mod.py").unlink()

    inputs, compiled = _guarded(root)
    result = guarded_read(
        GuardSession(),
        compiled,
        codeindex_substrate.CODEMAP_RECIPE,
        candidate,
        [inputs],
    )

    assert result.current
    assert result.stale is not None
    assert result.snapshot is not None
    assert result.snapshot.fingerprint == "no-files"
    assert result.snapshot.supersedes == candidate.ref
    assert result.snapshot.ref == "snapshot:code-map:no-files"


def test_no_files_candidate_is_current_without_new_persistence(tmp_path, monkeypatch):
    candidate = codeindex_substrate.load_code_map_candidate(tmp_path)
    inputs, compiled = _guarded(tmp_path)

    def unexpected_ensure_fresh(repo_root: Path, files: list[str] | None = None):
        raise AssertionError("an empty source set must not resolve")

    monkeypatch.setattr(codeindex_substrate, "ensure_fresh", unexpected_ensure_fresh)
    result = guarded_read(
        GuardSession(),
        compiled,
        codeindex_substrate.CODEMAP_RECIPE,
        candidate,
        [inputs],
    )

    assert result.current
    assert result.snapshot is candidate
    assert candidate.fingerprint == "no-files"
    assert not (tmp_path / ".factory" / "code-index").exists()
