"""Tests for factory.system.cli: brief/matrix/scope subcommands only.

`timeline` and `guide` are registered in later tasks and must not be stubbed
here. JSON is emitted only on `--json`; structured errors go to stderr with
a non-zero exit code.
"""
from __future__ import annotations

import json

import pytest

from factory.system.cli import main

from ._fixtures import write_bundle, write_sr, write_validation_report

pytestmark = pytest.mark.unit


def test_brief_json_flag_prints_valid_json(tmp_path, capsys):
    write_sr(tmp_path / "requirements", "SR-001")
    rc = main(["brief", "--scope", "sr:SR-001", "--repo-root", str(tmp_path), "--json"])
    out = capsys.readouterr().out
    assert rc == 0
    payload = json.loads(out)
    assert payload["scope"]["ref"] == "sr:SR-001"


def test_brief_without_json_flag_prints_human_readable_text(tmp_path, capsys):
    write_sr(tmp_path / "requirements", "SR-001")
    rc = main(["brief", "--scope", "sr:SR-001", "--repo-root", str(tmp_path)])
    out = capsys.readouterr().out
    assert rc == 0
    with pytest.raises(json.JSONDecodeError):
        json.loads(out)
    assert "SR-001" in out


def test_matrix_json_flag_prints_valid_json(tmp_path, capsys):
    write_sr(tmp_path / "requirements", "SR-001")
    write_validation_report(tmp_path, [{"id": "SR-001", "passed": True, "stale": False, "artifacts": []}])
    rc = main(["matrix", "--scope", "sr:SR-001", "--repo-root", str(tmp_path), "--json"])
    out = capsys.readouterr().out
    assert rc == 0
    payload = json.loads(out)
    assert payload["rows"][0]["status"] == "passed"


def test_scope_json_flag_lists_declared_scopes(tmp_path, capsys):
    write_sr(tmp_path / "requirements", "SR-001")
    write_bundle(tmp_path / "bundles", "b1", "Bundle One", [])
    rc = main(["scope", "--repo-root", str(tmp_path), "--json"])
    out = capsys.readouterr().out
    assert rc == 0
    payload = json.loads(out)
    refs = {s["ref"] for s in payload["scopes"]}
    assert refs == {"sr:SR-001", "bundle:b1"}


def test_scope_on_empty_repo_prints_something_sane(tmp_path, capsys):
    rc = main(["scope", "--repo-root", str(tmp_path), "--json"])
    out = capsys.readouterr().out
    assert rc == 0
    assert json.loads(out)["scopes"] == []


def test_unknown_scope_exits_nonzero_with_structured_stderr(tmp_path, capsys):
    rc = main(["brief", "--scope", "sr:SR-404", "--repo-root", str(tmp_path), "--json"])
    captured = capsys.readouterr()
    assert rc != 0
    assert captured.out == ""
    error = json.loads(captured.err)
    assert "error" in error


def test_malformed_scope_ref_exits_nonzero_with_structured_stderr(tmp_path, capsys):
    rc = main(["brief", "--scope", "not-a-scope", "--repo-root", str(tmp_path)])
    captured = capsys.readouterr()
    assert rc != 0
    error = json.loads(captured.err)
    assert "error" in error


def test_error_output_is_structured_json_even_without_json_flag(tmp_path, capsys):
    # "Emit JSON only on --json" governs *successful* output; errors are
    # always structured on stderr regardless of --json.
    rc = main(["brief", "--scope", "sr:SR-404", "--repo-root", str(tmp_path)])
    captured = capsys.readouterr()
    assert rc != 0
    parsed = json.loads(captured.err)
    assert "error" in parsed


def test_no_timeline_or_guide_subcommands_registered(tmp_path, capsys):
    with pytest.raises(SystemExit):
        main(["timeline", "--scope", "sr:SR-001", "--repo-root", str(tmp_path)])
    with pytest.raises(SystemExit):
        main(["guide", "--scope", "sr:SR-001", "--repo-root", str(tmp_path)])


def test_module_invocation_matches_python_dash_m_factory_system(tmp_path):
    # Design SS5.1/SS12: invocation is exactly `python -m factory.system`,
    # mirroring factory.trace.__main__ (spawnSync shape trace-cli.ts uses).
    import subprocess
    import sys

    write_sr(tmp_path / "requirements", "SR-001")
    result = subprocess.run(
        [sys.executable, "-m", "factory.system", "scope", "--repo-root", str(tmp_path), "--json"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["scopes"] == [{"kind": "sr", "ref": "sr:SR-001"}]
