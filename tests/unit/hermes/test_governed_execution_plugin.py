"""RED-first tests for the Hermes-side governed-execution plugin (SR-034 AC-10).

Mirrors `tests/unit/hermes/test_coherence_plan_plugin.py`'s pattern: a minimal
`CommandContext` stands in for the Hermes host (no session, model or Kanban
authority), and `subprocess.run` is monkeypatched so no test shells out to the
real `uv run coherence execution ...` command except the one parity test that
deliberately does (mirroring `test_execution_cli.py`'s and the Pi TS adapter's
own real-subprocess parity check against the same checked-in fixture).

Unlike coherence-plan's plugin (purely read-only: it only ever renders a
projection), this plugin has real parity with Codex's
`.agents/skills/governed-execution/SKILL.md` and Claude Code's
`.claude/commands/governed-execution.md`: it can dispatch a task and resolve a
human decision, never just read state. Every test here checks the same
authority boundary those two host adapters must hold: `legal-actions` is
always consulted before a mutating action, `needs_input` is rendered verbatim
and never answered by the plugin itself, and `resolve-human` only fires when
the caller supplies an explicit decision as its own argument -- never inferred
from Hermes Kanban state or a model response.
"""

from __future__ import annotations

import asyncio
import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from tests.unit._legal_actions_json import completed_json

pytestmark = pytest.mark.unit

PLUGIN_PATH = (
    Path(__file__).parents[3] / ".hermes" / "plugins" / "governed-execution" / "plugin.py"
)

PARITY_FIXTURE = (
    Path(__file__).parents[3] / "tests" / "fixtures" / "execution_legal_actions_parity.json"
)


class CommandContext:
    """Minimal Hermes context: no host, session, model, or Kanban authority."""

    def __init__(self) -> None:
        self.registration: tuple[str, Any, dict[str, Any]] | None = None

    def register_command(self, name: str, handler: Any, **kwargs: Any) -> None:
        self.registration = (name, handler, kwargs)


def load_plugin():
    import importlib.util
    from types import ModuleType

    assert PLUGIN_PATH.is_file(), f"missing project-local plugin: {PLUGIN_PATH}"
    spec = importlib.util.spec_from_file_location("governed_execution_plugin", PLUGIN_PATH)
    assert spec is not None and spec.loader is not None
    module: ModuleType = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def register_command() -> tuple[Any, CommandContext, Any]:
    module = load_plugin()
    context = CommandContext()
    module.register(context)
    assert context.registration is not None
    name, handler, _ = context.registration
    return module, context, (name, handler)


def invoke(handler: Any, raw_args: str) -> str:
    result = handler(raw_args)
    if hasattr(result, "__await__"):
        result = asyncio.run(result)
    assert isinstance(result, str)
    return result


def projection_payload(**overrides: Any) -> dict[str, Any]:
    """A schema-1 ExecutionProjection payload, `ready` unless overridden."""
    payload: dict[str, Any] = {
        "schema": 1,
        "run_id": "run-001",
        "task_id": "T-001",
        "state": "ready",
        "blocked": False,
        "reason": None,
        "detail": None,
        "legal_next_actions": ["dispatch-task", "report-worker-result", "stream-progress"],
        "stage": None,
        "revision": None,
        "attempt": None,
        "hashes": {"contract_sha256": None, "gate_plan_sha256": None},
        "pending_request": None,
        "denied_write_count": 0,
        "starts_automatically": False,
    }
    payload.update(overrides)
    return payload


def needs_input_payload(**overrides: Any) -> dict[str, Any]:
    payload = projection_payload(
        state="needs_input",
        legal_next_actions=["resolve-human", "stream-progress"],
        pending_request={
            "request_id": "req-1",
            "request_sha256": "a" * 64,
            "reason": "GATE_FAILED_TWICE",
            "stage_id": "unit",
            "revision": 1,
            "attempt": 2,
            "allowed_decisions": ["retry", "defer", "block"],
            "input_sha256": "b" * 64,
            "finding_universe_sha256": None,
        },
    )
    payload.update(overrides)
    return payload


# -- registration ---------------------------------------------------------


def test_registers_namespaced_command_without_optional_host_authority() -> None:
    _, context, (name, handler) = register_command()

    assert name == "governed-execution"
    assert callable(handler)
    assert context.registration is not None
    assert context.registration[2]["description"]


# -- safe identifiers required before anything runs ------------------------


@pytest.mark.parametrize(
    "raw_args",
    [
        "legal-actions",
        "legal-actions run-001",
        "legal-actions ../escape task-1",
        "legal-actions run-001 ../escape",
        "legal-actions 'run 001' task-1",
        "dispatch-task ../escape task-1",
        "stream-progress ../escape",
        "resolve-human ../escape task-1 " + "a" * 64 + " req-1/retry retry hi",
    ],
)
def test_rejects_unsafe_or_incomplete_identifiers_without_invoking_backend(
    monkeypatch: pytest.MonkeyPatch, raw_args: str
) -> None:
    _, _, (_, handler) = register_command()
    calls: list[Any] = []
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: calls.append(a) or None)

    output = invoke(handler, raw_args)

    assert calls == [], f"backend invoked for unsafe input {raw_args!r}"
    assert output
    assert "usage" in output.lower()


# -- legal-actions is the read-only projection ------------------------------


def test_legal_actions_forwards_argv_safe_projection(monkeypatch: pytest.MonkeyPatch) -> None:
    _, _, (_, handler) = register_command()
    calls: list[list[str]] = []

    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        return completed_json(projection_payload())

    monkeypatch.setattr(subprocess, "run", fake_run)
    output = invoke(handler, "legal-actions run-001 T-001")

    assert len(calls) == 1
    command = calls[0]
    assert command[:4] == ["uv", "run", "coherence", "execution"]
    assert "legal-actions" in command
    assert "--run-id" in command and "run-001" in command
    assert "--task-id" in command and "T-001" in command
    assert "--json" in command
    assert all(isinstance(part, str) for part in command)
    assert '"state": "ready"' in output


def test_needs_input_is_rendered_verbatim_and_never_answered(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, _, (_, handler) = register_command()
    payload = needs_input_payload()
    calls: list[list[str]] = []

    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        return completed_json(payload)

    monkeypatch.setattr(subprocess, "run", fake_run)
    output = invoke(handler, "legal-actions run-001 T-001")

    rendered = json.loads(output)
    assert rendered == payload
    assert rendered["pending_request"]["request_sha256"] == "a" * 64
    # Only ever the one read call -- never a resolve-human call of its own.
    assert len(calls) == 1
    assert all("resolve-human" not in c for c in calls)


# -- dispatch-task only after legal-actions says so -------------------------


def test_dispatch_task_calls_legal_actions_first(monkeypatch: pytest.MonkeyPatch) -> None:
    _, _, (_, handler) = register_command()
    calls: list[list[str]] = []

    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        if "legal-actions" in command:
            return completed_json(projection_payload())
        return completed_json(
            {
                "schema": 1,
                "run_id": "run-001",
                "task_id": "T-001",
                "action": "dispatch-task",
                "result": {},
                "handoff": None,
                "projection": projection_payload(),
                "starts_automatically": False,
            }
        )

    monkeypatch.setattr(subprocess, "run", fake_run)
    invoke(handler, "dispatch-task run-001 T-001")

    assert len(calls) == 2
    assert "legal-actions" in calls[0]
    assert "dispatch-task" in calls[1]
    legal_index = " ".join(calls[0]).find("legal-actions")
    dispatch_index = " ".join(calls[1]).find("dispatch-task")
    assert legal_index >= 0 and dispatch_index >= 0


def test_dispatch_task_is_refused_when_not_currently_legal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, _, (_, handler) = register_command()
    calls: list[list[str]] = []

    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        return completed_json(needs_input_payload())

    monkeypatch.setattr(subprocess, "run", fake_run)
    output = invoke(handler, "dispatch-task run-001 T-001")

    # Only the legal-actions gate ran; dispatch-task itself was never invoked.
    assert len(calls) == 1
    assert "legal-actions" in calls[0]
    assert "dispatch-task" not in " ".join(a for c in calls for a in c)
    assert "not currently legal" in output.lower() or "blocked" in output.lower()


# -- resolve-human only after an explicit decision --------------------------


def test_resolve_human_requires_an_explicit_decision_argument(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, _, (_, handler) = register_command()
    calls: list[Any] = []
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: calls.append(a) or None)

    # No decision word supplied at all -- must not guess one.
    output = invoke(handler, "resolve-human run-001 T-001 " + "a" * 64 + " req-1/retry")

    assert calls == []
    assert "usage" in output.lower()


def test_resolve_human_calls_legal_actions_first_and_forwards_the_decision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, _, (_, handler) = register_command()
    calls: list[list[str]] = []

    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        if "legal-actions" in command:
            return completed_json(needs_input_payload())
        return completed_json(
            {
                "schema": 1,
                "run_id": "run-001",
                "task_id": "T-001",
                "action": "resolve-human",
                "decision": "retry",
                "replayed": False,
                "result": None,
                "handoff": None,
                "projection": projection_payload(),
                "starts_automatically": False,
            }
        )

    monkeypatch.setattr(subprocess, "run", fake_run)
    output = invoke(
        handler,
        "resolve-human run-001 T-001 " + "a" * 64 + " req-1/retry retry the human said retry",
    )

    assert len(calls) == 2
    assert "legal-actions" in calls[0]
    resolve_call = calls[1]
    assert "resolve-human" in resolve_call
    assert "--decision" in resolve_call
    assert resolve_call[resolve_call.index("--decision") + 1] == "retry"
    assert "--response" in resolve_call
    assert resolve_call[resolve_call.index("--response") + 1] == "the human said retry"
    assert "--decided-by" in resolve_call
    assert resolve_call[resolve_call.index("--decided-by") + 1] == "human"
    assert "recorded" in output.lower() or "retry" in output.lower()


def test_resolve_human_is_refused_when_not_currently_legal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, _, (_, handler) = register_command()
    calls: list[list[str]] = []

    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        return completed_json(projection_payload())  # ready: no pending decision

    monkeypatch.setattr(subprocess, "run", fake_run)
    output = invoke(
        handler,
        "resolve-human run-001 T-001 " + "a" * 64 + " req-1/retry retry the human said retry",
    )

    assert len(calls) == 1
    assert "legal-actions" in calls[0]
    assert "not currently legal" in output.lower() or "blocked" in output.lower()


def test_resolve_human_rejects_an_unknown_decision_word_without_invoking_backend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, _, (_, handler) = register_command()
    calls: list[Any] = []
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: calls.append(a) or None)

    output = invoke(
        handler,
        "resolve-human run-001 T-001 " + "a" * 64 + " req-1/approve approve just do it",
    )

    assert calls == []
    assert "usage" in output.lower() or "decision" in output.lower()


def test_resolve_human_rejects_a_malformed_sha256_without_invoking_backend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, _, (_, handler) = register_command()
    calls: list[Any] = []
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: calls.append(a) or None)

    output = invoke(handler, "resolve-human run-001 T-001 not-a-hash req-1/retry retry go")

    assert calls == []
    assert "usage" in output.lower() or "sha256" in output.lower()


# -- stream-progress ---------------------------------------------------------


def test_stream_progress_forwards_argv_safe_call(monkeypatch: pytest.MonkeyPatch) -> None:
    _, _, (_, handler) = register_command()
    calls: list[list[str]] = []

    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        return completed_json({"schema": 1, "run_id": "run-001", "events": [],
                                "denied_write_count": 0, "starts_automatically": False})

    monkeypatch.setattr(subprocess, "run", fake_run)
    output = invoke(handler, "stream-progress run-001")

    assert len(calls) == 1
    assert "stream-progress" in calls[0]
    assert "run-001" in calls[0]
    assert "no recorded events" in output or "events" in output


# -- fail-closed rendering, never a raise into the Hermes host --------------


def test_a_missing_or_unreadable_cli_renders_as_blocked_not_a_raise(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, _, (_, handler) = register_command()

    def fake_run(*args: Any, **kwargs: Any):
        raise FileNotFoundError("uv: command not found")

    monkeypatch.setattr(subprocess, "run", fake_run)
    output = invoke(handler, "legal-actions run-001 T-001")

    assert "blocked" in output.lower()
    assert "uv" in output.lower() or "command not found" in output.lower()


def test_a_nonzero_cli_exit_outside_the_canonical_pair_renders_as_blocked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, _, (_, handler) = register_command()

    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            args=command, returncode=2, stdout="", stderr="error: run id is not a safe identifier"
        )

    monkeypatch.setattr(subprocess, "run", fake_run)
    output = invoke(handler, "legal-actions run-001 T-001")

    assert "blocked" in output.lower()
    assert "not a safe identifier" in output


def test_a_canonical_blocked_exit_still_forwards_the_structured_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Exit 1 is the CLI's normal 'blocked/escalated' signal, not a plugin-level
    failure -- the payload must still be forwarded, not replaced by a generic
    failure string (mirrors coherence-plan's own exit-code-1 test)."""
    _, _, (_, handler) = register_command()
    payload = projection_payload(state="blocked", blocked=True, reason="HUMAN_BLOCK")

    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        return completed_json(payload, returncode=1)

    monkeypatch.setattr(subprocess, "run", fake_run)
    output = invoke(handler, "legal-actions run-001 T-001")

    rendered = json.loads(output)
    assert rendered == payload


# -- project root resolution (mirrors coherence-plan's plugin) --------------


def test_project_root_override_reaches_the_backend_argv(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _, _, (_, handler) = register_command()
    calls: list[list[str]] = []

    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        return completed_json(projection_payload())

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setenv("COHERENCE_PROJECT_ROOT", str(tmp_path))

    invoke(handler, "legal-actions run-001 T-001")

    assert len(calls) == 1
    command = calls[0]
    assert command[command.index("--project-root") + 1] == str(tmp_path)


REPO_ROOT = PLUGIN_PATH.parents[3].resolve()


def test_project_root_falls_back_to_the_checkout_when_cwd_is_not_one(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _, _, (_, handler) = register_command()
    calls: list[list[str]] = []

    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        return completed_json(projection_payload())

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.delenv("COHERENCE_PROJECT_ROOT", raising=False)
    monkeypatch.chdir(tmp_path)

    invoke(handler, "legal-actions run-001 T-001")

    assert len(calls) == 1
    command = calls[0]
    assert command[command.index("--project-root") + 1] == str(REPO_ROOT)


def test_deployment_marker_points_an_out_of_tree_install_at_the_checkout(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    module, _, (_, handler) = register_command()
    install = tmp_path / "plugins" / "governed-execution"
    install.mkdir(parents=True)
    (install / "repo_root.txt").write_text(str(REPO_ROOT), encoding="utf-8")
    monkeypatch.setattr(module, "__file__", str(install / "plugin.py"))
    monkeypatch.delenv("COHERENCE_REPO_ROOT", raising=False)
    monkeypatch.delenv("COHERENCE_PROJECT_ROOT", raising=False)
    calls: list[list[str]] = []

    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        return completed_json(projection_payload())

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.chdir(tmp_path)

    invoke(handler, "legal-actions run-001 T-001")

    assert len(calls) == 1
    command = calls[0]
    assert command[command.index("--project-root") + 1] == str(REPO_ROOT)


# -- real cross-host parity: the same fixture Task 6 checked in ------------


def test_legal_actions_output_is_byte_identical_to_the_checked_in_host_expectation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The fourth surface: this plugin, invoked for real against this repo's own
    `uv run coherence execution legal-actions ...`, produces the exact same
    checked-in projection that `tests/unit/coherence/test_execution_cli.py`
    (the direct CLI) and `pi-ext/factory-watch/test/execution-tools.integration.test.ts`
    (the Pi tool) already assert byte-identity against, after key sorting.
    """
    _, _, (_, handler) = register_command()
    monkeypatch.setenv("COHERENCE_PROJECT_ROOT", str(REPO_ROOT))

    output = invoke(handler, "legal-actions feat013-parity T-013")

    produced = json.loads(output)
    expected = json.loads(PARITY_FIXTURE.read_text(encoding="utf-8"))
    assert _sorted(produced) == _sorted(expected)
    assert produced["starts_automatically"] is False


def _sorted(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _sorted(value[key]) for key in sorted(value)}
    if isinstance(value, list):
        return [_sorted(item) for item in value]
    return value
