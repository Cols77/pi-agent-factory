"""Task 4 — ``python -m factory.presentation present`` CLI (headless/agent)."""
from __future__ import annotations

import json

import pytest

from factory.presentation.cli import main

pytestmark = pytest.mark.unit


def test_present_cli_returns_ts_shaped_json(tmp_path, capsys):
    repo_root = str(tmp_path)
    rc = main(["present", "feat:FEAT-NAV-017", "--focus", "overview", "--repo-root", repo_root, "--json"])
    out = capsys.readouterr().out
    assert rc == 0
    payload = json.loads(out)
    assert payload["artifact"] == "feat:FEAT-NAV-017"
    assert payload["focus"] == "overview"
    assert payload["intent"] == {"artifact": "feat:FEAT-NAV-017", "focus": "overview"}
    assert payload["level"] == "INSPECT"
    assert payload["adapter"] == "browser"
    assert payload["target"] == "system?scope=feat:FEAT-NAV-017"


def test_present_cli_accepts_explicit_level(tmp_path, capsys):
    rc = main(["present", "sr:SR-066", "--level", "REVIEW", "--repo-root", str(tmp_path), "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert payload["level"] == "REVIEW"
    assert "REVIEW" in payload["resolution"]


def test_present_cli_rejects_bad_level(tmp_path, capsys):
    rc = main(["present", "sr:SR-066", "--level", "nope", "--repo-root", str(tmp_path), "--json"])
    err = capsys.readouterr().err
    assert rc == 1
    assert "invalid --level" in err


def test_present_cli_rejects_empty_artifact(tmp_path, capsys):
    rc = main(["present", "", "--repo-root", str(tmp_path), "--json"])
    err = capsys.readouterr().err
    assert rc == 1
    assert "non-empty artifact" in err


def test_present_cli_resolves_file_to_ide(tmp_path, capsys):
    src = tmp_path / "src"
    src.mkdir()
    (src / "a.py").write_text("# x\n", encoding="utf-8")
    rc = main(["present", "src/a.py", "--focus", "2", "--repo-root", str(tmp_path), "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert payload["adapter"] == "ide"
    assert payload["target"].startswith("vscode://file/")


def test_present_cli_blocks_traversal(tmp_path, capsys):
    rc = main(["present", "../../etc/passwd", "--repo-root", str(tmp_path), "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert payload["adapter"] is None
    assert payload["target"] is None
    assert "traversal blocked" in payload["note"]


def test_present_cli_why_required_calls_why_required(tmp_path, capsys):
    (tmp_path / ".factory").mkdir()
    (tmp_path / ".factory" / "factory.yaml").write_text(
        "gates:\n  unit:\n  - { cmd: 'pytest -m unit -q' }\n", encoding="utf-8",
    )
    (tmp_path / "requirements").mkdir()
    (tmp_path / "requirements" / "SR-001.md").write_text(
        "---\nid: SR-001\ntitle: t\nstatement: s\ndomain: d\n---\n", encoding="utf-8",
    )
    rc = main([
        "present", "sr:SR-001", "--why-required", "--repo-root", str(tmp_path), "--json",
    ])
    payload = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert payload["obligations"] is not None
    ci = next(o for o in payload["obligations"] if o["kind"] == "ci_verification")
    assert ci["why"] is not None


def test_present_cli_why_required_off_by_default(tmp_path, capsys):
    rc = main(["present", "feat:FEAT-NAV-017", "--repo-root", str(tmp_path), "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert "obligations" not in payload
