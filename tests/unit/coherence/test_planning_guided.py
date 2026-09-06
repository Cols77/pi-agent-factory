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

    code, stdout, stderr = invoke_backend(["uv", "run", "coherence", "plan", "status"], Path("/p"))

    assert code == exit_code
    assert json.loads(stdout) == {"ok": True}
    assert stderr == ""


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
        "--prompt=Plan the thing",
        "--json",
    ]


def test_resume_builds_argv_only_command() -> None:
    command = build_session_command(Path("/p"), "FEAT-018", "resume")

    assert command == [
        "uv",
        "run",
        "coherence",
        "plan",
        "resume",
        "--project-root",
        str(Path("/p")),
        "--run-id",
        "FEAT-018",
        "--json",
    ]


def test_run_session_command_resume_round_trips_the_backend_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = session_payload(run_id="FEAT-018", state="intent_provisional")
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: completed_json(payload, returncode=0))

    assert run_session_command(Path("/p"), "FEAT-018", "resume") == payload


def test_main_resume_prints_payload_and_exits_zero(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    payload = session_payload(run_id="FEAT-018")
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: completed_json(payload, returncode=0))

    assert main(["resume", "--run-id", "FEAT-018", "--project-root", "."]) == 0
    assert json.loads(capsys.readouterr().out) == payload


def test_append_joins_each_flag_and_value_as_one_argv_token() -> None:
    command = build_session_command(
        Path("/p"),
        "run-001",
        "append",
        answer_id="a3",
        question="What breaks?",
        text="Nothing",
        source="intent-review-agent",
    )

    assert "--answer-id=a3" in command
    assert "--question=What breaks?" in command
    assert "--text=Nothing" in command
    assert "--source=intent-review-agent" in command


@pytest.mark.parametrize("hyphen_value", ["-N/A", "-none", "-1", "--looks-like-a-flag"])
def test_append_survives_free_text_answers_starting_with_a_hyphen(hyphen_value: str) -> None:
    """A single hyphen-prefixed token with no space is what argparse's
    `_parse_optional` heuristic misreads as an unknown option when a flag and
    its value are two separate argv tokens; joining them with `=` removes the
    ambiguity regardless of what the value looks like."""
    command = build_session_command(
        Path("/p"), "run-001", "append",
        answer_id="a1", question="q?", text=hyphen_value, source="user",
    )

    assert f"--text={hyphen_value}" in command


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


def test_run_session_command_surfaces_stderr_when_a_trusted_exit_has_empty_stdout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A crash inside the backend can still exit with a trusted code and no
    stdout (see session.py::_write_state raising OSError past cli.py's
    ``except SessionError``). The real cause must not be discarded."""
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *a, **k: subprocess.CompletedProcess(
            [], returncode=1, stdout="", stderr="PermissionError: [WinError 5] ..."
        ),
    )

    with pytest.raises(BackendError, match="PermissionError"):
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
    assert "--intent=.intent/intent.json" in command
    assert "--spec=docs/superpowers/specs/s.md" in command
    assert "--plan=docs/superpowers/plans/p.md" in command
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

    assert "--workflow=standard-development" in command


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


def test_pipeline_surfaces_stderr_when_a_trusted_exit_has_unparseable_stdout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *a, **k: subprocess.CompletedProcess(
            [], returncode=1, stdout="", stderr="Traceback: KeyError('boom')"
        ),
    )

    with pytest.raises(BackendError, match="KeyError"):
        run_pipeline_command(Path("/p"), "FEAT-018", "review")


# --- SR-065 AC-1/AC-3: command-dispatch and non-executing-boundary pinning
#
# SR-065 names this file as the verification for AC-1 (start-or-resume
# dispatch) and AC-3 (the guided handoff stays non-executing). Those two
# specific claims are prose in `.claude/commands/coherence-plan.md`, not
# behaviour a Python function exposes to assert against directly -- so the
# assertions live here as well as in `test_coherence_plan_command_contract.py`
# (which pins the command file's other invariants), rather than only in a
# file this SR's acceptance criteria do not name.


_COMMAND_FILE = Path(__file__).parents[3] / ".claude" / "commands" / "coherence-plan.md"


def test_ac1_start_or_resume_dispatch_is_not_swapped() -> None:
    """A swap here (calling `start` on `ok: true` or `resume` on `ok: false`)
    would double-start every existing run and never resume one."""
    text = _COMMAND_FILE.read_text(encoding="utf-8")
    section = text[text.index("## 2. Start or resume") : text.index("## 3.")]

    true_branch = section[section.index("`ok: true`") : section.index("`ok: false`")]
    false_branch = section[section.index("`ok: false`") :]

    assert "resume" in true_branch
    assert "start" not in true_branch
    assert "start" in false_branch


def test_ac3_non_executing_boundary_is_stated() -> None:
    text = _COMMAND_FILE.read_text(encoding="utf-8")
    lowered = text.lower()

    assert "starts_automatically" in lowered
    assert "downstream" in lowered


# --- SR-065 AC-2: a real backend-detected staleness reaches the host as data
#
# `parse_session_response` validates shape, not whether one response is fresh
# relative to a prior one -- that comparison is backend-owned structural work
# (`session.py::status_session` recomputes the projection from the journal and
# rejects a `state.json` that disagrees with it). This test drives that real
# rejection through the adapter, rather than only asserting against a
# hand-authored fixture dict, so the SR's staleness claim is checked against
# what the backend actually does.


def test_ac2_a_genuinely_stale_session_state_is_relayed_as_data_not_raised(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Drives the real `session.py::status_session` staleness check
    in-process (never a hand-authored fixture payload) and feeds its actual
    stdout through the adapter's own parsing path, proving a genuine backend
    rejection reaches the host as `ok: false` data rather than being lost."""
    from coherence.planning.cli import main as backend_main

    root = tmp_path
    run_id = "run-001"
    assert (
        backend_main(
            ["start", "--project-root", str(root), "--run-id", run_id, "--prompt", "p", "--json"]
        )
        == 0
    )
    capsys.readouterr()

    state_path = root / ".factory" / "planning" / run_id / "state.json"
    state_path.write_text(json.dumps({"schema": 1, "run_id": run_id}), encoding="utf-8")

    exit_code = backend_main(
        ["status", "--project-root", str(root), "--run-id", run_id, "--json"]
    )
    real_stdout = capsys.readouterr().out
    assert exit_code == 1

    payload = parse_session_response(real_stdout, run_id)

    assert payload["ok"] is False
    assert "stale" in payload["error"]
