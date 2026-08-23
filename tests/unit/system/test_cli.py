"""Tests for factory.system.cli: brief/matrix/timeline/story/guide/scope
subcommands.

JSON is emitted only on `--json`; structured errors go to stderr with a
non-zero exit code.
"""
from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path

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
    # sr: scopes leave the listing (SP-B Task 3); bundle: scopes remain.
    assert refs == {"bundle:b1"}


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


def test_health_subcommand_emits_composed_projection(tmp_path, capsys):
    write_sr(tmp_path / "requirements", "SR-001")
    write_bundle(tmp_path / "bundles", "b1", "B1", ["sr:SR-001"])

    rc = main(["health", "--repo-root", str(tmp_path), "--json"])
    out = capsys.readouterr().out
    assert rc == 0
    payload = json.loads(out)
    assert "bundles" in payload and "health" in payload
    assert "coverage" in payload
    assert payload["sr_listed"] is False


def test_dossier_json_flag_emits_all_sections_for_a_bundle(tmp_path, capsys):
    write_sr(tmp_path / "requirements", "SR-001")
    write_bundle(tmp_path / "bundles", "b1", "B1", ["sr:SR-001"])

    rc = main(["dossier", "--scope", "bundle:b1", "--repo-root", str(tmp_path), "--json"])
    out = capsys.readouterr().out
    assert rc == 0
    payload = json.loads(out)
    assert payload["scope"] == {"kind": "bundle", "ref": "bundle:b1"}
    assert payload["brief"]["claims"]
    assert payload["matrix"]["rows"]
    assert "events" in payload["timeline"]
    assert payload["validation"] is None
    assert payload["vcycle"] is None
    # Every section is present as a key, even when null, so the browser can
    # branch on the same shape for every scope kind.
    assert set(payload) == {
        "scope", "brief", "matrix", "timeline",
        "guide", "guide_error", "vcycle", "vcycle_error",
        "validation", "validation_error",
    }


def test_dossier_without_json_flag_prints_human_readable_text(tmp_path, capsys):
    write_sr(tmp_path / "requirements", "SR-001")
    write_bundle(tmp_path / "bundles", "b1", "B1", ["sr:SR-001"])

    rc = main(["dossier", "--scope", "bundle:b1", "--repo-root", str(tmp_path)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "scope: bundle:b1" in out
    assert "brief:" in out and "matrix:" in out and "timeline:" in out
    with pytest.raises(json.JSONDecodeError):
        json.loads(out)


def test_dossier_unknown_scope_exits_nonzero_with_structured_stderr(tmp_path, capsys):
    rc = main(["dossier", "--scope", "bundle:missing", "--repo-root", str(tmp_path), "--json"])
    err = capsys.readouterr().err
    assert rc == 1
    assert json.loads(err)["kind"] == "ScopeNotFoundError"


def test_health_without_json_flag_prints_human_readable_text(tmp_path, capsys):
    write_sr(tmp_path / "requirements", "SR-001")
    write_bundle(tmp_path / "bundles", "b1", "B1", ["sr:SR-001"])

    rc = main(["health", "--repo-root", str(tmp_path)])
    out = capsys.readouterr().out
    assert rc == 0
    with pytest.raises(json.JSONDecodeError):
        json.loads(out)
    assert "health:" in out
    assert "b1" in out


def test_memberships_subcommand_reports_containing_bundles(tmp_path, capsys):
    write_sr(tmp_path / "requirements", "SR-001")
    write_bundle(tmp_path / "bundles", "b1", "B1", ["sr:SR-001"])
    write_bundle(tmp_path / "bundles", "b2", "B2", ["sr:SR-001"])

    rc = main(["memberships", "sr:SR-001", "--repo-root", str(tmp_path), "--json"])
    out = capsys.readouterr().out
    assert rc == 0
    payload = json.loads(out)
    assert payload["ref"] == "sr:SR-001"
    assert payload["bundles"] == ["b1", "b2"]


def test_memberships_for_ref_in_no_bundle_is_empty(tmp_path, capsys):
    write_sr(tmp_path / "requirements", "SR-001")

    rc = main(["memberships", "sr:SR-001", "--repo-root", str(tmp_path), "--json"])
    out = capsys.readouterr().out
    assert rc == 0
    assert json.loads(out)["bundles"] == []


def test_memberships_without_json_flag_prints_human_readable_text(tmp_path, capsys):
    write_sr(tmp_path / "requirements", "SR-001")
    write_bundle(tmp_path / "bundles", "b1", "B1", ["sr:SR-001"])

    rc = main(["memberships", "sr:SR-001", "--repo-root", str(tmp_path)])
    out = capsys.readouterr().out
    assert rc == 0
    with pytest.raises(json.JSONDecodeError):
        json.loads(out)
    assert "sr:SR-001" in out
    assert "b1" in out


def test_module_invocation_matches_python_dash_m_factory_system(tmp_path):
    # Design SS5.1/SS12: invocation is exactly `python -m factory.system`,
    # mirroring factory.trace.__main__ (spawnSync shape trace-cli.ts uses).
    import subprocess
    import sys

    write_sr(tmp_path / "requirements", "SR-001")
    write_bundle(tmp_path / "bundles", "b1", "Bundle One", ["sr:SR-001"])
    result = subprocess.run(
        [sys.executable, "-m", "factory.system", "scope", "--repo-root", str(tmp_path), "--json"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    # sr: is no longer listed (SP-B Task 3); the containing bundle is.
    assert payload["scopes"] == [{"kind": "bundle", "ref": "bundle:b1"}]


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


def _write_feature_repo(root: Path) -> None:
    """A minimal repo with one feature, its requirement, goal and metric."""
    (root / "docs" / "features").mkdir(parents=True, exist_ok=True)
    (root / "docs" / "features" / "FEAT-CLI-001.md").write_text(
        "---\n"
        "id: FEAT-CLI-001\n"
        "title: CLI feature\n"
        "contains: [SR-001]\n"
        "---\n\n"
        "Provide a trace-backed dossier through the CLI.\n",
        encoding="utf-8",
    )
    write_sr(root / "requirements", "SR-001")
    (root / "goals").mkdir(exist_ok=True)
    (root / "goals" / "GOAL-CLI-001.md").write_text(
        "---\n"
        "id: GOAL-CLI-001\n"
        "title: CLI goal\n"
        "demonstrates: [SR-001]\n"
        "evaluates: [MET-CLI-001]\n"
        "---\n",
        encoding="utf-8",
    )
    (root / "metrics").mkdir(exist_ok=True)
    (root / "metrics" / "MET-CLI-001.md").write_text(
        "---\n"
        "id: MET-CLI-001\n"
        "title: CLI metric\n"
        "---\n",
        encoding="utf-8",
    )


def test_brief_feat_scope_renders_the_dossier(tmp_path, capsys):
    _write_feature_repo(tmp_path)
    rc = main(["brief", "--scope", "feat:FEAT-CLI-001", "--repo-root", str(tmp_path)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "FEAT-CLI-001" in out
    assert "intent:" in out
    assert "SR-001" in out
    assert "GOAL-CLI-001" in out
    assert "MET-CLI-001" in out


def test_brief_feat_json_flag_prints_the_dossier_payload(tmp_path, capsys):
    _write_feature_repo(tmp_path)
    rc = main(["brief", "--scope", "feat:FEAT-CLI-001", "--repo-root", str(tmp_path), "--json"])
    out = capsys.readouterr().out
    assert rc == 0
    payload = json.loads(out)
    assert payload["scope"]["ref"] == "feat:FEAT-CLI-001"
    assert payload["dossier"]["id"] == "FEAT-CLI-001"
    assert [r["id"] for r in payload["dossier"]["requirements"]] == ["SR-001"]
    assert payload["dossier"]["goal_ids"] == ["GOAL-CLI-001"]
    assert payload["dossier"]["metric_ids"] == ["MET-CLI-001"]


def test_brief_feat_unknown_scope_fails_with_structured_error(tmp_path, capsys):
    _write_feature_repo(tmp_path)
    rc = main(["brief", "--scope", "feat:FEAT-UNKNOWN", "--repo-root", str(tmp_path)])
    err = capsys.readouterr().err
    assert rc == 1
    assert "FEAT-UNKNOWN" in err


def test_vcycle_feat_scope_renders_the_slice(tmp_path, capsys):
    _write_feature_repo(tmp_path)
    rc = main(["vcycle", "--scope", "feat:FEAT-CLI-001", "--repo-root", str(tmp_path)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "anchor: feat:FEAT-CLI-001" in out
    assert "SYSTEM_REQUIREMENTS: SR-001" in out
    assert "SIMULATION_VERIFICATION: GOAL-CLI-001, MET-CLI-001" in out


def test_vcycle_json_flag_prints_the_slice_payload(tmp_path, capsys):
    _write_feature_repo(tmp_path)
    rc = main(["vcycle", "--scope", "feat:FEAT-CLI-001", "--repo-root", str(tmp_path), "--json"])
    out = capsys.readouterr().out
    assert rc == 0
    payload = json.loads(out)
    assert payload["vcycle"]["anchor"] == "feat:FEAT-CLI-001"
    assert [n["id"] for n in payload["vcycle"]["goals"]] == ["GOAL-CLI-001"]


def _seed_sim_runs(root: Path) -> None:
    """Seed two simulation run manifests (one pass, one fail) for a feature."""
    from factory.evidence.manifests import write_run_manifest

    evidence = root / "evidence"
    evidence.mkdir(parents=True, exist_ok=True)
    write_run_manifest(
        evidence,
        {
            "run": "RUN-2",
            "experiment": "SIM-X",
            "feature": "FEAT-CLI-001",
            "requirements": [],
            "goals": ["GOAL-CLI-001"],
            "commit": "f92b004",
            "result": "failed",
        },
    )
    write_run_manifest(
        evidence,
        {
            "run": "RUN-3",
            "experiment": "SIM-X",
            "feature": "FEAT-CLI-001",
            "requirements": [],
            "goals": ["GOAL-CLI-001"],
            "commit": "f92b005",
            "result": "passed",
        },
    )


def _write_goal_file(root: Path, goal_id: str = "GOAL-CLI-001") -> None:
    (root / "goals").mkdir(exist_ok=True)
    (root / "goals" / f"{goal_id}.md").write_text(
        "---\n"
        f"id: {goal_id}\n"
        "title: CLI goal\n"
        "feature: [FEAT-CLI-001]\n"
        "requirements: [SR-001]\n"
        "metric: m\n"
        "source_experiment: SIM-X\n"
        "target: '>=0.9'\n"
        "---\n",
        encoding="utf-8",
    )


def test_diagram_subcommand_renders_and_json(tmp_path, capsys):
    (tmp_path / "docs" / "diagrams").mkdir(parents=True)
    (tmp_path / "docs" / "diagrams" / "DIAG-CLI-001.md").write_text(
        "---\nid: DIAG-CLI-001\ntitle: CLI diagram\ndiagram_file: assets/overview.html\n---\n",
        encoding="utf-8",
    )
    rc = main(["diagram", "DIAG-CLI-001", "--repo-root", str(tmp_path), "--json"])
    out = capsys.readouterr().out
    assert rc == 0
    payload = json.loads(out)
    assert payload["id"] == "DIAG-CLI-001"
    # The declared file does not exist, so path is None and errors are listed.
    assert payload["diagram_path"] is None
    assert payload["errors"]


def test_sim_latest_returns_most_recent_run_for_feature(tmp_path, capsys):
    _seed_sim_runs(tmp_path)
    rc = main(["sim", "latest", "--feature", "FEAT-CLI-001", "--repo-root", str(tmp_path), "--json"])
    out = capsys.readouterr().out
    assert rc == 0
    payload = json.loads(out)
    assert payload["run"] == "RUN-3"
    assert payload["result"] == "passed"


def test_sim_failure_returns_most_recent_failed_run(tmp_path, capsys):
    _seed_sim_runs(tmp_path)
    rc = main(["sim", "failure", "--feature", "FEAT-CLI-001", "--repo-root", str(tmp_path), "--json"])
    out = capsys.readouterr().out
    assert rc == 0
    payload = json.loads(out)
    assert payload["run"] == "RUN-2"
    assert payload["result"] == "failed"


def test_sim_goal_evidence_lists_runs_for_goal(tmp_path, capsys):
    _seed_sim_runs(tmp_path)
    rc = main(["sim", "goal-evidence", "--goal", "GOAL-CLI-001", "--repo-root", str(tmp_path), "--json"])
    out = capsys.readouterr().out
    assert rc == 0
    payload = json.loads(out)
    assert payload["goal"] == "GOAL-CLI-001"
    assert [r["run"] for r in payload["runs"]] == ["RUN-2", "RUN-3"]


def test_goal_show_and_list_subcommands(tmp_path, capsys):
    _write_feature_repo(tmp_path)
    # Seed a goal that binds to the feature by frontmatter so feat-scope
    # listing resolves it (the _write_feature_repo goal only demonstrates SR).
    _write_goal_file(tmp_path)
    rc = main(["goal", "show", "GOAL-CLI-001", "--repo-root", str(tmp_path), "--json"])
    out = capsys.readouterr().out
    assert rc == 0
    payload = json.loads(out)
    assert payload["id"] == "GOAL-CLI-001"

    rc = main(["goal", "list", "--scope", "feat:FEAT-CLI-001", "--repo-root", str(tmp_path), "--json"])
    out = capsys.readouterr().out
    assert rc == 0
    payload = json.loads(out)
    assert payload["scope"] == "feat:FEAT-CLI-001"
    assert "GOAL-CLI-001" in [g["id"] for g in payload["goals"]]


def _write_goal_evaluate_fixture(root: Path, state: str = "EVALUATING") -> None:
    """A goal in an evaluable state plus one SIM-X run with a measurable metric."""
    (root / "goals").mkdir(parents=True, exist_ok=True)
    (root / "goals" / "GOAL-CLI-001.md").write_text(
        "---\n"
        "id: GOAL-CLI-001\n"
        "title: CLI goal\n"
        "feature: [FEAT-CLI-001]\n"
        "requirements: [SR-001]\n"
        "metric: {name: m, source_experiment: SIM-X}\n"
        "target: {operator: \">=\", value: 0.9}\n"
        f"state: {state}\n"
        "---\n",
        encoding="utf-8",
    )
    from factory.evidence.manifests import write_run_manifest

    evidence = root / "evidence"
    evidence.mkdir(parents=True, exist_ok=True)
    man = write_run_manifest(
        evidence,
        {
            "run": "RUN-1",
            "experiment": "SIM-X",
            "feature": "FEAT-CLI-001",
            "requirements": [],
            "goals": ["GOAL-CLI-001"],
            "commit": "abc",
            "result": "passed",
        },
    )
    (man.parent / "metrics.json").write_text(json.dumps({"m": 0.93}), encoding="utf-8")


def test_goal_evaluate_records_a_legal_transition(tmp_path, capsys):
    _write_goal_evaluate_fixture(tmp_path, state="EVALUATING")
    rc = main(["goal", "evaluate", "GOAL-CLI-001", "--repo-root", str(tmp_path), "--json"])
    out = capsys.readouterr().out
    assert rc == 0
    payload = json.loads(out)
    assert payload["evaluated"] is True
    assert payload["transition"] == {"from": "EVALUATING", "to": "REACHED", "legal": True}
    assert payload["derived"]["value"] == 0.93
    # The goal file's state was actually persisted.
    rc = main(["goal", "show", "GOAL-CLI-001", "--repo-root", str(tmp_path), "--json"])
    assert json.loads(capsys.readouterr().out)["state"] == "REACHED"


def test_goal_evaluate_refuses_illegal_lifecycle_edge(tmp_path, capsys):
    _write_goal_evaluate_fixture(tmp_path, state="DECLARED")
    rc = main(["goal", "evaluate", "GOAL-CLI-001", "--repo-root", str(tmp_path), "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert payload["evaluated"] is False
    assert payload["transition"] is None
    assert payload["derived"]["state"] == "REACHED"


def test_goal_evaluate_unknown_goal_is_a_structured_error(tmp_path, capsys):
    (tmp_path / "goals").mkdir(parents=True, exist_ok=True)
    rc = main(["goal", "evaluate", "GOAL-NOPE", "--repo-root", str(tmp_path), "--json"])
    err = capsys.readouterr().err
    assert rc == 1
    assert "no goal with id" in err


def test_present_routes_to_router(tmp_path, capsys):
    rc = main(["present", "feat:FEAT-NAV-017", "--focus", "overview", "--repo-root", str(tmp_path), "--json"])
    out = capsys.readouterr().out
    assert rc == 0
    payload = json.loads(out)
    assert payload["artifact"] == "feat:FEAT-NAV-017"
    assert payload["focus"] == "overview"
    assert payload["level"] == "INSPECT"
    assert payload["intent"] == {"artifact": "feat:FEAT-NAV-017", "focus": "overview"}
    assert payload["adapter"] == "browser"
    assert payload["target"] == "system?scope=feat:FEAT-NAV-017"


def test_present_routes_with_level_override(tmp_path, capsys):
    rc = main(["present", "sr:SR-066", "--level", "PRESENT", "--repo-root", str(tmp_path), "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert payload["level"] == "PRESENT"
    assert "PRESENT" in payload["resolution"]


def test_present_rejects_empty_artifact(tmp_path, capsys):
    rc = main(["present", "", "--repo-root", str(tmp_path), "--json"])
    err = capsys.readouterr().err
    assert rc == 1
    assert "non-empty artifact" in err


def _seed_gates(root: Path) -> None:
    (root / ".factory").mkdir(exist_ok=True)
    (root / ".factory" / "factory.yaml").write_text(
        "gates:\n  unit:\n  - { cmd: 'pytest -m unit -q' }\n", encoding="utf-8",
    )


def test_obligations_project_scope_renders_and_json(tmp_path, capsys):
    _seed_gates(tmp_path)
    rc = main(["obligations", "--scope", "project", "--repo-root", str(tmp_path), "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert payload["scope_ref"] == "project"
    assert payload["profile"] == "prototype"
    ci = next(o for o in payload["obligations"] if o["kind"] == "ci_verification")
    assert ci["scope_ref"] == "project"
    assert ci["source_policy"] == "prototype"


def test_obligations_rejects_garbage_scope_with_structured_error(tmp_path, capsys):
    """review finding #6: --scope must not silently accept an arbitrary
    string and return project-default obligations mislabeled with it."""
    _seed_gates(tmp_path)
    rc = main(["obligations", "--scope", "garbage", "--repo-root", str(tmp_path), "--json"])
    err = capsys.readouterr().err
    assert rc == 1
    assert "invalid scope ref" in err


def test_obligations_rejects_unknown_declared_kind_id_with_structured_error(tmp_path, capsys):
    """A supported scope kind with an undeclared id must fail closed at the
    CLI boundary instead of inheriting project-default obligations."""
    _seed_gates(tmp_path)
    rc = main([
        "obligations", "--scope", "goal:GOAL-DOES-NOT-EXIST",
        "--repo-root", str(tmp_path), "--json",
    ])
    err = capsys.readouterr().err
    assert rc == 1
    assert "not declared" in err
    assert "ScopeNotFoundError" in err


def test_obligations_accepts_a_real_trace_scope(tmp_path, capsys):
    _seed_gates(tmp_path)
    write_sr(tmp_path / "requirements", "SR-001")
    rc = main(["obligations", "--scope", "sr:SR-001", "--repo-root", str(tmp_path), "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert payload["scope_ref"] == "sr:SR-001"


def test_present_why_required_calls_why_required_for_relevant_obligation(tmp_path, capsys):
    """Blocking finding #1: not just that an 'obligations' key exists, but
    that why_required actually ran for the relevant obligation(s)."""
    _seed_gates(tmp_path)
    write_sr(tmp_path / "requirements", "SR-001")
    rc = main([
        "present", "sr:SR-001", "--why-required", "--repo-root", str(tmp_path), "--json",
    ])
    payload = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert payload["obligations"] is not None
    ci = next(o for o in payload["obligations"] if o["kind"] == "ci_verification")
    assert ci["why"] is not None
    assert "prototype" in ci["why"]


def test_present_why_required_is_additive_and_off_by_default(tmp_path, capsys):
    _seed_gates(tmp_path)
    # Create the feature so it has a policy scope
    (tmp_path / "docs" / "features").mkdir(parents=True, exist_ok=True)
    (tmp_path / "docs" / "features" / "FEAT-NAV-017.md").write_text(
        "---\nid: FEAT-NAV-017\ntitle: Test Feature\ncontains: [SR-001]\n---\n\nTest feature description\n",
        encoding="utf-8",
    )
    write_sr(tmp_path / "requirements", "SR-001")

    rc = main(["present", "feat:FEAT-NAV-017", "--repo-root", str(tmp_path), "--json"])
    baseline = json.loads(capsys.readouterr().out)
    assert "obligations" not in baseline

    rc = main([
        "present", "feat:FEAT-NAV-017", "--why-required", "--repo-root", str(tmp_path), "--json",
    ])
    with_why = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert baseline.keys() <= with_why.keys()
    assert with_why["obligations"] is not None


def test_present_why_required_skips_non_scope_artifact(tmp_path, capsys):
    """review finding #7: a raw file path must not fall through to
    mislabeled project-default obligations."""
    _seed_gates(tmp_path)
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_text("# x\n", encoding="utf-8")
    rc = main([
        "present", "src/a.py", "--why-required", "--repo-root", str(tmp_path), "--json",
    ])
    payload = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert payload["obligations"] is None
    assert payload["obligations_note"] == "no policy scope for this artifact kind"


def test_obligations_renderer_handles_stale_scope_result():
    from factory.system.cli import _render_obligations

    rendered = _render_obligations({
        "scope": {"kind": "sr", "ref": "sr:SR-001"},
        "stale": True,
        "freshness": "stale",
        "snapshot": {"ref": "sr:SR-001"},
        "resolver": "coherence navigate snapshot refresh --ref sr:SR-001",
        "message": "navigation input is not current",
    })
    assert "stale: true" in rendered
    assert "navigation input is not current" in rendered


def test_obligations_renderer_handles_malformed_payload_without_crashing():
    from factory.system.cli import _render_obligations

    rendered = _render_obligations({
        "scope_ref": "project",
        "profile": "prototype",
        "obligations": [{"kind": "ci_verification"}, "not-an-obligation"],
    })
    assert "malformed obligation[0]" in rendered
    assert "malformed obligation[1]" in rendered
