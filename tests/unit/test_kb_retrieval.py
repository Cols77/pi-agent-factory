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
