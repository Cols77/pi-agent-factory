import json
import shutil
import pytest
from pathlib import Path
from factory.kb.index import build_index

pytestmark = pytest.mark.unit

SRC_KB = Path(__file__).resolve().parents[2] / "kb"


def test_build_index_writes_file(tmp_path):
    shutil.copy(SRC_KB / "kb-0001-pybullet-arming.md", tmp_path / "kb-0001-pybullet-arming.md")
    idx = build_index(tmp_path)
    assert "kb-0001" in idx
    assert idx["kb-0001"]["status"] == "active"
    written = json.loads((tmp_path / "index.json").read_text(encoding="utf-8"))
    assert written == idx
