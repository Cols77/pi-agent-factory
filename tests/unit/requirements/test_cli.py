import json

import pytest
from factory.requirements.cli import cmd_index, cmd_new, cmd_show, cmd_status, main

pytestmark = pytest.mark.unit


def test_new_allocates_sequential_ids(tmp_path):
    p1 = cmd_new(tmp_path, "First req", "behavioral")
    p2 = cmd_new(tmp_path, "Second req", "perception")
    assert p1.name == "SR-001.md"
    assert p2.name == "SR-002.md"
    assert "First req" in p1.read_text(encoding="utf-8")


def test_index_stamps_checksums_and_writes_index(tmp_path):
    cmd_new(tmp_path, "First", "behavioral")
    result = cmd_index(tmp_path)
    assert result["requirements"][0]["id"] == "SR-001"
    assert result["requirements"][0]["checksum"].startswith("sha256:")
    assert result["requirements"][0]["stale"] is False
    assert json.loads((tmp_path / "index.json").read_text(encoding="utf-8")) == result


def test_status_flags_stale_after_edit(tmp_path):
    path = cmd_new(tmp_path, "First", "behavioral")
    cmd_index(tmp_path)
    assert "current" in cmd_status(tmp_path)
    # Mutate the STATEMENT so the stored checksum no longer matches.
    # (content_checksum covers statement+binding, not the title.)
    text = path.read_text(encoding="utf-8").replace("shall <response>", "shall RESPOND NOW")
    path.write_text(text, encoding="utf-8")
    assert "STALE" in cmd_status(tmp_path)
    assert "SR-001" in cmd_status(tmp_path, stale_only=True)


def test_show(tmp_path):
    cmd_new(tmp_path, "First", "behavioral")
    assert "SR-001" in cmd_show(tmp_path, "SR-001")
    assert "not found" in cmd_show(tmp_path, "SR-999")


def test_main_status_exit_code(tmp_path, capsys):
    cmd_new(tmp_path, "First", "behavioral")
    rc = main(["status", "--requirements-dir", str(tmp_path)])
    assert rc == 0
    assert "SR-001" in capsys.readouterr().out
