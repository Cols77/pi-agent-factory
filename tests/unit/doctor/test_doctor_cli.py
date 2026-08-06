import json

import pytest
from factory.doctor.cli import main

pytestmark = pytest.mark.unit


def _repo(tmp_path):
    specs = tmp_path / "docs" / "superpowers" / "specs"
    specs.mkdir(parents=True)
    (specs / "a.md").write_text("# A\n", encoding="utf-8")
    return tmp_path


def _run(argv, tmp_path):
    return main([*argv, "--project-root", str(tmp_path)])


def test_context_json_is_machine_readable(tmp_path, capsys):
    assert _run(["context", "--json"], _repo(tmp_path)) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["specs"] == ["docs/superpowers/specs/a.md"]


def test_mint_then_promote_then_task(tmp_path, capsys):
    repo = _repo(tmp_path)
    assert _run(["mint", "--source", "docs/superpowers/specs/a.md",
                 "--title", "t", "--statement", "s"], repo) == 0
    assert "SR-001" in capsys.readouterr().out

    assert _run(["promote", "SR-001", "--harness", "sim-testbench", "--experiment", "e",
                 "--metric", "m", "--assert", ">= 0.9",
                 "--window-json", '{"after_event": "zone_clear", "within_s": 5}'], repo) == 0
    out = capsys.readouterr().out
    assert "promoted SR-001" in out
    assert "NOT implemented" in out

    assert _run(["task", "--satisfies", "SR-001", "--title", "Implement m",
                 "--dod", "SCORERS exposes m"], repo) == 0
    assert "T-001" in capsys.readouterr().out


def test_a_refusal_exits_nonzero_with_the_reason(tmp_path, capsys):
    rc = _run(["mint", "--source", "docs/superpowers/specs/missing.md",
               "--title", "t", "--statement", "s"], _repo(tmp_path))
    assert rc == 1
    assert "no such source" in capsys.readouterr().out
