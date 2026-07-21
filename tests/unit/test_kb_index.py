import json
import shutil
import pytest
from pathlib import Path
from factory.kb.index import build_index

pytestmark = pytest.mark.unit

SRC_KB = Path(__file__).resolve().parents[2] / "kb"


def test_build_index_writes_file(tmp_path):
    shutil.copy(SRC_KB / "kb-0001-example-entry.md", tmp_path / "kb-0001-example-entry.md")
    idx = build_index(tmp_path)
    assert "kb-0001" in idx
    assert idx["kb-0001"]["status"] == "active"
    written = json.loads((tmp_path / "index.json").read_text(encoding="utf-8"))
    assert written == idx


def test_build_index_skips_invalid_entry_without_crashing(tmp_path):
    shutil.copy(SRC_KB / "kb-0001-example-entry.md", tmp_path / "kb-0001-example-entry.md")
    # Missing the required "id" field entirely: would raise KeyError if
    # indexed without validation first.
    (tmp_path / "kb-0002-broken.md").write_text(
        "---\ntitle: t\nstatus: active\nseverity: low\ntags: []\nscope:\n  files: []\n---\nbody\n",
        encoding="utf-8",
    )
    idx = build_index(tmp_path)
    assert "kb-0001" in idx
    assert len(idx) == 1
