"""Build CI's required command list from the compiled project obligations."""
from __future__ import annotations

import shlex
from collections.abc import Iterable
from pathlib import Path

from coherence.policy.compiler import compile_obligations


class NoBlockingObligationError(RuntimeError):
    """The project has no complete blocking CI obligation set."""


def required_ci_commands(root: Path) -> list[str]:
    """Return compiled blocking CI commands followed by structural checks."""
    obligations = compile_obligations(root, "project")
    selected = [
        obligation
        for obligation in obligations
        if obligation.kind == "ci_verification" and obligation.requiredness == "blocking"
    ]
    if not selected:
        raise NoBlockingObligationError("no blocking ci_verification obligations found")

    commands: list[str] = []
    for obligation in selected:
        if not obligation.resolve_cmd or any(not command.strip() for command in obligation.resolve_cmd):
            raise NoBlockingObligationError(
                f"blocking obligation {obligation.id} has no complete resolve_cmd"
            )
        commands.extend(obligation.resolve_cmd)

    return commands + [
        "coherence trace check",
        "coherence register check",
    ]


def _resolved_gate_commands(root: Path) -> dict[str, list[str]]:
    """Resolve configured gate commands without introducing another command source."""
    from factory.config import load_config
    from factory.orchestrator.backends import _quote_for_shell, _target_python

    python = _quote_for_shell(_target_python(root))
    return {
        name: [step.cmd.replace("{python}", python) for step in steps]
        for name, steps in load_config(root).gates.items()
    }


def _is_static_command(command: str) -> bool:
    try:
        tokens = shlex.split(command)
    except ValueError:
        return False
    return any(token in {"ruff", "pyright", "ruff.exe", "pyright.exe"} for token in tokens)


def _is_extension_command(command: str) -> bool:
    try:
        tokens = shlex.split(command)
    except ValueError:
        return False
    return any(
        token.replace("\\", "/").rsplit("/", 1)[-1] in {"ext.py", "watch_ext.py"}
        for token in tokens
    )


def campaign_ci_commands(root: Path, campaigns: Iterable[str]) -> list[str]:
    """Project configured CI commands for internal campaign identifiers.

    The all-command projection is deliberately delegated to
    :func:`required_ci_commands`, preserving its existing output and order. A
    narrow projection is permitted only when every requested campaign has a
    configured or unambiguously discoverable command. Otherwise this returns
    the complete list, so a missing command can never become a false-green job.
    """
    all_commands = required_ci_commands(root)
    if isinstance(campaigns, (str, bytes)):
        return all_commands
    try:
        requested = set(campaigns)
    except (TypeError, ValueError):
        return all_commands
    if not requested or "full" in requested:
        return all_commands
    if not requested.issubset(
        {"unit", "integration", "e2e", "static", "extensions", "structural"}
    ):
        return all_commands

    configured = _resolved_gate_commands(root)
    structural = all_commands[-2:]
    projected: list[str] = []
    for campaign in (
        "unit",
        "integration",
        "e2e",
        "extensions",
        "static",
        "structural",
    ):
        if campaign not in requested:
            continue
        if campaign == "structural":
            commands = structural
        elif campaign in configured:
            commands = configured[campaign]
        elif campaign == "static":
            commands = [
                command
                for command in configured.get("full", [])
                if _is_static_command(command)
            ]
        elif campaign == "extensions":
            commands = [
                command
                for command in configured.get("full", [])
                if _is_extension_command(command)
            ]
        else:
            # In particular, this handles an e2e campaign when the project has
            # no declared e2e command. Falling back to all is safer than
            # guessing that another gate is equivalent.
            return all_commands
        if not commands:
            return all_commands
        for command in commands:
            if command not in projected:
                projected.append(command)

    if not projected or any(command not in all_commands for command in projected):
        return all_commands
    return projected


# Explicit alias for callers that describe this operation as a selected-command
# projection rather than a campaign projection.
selected_ci_commands = campaign_ci_commands
