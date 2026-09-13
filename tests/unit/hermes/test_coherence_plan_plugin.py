from __future__ import annotations

import asyncio
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from tests.unit._legal_actions_json import completed_json, valid_payload

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
    payload = valid_payload(
        blocked=True,
        reason="SESSION_NOT_READY",
        legal_next_actions=[],
    )

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


def test_transports_capture_command_with_controlled_root_and_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, _, (_, handler) = register_command()
    payload = {
        "schema": 2,
        "ok": True,
        "run_id": "run-010",
        "state": "capture",
        "next_sequence": 1,
        "journal_sha256": "a" * 64,
        "challenges": [],
    }
    calls: list[tuple[list[str], dict[str, Any]]] = []

    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append((command, kwargs))
        return completed_json(payload)

    monkeypatch.setattr(subprocess, "run", fake_run)
    output = invoke(handler, 'start --run-id run-010 --prompt "Plan it"')

    assert json.loads(output) == payload
    assert calls == [
        (
            [
                "uv",
                "run",
                "coherence",
                "plan",
                "start",
                "--project-root",
                str(Path.cwd()),
                "--run-id",
                "run-010",
                "--prompt",
                "Plan it",
                "--json",
            ],
            {
                "cwd": Path.cwd(),
                "capture_output": True,
                "text": True,
                "check": False,
                "shell": False,
            },
        )
    ]


def test_transports_feat017_gate_command_and_preserves_block_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, _, (_, handler) = register_command()
    payload = {
        "schema": 2,
        "run_id": "FEAT-017",
        "ok": False,
        "error": "PLANNING_GATE_BLOCKED",
    }
    calls: list[list[str]] = []

    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        return completed_json(payload, returncode=1)

    monkeypatch.setattr(subprocess, "run", fake_run)
    output = invoke(handler, "run-planning-gates --run-id FEAT-017")

    assert json.loads(output) == payload
    assert calls == [
        [
            "uv",
            "run",
            "coherence",
            "plan",
            "run-planning-gates",
            "--project-root",
            str(Path.cwd()),
            "--run-id",
            "FEAT-017",
            "--json",
        ]
    ]


def test_rejects_unknown_workflow_verb_without_invoking_backend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, _, (_, handler) = register_command()
    calls: list[Any] = []
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: calls.append(args))

    output = invoke(handler, "exec --run-id run-011")

    assert "unsupported planning verb" in output
    assert calls == []


def test_rejects_caller_controlled_project_root_and_json_flags(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, _, (_, handler) = register_command()
    calls: list[Any] = []
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: calls.append(args))

    project_output = invoke(handler, "status --run-id run-012 --project-root C:/other")
    json_output = invoke(handler, "status --run-id run-012 --json=true")

    assert "controlled by the Hermes adapter" in project_output
    assert "controlled by the Hermes adapter" in json_output
    assert calls == []


def test_rejects_schema_one_or_mismatched_workflow_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, _, (_, handler) = register_command()
    invalid_payload = {"schema": 1, "run_id": "run-013", "ok": True}
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: completed_json(invalid_payload),
    )

    output = invoke(handler, "status --run-id run-013")

    assert output == "planning blocked: invalid planning response"


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
    payload = valid_payload(
        run_id="run-002",
        blocked=True,
        reason="HANDOFF_INVALID",
        legal_next_actions=[],
    )
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: completed_json(payload))

    output = invoke(handler, "run-002")

    assert "HANDOFF_INVALID" in output
    assert "Legal actions: none" in output


def test_returns_canonical_legal_actions_report_verbatim(monkeypatch: pytest.MonkeyPatch) -> None:
    module, _, (_, handler) = register_command()
    expected = "Planning ready\nLegal actions: author-plan\nStarts automatically: no"
    calls: list[tuple[Path, str]] = []

    def fake_report(root: Path, run_id: str) -> str:
        calls.append((root, run_id))
        return expected

    class FakeAdapter:
        @staticmethod
        def is_safe_run_id(run_id: str) -> bool:
            return bool(run_id)

        @staticmethod
        def legal_actions_report(root: Path, run_id: str) -> str:
            return fake_report(root, run_id)

    monkeypatch.setattr(module, "_load_adapter", lambda: FakeAdapter)
    assert invoke(handler, "run-verbatim") == expected
    assert calls == [(Path.cwd(), "run-verbatim")]


def test_backend_projection_is_the_only_authority_for_actions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, _, (_, handler) = register_command()
    payload = valid_payload(
        run_id="run-003",
        legal_next_actions=["inspect-handoff"],
        selected_downstream_workflow=None,
    )
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
    payload = valid_payload(
        run_id="run-004",
        legal_next_actions=["create-handoff"],
        selected_downstream_workflow="standard-development",
    )
    calls: list[list[str]] = []

    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        return completed_json(payload)

    monkeypatch.setattr(subprocess, "run", fake_run)
    output = invoke(handler, "run-004")

    assert "create-handoff" in output
    assert len(calls) == 1


def test_exit_code_one_surfaces_structured_block_reason(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Exit code 1 is the CLI's normal signal for "planning is blocked", not a
    backend failure. The adapter must still parse and render the structured
    payload's reason instead of falling back to a generic failure message."""
    _, _, (_, handler) = register_command()
    payload = valid_payload(
        run_id="run-007",
        blocked=True,
        reason="STALE_SESSION_STATE",
        legal_next_actions=[],
    )
    blocked_exit = completed_json(payload, returncode=1)
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: blocked_exit)

    output = invoke(handler, "run-007")

    assert "STALE_SESSION_STATE" in output
    assert "Legal actions: none" in output
    assert output != "planning blocked: backend exited unsuccessfully"
    assert "backend exited unsuccessfully" not in output


def test_nonzero_backend_exit_blocks_even_with_projection_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, _, (_, handler) = register_command()
    payload = valid_payload(run_id="run-005")
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
        "schema": 2,
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


REPO_ROOT = PLUGIN_PATH.parents[3].resolve()
ADAPTER_PATH = REPO_ROOT / "src" / "coherence" / "planning" / "legal_actions_adapter.py"

# 0-based index of the ``--project-root`` value in the backend argv.
PROJECT_ROOT_ARG = 6


def fake_run_recording(calls: list[list[str]], run_id: str):
    """A `subprocess.run` replacement that records argv and returns a valid payload."""

    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        del kwargs
        calls.append(command)
        return completed_json(valid_payload(run_id=run_id))

    return fake_run


def test_adapter_module_is_loaded_by_file_path_not_by_package_import(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The shared logic is executed from this repository's source file directly.

    ``Path(adapter.__file__)`` alone does not prove *how* the module was
    loaded: a package import of ``coherence.planning.legal_actions_adapter``
    resolves to this same file in a checkout with the project installed, so
    that assertion passes either way. What distinguishes file-path loading is
    that the loaded module is never registered in ``sys.modules`` under the
    package name -- a package import always leaves that entry behind. The
    assertion therefore proves the file-path load path, not the site-packages
    question the module docstring used to claim.
    """
    module = load_plugin()

    # Another test module in the same session may already have imported the
    # submodule as a package; clear it so the assertion observes only what this
    # plugin's own load path does. monkeypatch restores it afterwards.
    monkeypatch.delitem(
        sys.modules, "coherence.planning.legal_actions_adapter", raising=False
    )

    adapter = module._load_adapter()

    assert Path(adapter.__file__).resolve() == ADAPTER_PATH
    assert "coherence.planning.legal_actions_adapter" not in sys.modules
    assert adapter.is_safe_run_id("run-001")


def test_loading_the_adapter_does_not_import_the_planning_package() -> None:
    """Loading the adapter by file path -- all the way through
    ``_load_adapter()``, not merely importing this plugin module -- never runs
    ``coherence/planning/__init__.py``, which would pull this project's full
    runtime (``python-frontmatter`` and the rest of the planning chain) into
    whatever interpreter is hosting Hermes.

    The probe runs in a fresh interpreter (so ``sys.modules`` starts empty) and
    calls ``_load_adapter()`` for real, with the checkout supplied through
    ``COHERENCE_REPO_ROOT`` so resolution succeeds. That is what makes this a
    regression guard for the load path itself: a package import injected
    anywhere inside ``_load_adapter()`` shows up as ``planning_imported=True``.
    """
    program = (
        "import importlib.util, sys\n"
        "from pathlib import Path\n"
        "spec = importlib.util.spec_from_file_location('probe', sys.argv[1])\n"
        "module = importlib.util.module_from_spec(spec)\n"
        "spec.loader.exec_module(module)\n"
        "adapter = module._load_adapter()\n"
        "print('adapter_file=' + str(Path(adapter.__file__).resolve()))\n"
        "print('planning_imported=' + str('coherence.planning' in sys.modules))\n"
        "print('has_loader=' + str(hasattr(module, '_load_adapter')))\n"
    )

    result = subprocess.run(
        [sys.executable, "-c", program, str(PLUGIN_PATH)],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=True,
        env={**os.environ, "COHERENCE_REPO_ROOT": str(REPO_ROOT)},
    )

    assert f"adapter_file={ADAPTER_PATH}" in result.stdout
    assert "planning_imported=False" in result.stdout
    assert "has_loader=True" in result.stdout


def test_project_root_override_reaches_the_backend_argv(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _, _, (_, handler) = register_command()
    calls: list[list[str]] = []
    monkeypatch.setattr(subprocess, "run", fake_run_recording(calls, "run-010"))
    monkeypatch.setenv("COHERENCE_PROJECT_ROOT", str(tmp_path))

    invoke(handler, "run-010")

    assert len(calls) == 1
    assert calls[0][PROJECT_ROOT_ARG] == str(tmp_path)


def test_project_root_falls_back_to_the_checkout_when_cwd_is_not_one(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A host started outside the checkout (a user-level install) still queries
    this project rather than failing or silently using the wrong root."""
    _, _, (_, handler) = register_command()
    calls: list[list[str]] = []
    monkeypatch.setattr(subprocess, "run", fake_run_recording(calls, "run-011"))
    monkeypatch.delenv("COHERENCE_PROJECT_ROOT", raising=False)
    monkeypatch.chdir(tmp_path)

    invoke(handler, "run-011")

    assert len(calls) == 1
    assert calls[0][PROJECT_ROOT_ARG] == str(REPO_ROOT)


def test_deployment_marker_points_an_out_of_tree_install_at_the_checkout(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """An install that does not live inside the checkout (a user-level Hermes
    plugin) declares the checkout via ``repo_root.txt`` beside the plugin."""
    module, _, (_, handler) = register_command()
    install = tmp_path / "plugins" / "coherence-plan"
    install.mkdir(parents=True)
    (install / "repo_root.txt").write_text(str(REPO_ROOT), encoding="utf-8")
    monkeypatch.setattr(module, "__file__", str(install / "plugin.py"))
    monkeypatch.delenv("COHERENCE_REPO_ROOT", raising=False)
    calls: list[list[str]] = []
    monkeypatch.setattr(subprocess, "run", fake_run_recording(calls, "run-012"))
    monkeypatch.chdir(tmp_path)

    invoke(handler, "run-012")

    assert len(calls) == 1
    assert calls[0][PROJECT_ROOT_ARG] == str(REPO_ROOT)


def test_unresolvable_checkout_blocks_instead_of_raising(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """No candidate can supply the adapter, so ``_repo_root()`` returns ``None``
    and ``_load_adapter()`` raises the plugin's own ``FileNotFoundError``, which
    ``_run`` renders as a block.

    This takes the plugin's own ``root is None`` guard: both env overrides are
    cleared (an override that does not carry the adapter is now skipped like
    any other candidate), and ``__file__`` points at a marker-less out-of-tree
    install directory, so neither the ``repo_root.txt`` marker nor
    self-location can reach a checkout. That is what makes the None branch --
    not ``exec_module``'s errno from a bogus override path -- the branch under
    test.
    """
    module, _, (_, handler) = register_command()
    install = tmp_path / "plugins" / "coherence-plan"
    install.mkdir(parents=True)
    monkeypatch.setattr(module, "__file__", str(install / "plugin.py"))
    calls: list[Any] = []
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: calls.append(args))
    monkeypatch.delenv("COHERENCE_REPO_ROOT", raising=False)
    monkeypatch.delenv("COHERENCE_PROJECT_ROOT", raising=False)

    output = invoke(handler, "run-013")

    assert calls == []
    assert output.startswith("planning blocked:")
    assert "no pi-agent-factory checkout found" in output
    assert "legal_actions_adapter" in output
