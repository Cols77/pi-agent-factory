from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from coherence.planning.adapter_backend import BackendError, invoke_backend, require_safe_run_id
from coherence.planning.guided_entrypoint import (
    SESSION_VERBS,
    build_session_command,
    main,
    parse_session_response,
    run_session_command,
)
from coherence.planning.guided_pipeline import (
    PIPELINE_VERBS,
    build_pipeline_command,
    run_pipeline_command,
)
from tests.unit._legal_actions_json import completed_json

pytestmark = pytest.mark.unit


def test_require_safe_run_id_accepts_the_shared_grammar() -> None:
    require_safe_run_id("FEAT-018")
    require_safe_run_id("run-001")


@pytest.mark.parametrize("run_id", ["", "../escape", "run 001", "run;rm -rf", "-run", "run/001"])
def test_require_safe_run_id_rejects_unsafe_ids(run_id: str) -> None:
    with pytest.raises(BackendError, match="safe run-id grammar"):
        require_safe_run_id(run_id)


@pytest.mark.parametrize("exit_code", [0, 1])
def test_trusted_exit_codes_return_stdout(monkeypatch: pytest.MonkeyPatch, exit_code: int) -> None:
    monkeypatch.setattr(
        subprocess, "run", lambda *a, **k: completed_json({"ok": True}, returncode=exit_code)
    )

    code, stdout = invoke_backend(["uv", "run", "coherence", "plan", "status"], Path("/p"))

    assert code == exit_code
    assert json.loads(stdout) == {"ok": True}


@pytest.mark.parametrize("exit_code", [2, 3, 127])
def test_untrusted_exit_codes_never_return_stdout(
    monkeypatch: pytest.MonkeyPatch, exit_code: int
) -> None:
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *a, **k: completed_json({"ok": True}, returncode=exit_code, stderr="segfault"),
    )

    with pytest.raises(BackendError, match="segfault"):
        invoke_backend(["uv", "run", "coherence", "plan", "status"], Path("/p"))


def test_untrusted_exit_with_no_stderr_still_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        subprocess, "run", lambda *a, **k: completed_json({}, returncode=2, stderr="")
    )

    with pytest.raises(BackendError, match="backend exited unsuccessfully"):
        invoke_backend(["uv", "run", "coherence"], Path("/p"))


def test_launch_failure_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*a: Any, **k: Any) -> None:
        raise OSError("uv not found")

    monkeypatch.setattr(subprocess, "run", boom)

    with pytest.raises(BackendError, match="uv not found"):
        invoke_backend(["uv"], Path("/p"))


def test_invocation_never_uses_a_shell(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, Any] = {}

    def capture(command: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        seen.update(command=command, kwargs=kwargs)
        return completed_json({}, returncode=0)

    monkeypatch.setattr(subprocess, "run", capture)
    invoke_backend(["uv", "run", "coherence"], Path("/p"))

    assert isinstance(seen["command"], list)
    assert seen["kwargs"]["shell"] is False


# --- capture-session verbs -----------------------------------------------


def session_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema": 1,
        "ok": True,
        "run_id": "run-001",
        "state": "capture",
        "next_sequence": 2,
        "journal_sha256": "a" * 64,
        "challenges": [],
    }
    payload.update(overrides)
    return payload


def challenge(**overrides: Any) -> dict[str, Any]:
    item: dict[str, Any] = {
        "id": "challenge-a1-evidence",
        "kind": "unsupported_claim",
        "claim": "This always works",
        "rationale": "This consequential claim is asserted without supporting evidence.",
        "provenance": "user",
        "evidence_needed": "repository inspection or a cited external source",
        "status": "unresolved",
        "response": "",
        "response_provenance": "",
    }
    item.update(overrides)
    return item


def test_session_verbs_are_exactly_the_implemented_capture_verbs() -> None:
    assert SESSION_VERBS == ("start", "resume", "status", "append", "resolve", "finalize")


def test_start_builds_argv_only_command_with_prompt() -> None:
    command = build_session_command(Path("/p"), "FEAT-018", "start", prompt="Plan the thing")

    assert command == [
        "uv",
        "run",
        "coherence",
        "plan",
        "start",
        "--project-root",
        str(Path("/p")),
        "--run-id",
        "FEAT-018",
        "--prompt",
        "Plan the thing",
        "--json",
    ]


def test_append_passes_each_field_as_its_own_argv_token() -> None:
    command = build_session_command(
        Path("/p"),
        "run-001",
        "append",
        answer_id="a3",
        question="What breaks?",
        text="Nothing",
        source="intent-review-agent",
    )

    assert command[command.index("--answer-id") + 1] == "a3"
    assert command[command.index("--question") + 1] == "What breaks?"
    assert command[command.index("--text") + 1] == "Nothing"
    assert command[command.index("--source") + 1] == "intent-review-agent"


def test_unsupported_verb_is_rejected() -> None:
    with pytest.raises(ValueError, match="unsupported planning session verb"):
        build_session_command(Path("/p"), "run-001", "adopt")


def test_parse_accepts_ok_payload_with_challenges() -> None:
    payload = session_payload(challenges=[challenge()])

    assert parse_session_response(json.dumps(payload), "run-001") == payload


def test_parse_returns_operation_failure_without_raising() -> None:
    payload = {"schema": 1, "run_id": "run-001", "ok": False, "error": "session already exists"}

    assert parse_session_response(json.dumps(payload), "run-001")["ok"] is False


@pytest.mark.parametrize(
    "payload",
    [
        session_payload(schema=2),
        session_payload(run_id="other"),
        session_payload(ok="yes"),
        session_payload(state="handoff_ready"),
        session_payload(state="spec_authoring"),
        session_payload(next_sequence=0),
        session_payload(journal_sha256=""),
        session_payload(challenges="none"),
        session_payload(challenges=[{"id": "c1"}]),
        {"schema": 1, "run_id": "run-001", "ok": False, "error": ""},
    ],
)
def test_parse_rejects_off_contract_payloads(payload: dict[str, Any]) -> None:
    with pytest.raises(ValueError, match="invalid planning session response"):
        parse_session_response(json.dumps(payload), "run-001")


@pytest.mark.parametrize("raw", ["", "not json", "[]", "null"])
def test_parse_rejects_non_objects(raw: str) -> None:
    with pytest.raises(ValueError, match="invalid planning session response"):
        parse_session_response(raw, "run-001")


def test_run_session_command_returns_validated_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = session_payload(state="intent_provisional")
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: completed_json(payload, returncode=0))

    assert run_session_command(Path("/p"), "run-001", "finalize", status="provisional") == payload


def test_run_session_command_rejects_unsafe_run_id_without_subprocess(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[Any] = []
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: calls.append(a))

    with pytest.raises(BackendError, match="safe run-id grammar"):
        run_session_command(Path("/p"), "../escape", "status")

    assert calls == []


def test_run_session_command_wraps_malformed_payload_as_backend_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *a, **k: subprocess.CompletedProcess([], returncode=0, stdout="{bad", stderr=""),
    )

    with pytest.raises(BackendError, match="invalid planning session response"):
        run_session_command(Path("/p"), "run-001", "status")


# --- capture-session CLI -------------------------------------------------


def test_main_prints_payload_and_exits_zero(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    payload = session_payload(challenges=[challenge()])
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: completed_json(payload, returncode=0))

    assert main(["status", "--run-id", "run-001", "--project-root", "."]) == 0
    assert json.loads(capsys.readouterr().out) == payload


def test_main_exits_zero_for_operation_error_so_the_host_can_react(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    payload = {"schema": 1, "run_id": "run-001", "ok": False, "error": "state is stale or missing"}
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: completed_json(payload, returncode=1))

    assert main(["status", "--run-id", "run-001"]) == 0
    assert json.loads(capsys.readouterr().out)["error"] == "state is stale or missing"


def test_main_exits_one_when_nothing_is_trustworthy(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        subprocess, "run", lambda *a, **k: completed_json({}, returncode=9, stderr="boom")
    )

    assert main(["status", "--run-id", "run-001"]) == 1
    assert "boom" in json.loads(capsys.readouterr().out)["error"]


@pytest.mark.parametrize(
    "argv",
    [
        [],
        ["adopt", "--run-id", "run-001"],
        ["start", "--run-id", "run-001"],
        ["finalize", "--run-id", "run-001", "--status", "adopted"],
        [
            "resolve",
            "--run-id",
            "r",
            "--challenge-id",
            "c",
            "--resolution",
            "approve",
            "--response",
            "ok",
        ],
    ],
)
def test_main_usage_errors_exit_two(argv: list[str]) -> None:
    assert main(argv) == 2


# --- pipeline verbs ------------------------------------------------------


def test_pipeline_verbs_are_the_implemented_compile_and_handoff_verbs() -> None:
    assert PIPELINE_VERBS == ("bootstrap", "check", "review", "handoff")


def test_bootstrap_passes_all_three_artifacts_and_decompose() -> None:
    command = build_pipeline_command(
        Path("/p"),
        "FEAT-018",
        "bootstrap",
        intent=".intent/intent.json",
        spec="docs/superpowers/specs/s.md",
        plan="docs/superpowers/plans/p.md",
        decompose="true",
    )

    assert command[:5] == ["uv", "run", "coherence", "plan", "bootstrap"]
    assert command[command.index("--intent") + 1] == ".intent/intent.json"
    assert command[command.index("--spec") + 1] == "docs/superpowers/specs/s.md"
    assert command[command.index("--plan") + 1] == "docs/superpowers/plans/p.md"
    assert "--decompose" in command


def test_bootstrap_omits_decompose_flag_when_not_requested() -> None:
    command = build_pipeline_command(
        Path("/p"), "FEAT-018", "bootstrap", intent="i", spec="s", plan="p", decompose="false"
    )

    assert "--decompose" not in command


def test_handoff_carries_the_workflow_selection() -> None:
    command = build_pipeline_command(
        Path("/p"), "FEAT-018", "handoff", workflow="standard-development"
    )

    assert command[command.index("--workflow") + 1] == "standard-development"


def test_unsupported_pipeline_verb_is_rejected() -> None:
    with pytest.raises(ValueError, match="unsupported planning pipeline verb"):
        build_pipeline_command(Path("/p"), "FEAT-018", "adopt")


def test_pipeline_exit_one_is_findings_data_not_a_crash(monkeypatch: pytest.MonkeyPatch) -> None:
    report = {"ok": False, "findings": [{"code": "PLAN_TASK_PARITY"}]}
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: completed_json(report, returncode=1))

    code, payload = run_pipeline_command(
        Path("/p"), "FEAT-018", "check", intent="i", spec="s", plan="p"
    )

    assert code == 1
    assert payload["findings"][0]["code"] == "PLAN_TASK_PARITY"


def test_pipeline_untrusted_exit_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        subprocess, "run", lambda *a, **k: completed_json({"ok": True}, returncode=7, stderr="bad")
    )

    with pytest.raises(BackendError, match="bad"):
        run_pipeline_command(Path("/p"), "FEAT-018", "review")


def test_pipeline_rejects_unsafe_run_id_without_subprocess(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[Any] = []
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: calls.append(a))

    with pytest.raises(BackendError, match="safe run-id grammar"):
        run_pipeline_command(Path("/p"), "run 001", "review")

    assert calls == []


def test_pipeline_rejects_non_json_output(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *a, **k: subprocess.CompletedProcess([], returncode=0, stdout="not json", stderr=""),
    )

    with pytest.raises(BackendError, match="invalid planning pipeline response"):
        run_pipeline_command(Path("/p"), "FEAT-018", "review")
