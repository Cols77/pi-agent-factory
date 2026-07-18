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


def test_filename_numeric_prefix_collision_reported(tmp_path):
    # "kb-00019-x" starts with "kb-0001" as a plain string, but the ids
    # (00019 vs 0001) don't actually match — the boundary-aware check must
    # still catch this.
    p = tmp_path / "kb-00019-x.md"
    p.write_text(
        "---\nid: kb-0001\ntitle: t\nstatus: active\nseverity: low\n"
        "tags: []\nscope:\n  files: []\n---\nbody\n",
        encoding="utf-8",
    )
    assert any("filename" in e for e in validate_entry_file(p))


def test_unquoted_date_normalized_to_string(tmp_path):
    p = tmp_path / "kb-0004-x.md"
    p.write_text(
        "---\nid: kb-0004\ntitle: t\nstatus: active\nseverity: low\n"
        "created: 2026-07-16\nlast_seen: 2026-07-16\n"
        "tags: []\nscope:\n  files: []\n---\nbody\n",
        encoding="utf-8",
    )
    data = parse_entry(p)
    assert data["created"] == "2026-07-16"
    assert isinstance(data["last_seen"], str)
    assert validate_entry_file(p) == []
