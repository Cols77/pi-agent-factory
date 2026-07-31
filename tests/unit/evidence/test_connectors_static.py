from __future__ import annotations

import pytest

from factory.evidence.types import EvidenceContext
from factory.evidence.connectors import (
    FilesExist, FileContains, SymbolDefined, AnchorResolves, symbol_in_file,
)

pytestmark = pytest.mark.unit


def _ctx(tmp_path):
    return EvidenceContext(repo_root=tmp_path)


def test_files_exist_pass_and_fail(tmp_path):
    (tmp_path / "a.py").write_text("x", encoding="utf-8")
    assert FilesExist().evaluate({"paths": ["a.py"]}, _ctx(tmp_path)).passed is True
    res = FilesExist().evaluate({"paths": ["a.py", "missing.py"]}, _ctx(tmp_path))
    assert res.passed is False and "missing.py" in res.evidence


def test_file_contains_literal_and_regex(tmp_path):
    (tmp_path / "f.txt").write_text("hello world 42", encoding="utf-8")
    assert FileContains().evaluate({"path": "f.txt", "pattern": "world", "mode": "literal"}, _ctx(tmp_path)).passed
    assert FileContains().evaluate({"path": "f.txt", "pattern": r"\d+", "mode": "regex"}, _ctx(tmp_path)).passed
    assert not FileContains().evaluate({"path": "f.txt", "pattern": "nope", "mode": "literal"}, _ctx(tmp_path)).passed


def test_file_contains_missing_file_fails(tmp_path):
    res = FileContains().evaluate({"path": "no.txt", "pattern": "x", "mode": "literal"}, _ctx(tmp_path))
    assert res.passed is False and "not found" in res.evidence


def test_symbol_in_file_python(tmp_path):
    (tmp_path / "m.py").write_text("class Foo:\n    pass\n\ndef bar():\n    return 1\n", encoding="utf-8")
    assert symbol_in_file(tmp_path / "m.py", "Foo") is True
    assert symbol_in_file(tmp_path / "m.py", "bar") is True
    assert symbol_in_file(tmp_path / "m.py", "Baz") is False


def test_symbol_in_file_markdown_heading(tmp_path):
    (tmp_path / "d.md").write_text("# Title\n\n## Design Notes\n\ntext\n", encoding="utf-8")
    assert symbol_in_file(tmp_path / "d.md", "Design Notes") is True
    assert symbol_in_file(tmp_path / "d.md", "Absent") is False


def test_symbol_defined_connector(tmp_path):
    (tmp_path / "m.py").write_text("def bar():\n    return 1\n", encoding="utf-8")
    assert SymbolDefined().evaluate({"path": "m.py", "symbol": "bar"}, _ctx(tmp_path)).passed
    assert not SymbolDefined().evaluate({"path": "m.py", "symbol": "nope"}, _ctx(tmp_path)).passed


def test_anchor_resolves(tmp_path):
    (tmp_path / "m.py").write_text("class Foo:\n    pass\n", encoding="utf-8")
    assert AnchorResolves().evaluate({"ref": "m.py#Foo"}, _ctx(tmp_path)).passed
    assert not AnchorResolves().evaluate({"ref": "m.py#Bar"}, _ctx(tmp_path)).passed
    # No anchor -> existence only.
    assert AnchorResolves().evaluate({"ref": "m.py"}, _ctx(tmp_path)).passed
    assert not AnchorResolves().evaluate({"ref": "missing.py"}, _ctx(tmp_path)).passed
