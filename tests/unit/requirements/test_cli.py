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


def _manifest_with_validation_entries(
    requirements: list[dict], run_id: str = "run-1", ended_at: str = "2026-08-07T12:01:00Z"
) -> dict:
    # Mirrors evidence/test_manifests.py's fixture -- schema requires every one of
    # these keys, but only `validation` is relevant to closure resolution.
    return {
        "schema_version": 2,
        "run_id": run_id,
        "task_id": "T-001",
        "started_at": "2026-08-07T12:00:00Z",
        "ended_at": ended_at,
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


def test_bind_reaffirm_on_a_proposed_requirement_is_reported_and_leaves_the_file_alone(tmp_path):
    # 180 of the 181 requirements in the field register are proposed, so this is
    # the likeliest mistaken invocation there is. It must refuse before writing:
    # the old order wrote `reaffirmed:` and only then discovered there was no
    # binding to checksum, leaving a record of a reaffirmation that never happened.
    path = _write(tmp_path, "SR-009.md", _PROPOSED)
    before = path.read_text(encoding="utf-8")
    out = cmd_bind(
        tmp_path, "SR-009", experiment=None, metric=None, assert_expr=None,
        harness=None, trials=1, reaffirm_reason="the statement was reworded",
    )
    assert "SR-009" in out
    assert "no binding" in out
    assert path.read_text(encoding="utf-8") == before, "a refusal leaves no partial write"
    assert "reaffirmed" not in path.read_text(encoding="utf-8")


def test_main_bind_reaffirm_on_a_proposed_requirement_does_not_traceback(tmp_path, capsys):
    _write(tmp_path, "SR-009.md", _PROPOSED)
    rc = main(["bind", "SR-009", "--requirements-dir", str(tmp_path), "--reaffirm", "reworded"])
    assert rc == 0, "reported, never raised -- the idiom the rest of this CLI uses"
    assert "no binding" in capsys.readouterr().out


def test_bind_reaffirm_with_a_blank_reason_is_refused(tmp_path):
    path = _write(tmp_path, "SR-001.md", _BOUND)
    cmd_index(tmp_path)
    before = path.read_text(encoding="utf-8")
    out = cmd_bind(
        tmp_path, "SR-001", experiment=None, metric=None, assert_expr=None,
        harness=None, trials=1, reaffirm_reason="   ",
    )
    assert "reason" in out.lower()
    assert path.read_text(encoding="utf-8") == before


def test_rebinding_keeps_a_window_the_call_did_not_name(tmp_path):
    # The single bound requirement in the field register carries a window, and
    # `window` is a content_checksum input -- so dropping it and stamping would
    # certify the mutilated binding as current, the exact laundering `index`
    # was fixed to prevent.
    _write(tmp_path, "SR-009.md", _PROPOSED)
    cmd_bind(
        tmp_path, "SR-009", experiment="e", metric="m", assert_expr=">= 1",
        harness="sim-testbench", trials=1, reaffirm_reason=None,
        window_json='{"after_event": "shark_detected", "within_s": 5}',
    )
    cmd_bind(
        tmp_path, "SR-009", experiment="e", metric="m", assert_expr=">= 2",
        harness="sim-testbench", trials=1, reaffirm_reason=None,
    )
    req = parse_requirement(tmp_path / "SR-009.md")
    assert req.binding.window == {"after_event": "shark_detected", "within_s": 5}
    assert is_checksum_current(req)


def test_bind_window_json_round_trips(tmp_path):
    _write(tmp_path, "SR-009.md", _PROPOSED)
    cmd_bind(
        tmp_path, "SR-009", experiment="e", metric="m", assert_expr=">= 1",
        harness="h", trials=1, reaffirm_reason=None,
        window_json='{"after_event": "shark_detected", "within_s": 5}',
    )
    req = parse_requirement(tmp_path / "SR-009.md")
    assert req.binding.window == {"after_event": "shark_detected", "within_s": 5}
    assert isinstance(req.binding.window["within_s"], int), "JSON, not k=v, so numbers stay numbers"


def test_bind_reports_a_malformed_window_json_without_writing(tmp_path):
    path = _write(tmp_path, "SR-009.md", _PROPOSED)
    before = path.read_text(encoding="utf-8")
    out = cmd_bind(
        tmp_path, "SR-009", experiment="e", metric="m", assert_expr=">= 1",
        harness="h", trials=1, reaffirm_reason=None, window_json="{not json",
    )
    assert "--window-json" in out
    assert path.read_text(encoding="utf-8") == before


def test_main_wires_window_json(tmp_path, capsys):
    _write(tmp_path, "SR-009.md", _PROPOSED)
    rc = main([
        "bind", "SR-009", "--requirements-dir", str(tmp_path),
        "--experiment", "e", "--metric", "m", "--assert", ">= 1",
        "--window-json", '{"within_s": 5}',
    ])
    assert rc == 0
    capsys.readouterr()
    assert parse_requirement(tmp_path / "SR-009.md").binding.window == {"within_s": 5}


def test_main_index_exits_nonzero_on_a_stale_checksum(tmp_path, capsys):
    # A CI step running `index` alone must not read exit 0 over a stale register.
    path = _write(tmp_path, "SR-001.md", _BOUND)
    assert main(["index", "--requirements-dir", str(tmp_path)]) == 0
    path.write_text(
        path.read_text(encoding="utf-8").replace("shall do Y", "shall do Y NOW"), encoding="utf-8"
    )
    assert main(["index", "--requirements-dir", str(tmp_path)]) == 1
    assert "true" in capsys.readouterr().out.lower(), "and still prints the report"


def test_check_renders_a_measured_failing_requirement_distinctly_and_still_passes(tmp_path):
    # Without this the unproven path is unfalsifiable: a requirement the system
    # provably fails rendered byte-identically to one that passes.
    reqs = tmp_path / "requirements"
    reqs.mkdir()
    _write(reqs, "SR-001.md", _BOUND)
    cmd_index(reqs)
    write_run_manifest(
        tmp_path / "evidence",
        _manifest_with_validation_entries([{"id": "SR-001", "passed": False}]),
    )
    report, code = cmd_check(tmp_path)
    assert code == 0, "a measured failure is a healthy closure state; the register does not judge it"
    assert "1 measured-failing" in report
    assert "0 measured-passing" in report
    assert "SR-001" in report
    assert "measured failing" in report


def test_check_resolves_a_requirement_against_the_newest_manifest_that_measured_it(tmp_path):
    # A requirement that failed, was fixed and now passes must read as passing.
    # Aggregating across all history lets one ancient `passed: false` outvote
    # every later run and parks it in measured-failing forever.
    reqs = tmp_path / "requirements"
    reqs.mkdir()
    _write(reqs, "SR-001.md", _BOUND)
    cmd_index(reqs)
    write_run_manifest(
        tmp_path / "evidence",
        _manifest_with_validation_entries(
            [{"id": "SR-001", "passed": False}], run_id="run-old",
            ended_at="2026-08-07T12:01:00Z",
        ),
    )
    write_run_manifest(
        tmp_path / "evidence",
        _manifest_with_validation_entries(
            [{"id": "SR-001", "passed": True}], run_id="run-new",
            ended_at="2026-08-08T12:01:00Z",
        ),
    )
    report, code = cmd_check(tmp_path)
    assert code == 0
    assert "1 measured-passing" in report
    assert "0 measured-failing" in report, "the fix supersedes the old failure"


def test_check_fails_on_an_integrity_finding_not_just_a_blocking_one(tmp_path, monkeypatch):
    # Nothing emits INTEGRITY today, so this pins the gate's filter rather than a
    # live state: INTEGRITY is the MORE severe tier, and FreshnessReport.ok
    # already treats it as failing.
    from factory.freshness.model import FreshnessSeverity
    from factory.requirements import cli as cli_mod
    from factory.requirements.closure import ClosureFinding, RequirementState
    from factory.requirements.register import Requirement

    req = Requirement(
        id="SR-001", title="t", statement="s", domain="behavioral", upstream=[],
        binding=None, body="", path=tmp_path / "SR-001.md",
    )
    finding = ClosureFinding(
        req_id="SR-001", state=RequirementState.PENDING,
        severity=FreshnessSeverity.INTEGRITY, detail="SR-001: integrity",
    )
    monkeypatch.setattr(cli_mod, "_findings", lambda _root, **_kwargs: [(req, finding)])
    report, code = cmd_check(tmp_path)
    assert code == 1, "the more severe tier must not pass the gate silently"
    assert "SR-001" in report


def test_check_surfaces_a_deferral_that_closed_a_requirement_with_no_binding(tmp_path):
    # `trace_deferred` is shared with trace, where it answers a traceability
    # question, not a measurement one. A deferral on an unbound requirement
    # therefore closes it with nobody having decided how it would be measured --
    # reported rather than silently closed, but still not a gate failure.
    reqs = tmp_path / "requirements"
    reqs.mkdir()
    _write(reqs, "SR-009.md", _PROPOSED)
    cmd_defer(reqs, "SR-009", "traceability handled elsewhere")
    report, code = cmd_check(tmp_path)
    assert code == 0, "a recorded deferral is still a real disposition; this is visibility, not a gate change"
    assert "1 declined (1 with no binding)" in report
    assert "declined with no binding" in report
    assert "SR-009" in report


def test_check_does_not_flag_a_deferred_requirement_that_is_bound(tmp_path):
    reqs = tmp_path / "requirements"
    reqs.mkdir()
    _write(reqs, "SR-001.md", _BOUND)
    cmd_index(reqs)
    cmd_defer(reqs, "SR-001", "scheduled for the next increment")
    report, code = cmd_check(tmp_path)
    assert code == 0
    assert "1 declined (0 with no binding)" in report
    assert "declined with no binding" not in report


def test_next_names_the_first_undecided_requirement(tmp_path):
    (tmp_path / "requirements").mkdir()
    _write(tmp_path / "requirements", "SR-009.md", _PROPOSED)
    out = cmd_next(tmp_path)
    assert "SR-009" in out
    assert "When the zone clears" in out, "the statement is what the judgment is made against"


def test_next_says_so_when_nothing_is_open(tmp_path):
    (tmp_path / "requirements").mkdir()
    assert "nothing" in cmd_next(tmp_path).lower()


def _bound_sr_marker_fixture(
    tmp_path, *, req_id="SR-001", experiment="tests/test_sr.py", profile=None, marker=False,
):
    """Write a bound SR with a current checksum and (optionally) a real .py
    experiment file, so cmd_check's SR test-marker closure wiring is exercised
    end-to-end rather than against fake classify inputs."""
    (tmp_path / "requirements").mkdir(parents=True)
    profile_line = f"profile: {profile}\n" if profile else ""
    (tmp_path / "requirements" / f"{req_id}.md").write_text(
        "---\n"
        f"id: {req_id}\n"
        "title: Bound requirement\n"
        "statement: When X, the system shall do Y.\n"
        "domain: behavioral\n"
        f"{profile_line}"
        "binding:\n"
        f"  experiment: {experiment}\n"
        "  metric: unit_pass_rate\n"
        "  assert: '>= 0.90'\n"
        "  harness: sim-testbench\n"
        "  trials: 1\n"
        "checksum: null\n"
        "---\n"
        "Rationale.\n",
        encoding="utf-8",
    )
    cmd_index(tmp_path / "requirements")
    if experiment.endswith(".py"):
        test_path = tmp_path / experiment
        test_path.parent.mkdir(parents=True, exist_ok=True)
        marker_line = f'@pytest.mark.sr("{req_id}")\n' if marker else ""
        test_path.write_text(
            f"import pytest\n\n{marker_line}def test_x():\n    assert True\n",
            encoding="utf-8",
        )


def test_check_gates_a_bound_sr_missing_its_marker_on_a_blocking_profile(tmp_path):
    _bound_sr_marker_fixture(tmp_path, profile="high_assurance", marker=False)
    write_run_manifest(
        tmp_path / "evidence",
        _manifest_with_validation_entries([{"id": "SR-001", "passed": True}]),
    )
    report, code = cmd_check(tmp_path)
    assert code == 1, "a missing sr marker on a blocking profile must fail the gate"
    assert "1 measured-passing" in report, "the classify finding still shows"
    assert "marker" in report.lower()
    assert "@pytest.mark.sr" in report


def test_check_does_not_flag_an_sr_whose_marker_is_present(tmp_path):
    _bound_sr_marker_fixture(tmp_path, marker=True)
    write_run_manifest(
        tmp_path / "evidence",
        _manifest_with_validation_entries([{"id": "SR-001", "passed": True}]),
    )
    report, code = cmd_check(tmp_path)
    assert code == 0
    assert "1 measured-passing" in report
    assert "marker" not in report.lower(), "a present marker adds no finding"


def test_check_surfaces_a_command_experiment_as_a_non_gating_configuration_warning(tmp_path):
    _bound_sr_marker_fixture(tmp_path, experiment="patrol")
    write_run_manifest(
        tmp_path / "evidence",
        _manifest_with_validation_entries([{"id": "SR-001", "passed": True}]),
    )
    report, code = cmd_check(tmp_path)
    assert code == 0, "a command experiment is a configuration warning, never a blocker"
    assert "1 measured-passing" in report
    assert "patrol" in report
    assert "unmeasurable" in report.lower(), "the configuration warning is visible in the report"


def test_check_surfaces_an_uncompiled_marker_skip_instead_of_silently_swallowing_it(tmp_path):
    _bound_sr_marker_fixture(tmp_path, profile="exploration")
    write_run_manifest(
        tmp_path / "evidence",
        _manifest_with_validation_entries([{"id": "SR-001", "passed": True}]),
    )
    report, code = cmd_check(tmp_path)
    assert code == 0, "a skipped marker check under an uncompiled profile must not gate"
    assert "marker-closure skips" in report
    assert "skipped" in report.lower()
    assert "exploration" in report
