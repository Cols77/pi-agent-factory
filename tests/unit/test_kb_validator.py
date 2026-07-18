import pytest
from pathlib import Path
from factory.validation.kb_validator import parse_entry, validate_entry_file

pytestmark = pytest.mark.unit

KB_DIR = Path(__file__).resolve().parents[2] / "kb"


def test_seeded_entry_parses_and_validates():
    path = KB_DIR / "kb-0001-pybullet-arming.md"
    data = parse_entry(path)
    assert data["id"] == "kb-0001"
    assert validate_entry_file(path) == []


def test_filename_id_mismatch_reported(tmp_path):
    p = tmp_path / "kb-9999-wrong.md"
    p.write_text(
        "---\nid: kb-0002\ntitle: t\nstatus: active\nseverity: low\n"
        "tags: []\nscope:\n  files: []\n---\nbody\n",
        encoding="utf-8",
    )
    assert any("filename" in e for e in validate_entry_file(p))


def test_bad_status_enum_reported(tmp_path):
    p = tmp_path / "kb-0003-x.md"
    p.write_text(
        "---\nid: kb-0003\ntitle: t\nstatus: nope\nseverity: low\n"
        "tags: []\nscope:\n  files: []\n---\nbody\n",
        encoding="utf-8",
    )
    assert validate_entry_file(p)
