import pytest
from pathlib import Path

from factory.memory.nonconformance import (
    DuplicateNonconformanceIdError,
    load_nonconformances,
)

pytestmark = pytest.mark.unit


def _write_nc(root: Path, filename: str, body: str) -> None:
    (root / "docs" / "nonconformances").mkdir(parents=True, exist_ok=True)
    (root / "docs" / "nonconformances" / filename).write_text(body, encoding="utf-8")


def test_no_directory_returns_empty(tmp_path):
    assert load_nonconformances(tmp_path) == {}


def test_load_valid_record(tmp_path):
    _write_nc(
        tmp_path,
        "NC-0001.md",
        "---\nid: NC-0001\ntitle: t\nexternal_ref: gh-issue:1\nstatus: corrected\n"
        "corrected_by: T-031\n---\nbody\n",
    )
    records = load_nonconformances(tmp_path)
    assert records["NC-0001"].external_ref == "gh-issue:1"
    assert records["NC-0001"].corrected_by == "T-031"
    assert records["NC-0001"].scope_errors == []


def test_malformed_record_degrades_to_scope_errors(tmp_path):
    _write_nc(tmp_path, "NC-0002.md", "---\ntitle: no id\n---\nbody\n")
    records = load_nonconformances(tmp_path)
    assert records == {}  # no id -> not keyed, but load must not crash


def test_duplicate_id_raises(tmp_path):
    _write_nc(tmp_path, "a.md", "---\nid: NC-0003\ntitle: a\nstatus: open\n---\n")
    _write_nc(tmp_path, "b.md", "---\nid: NC-0003\ntitle: b\nstatus: open\n---\n")
    with pytest.raises(DuplicateNonconformanceIdError):
        load_nonconformances(tmp_path)
