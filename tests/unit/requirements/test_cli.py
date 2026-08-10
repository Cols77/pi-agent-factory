import json

import pytest
from factory.evidence.manifests import write_run_manifest
from factory.requirements.cli import (
    cmd_bind,
    cmd_check,
    cmd_defer,
    cmd_index,
    cmd_new,
    cmd_next,
    cmd_show,
    cmd_status,
    main,
)
from factory.requirements.register import is_checksum_current, parse_requirement

pytestmark = pytest.mark.unit

# A requirement whose measurement is already decided. `cmd_new` no longer produces
# one of these -- it mints proposed requirements -- so checksum and staleness
# behaviour is exercised against an explicitly bound fixture.
_BOUND = """---
id: SR-001
title: Bound requirement
statement: "When X happens, the system shall do Y."
domain: behavioral
upstream: []
binding:
  harness: demo-harness
  experiment: demo_experiment
  metric: demo_rate
  trials: 1
  assert: ">= 0.90"
checksum: null
---
Rationale.
"""

_PROPOSED = """---
id: SR-009
title: Proposed requirement
statement: "When the zone clears, the system shall resume patrol."
domain: behavioral
upstream: []
source: docs/superpowers/specs/a.md
---
Rationale.
"""


def _write(tmp_path, name: str, text: str):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def _manifest_with_validation_entries(requirements: list[dict], run_id: str = "run-1") -> dict:
    # Mirrors evidence/test_manifests.py's fixture -- schema requires every one of
    # these keys, but only `validation` is relevant to closure resolution.
    return {
        "schema_version": 2,
        "run_id": run_id,
        "task_id": "T-001",
        "started_at": "2026-08-07T12:00:00Z",
        "ended_at": "2026-08-07T12:01:00Z",
        "start_commit": "a" * 40,
        "result_commit": "b" * 40,
        "outcome": "completed",
        "inputs": {
            "task": {"path": "tasks/T-001.md", "sha256": "c" * 64},
            "requirements": [],
            "factory_config_sha256": "d" * 64,
        },
        "dependencies": [],
        "implementation": {
            "changed_files": ["src/a.py"],
            "patch": {"sha256": "e" * 64, "size": 12, "media_type": "text/x-diff"},
        },
        "validation": [{"requirements": requirements}],
        "reviews": [],
        "decisions": [],
        "publication": {"state": "local", "errors": []},
    }


def test_new_allocates_sequential_ids(tmp_path):
    p1 = cmd_new(tmp_path, "First req", "behavioral")
    p2 = cmd_new(tmp_path, "Second req", "perception")
    assert p1.name == "SR-001.md"
    assert p2.name == "SR-002.md"
    assert "First req" in p1.read_text(encoding="utf-8")


def test_new_mints_a_proposed_requirement(tmp_path):
    text = cmd_new(tmp_path, "Zone clear abandons investigate", "behavioral").read_text(
        encoding="utf-8"
    )
    assert "binding:" not in text
    assert "preemption_success_rate" not in text
    assert "sim-testbench" not in text


def test_index_stamps_checksums_and_writes_index(tmp_path):
    _write(tmp_path, "SR-001.md", _BOUND)
    result = cmd_index(tmp_path)
    assert result["requirements"][0]["id"] == "SR-001"
    assert result["requirements"][0]["checksum"].startswith("sha256:")
    assert result["requirements"][0]["stale"] is False
    assert json.loads((tmp_path / "index.json").read_text(encoding="utf-8")) == result


def test_index_leaves_a_proposed_requirement_untouched(tmp_path):
    path = _write(tmp_path, "SR-009.md", _PROPOSED)
    before = path.read_text(encoding="utf-8")
    result = cmd_index(tmp_path)
    assert path.read_text(encoding="utf-8") == before
    assert result["requirements"] == [{"id": "SR-009", "checksum": None, "proposed": True}]


def test_status_flags_stale_after_edit(tmp_path):
    path = _write(tmp_path, "SR-001.md", _BOUND)
    cmd_index(tmp_path)
    assert "current" in cmd_status(tmp_path)
    # Mutate the STATEMENT so the stored checksum no longer matches.
    text = path.read_text(encoding="utf-8").replace("shall do Y", "shall do Y NOW")
    path.write_text(text, encoding="utf-8")
    assert "STALE" in cmd_status(tmp_path)
    assert "SR-001" in cmd_status(tmp_path, stale_only=True)


def test_status_says_proposed_not_current(tmp_path):
    _write(tmp_path, "SR-009.md", _PROPOSED)
    assert "[proposed]" in cmd_status(tmp_path)
    assert "current" not in cmd_status(tmp_path)


def test_status_stale_only_hides_proposed(tmp_path):
    _write(tmp_path, "SR-009.md", _PROPOSED)
    assert cmd_status(tmp_path, stale_only=True) == "no requirements"


def test_show(tmp_path):
    _write(tmp_path, "SR-001.md", _BOUND)
    assert "SR-001" in cmd_show(tmp_path, "SR-001")
    assert "not found" in cmd_show(tmp_path, "SR-999")


def test_show_reports_no_binding(tmp_path):
    _write(tmp_path, "SR-009.md", _PROPOSED)
    out = cmd_show(tmp_path, "SR-009")
    assert "not yet measurable" in out
    assert "docs/superpowers/specs/a.md" in out


def test_index_refuses_to_relaunder_a_stale_checksum(tmp_path):
    path = _write(tmp_path, "SR-001.md", _BOUND)
    cmd_index(tmp_path)
    stamped = path.read_text(encoding="utf-8")

    text = stamped.replace("shall do Y", "shall do Y NOW")
    path.write_text(text, encoding="utf-8")

    result = cmd_index(tmp_path)

    entry = next(r for r in result["requirements"] if r["id"] == "SR-001")
    assert entry["stale"] is True, "index must report staleness, never absorb it"
    assert path.read_text(encoding="utf-8") == text, "a stale file is left exactly as found"
    assert "STALE" in cmd_status(tmp_path), "the signal survives an index run"


def test_index_still_stamps_a_requirement_that_has_no_checksum(tmp_path):
    _write(tmp_path, "SR-001.md", _BOUND)
    result = cmd_index(tmp_path)
    entry = next(r for r in result["requirements"] if r["id"] == "SR-001")
    assert entry["stale"] is False
    assert entry["checksum"].startswith("sha256:")


def test_main_status_exit_code(tmp_path, capsys):
    cmd_new(tmp_path, "First", "behavioral")
    rc = main(["status", "--requirements-dir", str(tmp_path)])
    assert rc == 0
    assert "SR-001" in capsys.readouterr().out


def test_show_reports_no_harness_binding(tmp_path):
    _write(tmp_path, "SR-009.md", _PROPOSED)
    cmd_bind(
        tmp_path, "SR-009", experiment="zone_clear", metric="resume_rate",
        assert_expr=">= 0.95", harness=None, trials=1, reaffirm_reason=None,
    )
    out = cmd_show(tmp_path, "SR-009")
    assert "(no harness)" in out
    assert "None" not in out


def test_bind_writes_a_measurement_and_reports_it(tmp_path):
    _write(tmp_path, "SR-009.md", _PROPOSED)
    out = cmd_bind(
        tmp_path, "SR-009", experiment="zone_clear", metric="resume_rate",
        assert_expr=">= 0.95", harness="sim-testbench", trials=3, reaffirm_reason=None,
    )
    assert "SR-009" in out
    assert "sim-testbench" in out
    assert "[proposed]" not in cmd_status(tmp_path)


def test_bind_accepts_no_harness_and_says_so(tmp_path):
    _write(tmp_path, "SR-009.md", _PROPOSED)
    out = cmd_bind(
        tmp_path, "SR-009", experiment="zone_clear", metric="resume_rate",
        assert_expr=">= 0.95", harness=None, trials=1, reaffirm_reason=None,
    )
    assert "no harness" in out.lower()


def test_bind_on_an_unknown_id_is_reported_not_raised(tmp_path):
    assert "not found" in cmd_bind(
        tmp_path, "SR-999", experiment="e", metric="m", assert_expr=">= 1",
        harness=None, trials=1, reaffirm_reason=None,
    )


def test_defer_records_the_reason_where_trace_reads_it(tmp_path):
    _write(tmp_path, "SR-009.md", _PROPOSED)
    out = cmd_defer(tmp_path, "SR-009", "no current task delivers this")
    assert "SR-009" in out
    assert "trace_deferred: no current task delivers this" in (
        tmp_path / "SR-009.md"
    ).read_text(encoding="utf-8")


def test_defer_with_a_blank_reason_is_refused(tmp_path):
    _write(tmp_path, "SR-009.md", _PROPOSED)
    assert "reason" in cmd_defer(tmp_path, "SR-009", "   ").lower()


def test_main_wires_bind_and_defer(tmp_path, capsys):
    _write(tmp_path, "SR-009.md", _PROPOSED)
    rc = main([
        "bind", "SR-009", "--requirements-dir", str(tmp_path),
        "--experiment", "zone_clear", "--metric", "resume_rate", "--assert", ">= 0.95",
    ])
    assert rc == 0
    assert "SR-009" in capsys.readouterr().out
    rc = main(["defer", "SR-009", "--requirements-dir", str(tmp_path), "--reason", "later"])
    assert rc == 0


def test_bind_reaffirm_clears_staleness_without_a_measurement(tmp_path):
    path = _write(tmp_path, "SR-001.md", _BOUND)
    cmd_index(tmp_path)
    # Mutate the statement so the stamped checksum no longer matches.
    text = path.read_text(encoding="utf-8").replace("shall do Y", "shall do Y NOW")
    path.write_text(text, encoding="utf-8")
    assert "STALE" in cmd_status(tmp_path)

    out = cmd_bind(
        tmp_path, "SR-001", experiment=None, metric=None, assert_expr=None,
        harness=None, trials=1, reaffirm_reason="wording clarified",
    )
    assert "wording clarified" in out
    assert "bound to" not in out
    assert is_checksum_current(parse_requirement(path))


def test_bind_with_an_incomplete_measurement_and_no_reaffirm_is_reported(tmp_path):
    path = _write(tmp_path, "SR-009.md", _PROPOSED)
    before = path.read_text(encoding="utf-8")
    out = cmd_bind(
        tmp_path, "SR-009", experiment="zone_clear", metric=None, assert_expr=None,
        harness=None, trials=1, reaffirm_reason=None,
    )
    assert "--metric" in out
    assert "--assert" in out
    assert path.read_text(encoding="utf-8") == before


def test_main_wires_bind_reaffirm_without_measurement_args(tmp_path):
    _write(tmp_path, "SR-001.md", _BOUND)
    rc = main([
        "bind", "SR-001", "--requirements-dir", str(tmp_path), "--reaffirm", "reworded",
    ])
    assert rc == 0


def test_check_fails_on_a_pending_requirement_and_says_why(tmp_path):
    (tmp_path / "requirements").mkdir()
    _write(tmp_path / "requirements", "SR-009.md", _PROPOSED)
    report, code = cmd_check(tmp_path)
    assert code == 1, "an undecided requirement fails the gate"
    assert "SR-009" in report
    assert "pending" in report.lower()


def test_check_passes_when_every_requirement_is_decided(tmp_path):
    (tmp_path / "requirements").mkdir()
    _write(tmp_path / "requirements", "SR-009.md", _PROPOSED)
    cmd_defer(tmp_path / "requirements", "SR-009", "no task delivers this yet")
    report, code = cmd_check(tmp_path)
    assert code == 0
    assert "0 pending" in report


def test_an_unmeasurable_requirement_warns_without_failing(tmp_path):
    (tmp_path / "requirements").mkdir()
    _write(tmp_path / "requirements", "SR-009.md", _PROPOSED)
    cmd_bind(
        tmp_path / "requirements", "SR-009", experiment="e", metric="m",
        assert_expr=">= 1", harness=None, trials=1, reaffirm_reason=None,
    )
    report, code = cmd_check(tmp_path)
    assert code == 0, "an unnamed harness is a warning, never a blocker"
    assert "unmeasurable" in report.lower()
    assert "SR-009" in report


def test_check_reports_a_stale_requirement_as_blocking(tmp_path):
    reqs = tmp_path / "requirements"
    reqs.mkdir()
    path = _write(reqs, "SR-001.md", _BOUND)
    cmd_index(reqs)
    path.write_text(
        path.read_text(encoding="utf-8").replace("shall do Y", "shall do Y NOW"), encoding="utf-8"
    )
    report, code = cmd_check(tmp_path)
    assert code == 1
    assert "SR-001" in report


def test_check_treats_an_error_only_validation_entry_as_no_measurement(tmp_path):
    # An error entry ("no passed key") is what run_requirement_validation emits for
    # an unknown/proposed requirement or a harness that raised -- it must never be
    # read as evidence the requirement was measured. If it were, SR-001 here would
    # wrongly resolve to measured-passing instead of staying pending.
    reqs = tmp_path / "requirements"
    reqs.mkdir()
    _write(reqs, "SR-001.md", _BOUND)
    cmd_index(reqs)
    write_run_manifest(
        tmp_path / "evidence",
        _manifest_with_validation_entries(
            [{"id": "SR-001", "error": "binding: no harness named yet"}]
        ),
    )
    report, code = cmd_check(tmp_path)
    assert code == 1, "an error entry is not a measurement; SR-001 must stay pending"
    assert "SR-001" in report
    assert "pending" in report.lower()


def test_check_lets_a_live_task_mask_a_stale_done_task_for_the_same_requirement(tmp_path):
    # T-001 is done and T-002 is still live, both naming SR-001. load_tasks sorts
    # by id, so T-001 sorts first -- if _linked_task_status didn't prefer the
    # not-done match, it would pick T-001's "done" status and SR-001 would fall
    # through to pending (exit 1) instead of resolving planned (exit 0).
    reqs = tmp_path / "requirements"
    reqs.mkdir()
    _write(reqs, "SR-001.md", _BOUND)
    cmd_index(reqs)
    tasks = tmp_path / "tasks"
    tasks.mkdir()
    _write(
        tasks, "T-001.md",
        "---\nid: T-001\ntitle: old\nstatus: done\ndod:\n  - x\nsatisfies:\n  - SR-001\n---\nbody\n",
    )
    _write(
        tasks, "T-002.md",
        "---\nid: T-002\ntitle: live\nstatus: todo\ndod:\n  - x\nsatisfies:\n  - SR-001\n---\nbody\n",
    )
    report, code = cmd_check(tmp_path)
    assert code == 0, "the live task must mask the stale done one; SR-001 is planned, not pending"
    assert "0 pending" in report


def test_next_names_the_first_undecided_requirement(tmp_path):
    (tmp_path / "requirements").mkdir()
    _write(tmp_path / "requirements", "SR-009.md", _PROPOSED)
    out = cmd_next(tmp_path)
    assert "SR-009" in out
    assert "When the zone clears" in out, "the statement is what the judgment is made against"


def test_next_says_so_when_nothing_is_open(tmp_path):
    (tmp_path / "requirements").mkdir()
    assert "nothing" in cmd_next(tmp_path).lower()
