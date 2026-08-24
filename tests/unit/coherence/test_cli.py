from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest


pytestmark = pytest.mark.unit

_PROJECT_ROOT = Path(__file__).parents[3]


def _run_coherence(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "coherence", *args],
        cwd=_PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def _run_module(module: str, *args: str) -> subprocess.CompletedProcess[str]:
    # -W always::DeprecationWarning: the interpreter's built-in default filter
    # only shows a DeprecationWarning raised directly in __main__, but `python
    # -m` runs the target through runpy with an extra frame, so the
    # stacklevel=2 warning in these __main__ shims is blamed on runpy, not
    # __main__ -- silent under the plain default filter. Forcing the warning
    # on is how a caller would actually observe it (e.g. via PYTHONWARNINGS).
    return subprocess.run(
        [sys.executable, "-W", "always::DeprecationWarning", "-m", module, *args],
        cwd=_PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def _audit_fixture(root: Path) -> None:
    """Minimal fixture with one SR, one task, one manifest -- enough for
    ``coherence audit audit`` to produce a real (non-empty) scope."""
    (root / "docs" / "features").mkdir(parents=True)
    (root / "docs" / "features" / "FEAT-001.md").write_text(
        "---\nid: FEAT-001\ntitle: Test\nrequirements: [SR-001]\n---\n"
    )
    (root / "requirements").mkdir()
    (root / "requirements" / "SR-001.md").write_text(
        "---\nid: SR-001\ntitle: X\nstatement: shall do X\ndomain: behavioral\n"
        "binding:\n  harness: sim-testbench\n  experiment: tests/test_x.py\n"
        "  metric: unit_pass_rate\n  trials: 1\n  assert: '== 1.0'\nchecksum: null\n---\n"
    )
    (root / "tasks").mkdir()
    (root / "tasks" / "T-001.md").write_text(
        "---\nid: T-001\ntitle: T\ndeliverables: []\nsatisfies: [SR-001]\n---\n"
    )


def _measurement_fixture(root: Path) -> None:
    """Minimal fixture with one SR bound to a sim-testbench harness's pytest
    trial source (the reserved ``unit_pass_rate`` metric, no scorer module
    required) -- enough for ``coherence measurement run --satisfies SR-001``
    to pass."""
    from coherence.register.register import content_checksum, parse_requirement

    sr = """---
id: SR-001
title: X
statement: shall do X
domain: behavioral
upstream: []
binding:
  harness: sim-testbench
  experiment: tests/test_x.py
  metric: unit_pass_rate
  trials: 1
  assert: '== 1.0'
checksum: {ck}
---
body
"""
    req = root / "requirements"
    req.mkdir()
    stub = req / "SR-001.md"
    stub.write_text(sr.format(ck="null"), encoding="utf-8")
    ck = content_checksum(parse_requirement(stub))
    stub.write_text(sr.format(ck=ck), encoding="utf-8")
    (root / ".factory").mkdir()
    (root / ".factory" / "factory.yaml").write_text(
        "harnesses:\n  sim-testbench:\n    type: sim-testbench\n    traces_dir: traces\n",
        encoding="utf-8",
    )
    (root / "tests").mkdir()
    (root / "tests" / "test_x.py").write_text(
        "import pytest\n\npytestmark = pytest.mark.unit\n\n\ndef test_ok():\n    assert True\n",
        encoding="utf-8",
    )


def test_trace_check_dispatches_through_top_level_module(tmp_path: Path):
    result = _run_coherence("trace", "check", "--project-root", str(tmp_path))

    assert result.returncode == 0
    assert "traceability health:" in result.stdout


def test_register_status_dispatches_and_preserves_requirements_dir(tmp_path: Path):
    requirements_dir = tmp_path / "requirements"
    requirements_dir.mkdir()
    (requirements_dir / "SR-001.md").write_text(
        "---\n"
        "id: SR-001\n"
        "title: Dispatch works\n"
        "statement: The dispatcher shall forward arguments.\n"
        "domain: behavioral\n"
        "---\n",
        encoding="utf-8",
    )

    result = _run_coherence("register", "status", "--requirements-dir", str(requirements_dir))

    assert result.returncode == 0
    assert result.stdout == "SR-001  [proposed]  Dispatch works\n"


def test_doctor_context_dispatches_through_top_level_module(tmp_path: Path):
    result = _run_coherence(
        "doctor", "context", "--project-root", str(tmp_path), "--json"
    )

    assert result.returncode == 0
    assert json.loads(result.stdout) == {
        "specs": [],
        "requirements": [],
        "config": {"present": False, "harnesses": {}},
    }


@pytest.mark.parametrize("argv", [[], ["unknown", "--keep", "value"]])
def test_missing_or_unknown_group_module_entry_returns_two_and_lists_valid_groups(argv):
    result = _run_coherence(*argv)

    assert result.returncode == 2
    output = result.stdout + result.stderr
    assert "valid groups:" in output
    assert all(group in output for group in ("trace", "register", "doctor"))


@pytest.mark.parametrize("group", ["navigate", "presentation", "goals", "simulation"])
def test_coherence_exposes_increment_three_groups(group):
    from coherence import cli

    assert group in cli.GROUPS


@pytest.mark.parametrize("group", ["audit", "measurement"])
def test_coherence_exposes_increment_four_groups(group):
    from coherence import cli

    assert group in cli.GROUPS


@pytest.mark.parametrize(
    "group",
    [
        "trace",
        "register",
        "doctor",
        "navigate",
        "presentation",
        "goals",
        "simulation",
        "audit",
        "measurement",
    ],
)
def test_dispatch_passes_child_argv_unchanged(group, monkeypatch):
    from coherence import cli

    received: list[str] = []

    def child_main(argv: list[str]) -> int:
        received.extend(argv)
        return 17

    monkeypatch.setitem(cli.GROUPS, group, child_main)
    child_argv = ["status", "--requirements-dir", "fixture", "--", "value"]

    assert cli.main([group, *child_argv]) == 17
    assert received == child_argv


def test_audit_audit_dispatches_through_top_level_module(tmp_path: Path):
    _audit_fixture(tmp_path)

    result = _run_coherence(
        "audit", "audit", "FEAT-001", "--project-root", str(tmp_path), "--run-id", "test-run"
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["feature"] == "FEAT-001"
    assert "SR-001" in payload["srs"]
    assert (tmp_path / "coverage-reviews" / "FEAT-001-test-run" / "audit.json").exists()


def test_measurement_run_dispatches_through_top_level_module(tmp_path: Path):
    _measurement_fixture(tmp_path)

    result = _run_coherence(
        "measurement", "run", "--project-root", str(tmp_path), "--satisfies", "SR-001"
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert [e["id"] for e in payload["requirements"]] == ["SR-001"]


def test_factory_coverage_main_module_forwards_and_warns(tmp_path: Path):
    _audit_fixture(tmp_path)

    result = _run_module(
        "factory.coverage",
        "audit",
        "FEAT-001",
        "--project-root",
        str(tmp_path),
        "--run-id",
        "test-run",
    )

    assert result.returncode == 0
    assert "DeprecationWarning" in result.stderr
    assert "factory.coverage.__main__ is deprecated" in result.stderr
    payload = json.loads(result.stdout)
    assert payload["feature"] == "FEAT-001"


def test_factory_validation_main_module_forwards_and_warns(tmp_path: Path):
    _measurement_fixture(tmp_path)

    result = _run_module(
        "factory.validation", "run", "--project-root", str(tmp_path), "--satisfies", "SR-001"
    )

    assert result.returncode == 0
    assert "DeprecationWarning" in result.stderr
    assert "factory.validation.__main__ is deprecated" in result.stderr
    payload = json.loads(result.stdout)
    assert [e["id"] for e in payload["requirements"]] == ["SR-001"]
