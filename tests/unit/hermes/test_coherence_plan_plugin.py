from __future__ import annotations

import asyncio
import importlib.util
import subprocess
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from tests.unit._legal_actions_json import completed_json

pytestmark = pytest.mark.unit

PLUGIN_PATH = (
    Path(__file__).parents[3] / ".hermes" / "plugins" / "coherence-plan" / "plugin.py"
)


class CommandContext:
    """Minimal Hermes context: no host, session, model, or Kanban authority."""

    def __init__(self) -> None:
        self.registration: tuple[str, Any, dict[str, Any]] | None = None

    def register_command(self, name: str, handler: Any, **kwargs: Any) -> None:
        self.registration = (name, handler, kwargs)


def load_plugin() -> ModuleType:
    assert PLUGIN_PATH.is_file(), f"missing project-local plugin: {PLUGIN_PATH}"
    spec = importlib.util.spec_from_file_location("coherence_plan_plugin", PLUGIN_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def register_command() -> tuple[ModuleType, CommandContext, Any]:
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


def test_registers_namespaced_command_without_optional_host_authority() -> None:
    _, context, (name, handler) = register_command()

    assert name == "coherence-plan"
    assert name != "plan"
    assert callable(handler)
    assert context.registration is not None
    assert context.registration[2]["description"]


def test_forwards_only_argv_safe_legal_actions_call(monkeypatch: pytest.MonkeyPatch) -> None:
    _, _, (_, handler) = register_command()
    calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []
    payload = {
        "schema": 1,
        "run_id": "run-001",
        "blocked": True,
        "reason": "SESSION_NOT_READY",
        "legal_next_actions": [],
        "starts_automatically": False,
    }

    def fake_run(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append((args, kwargs))
        return completed_json(payload)

    monkeypatch.setattr(subprocess, "run", fake_run)
    output = invoke(handler, "run-001")

    assert len(calls) == 1
    command = calls[0][0][0]
    assert command == [
        "uv",
        "run",
        "coherence",
        "plan",
        "legal-actions",
        "--project-root",
        str(Path.cwd()),
        "--run-id",
        "run-001",
        "--json",
    ]
    assert all(isinstance(argument, str) for argument in command)
    assert "SESSION_NOT_READY" in output


def test_rejects_unsafe_run_id_without_invoking_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    _, _, (_, handler) = register_command()
    calls: list[Any] = []
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: calls.append(args))

    output = invoke(handler, "../escape; uv run coherence plan")

    assert calls == []
    assert output
    assert "usage" in output.lower() or "invalid" in output.lower() or "blocked" in output.lower()


def test_renders_backend_declared_actions_and_block_reason(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, _, (_, handler) = register_command()
    payload = {
        "schema": 1,
        "run_id": "run-002",
        "blocked": True,
        "reason": "HANDOFF_INVALID",
        "legal_next_actions": ["resolve-blocking-input"],
        "starts_automatically": False,
    }
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: completed_json(payload))

    output = invoke(handler, "run-002")

    assert "HANDOFF_INVALID" in output
    assert "resolve-blocking-input" in output


def test_returns_canonical_legal_actions_report_verbatim(monkeypatch: pytest.MonkeyPatch) -> None:
    module, _, (_, handler) = register_command()
    expected = "Planning ready\nLegal actions: author-plan\nStarts automatically: no"
    calls: list[tuple[Path, str]] = []

    def fake_report(root: Path, run_id: str) -> str:
        calls.append((root, run_id))
        return expected

    monkeypatch.setattr(module, "legal_actions_report", fake_report)
    assert invoke(handler, "run-verbatim") == expected
    assert calls == [(Path.cwd(), "run-verbatim")]


def test_backend_projection_is_the_only_authority_for_actions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, _, (_, handler) = register_command()
    payload = {
        "schema": 1,
        "run_id": "run-003",
        "blocked": False,
        "reason": None,
        "legal_next_actions": ["inspect-handoff"],
        "selected_downstream_workflow": None,
        "starts_automatically": False,
    }
    calls: list[list[str]] = []

    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        return completed_json(payload)

    monkeypatch.setattr(subprocess, "run", fake_run)
    output = invoke(handler, "run-003")

    assert "inspect-handoff" in output
    assert "create-downstream-session" not in output
    assert len(calls) == 1


def test_never_launches_downstream_work_from_backend_action_projection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, _, (_, handler) = register_command()
    payload = {
        "schema": 1,
        "run_id": "run-004",
        "blocked": False,
        "reason": None,
        "legal_next_actions": ["create-downstream-session"],
        "selected_downstream_workflow": "standard-development",
        "starts_automatically": False,
    }
    calls: list[list[str]] = []

    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        return completed_json(payload)

    monkeypatch.setattr(subprocess, "run", fake_run)
    output = invoke(handler, "run-004")

    assert "create-downstream-session" in output
    assert len(calls) == 1


def test_exit_code_one_surfaces_structured_block_reason(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Exit code 1 is the CLI's normal signal for "planning is blocked", not a
    backend failure. The adapter must still parse and render the structured
    payload's reason instead of falling back to a generic failure message."""
    _, _, (_, handler) = register_command()
    payload = {
        "schema": 1,
        "run_id": "run-007",
        "blocked": True,
        "reason": "STALE_SESSION_STATE",
        "legal_next_actions": ["resolve-blocking-input"],
        "starts_automatically": False,
    }
    blocked_exit = completed_json(payload, returncode=1)
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: blocked_exit)

    output = invoke(handler, "run-007")

    assert "STALE_SESSION_STATE" in output
    assert "resolve-blocking-input" in output
    assert output != "planning blocked: backend exited unsuccessfully"
    assert "backend exited unsuccessfully" not in output


def test_nonzero_backend_exit_blocks_even_with_projection_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, _, (_, handler) = register_command()
    payload = {
        "schema": 1,
        "run_id": "run-005",
        "blocked": False,
        "reason": None,
        "legal_next_actions": ["inspect-handoff"],
        "starts_automatically": False,
    }
    failed = completed_json(payload, returncode=2, stderr="backend failure")
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: failed)

    output = invoke(handler, "run-005")

    assert output == "planning blocked: backend failure"


@pytest.mark.parametrize(
    "malformed_update",
    [
        {"schema": True},
        {"reason": "__missing_reason__"},
    ],
)
def test_rejects_malformed_projection_contract(
    monkeypatch: pytest.MonkeyPatch,
    malformed_update: dict[str, Any],
) -> None:
    _, _, (_, handler) = register_command()
    payload: dict[str, Any] = {
        "schema": 1,
        "run_id": "run-006",
        "blocked": False,
        "reason": None,
        "legal_next_actions": [],
        "starts_automatically": False,
    }
    if malformed_update.get("reason") == "__missing_reason__":
        payload.pop("reason")
    else:
        payload.update(malformed_update)
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: completed_json(payload),
    )

    output = invoke(handler, "run-006")

    assert output.startswith("planning blocked: invalid planning legal-actions response")
