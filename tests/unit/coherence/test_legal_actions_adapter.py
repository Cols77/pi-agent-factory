from __future__ import annotations

import json
import hashlib
import subprocess
from pathlib import Path
from typing import Any

import pytest

from coherence.planning.legal_actions_adapter import (
    SAFE_RUN_ID,
    build_legal_actions_command,
    is_safe_run_id,
    legal_actions_report,
    main,
    parse_legal_actions_projection,
    render_legal_actions_projection,
)
from tests.unit._legal_actions_json import completed_json, valid_payload

pytestmark = pytest.mark.unit


# --- run-id grammar -----------------------------------------------------


@pytest.mark.parametrize(
    "run_id",
    ["run-001", "a", "A1", "run_002", "run.003", "RUN-004"],
)
def test_safe_run_ids_accepted(run_id: str) -> None:
    assert is_safe_run_id(run_id)
    assert SAFE_RUN_ID.fullmatch(run_id)


@pytest.mark.parametrize(
    "run_id",
    [
        "",
        "../escape",
        "run 001",
        "run;rm -rf",
        "-run-001",
        ".run-001",
        "run/001",
        "run\\001",
        "run\n001",
        "run\t001",
        "$(whoami)",
        "run-001;",
    ],
)
def test_unsafe_run_ids_rejected(run_id: str) -> None:
    assert not is_safe_run_id(run_id)


# --- argv construction ---------------------------------------------------


def test_builds_argv_only_command_with_no_shell_string() -> None:
    command = build_legal_actions_command(Path("/tmp/project"), "run-001")

    assert command == [
        "uv",
        "run",
        "coherence",
        "plan",
        "legal-actions",
        "--project-root",
        str(Path("/tmp/project")),
        "--run-id",
        "run-001",
        "--json",
    ]
    assert all(isinstance(part, str) for part in command)


# --- projection parsing ---------------------------------------------------


def test_parse_accepts_valid_blocked_projection() -> None:
    payload = valid_payload(blocked=True, reason="SESSION_NOT_READY", legal_next_actions=[])

    parsed = parse_legal_actions_projection(json.dumps(payload), "run-001")

    assert parsed == payload


def _schema_two_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema": 2,
        "run_id": "run-001",
        "blocked": False,
        "reason": None,
        "state": "capture",
        "legal_next_actions": ["author-requirements"],
        "starts_automatically": False,
        "run_identity": {
            "run_id": "run-001",
            "next_sequence": 2,
            "journal_sha256": "a" * 64,
        },
        "action_registry": {
            "schema": 1,
            "legal_ids": ["author-requirements"],
            "registry_hash": hashlib.sha256(b"author-requirements").hexdigest(),
        },
    }
    payload.update(overrides)
    return payload


def test_parse_accepts_schema_two_single_action_projection() -> None:
    payload = _schema_two_payload()

    assert parse_legal_actions_projection(json.dumps(payload), "run-001") == payload


def test_parse_rejects_schema_two_multiple_actions() -> None:
    payload = _schema_two_payload(
        legal_next_actions=["author-requirements", "record-sr-consent"]
    )

    with pytest.raises(ValueError, match="invalid planning legal-actions response"):
        parse_legal_actions_projection(json.dumps(payload), "run-001")


def test_parse_rejects_schema_two_missing_lifecycle_identity() -> None:
    payload = _schema_two_payload()
    payload.pop("run_identity")

    with pytest.raises(ValueError, match="invalid planning legal-actions response"):
        parse_legal_actions_projection(json.dumps(payload), "run-001")


@pytest.mark.parametrize("identity", [None, {}, {"run_id": "other-run"}])
def test_parse_rejects_unblocked_projection_without_matching_identity(identity: object) -> None:
    payload = _schema_two_payload(run_identity=identity)

    with pytest.raises(ValueError):
        parse_legal_actions_projection(json.dumps(payload), "run-001")


def test_parse_rejects_multiple_actions_in_legacy_schema() -> None:
    payload = valid_payload(legal_next_actions=["author-spec", "author-plan"])

    with pytest.raises(ValueError):
        parse_legal_actions_projection(json.dumps(payload), "run-001")


@pytest.mark.parametrize("changes", [
    {"schema": 2},
    {"registry_hash": "bad-hash"},
    {"registry_hash": "0" * 64},
    {"legal_ids": ["author-requirements", "author-requirements"]},
])
def test_parse_rejects_invalid_action_registry(changes: dict[str, object]) -> None:
    payload = _schema_two_payload()
    payload["action_registry"].update(changes)

    with pytest.raises(ValueError):
        parse_legal_actions_projection(json.dumps(payload), "run-001")


@pytest.mark.parametrize("changes", [
    {"next_sequence": True},
    {"next_sequence": 0},
    {"journal_sha256": "not-a-digest"},
])
def test_parse_rejects_invalid_run_identity(changes: dict[str, object]) -> None:
    payload = _schema_two_payload()
    payload["run_identity"].update(changes)

    with pytest.raises(ValueError):
        parse_legal_actions_projection(json.dumps(payload), "run-001")


def test_parse_accepts_blocked_projection_without_identity() -> None:
    payload = _schema_two_payload(
        blocked=True, reason="STALE_SESSION_STATE", legal_next_actions=[], run_identity=None
    )

    assert parse_legal_actions_projection(json.dumps(payload), "run-001") == payload


def test_parse_rejects_invalid_json() -> None:
    with pytest.raises(ValueError, match="invalid planning legal-actions response"):
        parse_legal_actions_projection("not json", "run-001")


def test_parse_rejects_run_id_mismatch() -> None:
    payload = valid_payload(run_id="other-run")

    with pytest.raises(ValueError):
        parse_legal_actions_projection(json.dumps(payload), "run-001")


def test_parse_rejects_starts_automatically_true() -> None:
    payload = valid_payload(starts_automatically=True)

    with pytest.raises(ValueError):
        parse_legal_actions_projection(json.dumps(payload), "run-001")


# --- rendering -------------------------------------------------------------


def test_render_ready_projection() -> None:
    payload = valid_payload(legal_next_actions=["inspect-handoff"])

    assert render_legal_actions_projection(payload) == (
        "Planning ready\nLegal actions: inspect-handoff\nStarts automatically: no"
    )


def test_render_blocked_projection_with_reason() -> None:
    payload = valid_payload(blocked=True, reason="HANDOFF_INVALID", legal_next_actions=[])

    assert render_legal_actions_projection(payload) == (
        "Planning blocked: HANDOFF_INVALID\nLegal actions: none\nStarts automatically: no"
    )


def test_render_blocked_projection_falls_back_to_unknown_reason() -> None:
    payload = valid_payload(blocked=True, reason=None, legal_next_actions=[])

    assert render_legal_actions_projection(payload).startswith("Planning blocked: UNKNOWN")


# --- legal_actions_report: end-to-end orchestration ------------------------


def test_report_rejects_unsafe_run_id_without_invoking_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[Any] = []
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: calls.append(args))

    with pytest.raises(ValueError):
        legal_actions_report(Path.cwd(), "../escape; uv run coherence plan")

    assert calls == []


def test_report_exit_0_with_valid_payload_renders_ready(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = valid_payload(blocked=False, reason=None, legal_next_actions=["inspect-handoff"])
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: completed_json(payload, returncode=0))

    output = legal_actions_report(Path.cwd(), "run-001")

    assert output == "Planning ready\nLegal actions: inspect-handoff\nStarts automatically: no"


def test_report_exit_1_with_valid_blocked_payload_surfaces_reason(monkeypatch: pytest.MonkeyPatch) -> None:
    """The bug this module traces back to: exit code 1 is the CLI's normal
    "planning is blocked" signal, not a backend failure. The structured
    payload's reason must still be parsed and rendered, not replaced by a
    generic failure message."""
    payload = valid_payload(blocked=True, reason="STALE_SESSION_STATE", legal_next_actions=["resolve-blocking-input"])
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: completed_json(payload, returncode=1))

    output = legal_actions_report(Path.cwd(), "run-001")

    assert "STALE_SESSION_STATE" in output
    assert "resolve-blocking-input" in output
    assert "backend exited unsuccessfully" not in output


def test_report_nonzero_exit_never_trusts_stdout_even_if_valid_json(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = valid_payload(blocked=False, reason=None, legal_next_actions=["inspect-handoff"])
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: completed_json(payload, returncode=2, stderr="backend failure"),
    )

    output = legal_actions_report(Path.cwd(), "run-001")

    assert output == "planning blocked: backend failure"
    assert "inspect-handoff" not in output


def test_report_nonzero_exit_with_no_stderr_uses_generic_detail(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = valid_payload()
    monkeypatch.setattr(
        subprocess, "run", lambda *args, **kwargs: completed_json(payload, returncode=127, stderr="")
    )

    output = legal_actions_report(Path.cwd(), "run-001")

    assert output == "planning blocked: backend exited unsuccessfully"


@pytest.mark.parametrize("exit_code", [0, 1])
def test_report_malformed_payload_falls_back_to_generic_failure(
    monkeypatch: pytest.MonkeyPatch, exit_code: int
) -> None:
    malformed = valid_payload()
    malformed.pop("reason")
    monkeypatch.setattr(
        subprocess, "run", lambda *args, **kwargs: completed_json(malformed, returncode=exit_code)
    )

    output = legal_actions_report(Path.cwd(), "run-001")

    assert output == "planning blocked: invalid planning legal-actions response"


def test_report_subprocess_launch_failure_blocks_without_raising(monkeypatch: pytest.MonkeyPatch) -> None:
    def raise_oserror(*args: Any, **kwargs: Any) -> Any:
        raise OSError("uv not found")

    monkeypatch.setattr(subprocess, "run", raise_oserror)

    output = legal_actions_report(Path.cwd(), "run-001")

    assert output == "planning blocked: uv not found"


# --- CLI entry point --------------------------------------------------------


def test_main_rejects_missing_run_id(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = main(["prog"])

    assert exit_code == 2
    assert "usage" in capsys.readouterr().out.lower()


def test_main_rejects_unsafe_run_id_without_invoking_backend(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    calls: list[Any] = []
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: calls.append(args))

    exit_code = main(["prog", "../escape"])

    assert exit_code == 2
    assert calls == []
    assert "usage" in capsys.readouterr().out.lower()


def test_main_prints_rendered_report_for_safe_run_id(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    payload = valid_payload(blocked=True, reason="SESSION_NOT_READY", legal_next_actions=[])
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: completed_json(payload, returncode=1))

    exit_code = main(["prog", "run-001"])

    out = capsys.readouterr().out
    assert exit_code == 0
    assert "SESSION_NOT_READY" in out
