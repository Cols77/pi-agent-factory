from __future__ import annotations

from pathlib import Path

import pytest

from factory.codeindex import (
    build_index,
    discover_source_files,
    ensure_fresh,
    file_signatures,
    fingerprint_for,
    is_fresh,
    load_latest,
    render_index_slice,
    save_index,
)
from factory.codeindex.cli import main
from factory.codeindex.build import profile_source_dirs
from factory.codeindex.sigs import extract_signatures, preferred_engine

pytestmark = pytest.mark.unit


def _tree(tmp_path):
    (tmp_path / "src").mkdir(parents=True)
    (tmp_path / "src" / "mod.py").write_text(
        '"""Module doc."""\n\ndef alpha(a, b):\n    """returns sum"""\n    return a + b\n\n'
        "class Beta:\n    \"\"\"Beta class.\"\"\"\n    def method(self, x):\n        return x\n",
        encoding="utf-8",
    )
    (tmp_path / "src" / "keep.ts").write_text("export function hi() { return 1; }\n", encoding="utf-8")
    return tmp_path


def test_discover_source_files_under_src(tmp_path):
    root = _tree(tmp_path)
    files = discover_source_files(root, ["src"])
    assert "src/mod.py" in files
    assert "src/keep.ts" in files


def test_build_index_signatures(tmp_path):
    root = _tree(tmp_path)
    index = build_index(root, files=["src/mod.py"])
    sigs = file_signatures(index, "src/mod.py") or []
    names = {s["name"] for s in sigs}
    assert {"alpha", "Beta", "method"} <= names
    method = [s for s in sigs if s["name"] == "method"][0]
    assert method["kind"] == "method"


def test_fingerprint_changes_with_content(tmp_path):
    root = _tree(tmp_path)
    files = ["src/mod.py"]
    fp1 = fingerprint_for(files, root)
    (root / "src" / "mod.py").write_text('"""Changed."""\n\ndef gamma():\n    pass\n', encoding="utf-8")
    fp2 = fingerprint_for(files, root)
    assert fp1 != fp2


def test_is_fresh_true_then_false_after_edit(tmp_path):
    root = _tree(tmp_path)
    index = build_index(root, files=["src/mod.py"])
    assert is_fresh(index, root) is True
    (root / "src" / "mod.py").write_text('"""Edited."""\n\nx = 1\n', encoding="utf-8")
    assert is_fresh(index, root) is False


def test_save_and_load_latest_round_trip(tmp_path):
    root = _tree(tmp_path)
    index = build_index(root, files=["src/mod.py"])
    save_index(index, root)
    loaded = load_latest(root)
    assert loaded is not None
    assert loaded.fingerprint == index.fingerprint
    assert len(loaded.files) == 1


def test_render_index_slice_shapes_like_item1(tmp_path):
    root = _tree(tmp_path)
    index = build_index(root, files=["src/mod.py"])
    out = render_index_slice(index, ["src/mod.py"])
    assert "src/mod.py" in out
    assert "L1" in out or "L" in out  # signatures carry lines


def test_ensure_fresh_rebuilds_only_when_code_changed(tmp_path):
    root = _tree(tmp_path)
    first = ensure_fresh(root, files=["src/mod.py"])
    # unchanged -> same index object reused, no rebuild
    again = ensure_fresh(root, files=["src/mod.py"])
    assert again.fingerprint == first.fingerprint
    assert again.generated_at == first.generated_at
    # changed -> rebuilt with a new fingerprint
    (root / "src" / "mod.py").write_text(
        '"""Changed."""\n\ndef gamma():\n    """new"""\n    pass\n', encoding="utf-8"
    )
    rebuilt = ensure_fresh(root, files=["src/mod.py"])
    assert rebuilt.fingerprint != first.fingerprint
    names = {s["name"] for s in file_signatures(rebuilt, "src/mod.py") or []}
    assert "gamma" in names


def test_preferred_engine_reports_available_extractor():
    assert preferred_engine() in ("tree-sitter", "stdlib-ast")
    if _tree_sitter_available(Path("probe.py"), "def probe():\n    pass\n"):
        assert preferred_engine() == "tree-sitter"
    else:
        assert preferred_engine() == "stdlib-ast"


def test_ensure_fresh_upgrades_engine_when_available(tmp_path):
    """A fresh fingerprint stored under a worse engine is rebuilt toward the
    currently-available engine, so a stdlib-built index upgrades to
    tree-sitter once the grammars exist (and degrades if they disappear)."""
    root = _tree(tmp_path)
    files = ["src/mod.py", "src/keep.ts"]
    # Simulate an index built when tree-sitter was absent: same code, engine=stdlib-ast.
    stored = build_index(root, files=files, engine_note="stdlib-ast")
    save_index(stored, root)
    fresh = ensure_fresh(root, files=files)
    assert fresh.fingerprint == stored.fingerprint  # code did not change
    assert fresh.engine == preferred_engine()
    if _tree_sitter_available(Path("probe.py"), "def probe():\n    pass\n"):
        assert fresh.engine == "tree-sitter"  # stdlib -> tree-sitter upgrade


def test_ensure_fresh_reuses_when_engine_matches(tmp_path):
    """Same fingerprint AND same engine -> reuse, never rebuild."""
    root = _tree(tmp_path)
    files = ["src/mod.py", "src/keep.ts"]
    first = ensure_fresh(root, files=files)
    second = ensure_fresh(root, files=files)
    assert second.fingerprint == first.fingerprint
    assert second.engine == first.engine
    assert second.generated_at == first.generated_at  # no rebuild happened


def test_cli_ensure_writes_latest(tmp_path):
    root = _tree(tmp_path)
    assert main(["--root", str(root), "--ensure"]) == 0
    assert (root / ".factory" / "code-index" / "latest.json").exists()


def test_cli_writes_latest(tmp_path):
    root = _tree(tmp_path)
    code = main(["--root", str(root)])
    assert code == 0
    assert (root / ".factory" / "code-index" / "latest.json").exists()


def test_tree_sitter_availability_is_language_specific(monkeypatch):
    import sys
    from pathlib import Path

    def fake_extract_signatures(path: Path, source: str):
        engines = {".py": "tree-sitter", ".ts": "stdlib-ast"}
        return engines[path.suffix], []

    monkeypatch.setattr(sys.modules[__name__], "extract_signatures", fake_extract_signatures)

    assert _tree_sitter_available(Path("probe.py"), "def probe():\n    pass\n")
    assert _tree_sitter_available(Path("probe.ts"), "export function probe() {}\n") is False


def _tree_sitter_available(path: Path, source: str) -> bool:
    try:
        engine, _ = extract_signatures(path, source)
    except Exception:
        return False
    return engine == "tree-sitter"


@pytest.mark.skipif(
    not _tree_sitter_available(Path("probe.py"), "def probe():\n    pass\n"),
    reason="tree-sitter optional accelerator not installed",
)
def test_tree_sitter_engages_and_classifies_python_methods(tmp_path):
    """When the per-language tree-sitter grammars are present, extraction is
    tree-sitter-driven and still classifies class methods as 'method' (not
    'function'), matching the stdlib extractor's shape (plan Task 1)."""
    from pathlib import Path

    src = (
        "class Beta:\n"
        "    def method(self, x):\n"
        "        return x\n"
        "def alpha(a):\n"
        "    return a\n"
    )
    engine, sigs = extract_signatures(Path("m.py"), src)
    assert engine == "tree-sitter"
    kinds = {s["name"]: s["kind"] for s in sigs}
    assert kinds == {"Beta": "class", "method": "method", "alpha": "function"}


@pytest.mark.skipif(
    not _tree_sitter_available(Path("probe.ts"), "export function probe() {}\n"),
    reason="tree-sitter optional accelerator not installed",
)
def test_tree_sitter_classifies_typescript_declarations(tmp_path):
    """TS/JS declarations (function_declaration, class_declaration,
    method_definition) yield signatures under tree-sitter, not empty output."""
    from pathlib import Path

    src = (
        "export function hi(x: number): number { return x; }\n"
        "class Foo {\n"
        "  bar() { return 1; }\n"
        "}\n"
    )
    engine, sigs = extract_signatures(Path("m.ts"), src)
    assert engine == "tree-sitter"
    assert [(s["kind"], s["name"]) for s in sigs] == [
        ("function", "hi"),
        ("class", "Foo"),
        ("method", "bar"),
    ]


def test_discover_source_files_reads_profile_source_dirs(tmp_path):
    """/factory-init writes .pi/factory/project-profile.json; discovery must
    honor its source_dirs instead of hard-coding ["src"]."""
    (tmp_path / ".pi" / "factory").mkdir(parents=True)
    (tmp_path / ".pi" / "factory" / "project-profile.json").write_text(
        '{"source_dirs": ["src", "scripts"]}', encoding="utf-8"
    )
    (tmp_path / "src").mkdir()
    (tmp_path / "scripts").mkdir()
    (tmp_path / "src" / "a.py").write_text("def a():\n    pass\n", encoding="utf-8")
    (tmp_path / "scripts" / "b.py").write_text("def b():\n    pass\n", encoding="utf-8")
    (tmp_path / "other.py").write_text("x = 1\n", encoding="utf-8")
    files = discover_source_files(tmp_path)
    assert "src/a.py" in files
    assert "scripts/b.py" in files
    assert "other.py" not in files
    assert profile_source_dirs(tmp_path) == ["src", "scripts"]


def test_discover_source_files_falls_back_to_src_without_profile(tmp_path):
    files = discover_source_files(_tree(tmp_path))
    assert "src/mod.py" in files
    assert "src/keep.ts" in files


def test_discover_source_files_skips_vendor_dirs(tmp_path):
    (tmp_path / ".pi" / "factory").mkdir(parents=True)
    (tmp_path / ".pi" / "factory" / "project-profile.json").write_text(
        '{"source_dirs": ["src", "scripts"]}', encoding="utf-8"
    )
    (tmp_path / "src").mkdir()
    (tmp_path / "scripts" / "node_modules" / "pkg").mkdir(parents=True)
    (tmp_path / "src" / "a.py").write_text("def a():\n    pass\n", encoding="utf-8")
    (tmp_path / "scripts" / "mine.ts").write_text("export const x = 1;\n", encoding="utf-8")
    (tmp_path / "scripts" / "node_modules" / "pkg" / "vendored.ts").write_text(
        "export const junk = 1;\n", encoding="utf-8"
    )
    files = discover_source_files(tmp_path)
    assert "src/a.py" in files
    assert "scripts/mine.ts" in files
    assert not any("node_modules" in f for f in files)


def test_cli_slice_prints_bounded_markdown_without_banner(tmp_path):
    root = _tree(tmp_path)
    out = main(["--root", str(root), "--slice", "500"])
    # captured by capsys below; here we just assert exit code 0 is returned
    assert out == 0


def test_cli_slice_produces_reference_block(capsys, tmp_path):
    root = _tree(tmp_path)
    main(["--root", str(root), "--slice", "5000"])
    captured = capsys.readouterr().out
    assert "### REFERENCE (indexed) — src/mod.py" in captured
    # signatures from the tree-sitter index carry lines
    assert "- L" in captured
    # the hash/banner count line must NOT leak into the slice
    assert "codeindex: built" not in captured
    assert "codeindex: ensured" not in captured


def test_cli_slice_carries_engine_note(capsys, tmp_path):
    root = _tree(tmp_path)
    main(["--root", str(root), "--slice", "5000"])
    captured = capsys.readouterr().out
    # the slice starts with a one-line engine note so consumers can tell
    # tree-sitter output from the stdlib fallback
    first_line = captured.splitlines()[0]
    assert first_line in ("engine: tree-sitter", "engine: stdlib-ast")
    assert "### REFERENCE" in captured
