"""Tests for factory.system.cli: brief/matrix/timeline/story/guide/scope
subcommands.

JSON is emitted only on `--json`; structured errors go to stderr with a
non-zero exit code.
"""
from __future__ import annotations

import contextlib
import io
import json

import pytest

from factory.system.cli import main

from ._fixtures import (
    _write_task_fixture,  # noqa: F401 -- registers the `write_task` fixture used below
    write_bundle,
    write_bundle_raw,
    write_decision_artifact,
    write_raw_manifest_json,
    write_sr,
    write_task,
    write_validation_report,
)

pytestmark = pytest.mark.unit


def run_cli(argv: list[str]) -> str:
    """Run the CLI and return captured stdout, asserting a zero exit code.

    A plain helper (not a `capsys`-based fixture): `capsys` only captures
    output written while pytest owns the file descriptors for the *current
    test*, which a bare module-level function can't request for itself the
    way a fixture can -- redirecting stdout directly here works the same
    from any caller, fixture or not.
    """
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = main(argv)
    assert rc == 0, buf.getvalue()
    return buf.getvalue()


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


def test_timeline_json_flag_prints_valid_json(tmp_path, capsys):
    write_task(tmp_path / "tasks", "T-001", status="done")
    write_bundle(tmp_path / "bundles", "b1", "Bundle", ["task:T-001"])
    write_decision_artifact(tmp_path, task_id="T-001")
    rc = main(["timeline", "--scope", "bundle:b1", "--repo-root", str(tmp_path), "--json"])
    out = capsys.readouterr().out
    assert rc == 0
    payload = json.loads(out)
    assert payload["scope"]["ref"] == "bundle:b1"
    assert len(payload["events"]) == 1
    assert payload["events"][0]["actor"] == "not-recorded"
    assert payload["degraded_reasons"] == ["1 event(s) do not have a recorded actor"]


def test_timeline_without_json_flag_prints_human_readable_text(tmp_path, capsys):
    write_task(tmp_path / "tasks", "T-001", status="done")
    write_bundle(tmp_path / "bundles", "b1", "Bundle", ["task:T-001"])
    write_decision_artifact(tmp_path, task_id="T-001")
    rc = main(["timeline", "--scope", "bundle:b1", "--repo-root", str(tmp_path)])
    out = capsys.readouterr().out
    assert rc == 0
    with pytest.raises(json.JSONDecodeError):
        json.loads(out)

    # Exact text, not a substring -- a substring check ("task:T-001" in out)
    # would pass just as well with the old, false "records were dropped"
    # wording still present. Nothing was dropped here; the warning must list
    # the actual counted reason(s), not direct the reader to "each event's
    # freshness" (which may not exist at all -- see the empty-timeline test
    # below).
    expected_lines = [
        "scope: bundle:b1",
        "  ! degraded:",
        "    - 1 event(s) do not have a recorded actor",
        "  [2026-08-08T12:00:00Z] not-recorded approved task:T-001 (degraded)",
    ]
    assert out == "\n".join(expected_lines) + "\n"
    assert "dropped" not in out
    assert "each event's freshness" not in out


def test_timeline_without_json_flag_on_empty_but_degraded_timeline_prints_reasons_not_event_pointer(
    tmp_path, capsys
):
    # The combination finding 3 (round 2) newly made reachable: zero events
    # (nothing to point a reader at) but degraded via an unreadable
    # manifest. The renderer must print the reason itself, not direct the
    # reader to per-event detail that does not exist.
    write_task(tmp_path / "tasks", "T-001", status="done")
    write_bundle(tmp_path / "bundles", "b1", "Bundle", ["task:T-001"])
    write_raw_manifest_json(tmp_path, run_id="run-bad", payload={"not": "a valid manifest"})

    rc = main(["timeline", "--scope", "bundle:b1", "--repo-root", str(tmp_path)])
    out = capsys.readouterr().out

    assert rc == 0
    expected_lines = [
        "scope: bundle:b1",
        "  ! degraded:",
        "    - 1 run manifest(s) under evidence/runs could not be read",
        "  no recorded decisions",
    ]
    assert out == "\n".join(expected_lines) + "\n"
    assert "each event's freshness" not in out


def test_timeline_on_empty_repo_reports_no_recorded_decisions(tmp_path, capsys):
    write_task(tmp_path / "tasks", "T-001", status="todo")
    write_bundle(tmp_path / "bundles", "b1", "Bundle", ["task:T-001"])
    rc = main(["timeline", "--scope", "bundle:b1", "--repo-root", str(tmp_path)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "no recorded decisions" in out


def test_story_subcommand_emits_json_for_a_task_scope(tmp_path, write_task):
    write_task(tmp_path, "T-059", status="done", satisfies=[])
    out = run_cli(["story", "--scope", "task:T-059", "--repo-root", str(tmp_path), "--json"])
    assert json.loads(out)["task"]["id"] == "T-059"


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


def test_scope_reports_bundle_load_errors_instead_of_erasing_them(tmp_path, capsys):
    # Finding 5: an operator who typos a bundle file gets feedback from
    # `factory.system scope`, not silence.
    write_bundle(tmp_path / "bundles", "good", "Good", [])
    write_bundle_raw(tmp_path / "bundles", "foo", {"id": "bar", "label": "X", "members": []})

    rc = main(["scope", "--repo-root", str(tmp_path), "--json"])
    payload = json.loads(capsys.readouterr().out)

    assert rc == 0
    assert {s["ref"] for s in payload["scopes"]} == {"bundle:good"}
    assert len(payload["errors"]) == 1
    assert payload["errors"][0]["bundle_id"] == "foo"


def test_scope_without_json_flag_renders_errors_too(tmp_path, capsys):
    write_bundle_raw(tmp_path / "bundles", "foo", {"id": "bar", "label": "X", "members": []})

    rc = main(["scope", "--repo-root", str(tmp_path)])
    out = capsys.readouterr().out

    assert rc == 0
    assert "foo" in out


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


def test_guide_json_flag_prints_valid_json(tmp_path, capsys):
    write_sr(tmp_path / "requirements", "SR-001", statement="When X happens, the system shall Y.")
    rc = main(["guide", "--scope", "sr:SR-001", "--repo-root", str(tmp_path), "--json"])
    out = capsys.readouterr().out
    assert rc == 0
    payload = json.loads(out)
    assert payload["scope"]["ref"] == "sr:SR-001"
    assert len(payload["sections"]) == 4


def test_guide_without_json_flag_prints_human_readable_text(tmp_path, capsys):
    write_sr(tmp_path / "requirements", "SR-001", statement="When X happens, the system shall Y.")
    rc = main(["guide", "--scope", "sr:SR-001", "--repo-root", str(tmp_path)])
    out = capsys.readouterr().out
    assert rc == 0
    with pytest.raises(json.JSONDecodeError):
        json.loads(out)
    assert "sr:SR-001" in out


def test_guide_without_export_flag_writes_nothing(tmp_path, capsys):
    write_sr(tmp_path / "requirements", "SR-001")
    before = {p for p in tmp_path.rglob("*") if p.is_file()}
    rc = main(["guide", "--scope", "sr:SR-001", "--repo-root", str(tmp_path), "--json"])
    after = {p for p in tmp_path.rglob("*") if p.is_file()}
    assert rc == 0
    assert before == after


def test_guide_with_export_flag_writes_the_requested_file(tmp_path, capsys):
    write_sr(tmp_path / "requirements", "SR-001")
    dest = tmp_path / "out" / "guide.json"
    rc = main(
        [
            "guide", "--scope", "sr:SR-001", "--repo-root", str(tmp_path), "--json",
            "--export", str(dest),
        ]
    )
    captured = capsys.readouterr()
    assert rc == 0
    assert dest.is_file()
    exported = json.loads(dest.read_text(encoding="utf-8"))
    assert exported["artifact"] == "system_guide_export"

    # stdout stays pure JSON, parseable end to end; the export confirmation
    # (review round 1: cmd_guide previously discarded the written path)
    # goes to stderr, naming the actual resolved path.
    json.loads(captured.out)
    assert "guide exported to" in captured.err
    assert str(dest.resolve()) in captured.err


def test_guide_with_export_flag_confirms_the_resolved_path_on_stderr_without_json_flag(tmp_path, capsys):
    write_sr(tmp_path / "requirements", "SR-001")
    dest = tmp_path / "out" / "guide.json"
    rc = main(["guide", "--scope", "sr:SR-001", "--repo-root", str(tmp_path), "--export", str(dest)])
    captured = capsys.readouterr()
    assert rc == 0
    with pytest.raises(json.JSONDecodeError):
        json.loads(captured.out)
    assert "guide exported to" in captured.err
    assert str(dest.resolve()) in captured.err


def _minimal_repo_with_one_unbundled_sr(tmp_path):
    (tmp_path / "requirements").mkdir()
    (tmp_path / "requirements" / "SR-001.md").write_text(
        "---\nid: SR-001\ntitle: One\nstatement: x\ndomain: behavioral\n---\n",
        encoding="utf-8",
    )
    return tmp_path


def test_coverage_json_reports_per_kind_totals(tmp_path, capsys):
    repo = _minimal_repo_with_one_unbundled_sr(tmp_path)

    exit_code = main(["coverage", "--repo-root", str(repo), "--json"])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["total"] == 1
    assert payload["bundled"] == 0
    assert payload["unbundled"] == ["sr:SR-001"]


def test_coverage_without_gate_exits_zero_even_when_artifacts_are_unbundled(tmp_path, capsys):
    repo = _minimal_repo_with_one_unbundled_sr(tmp_path)

    assert main(["coverage", "--repo-root", str(repo)]) == 0


def test_coverage_gate_fails_and_names_every_unbundled_artifact(tmp_path, capsys):
    repo = _minimal_repo_with_one_unbundled_sr(tmp_path)

    exit_code = main(["coverage", "--repo-root", str(repo), "--gate"])

    assert exit_code == 2
    assert "sr:SR-001" in capsys.readouterr().out


def test_coverage_gate_with_force_exits_zero_and_says_what_it_suppressed(tmp_path, capsys):
    repo = _minimal_repo_with_one_unbundled_sr(tmp_path)

    exit_code = main(["coverage", "--repo-root", str(repo), "--gate", "--force"])

    captured = capsys.readouterr()
    assert exit_code == 0
    # A silent override would make the gate decorative. The note goes to
    # stderr so a `--json` stdout stays pure for machine consumers.
    assert "forced" in captured.err.lower()
    assert "sr:SR-001" in captured.out
    assert captured.err


def test_coverage_gate_passes_when_everything_is_bundled(tmp_path, capsys):
    repo = _minimal_repo_with_one_unbundled_sr(tmp_path)
    (repo / "bundles").mkdir()
    (repo / "bundles" / "all.json").write_text(
        json.dumps({"id": "all", "label": "All", "members": ["sr:SR-001"]}), encoding="utf-8"
    )

    assert main(["coverage", "--repo-root", str(repo), "--gate"]) == 0


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


def _repo_with_two_srs(tmp_path):
    (tmp_path / "requirements").mkdir()
    for sr_id in ("SR-001", "SR-002"):
        (tmp_path / "requirements" / f"{sr_id}.md").write_text(
            f"---\nid: {sr_id}\ntitle: {sr_id}\nstatement: x\ndomain: behavioral\n---\n",
            encoding="utf-8",
        )
    (tmp_path / "bundles").mkdir()
    return tmp_path


def _draft(tmp_path, name, payload):
    path = tmp_path / name
    path.write_text(json.dumps(payload), encoding="utf-8")
    return str(path)


def test_bundle_check_reports_resolution_and_coverage_delta(tmp_path, capsys):
    repo = _repo_with_two_srs(tmp_path)
    draft = _draft(
        tmp_path, "draft.json", {"id": "one", "label": "One", "members": ["sr:SR-001"]}
    )

    exit_code = main(["bundle", "check", "--draft", draft, "--repo-root", str(repo), "--json"])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["members_total"] == 1
    assert payload["members_resolved"] == 1
    assert payload["unresolved"] == []
    assert payload["coverage_before"] == {"bundled": 0, "total": 2}
    assert payload["coverage_after"] == {"bundled": 1, "total": 2}


def test_bundle_check_names_unresolved_members(tmp_path, capsys):
    repo = _repo_with_two_srs(tmp_path)
    draft = _draft(
        tmp_path,
        "draft.json",
        {"id": "typo", "label": "Typo", "members": ["sr:SR-999", "adr:ADR-0404"]},
    )

    main(["bundle", "check", "--draft", draft, "--repo-root", str(repo), "--json"])

    payload = json.loads(capsys.readouterr().out)
    assert payload["members_resolved"] == 0
    assert payload["unresolved"] == ["sr:SR-999", "adr:ADR-0404"]


def test_bundle_check_reports_overlap_with_an_existing_bundle(tmp_path, capsys):
    repo = _repo_with_two_srs(tmp_path)
    (repo / "bundles" / "existing.json").write_text(
        json.dumps({"id": "existing", "label": "Existing", "members": ["sr:SR-001"]}),
        encoding="utf-8",
    )
    draft = _draft(
        tmp_path, "draft.json", {"id": "new", "label": "New", "members": ["sr:SR-001"]}
    )

    main(["bundle", "check", "--draft", draft, "--repo-root", str(repo), "--json"])

    payload = json.loads(capsys.readouterr().out)
    # Multi-membership is legal, so this is information, not an error.
    assert payload["overlaps"] == [{"member": "sr:SR-001", "bundles": ["existing"]}]


def test_bundle_check_flags_an_id_that_does_not_match_its_filename(tmp_path, capsys):
    repo = _repo_with_two_srs(tmp_path)
    draft = _draft(
        tmp_path, "misnamed.json", {"id": "other", "label": "Other", "members": []}
    )

    main(["bundle", "check", "--draft", draft, "--repo-root", str(repo), "--json"])

    payload = json.loads(capsys.readouterr().out)
    assert payload["id_matches_filename"] is False


def test_bundle_check_reads_a_draft_from_stdin(tmp_path, capsys, monkeypatch):
    repo = _repo_with_two_srs(tmp_path)
    monkeypatch.setattr(
        "sys.stdin",
        io.StringIO(json.dumps({"id": "piped", "label": "Piped", "members": ["sr:SR-002"]})),
    )

    exit_code = main(["bundle", "check", "--draft", "-", "--repo-root", str(repo), "--json"])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["members_resolved"] == 1
    # There is no filename to compare against when the draft is piped.
    assert payload["id_matches_filename"] is None
