import pytest
from pathlib import Path
from factory.kb.retrieval import select_entries

pytestmark = pytest.mark.unit

KB_DIR = Path(__file__).resolve().parents[2] / "kb"


def test_matches_by_file_glob():
    ids = select_entries(KB_DIR, ["src/drone/pybullet_flight_controller.py"], [])
    assert "kb-0001" in ids


def test_matches_by_signature_substring():
    ids = select_entries(KB_DIR, [], ["AssertionError: max_altitude > 0.6"])
    assert "kb-0001" in ids


def test_no_match_returns_empty():
    assert select_entries(KB_DIR, ["src/unrelated/thing.py"], ["totally other"]) == []


def test_invalid_entry_skipped_without_crashing(tmp_path):
    import shutil

    shutil.copy(
        KB_DIR / "kb-0001-pybullet-arming.md", tmp_path / "kb-0001-pybullet-arming.md"
    )
    # Missing the required "id" field entirely: would raise KeyError if
    # selected without validation first.
    (tmp_path / "kb-0002-broken.md").write_text(
        "---\ntitle: t\nstatus: active\nseverity: low\n"
        "tags: []\nscope:\n  files: ['*']\n---\nbody\n",
        encoding="utf-8",
    )
    ids = select_entries(tmp_path, [], ["AssertionError: max_altitude > 0.6"])
    assert ids == ["kb-0001"]
