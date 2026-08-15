from __future__ import annotations

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


def test_cli_ensure_writes_latest(tmp_path):
    root = _tree(tmp_path)
    assert main(["--root", str(root), "--ensure"]) == 0
    assert (root / ".factory" / "code-index" / "latest.json").exists()


def test_cli_writes_latest(tmp_path):
    root = _tree(tmp_path)
    code = main(["--root", str(root)])
    assert code == 0
    assert (root / ".factory" / "code-index" / "latest.json").exists()
