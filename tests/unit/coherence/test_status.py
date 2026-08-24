"""Tests for coherence.status: the pure StatusLine/StatusSnapshot precedence
contract (Increment 5 Task 1) and status_snapshot's concurrent, crash-isolated
probes."""
from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from coherence.status import (
    StatusLine,
    StatusSnapshot,
    snapshot_from_lines,
    status_snapshot,
)

pytestmark = pytest.mark.unit


def _line(source: str, outcome: str, *, resolve_cmd=None) -> StatusLine:
    return StatusLine(
        source=source,
        outcome=outcome,
        summary=f"{source} says {outcome}",
        produced_by=f"fake.producer.{source}",
        resolve_cmd=resolve_cmd if resolve_cmd is not None else (f"fix {source}",),
        observation_ref=f"ref:{source}",
    )


# --------------------------------------------------------------------------
# Pure contract shape
# --------------------------------------------------------------------------


def test_status_line_is_a_frozen_dataclass_with_the_declared_fields():
    line = _line("probe", "nothing_pending")
    assert line.source == "probe"
    assert line.outcome == "nothing_pending"
    assert line.produced_by == "fake.producer.probe"
    assert line.resolve_cmd == ("fix probe",)
    assert line.observation_ref == "ref:probe"
    with pytest.raises(Exception):
        line.source = "mutated"  # frozen -- must not be settable


def test_status_snapshot_is_a_frozen_dataclass_with_the_declared_fields():
    line = _line("probe", "nothing_pending", resolve_cmd=None)
    snapshot = snapshot_from_lines((line,))
    assert isinstance(snapshot, StatusSnapshot)
    assert snapshot.lines == (line,)
    assert snapshot.primary is line
    assert snapshot.exit_code == 0


def test_resolve_cmd_is_an_ordered_tuple_never_a_semicolon_string():
    line = _line("probe", "failing_gate", resolve_cmd=("first command", "second command"))
    assert isinstance(line.resolve_cmd, tuple)
    assert line.resolve_cmd == ("first command", "second command")
    for command in line.resolve_cmd:
        assert ";" not in command


def test_resolve_cmd_order_and_duplicates_are_preserved():
    # 2B ordered-tuple contract: no dedup, no reordering.
    dup = ("a", "b", "a")
    line = _line("probe", "failing_gate", resolve_cmd=dup)
    snapshot = snapshot_from_lines((line,))
    assert snapshot.primary.resolve_cmd == dup


def test_snapshot_from_lines_requires_at_least_one_line():
    with pytest.raises(ValueError):
        snapshot_from_lines(())


# --------------------------------------------------------------------------
# Precedence: interrupted_run > failing_gate > stale_audit > proposed_backlog
#              > nothing_pending
# --------------------------------------------------------------------------


def test_interrupted_run_outranks_failing_gate():
    lines = (_line("a", "failing_gate"), _line("b", "interrupted_run"))
    snapshot = snapshot_from_lines(lines)
    assert snapshot.primary.outcome == "interrupted_run"
    assert snapshot.primary.source == "b"
    assert snapshot.exit_code == 1


def test_failing_gate_outranks_stale_audit():
    lines = (_line("a", "stale_audit"), _line("b", "failing_gate"))
    snapshot = snapshot_from_lines(lines)
    assert snapshot.primary.outcome == "failing_gate"
    assert snapshot.exit_code == 1


def test_stale_audit_outranks_proposed_backlog():
    lines = (_line("a", "proposed_backlog"), _line("b", "stale_audit"))
    snapshot = snapshot_from_lines(lines)
    assert snapshot.primary.outcome == "stale_audit"
    assert snapshot.exit_code == 1


def test_proposed_backlog_outranks_nothing_pending():
    lines = (_line("a", "nothing_pending", resolve_cmd=None), _line("b", "proposed_backlog"))
    snapshot = snapshot_from_lines(lines)
    assert snapshot.primary.outcome == "proposed_backlog"
    assert snapshot.exit_code == 1


def test_nothing_pending_is_the_only_clean_outcome_and_is_exit_zero():
    lines = tuple(
        _line(str(i), "nothing_pending", resolve_cmd=None) for i in range(3)
    )
    snapshot = snapshot_from_lines(lines)
    assert snapshot.primary.outcome == "nothing_pending"
    assert snapshot.exit_code == 0


def test_full_precedence_chain_regardless_of_input_order():
    # Every level present, shuffled -- primary must always be the worst one,
    # exactly the order named in the task brief.
    ordered = ["interrupted_run", "failing_gate", "stale_audit", "proposed_backlog", "nothing_pending"]
    shuffled = ["stale_audit", "nothing_pending", "failing_gate", "interrupted_run", "proposed_backlog"]
    lines = tuple(_line(outcome, outcome) for outcome in shuffled)
    snapshot = snapshot_from_lines(lines)
    assert snapshot.primary.outcome == ordered[0]
    # And removing the worst each time reveals the next-worst, proving the
    # entire chain, not just the top of it.
    remaining = list(lines)
    for expected in ordered:
        snap = snapshot_from_lines(tuple(remaining))
        assert snap.primary.outcome == expected
        remaining = [ln for ln in remaining if ln.outcome != expected]


def test_ties_break_on_declared_order_not_arbitrarily():
    lines = (_line("first", "failing_gate"), _line("second", "failing_gate"))
    snapshot = snapshot_from_lines(lines)
    assert snapshot.primary.source == "first"


def test_every_line_names_its_producer_and_resolver():
    lines = (
        _line("a", "interrupted_run"),
        _line("b", "failing_gate"),
        _line("c", "stale_audit"),
    )
    for line in lines:
        assert line.produced_by
        assert line.resolve_cmd is not None
        assert all(isinstance(c, str) and c for c in line.resolve_cmd)


def test_unrecognized_outcome_never_reads_as_clean():
    # A probe author who typos/invents a new outcome string must not have it
    # silently sort as "nothing_pending" (clean) -- rank as severe as a
    # probe_error instead.
    lines = (_line("a", "nothing_pending", resolve_cmd=None), _line("b", "totally_unknown_outcome"))
    snapshot = snapshot_from_lines(lines)
    assert snapshot.primary.outcome == "totally_unknown_outcome"
    assert snapshot.exit_code == 1


# --------------------------------------------------------------------------
# Stale must render stale, never silently current (hard precedence-test
# requirement named in the task brief)
# --------------------------------------------------------------------------


def test_stale_snapshot_renders_stale_with_its_resolver_never_current():
    stale = _line("audit_age", "stale_audit", resolve_cmd=("coherence audit run FEAT-001",))
    clean = _line("trace_check", "nothing_pending", resolve_cmd=None)
    snapshot = snapshot_from_lines((clean, stale))
    assert snapshot.primary.outcome == "stale_audit"
    assert snapshot.primary is stale
    assert snapshot.primary.resolve_cmd == ("coherence audit run FEAT-001",)
    assert snapshot.exit_code != 0
    # The clean line staying present and un-elevated is fine; what must never
    # happen is the *snapshot* reporting nothing_pending while a stale line
    # exists among its probes.
    assert not any(ln.outcome == "nothing_pending" and ln is snapshot.primary for ln in snapshot.lines)


def test_probe_error_outcome_is_never_treated_as_clean():
    errored = StatusLine(
        source="trace_check",
        outcome="probe_error",
        summary="trace_check probe failed: boom",
        produced_by="coherence.status._probe_trace_check",
        resolve_cmd=None,
        observation_ref=None,
    )
    clean = _line("register_check", "nothing_pending", resolve_cmd=None)
    snapshot = snapshot_from_lines((clean, errored))
    assert snapshot.primary.outcome == "probe_error"
    assert snapshot.exit_code == 1


# --------------------------------------------------------------------------
# status_snapshot(project_root): real, concurrent, crash-isolated probes
# --------------------------------------------------------------------------


def test_status_snapshot_on_an_empty_repo_is_clean_with_five_lines(tmp_path: Path):
    snapshot = status_snapshot(tmp_path)
    assert len(snapshot.lines) == 5
    assert {line.source for line in snapshot.lines} == {
        "trace_check",
        "register_check",
        "run_checkpoint",
        "audit_age",
        "membership_gate",
    }
    assert snapshot.primary.outcome == "nothing_pending"
    assert snapshot.exit_code == 0


def test_status_snapshot_reports_interrupted_run(tmp_path: Path):
    run_dir = tmp_path / "sessions" / ".factory-runs" / "by-session" / "run-1"
    run_dir.mkdir(parents=True)
    checkpoint = {
        "schema_version": 2,
        "run_id": "run-1",
        "task_id": "T-001",
        "node": "dev",
        "attempt": 1,
        "remaining": {"dev": 3, "review": 3},
        "start_commit": "abc",
        "head_commit": "abc",
        "worktree_fingerprint": "x",
        "tracked_fingerprint": "x",
        "patch_path": None,
        "completed": [],
        "agent_sessions": {},
        "pending_human_round": None,
        "artifacts": [],
        "interruption": "manual",
    }
    (run_dir / "journal.jsonl").write_text(json.dumps(checkpoint) + "\n", encoding="utf-8")
    (run_dir / "checkpoint.json").write_text(json.dumps(checkpoint), encoding="utf-8")

    snapshot = status_snapshot(tmp_path)
    assert snapshot.primary.outcome == "interrupted_run"
    assert snapshot.primary.source == "run_checkpoint"
    assert snapshot.primary.resolve_cmd is not None
    assert "run-1" in snapshot.primary.resolve_cmd[0]
    assert "run-state inspect" in snapshot.primary.resolve_cmd[0]
    assert snapshot.exit_code == 1


def test_status_snapshot_reports_failing_trace_gate(tmp_path: Path):
    (tmp_path / "requirements").mkdir()
    (tmp_path / "requirements" / "SR-001.md").write_text(
        "---\nid: SR-001\ntitle: X\nstatement: shall do X\ndomain: behavioral\nupstream: []\n---\n",
        encoding="utf-8",
    )

    snapshot = status_snapshot(tmp_path)
    trace_line = next(ln for ln in snapshot.lines if ln.source == "trace_check")
    assert trace_line.outcome == "failing_gate"
    assert trace_line.resolve_cmd == (f"coherence trace check --project-root {tmp_path}",)


def test_status_snapshot_reports_proposed_backlog_when_a_feature_is_never_audited(tmp_path: Path):
    (tmp_path / "docs" / "features").mkdir(parents=True)
    (tmp_path / "docs" / "features" / "FEAT-001.md").write_text(
        "---\nid: FEAT-001\ntitle: Test\nrequirements: []\n---\n", encoding="utf-8"
    )

    snapshot = status_snapshot(tmp_path)
    audit_line = next(ln for ln in snapshot.lines if ln.source == "audit_age")
    assert audit_line.outcome == "proposed_backlog"
    assert audit_line.resolve_cmd == (
        f"coherence audit run FEAT-001 --project-root {tmp_path}",
    )
    assert snapshot.primary.outcome == "proposed_backlog"


def test_status_snapshot_reports_stale_audit_from_a_recorded_stale_checksum(tmp_path: Path):
    run_dir = tmp_path / "coverage-reviews" / "FEAT-001-run-1"
    run_dir.mkdir(parents=True)
    report = {
        "feature": "FEAT-001",
        "run_id": "run-1",
        "generated_at": "2026-01-01T00:00:00+00:00",
        "srs": {
            "SR-001": {"sr_id": "SR-001", "checksum_state": "stale"},
        },
    }
    (run_dir / "report.json").write_text(json.dumps(report), encoding="utf-8")

    snapshot = status_snapshot(tmp_path)
    audit_line = next(ln for ln in snapshot.lines if ln.source == "audit_age")
    assert audit_line.outcome == "stale_audit"
    assert audit_line.resolve_cmd == (
        f"coherence audit run FEAT-001 --project-root {tmp_path}",
    )
    assert "SR-001" in audit_line.summary


def test_status_snapshot_reports_current_audit_as_clean(tmp_path: Path):
    run_dir = tmp_path / "coverage-reviews" / "FEAT-001-run-1"
    run_dir.mkdir(parents=True)
    report = {
        "feature": "FEAT-001",
        "run_id": "run-1",
        "generated_at": "2026-01-01T00:00:00+00:00",
        "srs": {
            "SR-001": {"sr_id": "SR-001", "checksum_state": "current"},
        },
    }
    (run_dir / "report.json").write_text(json.dumps(report), encoding="utf-8")

    snapshot = status_snapshot(tmp_path)
    audit_line = next(ln for ln in snapshot.lines if ln.source == "audit_age")
    assert audit_line.outcome == "nothing_pending"
    assert audit_line.resolve_cmd is None


def test_status_snapshot_picks_the_newest_audit_run_across_features(tmp_path: Path):
    older = tmp_path / "coverage-reviews" / "FEAT-001-run-1"
    older.mkdir(parents=True)
    (older / "report.json").write_text(
        json.dumps(
            {
                "feature": "FEAT-001",
                "run_id": "run-1",
                "generated_at": "2020-01-01T00:00:00+00:00",
                "srs": {"SR-001": {"sr_id": "SR-001", "checksum_state": "stale"}},
            }
        ),
        encoding="utf-8",
    )
    newer = tmp_path / "coverage-reviews" / "FEAT-002-run-2"
    newer.mkdir(parents=True)
    (newer / "report.json").write_text(
        json.dumps(
            {
                "feature": "FEAT-002",
                "run_id": "run-2",
                "generated_at": "2026-01-01T00:00:00+00:00",
                "srs": {"SR-002": {"sr_id": "SR-002", "checksum_state": "current"}},
            }
        ),
        encoding="utf-8",
    )

    snapshot = status_snapshot(tmp_path)
    audit_line = next(ln for ln in snapshot.lines if ln.source == "audit_age")
    # The newer (FEAT-002) run is current -- the older stale run must not win.
    assert audit_line.outcome == "nothing_pending"
    assert "FEAT-002" in audit_line.summary


def test_status_snapshot_reports_failing_membership_gate(tmp_path: Path):
    (tmp_path / "requirements").mkdir()
    (tmp_path / "requirements" / "SR-001.md").write_text(
        "---\nid: SR-001\ntitle: X\nstatement: shall do X\ndomain: behavioral\nupstream: []\n---\n",
        encoding="utf-8",
    )

    snapshot = status_snapshot(tmp_path)
    membership_line = next(ln for ln in snapshot.lines if ln.source == "membership_gate")
    assert membership_line.outcome == "failing_gate"
    assert membership_line.resolve_cmd == (
        f"coherence navigate membership --gate --repo-root {tmp_path}",
    )


def test_status_snapshot_isolates_a_crashing_probe(tmp_path: Path, monkeypatch):
    import coherence.status as status_module

    def _boom(_root: Path) -> StatusLine:
        raise RuntimeError("simulated tool crash")

    monkeypatch.setattr(status_module, "_probe_trace_check", _boom)
    monkeypatch.setattr(
        status_module,
        "_PROBES",
        (
            ("trace_check", _boom),
            ("register_check", status_module._probe_register_check),
            ("run_checkpoint", status_module._probe_run_checkpoint),
            ("audit_age", status_module._probe_audit_age),
            ("membership_gate", status_module._probe_membership_gate),
        ),
    )

    snapshot = status_module.status_snapshot(tmp_path)
    assert len(snapshot.lines) == 5
    errored = next(ln for ln in snapshot.lines if ln.source == "trace_check")
    assert errored.outcome == "probe_error"
    assert "simulated tool crash" in errored.summary
    assert snapshot.primary.outcome == "probe_error"
    assert snapshot.exit_code == 1


def test_status_snapshot_runs_probes_concurrently_not_serially(tmp_path: Path, monkeypatch):
    import coherence.status as status_module

    delay = 0.2

    def _slow(_root: Path) -> StatusLine:
        time.sleep(delay)
        return StatusLine(
            source="slow",
            outcome="nothing_pending",
            summary="slow",
            produced_by="test",
            resolve_cmd=None,
            observation_ref=None,
        )

    monkeypatch.setattr(
        status_module,
        "_PROBES",
        tuple((f"slow{i}", _slow) for i in range(5)),
    )

    started = time.monotonic()
    status_module.status_snapshot(tmp_path)
    elapsed = time.monotonic() - started

    # Five serial 0.2s probes would take >= 1.0s; concurrently they should
    # finish in well under that -- generous bound to avoid CI flakiness.
    assert elapsed < delay * 3


# --------------------------------------------------------------------------
# CLI wiring
# --------------------------------------------------------------------------


def test_main_json_flag_prints_valid_json_with_primary_and_lines(tmp_path: Path, capsys):
    from coherence.status import main

    code = main(["--project-root", str(tmp_path), "--json"])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert "primary" in payload
    assert "lines" in payload
    assert len(payload["lines"]) == 5
    assert payload["exit_code"] == 0


def test_main_human_render_shows_primary_and_all_probes(tmp_path: Path, capsys):
    from coherence.status import main

    code = main(["--project-root", str(tmp_path)])
    assert code == 0
    out = capsys.readouterr().out
    assert "status: nothing_pending" in out
    assert "all probes:" in out
    for source in ("trace_check", "register_check", "run_checkpoint", "audit_age", "membership_gate"):
        assert source in out


def test_coherence_status_is_registered_in_the_group_dispatcher():
    from coherence import cli

    assert "status" in cli.GROUPS


def test_coherence_status_dispatches_through_top_level_module(tmp_path: Path):
    import subprocess
    import sys as _sys

    project_root = Path(__file__).parents[3]
    result = subprocess.run(
        [_sys.executable, "-m", "coherence", "status", "--project-root", str(tmp_path), "--json"],
        cwd=project_root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["primary"]["outcome"] == "nothing_pending"
