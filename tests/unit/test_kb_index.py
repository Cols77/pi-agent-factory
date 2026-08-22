import json
import shutil
import warnings
import pytest
from pathlib import Path

with warnings.catch_warnings():
    warnings.simplefilter("ignore", DeprecationWarning)
    from factory.kb.index import build_index

from substrate.kb.index import build_index as substrate_build_index
from substrate.kb.index import build_index_payload as substrate_build_index_payload

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


def test_old_shim_warns_and_matches_substrate_index_on_path_glob_fixtures(tmp_path):
    shutil.copy(SRC_KB / "kb-0001-example-entry.md", tmp_path / "kb-0001-example-entry.md")

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", DeprecationWarning)
        import importlib
        import sys

        sys.modules.pop("factory.kb.index", None)
        old_index_module = importlib.import_module("factory.kb.index")

    deprecations = [item for item in caught if item.category is DeprecationWarning]
    assert len(deprecations) == 1
    assert str(deprecations[0].message) == (
        "factory.kb.index is deprecated; import substrate.kb.index"
    )

    old_payload = old_index_module.build_index_payload(tmp_path)
    new_payload = substrate_build_index_payload(tmp_path)
    assert old_payload == new_payload
    assert old_index_module.build_index is substrate_build_index
