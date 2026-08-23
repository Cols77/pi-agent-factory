"""Tests for factory.system.worker: the JSON-lines docs-server protocol."""
from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path

import pytest

from factory.evidence.manifests import write_run_manifest
from factory.system.worker import run_worker

from ._fixtures import (
    _write_task_fixture,  # noqa: F401 -- registers the `write_task` fixture used below
    write_bundle as write_bundle_file,
    write_sr,
)

pytestmark = pytest.mark.unit


def _run_lines(repo_root: Path, lines: list[str]) -> list[str]:
    reader = io.StringIO("\n".join(lines) + "\n")
    writer = io.StringIO()
    exit_code = run_worker(repo_root, reader, writer)
    assert exit_code == 0
    outputs = writer.getvalue().splitlines()
    assert len(outputs) == len(lines), (
        f"one output line per request expected, got {len(outputs)} for {len(lines)}"
    )
    return [json.loads(line) for line in outputs]


def test_scope_and_health_respond(tmp_path):
    responses = _run_lines(tmp_path, [
        json.dumps({"id": 1, "cmd": "scope", "params": {}}),
        json.dumps({"id": 2, "cmd": "health", "params": {}}),
    ])
    assert responses[0] == {"id": 1, "ok": True, "value": {"scopes": [], "errors": []}}
    assert responses[1]["ok"] is True and "health" in responses[1]["value"]


def test_dossier_for_bundle_scope(tmp_path):
    write_bundle_file(tmp_path / "bundles", "lifecycle", "Evidence lifecycle", ["sr:SR-001"])
    write_sr(tmp_path / "requirements", "SR-001")
    responses = _run_lines(tmp_path, [
        json.dumps({"id": 7, "cmd": "dossier", "params": {"scope": "bundle:lifecycle"}}),
    ])
    assert responses[0]["ok"] is True
    value = responses[0]["value"]
    assert value["scope"] == {"kind": "bundle", "ref": "bundle:lifecycle"}
    assert value["brief"]["claims"]
    assert value["matrix"]["rows"]
    # A bundle scope never carries vcycle/validation -- the browser renders
    # the not-applicable affordance from these nulls.
    assert value["vcycle"] is None
    assert value["validation"] is None
    assert value.get("guide") is None or value["guide"]["sections"] is not None


def test_dossier_mirrors_individual_commands(tmp_path):
    """The dossier sections are the same computed JSON as the one-shot CLI.

    This pins the promise of the worker protocol: amortizing startup must
    never change an answer. Section equality is checked structurally (the
    CLI's --json and the worker's own json.dumps may differ in whitespace).
    """
    from factory.system.cli import main as cli_main

    write_bundle_file(tmp_path / "bundles", "lifecycle", "Evidence lifecycle", ["sr:SR-001"])
    write_sr(tmp_path / "requirements", "SR-001")

    def cli_json(argv: list[str]) -> dict:
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            exit_code = cli_main([*argv, "--repo-root", str(tmp_path), "--json"])
        out.seek(0)
        assert exit_code == 0
        return json.loads(out.read())

    responses = _run_lines(tmp_path, [
        json.dumps({"id": 1, "cmd": "dossier", "params": {"scope": "bundle:lifecycle"}}),
    ])
    value = responses[0]["value"]
    for section in ("brief", "matrix", "timeline"):
        assert value[section] == cli_json([section, "--scope", "bundle:lifecycle"]), section


def test_bad_scope_returns_structured_error_not_crash(tmp_path):
    responses = _run_lines(tmp_path, [
        json.dumps({"id": 9, "cmd": "brief", "params": {"scope": "bundle:does-not-exist"}}),
    ])
    assert responses[0]["ok"] is False
    assert responses[0]["kind"] == "ScopeNotFoundError"
    assert "does-not-exist" in responses[0]["error"]
    # The worker stays alive for the next request.
    responses = _run_lines(tmp_path, [
        json.dumps({"id": 1, "cmd": "brief", "params": {"scope": "bundle:does-not-exist"}}),
        json.dumps({"id": 2, "cmd": "scope", "params": {}}),
    ])
    assert responses[0]["ok"] is False
    assert responses[1]["ok"] is True


def test_unknown_command_is_worker_protocol_error(tmp_path):
    responses = _run_lines(tmp_path, [
        json.dumps({"id": 3, "cmd": "nope", "params": {}}),
    ])
    assert responses[0] == {
        "id": 3,
        "ok": False,
        "error": "unknown worker command: 'nope'",
        "kind": "WorkerProtocolError",
    }


def test_missing_mandatory_param_is_protocol_error(tmp_path):
    responses = _run_lines(tmp_path, [
        json.dumps({"id": 4, "cmd": "brief", "params": {}}),
    ])
    assert responses[0]["ok"] is False
    assert responses[0]["kind"] == "WorkerProtocolError"


def test_malformed_json_gets_error_response_and_worker_survives(tmp_path):
    responses = _run_lines(tmp_path, [
        "this is not json",
        json.dumps({"id": 5, "cmd": "scope", "params": {}}),
    ])
    assert responses[0]["ok"] is False
    assert responses[0]["kind"] == "WorkerProtocolError"
    assert responses[1]["ok"] is True


def test_non_object_request_is_error_response(tmp_path):
    responses = _run_lines(tmp_path, [
        json.dumps([1, 2, 3]),
    ])
    assert responses[0]["ok"] is False
    assert responses[0]["kind"] == "WorkerProtocolError"


def test_eof_terminates_cleanly(tmp_path):
    reader = io.StringIO("")
    writer = io.StringIO()
    assert run_worker(tmp_path, reader, writer) == 0
    assert writer.getvalue() == ""


def test_write_commands_are_not_served(tmp_path):
    """The worker is the browser's execution engine; browser-facing commands
    with a write affordance (goal evaluate mutates goal state, guide --export
    writes a file) have no worker handler by construction."""
    responses = _run_lines(tmp_path, [
        json.dumps({"id": 6, "cmd": "goal_evaluate", "params": {"goal_id": "go"}}),
    ])
    assert responses[0]["ok"] is False
    assert responses[0]["kind"] == "WorkerProtocolError"


# --- Inc 3B Task 6: browser transport boundary coverage for goal_show/sim_run
# obligations fields --------------------------------------------------------
#
# `cmd_goal_show`/`cmd_sim_run` (Task 3, coherence.navigate.cli) attach
# additive `obligations_open`/`obligations_error` fields. The worker's
# "goal_show"/"sim_run" handlers are one-line delegations to those same
# functions (see the `_HANDLERS` table above) with no reshaping in between,
# so the tests below prove the JSON-lines round trip does not drop, rename,
# or reshape anything -- structural equality against the direct `cmd_*` call
# pins that promise the same way `test_dossier_mirrors_individual_commands`
# already does for the dossier handler.


def _seed_gates(root: Path) -> None:
    (root / ".factory").mkdir(exist_ok=True)
    (root / ".factory" / "factory.yaml").write_text(
        "gates:\n  unit:\n  - { cmd: 'pytest -m unit -q' }\n", encoding="utf-8",
    )


def _write_goal_file(root: Path, goal_id: str = "GOAL-CLI-001") -> None:
    (root / "goals").mkdir(exist_ok=True)
    (root / "goals" / f"{goal_id}.md").write_text(
        "---\n"
        f"id: {goal_id}\n"
        "title: worker goal\n"
        "feature: [FEAT-CLI-001]\n"
        "requirements: [SR-001]\n"
        "metric: m\n"
        "source_experiment: SIM-X\n"
        "target: '>=0.9'\n"
        "---\n",
        encoding="utf-8",
    )


def _seed_sim_runs(root: Path) -> None:
    """Seed one simulation run manifest for a feature (mirrors
    tests/unit/system/test_cli.py's `_seed_sim_runs`, kept local so this file
    does not reach across test modules for a private helper)."""
    evidence = root / "evidence"
    evidence.mkdir(parents=True, exist_ok=True)
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


def test_goal_show_carries_additive_obligation_fields_through_the_worker(tmp_path):
    """A goal scope with no open/blocking obligations (2B compiles no other
    kind for `goal:` scope today -- see review finding #3) reports an honest
    zero, not a fabricated positive or a dropped field."""
    from coherence.navigate.cli import cmd_goal_show

    _seed_gates(tmp_path)
    _write_goal_file(tmp_path)
    responses = _run_lines(tmp_path, [
        json.dumps({"id": 1, "cmd": "goal_show", "params": {"goal_id": "GOAL-CLI-001"}}),
    ])
    assert responses[0]["ok"] is True
    value = responses[0]["value"]
    assert value["id"] == "GOAL-CLI-001"
    assert value["obligations_open"] == 0
    assert value["obligations_error"] is None
    # No reshaping between the worker handler and the CLI's own computed dict.
    assert value == cmd_goal_show(tmp_path, "GOAL-CLI-001")


def test_sim_run_carries_additive_obligation_fields_through_the_worker(tmp_path):
    """`run:<id>` is a policy scope kind `_load_scope_graph` explicitly does
    not support (`_UNSUPPORTED_POLICY_SCOPE_KINDS`) -- this is the stable
    degraded case Task 3 made explicit, and the worker must carry the
    resulting obligations_error through unchanged rather than dropping it or
    fabricating a positive obligations_open."""
    from coherence.navigate.cli import cmd_sim_run

    _seed_gates(tmp_path)
    _seed_sim_runs(tmp_path)
    responses = _run_lines(tmp_path, [
        json.dumps({"id": 1, "cmd": "sim_run", "params": {"run_id": "RUN-3"}}),
    ])
    assert responses[0]["ok"] is True
    value = responses[0]["value"]
    assert value["run"] == "RUN-3"
    assert value["obligations_open"] == 0
    assert value["obligations_error"] == (
        "policy scope unsupported for 'run:RUN-3': load_nodes exposes no run nodes"
    )
    assert value == cmd_sim_run(tmp_path, "RUN-3")


def test_sim_run_unsupported_scope_degrades_identically_on_repeated_calls(tmp_path):
    """The degraded payload is deterministic: two requests for the same
    unsupported run scope in the same worker session must return the exact
    same shape, not merely "an error" that could vary call to call."""
    _seed_gates(tmp_path)
    _seed_sim_runs(tmp_path)
    responses = _run_lines(tmp_path, [
        json.dumps({"id": 1, "cmd": "sim_run", "params": {"run_id": "RUN-3"}}),
        json.dumps({"id": 2, "cmd": "sim_run", "params": {"run_id": "RUN-3"}}),
    ])
    assert responses[0]["ok"] is True
    assert responses[1]["ok"] is True
    assert responses[0]["value"] == responses[1]["value"]


def test_present_action_is_not_registered_in_the_worker(tmp_path):
    """The worker's `_HANDLERS` table (grepped above, in this same file's
    import block) has no "present" entry -- the browser has no write
    affordance and this plan must not add one (design note, Task 6 brief). A
    request for it must degrade to the same stable "unknown worker command"
    protocol error every other unregistered command gets, not crash and not
    silently synthesize a presentation response."""
    responses = _run_lines(tmp_path, [
        json.dumps({"id": 1, "cmd": "present", "params": {"artifact": "goal:GOAL-CLI-001"}}),
    ])
    assert responses[0] == {
        "id": 1,
        "ok": False,
        "error": "unknown worker command: 'present'",
        "kind": "WorkerProtocolError",
    }
    # The worker stays alive for the next (supported) request.
    responses = _run_lines(tmp_path, [
        json.dumps({"id": 2, "cmd": "scope", "params": {}}),
    ])
    assert responses[0]["ok"] is True


def test_goal_show_for_an_undeclared_goal_id_is_a_structured_error_not_a_crash(tmp_path):
    """A stale browser reference (a goal id no file declares any more) must
    surface as the same structured `ok: false` shape every other
    unresolvable scope gets, and the worker must survive to answer the next
    request."""
    responses = _run_lines(tmp_path, [
        json.dumps({"id": 1, "cmd": "goal_show", "params": {"goal_id": "GOAL-GONE"}}),
        json.dumps({"id": 2, "cmd": "scope", "params": {}}),
    ])
    assert responses[0]["ok"] is False
    assert responses[0]["kind"] == "ScopeNotFoundError"
    assert "GOAL-GONE" in responses[0]["error"]
    assert responses[1]["ok"] is True


def test_sim_run_for_an_undeclared_run_id_is_a_structured_error_not_a_crash(tmp_path):
    """Same stale-reference contract as goal_show, for a run id no manifest
    declares."""
    _seed_sim_runs(tmp_path)
    responses = _run_lines(tmp_path, [
        json.dumps({"id": 1, "cmd": "sim_run", "params": {"run_id": "RUN-GONE"}}),
        json.dumps({"id": 2, "cmd": "scope", "params": {}}),
    ])
    assert responses[0]["ok"] is False
    assert responses[0]["kind"] == "ScopeNotFoundError"
    assert "RUN-GONE" in responses[0]["error"]
    assert responses[1]["ok"] is True


def test_goal_show_reports_malformed_profile_as_a_degraded_obligations_error_not_a_crash(tmp_path):
    """An uncompiled preset (malformed policy configuration, not a missing
    scope) is caught inside `obligations_open_count` and folded into the
    additive `obligations_error` field -- the worker still answers `ok: true`
    with the rest of the goal payload intact, it does not propagate an
    exception through the transport boundary."""
    (tmp_path / ".factory").mkdir()
    (tmp_path / ".factory" / "factory.yaml").write_text("profile: exploration\n", encoding="utf-8")
    _write_goal_file(tmp_path)
    responses = _run_lines(tmp_path, [
        json.dumps({"id": 1, "cmd": "goal_show", "params": {"goal_id": "GOAL-CLI-001"}}),
    ])
    assert responses[0]["ok"] is True
    value = responses[0]["value"]
    assert value["id"] == "GOAL-CLI-001"
    assert value["obligations_open"] == 0
    assert value["obligations_error"] is not None
    assert "exploration" in value["obligations_error"]


def test_goal_show_with_non_string_goal_id_param_degrades_without_crashing(tmp_path):
    """A malformed param (wrong JSON type, not merely a missing key) must not
    crash the worker -- `p["goal_id"]` still reaches `cmd_goal_show`, which
    resolves it against the registry's string keys and reports a structured
    not-found error rather than raising a type error through the transport."""
    responses = _run_lines(tmp_path, [
        json.dumps({"id": 1, "cmd": "goal_show", "params": {"goal_id": 12345}}),
        json.dumps({"id": 2, "cmd": "scope", "params": {}}),
    ])
    assert responses[0]["ok"] is False
    assert responses[0]["kind"] == "ScopeNotFoundError"
    assert responses[1]["ok"] is True
