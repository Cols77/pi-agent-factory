"""`factory memory` / `factory failure` CLI tests (Inc 8 Task 4).

Tests exercise the CLI through direct ``main()`` calls (the convention
``factory.evidence`` / ``factory.goals`` use) and one subprocess
module-invocation round-trip (the convention ``factory.system`` uses).
Records are *recorded, never inferred*: `add` only writes what the caller
passes, and validation rejects malformed input before writing.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from factory.memory.cli import main
from factory.memory.failure_record import parse_failure

pytestmark = pytest.mark.unit


def _run(tmp_path: Path, *args: str) -> int:
    return main([str(a) for a in (*args, "--repo", str(tmp_path))])


def _write_run(tmp_path: Path, run_id: str) -> None:
    """Write a minimal v1 run manifest (the health test helper shape)."""
    run_dir = tmp_path / "evidence" / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "manifest.json").write_text(
        json.dumps({"run": run_id, "experiment": "SIM-047", "feature": "FEAT-001"}),
        encoding="utf-8",
    )


def _write_failure(tmp_path: Path, text: str, filename: str = "FR-NAV-0001.md") -> None:
    failures_dir = tmp_path / "docs" / "failures"
    failures_dir.mkdir(parents=True, exist_ok=True)
    (failures_dir / filename).write_text(text, encoding="utf-8")


_WELL_FORMED = """\
---
id: FR-NAV-0001
title: False re-acquisition
reproduced_by: RUN-NAV-001
root_cause: "Pre-emption cleared the latch (ADR-0002)"
fix: "Re-arm the latch in resume path"
regression_link: null
linked_req: [SR-017]
linked_feature: [FEAT-NAV-017]
rejected_hypotheses:
  - hypothesis: "Sensor noise"
    why_rejected: "Deterministically reproduced"
    evidence: "run:RUN-NAV-001"
---
"""


# ── memory show ──────────────────────────────────────────────────────


def test_memory_show_empty_repo_returns_all_sections(tmp_path, capsys):
    rc = _run(tmp_path, "memory", "show", "--json")
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert "scope" in payload
    assert payload["scope"] == "all"
    assert isinstance(payload.get("decisions"), list)
    assert isinstance(payload.get("failure_records"), list)
    assert isinstance(payload.get("rejected_hypotheses"), list)
    assert isinstance(payload.get("open_goals"), list)
    assert isinstance(payload.get("conflicts"), list)


def test_memory_show_defaults_to_all_when_scope_omitted(tmp_path, capsys):
    rc = _run(tmp_path, "memory", "show", "--json")
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["scope"] == "all"


def test_memory_show_unknown_scope_is_nonzero(tmp_path, capsys):
    rc = _run(tmp_path, "memory", "show", "bogus:x", "--json")
    assert rc == 2
    assert "invalid scope ref" in capsys.readouterr().err


# ── memory conflicts ──────────────────────────────────────────────────


def test_memory_conflicts_empty_repo_returns_empty_list(tmp_path, capsys):
    rc = _run(tmp_path, "memory", "conflicts", "--json")
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["scope"] == "all"
    assert payload["conflicts"] == []


def test_memory_conflicts_surfaces_missing_run(tmp_path, capsys):
    _write_failure(tmp_path, _WELL_FORMED.replace("RUN-NAV-001", "RUN-NOPE"))
    _write_run(tmp_path, "RUN-OTHER")  # not RUN-NOPE → missing

    rc = _run(tmp_path, "memory", "conflicts", "--json")
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    kinds = {c["kind"] for c in payload["conflicts"]}
    assert "missing-run" in kinds


# ── failure add ────────────────────────────────────────────────────────


def test_failure_add_round_trips(tmp_path, capsys):
    rc = _run(
        tmp_path,
        "failure",
        "add",
        "--id", "FR-NAV-0001",
        "--title", "False re-acquisition",
        "--root-cause", "Pre-emption cleared latch",
        "--fix", "Re-arm the latch",
    )
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["id"] == "FR-NAV-0001"
    assert payload["scope_errors"] == []

    path = tmp_path / "docs" / "failures" / "FR-NAV-0001.md"
    assert path.is_file()
    rec = parse_failure(path)
    assert rec.id == "FR-NAV-0001"


def test_failure_add_with_optional_fields(tmp_path, capsys):
    rc = _run(
        tmp_path,
        "failure",
        "add",
        "--id", "FR-NAV-0002",
        "--title", "T",
        "--root-cause", "Cause",
        "--fix", "Fix",
        "--reproduced-by", "RUN-001",
        "--regression-link", "T-REG-001",
        "--linked-req", "SR-017",
        "--linked-feature", "FEAT-NAV-017",
    )
    assert rc == 0
    rec = parse_failure(tmp_path / "docs" / "failures" / "FR-NAV-0002.md")
    assert rec.reproduced_by == "RUN-001"
    assert rec.regression_link == "T-REG-001"
    assert rec.linked_req == ["SR-017"]
    assert rec.linked_feature == ["FEAT-NAV-017"]


def test_failure_add_with_hypothesis_round_trip(tmp_path, capsys):
    rc = _run(
        tmp_path,
        "failure",
        "add",
        "--id", "FR-NAV-0003",
        "--title", "Hypothesis test",
        "--root-cause", "X",
        "--fix", "Y",
        "--hypothesis",
        '{"hypothesis": "Sensor noise", "why_rejected": "Replay", "evidence": "run:RUN-001"}',
    )
    assert rc == 0
    rec = parse_failure(tmp_path / "docs" / "failures" / "FR-NAV-0003.md")
    assert len(rec.rejected_hypotheses) == 1
    assert rec.rejected_hypotheses[0]["hypothesis"] == "Sensor noise"
    assert rec.rejected_hypotheses[0]["evidence"] == "run:RUN-001"


def test_failure_add_requires_fix(tmp_path, capsys):
    # `--fix` is argparse-required (mirroring the schema's required fields).
    with pytest.raises(SystemExit) as excinfo:
        _run(
            tmp_path,
            "failure",
            "add",
            "--id", "FR-NAV-0004",
            "--title", "T",
            "--root-cause", "X",
            # no --fix
        )
    assert excinfo.value.code == 2
    assert "fix" in capsys.readouterr().err.lower()
    assert not (tmp_path / "docs" / "failures" / "FR-NAV-0004.md").exists()


def test_failure_add_rejects_invalid_id_pattern(tmp_path, capsys):
    rc = _run(
        tmp_path,
        "failure",
        "add",
        "--id", "BROKEN-1",
        "--title", "T",
        "--root-cause", "X",
        "--fix", "Y",
    )
    assert rc == 2
    assert "id" in capsys.readouterr().err
    assert not (tmp_path / "docs" / "failures" / "BROKEN-1.md").exists()


def test_failure_add_rejects_malformed_hypothesis_json(tmp_path, capsys):
    rc = _run(
        tmp_path,
        "failure",
        "add",
        "--id", "FR-NAV-0005",
        "--title", "T",
        "--root-cause", "X",
        "--fix", "Y",
        "--hypothesis", "not json",
    )
    assert rc == 2
    assert "invalid --hypothesis" in capsys.readouterr().err.lower()


def test_failure_add_rejects_hypothesis_missing_required_fields(tmp_path, capsys):
    rc = _run(
        tmp_path,
        "failure",
        "add",
        "--id", "FR-NAV-0006",
        "--title", "T",
        "--root-cause", "X",
        "--fix", "Y",
        "--hypothesis",
        '{"hypothesis": "no why, no evidence"}',
    )
    assert rc == 2
    assert "why_rejected" in capsys.readouterr().err


def test_failure_add_refuses_existing_file(tmp_path, capsys):
    _run(tmp_path, "failure", "add", "--id", "FR-NAV-0007", "--title", "T",
         "--root-cause", "X", "--fix", "Y")
    capsys.readouterr()
    rc = _run(tmp_path, "failure", "add", "--id", "FR-NAV-0007", "--title", "T",
              "--root-cause", "X", "--fix", "Y")
    assert rc == 2
    assert "already exists" in capsys.readouterr().err


# ── failure list ────────────────────────────────────────────────────────


def test_failure_list_empty_repo(tmp_path, capsys):
    rc = _run(tmp_path, "failure", "list", "--json")
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["failures"] == []


def test_failure_list_sorted_by_declared_id(tmp_path, capsys):
    _run(tmp_path, "failure", "add", "--id", "FR-Z-001", "--title", "Z",
         "--root-cause", "X", "--fix", "Y")
    _run(tmp_path, "failure", "add", "--id", "FR-A-001", "--title", "A",
         "--root-cause", "X", "--fix", "Y")
    capsys.readouterr()
    rc = _run(tmp_path, "failure", "list", "--json")
    assert rc == 0
    ids = [f["id"] for f in json.loads(capsys.readouterr().out)["failures"]]
    assert ids == ["FR-A-001", "FR-Z-001"]


def test_failure_list_includes_scope_errors(tmp_path, capsys):
    _write_failure(
        tmp_path,
        "---\nid: FR-BAD-001\ntitle: T\n---\n\nbody\n",  # no root_cause/fix
        "FR-BAD-001.md",
    )
    rc = _run(tmp_path, "failure", "list", "--json")
    assert rc == 0
    items = json.loads(capsys.readouterr().out)["failures"]
    assert items[0]["scope_errors"] != []


# ── failure show ────────────────────────────────────────────────────────


def test_failure_show_round_trips(tmp_path, capsys):
    _run(tmp_path, "failure", "add", "--id", "FR-NAV-0010", "--title", "T",
         "--root-cause", "Cause", "--fix", "Fix",
         "--reproduced-by", "RUN-001", "--linked-req", "SR-017")
    capsys.readouterr()
    rc = _run(tmp_path, "failure", "show", "FR-NAV-0010", "--json")
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["id"] == "FR-NAV-0010"
    assert payload["root_cause"] == "Cause"
    assert payload["reproduced_by"] == "RUN-001"
    assert payload["path"].endswith("FR-NAV-0010.md")


def test_failure_show_unknown_id_is_nonzero(tmp_path, capsys):
    rc = _run(tmp_path, "failure", "show", "FR-NOPE", "--json")
    assert rc == 2
    assert "no failure record" in capsys.readouterr().err


# ── module invocation (python -m factory.memory) ────────────────────────


def test_module_invocation_returns_structure(tmp_path):
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "factory.memory",
            "memory",
            "show",
            "--repo", str(tmp_path),
            "--json",
        ],
        capture_output=True,
        text=True,
        timeout=30,
        cwd=Path(__file__).resolve().parents[3],
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert "scope" in payload
    assert payload["scope"] == "all"