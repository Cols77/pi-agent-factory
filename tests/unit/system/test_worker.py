"""Tests for factory.system.worker: the JSON-lines docs-server protocol."""
from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path

import pytest

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
