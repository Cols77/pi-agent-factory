"""Thin Hermes adapter for the Coherence planning projection."""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any

_SAFE_RUN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def _legal_actions_command(project_root: Path, run_id: str) -> list[str]:
    return [
        "uv",
        "run",
        "coherence",
        "plan",
        "legal-actions",
        "--project-root",
        str(project_root),
        "--run-id",
        run_id,
        "--json",
    ]


def _parse_projection(raw: str, run_id: str) -> dict[str, Any]:
    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, TypeError) as exc:
        raise ValueError("invalid planning legal-actions response") from exc

    if not isinstance(payload, dict):
        raise ValueError("invalid planning legal-actions response")
    if (
        type(payload.get("schema")) is not int
        or payload["schema"] != 1
        or not isinstance(payload.get("run_id"), str)
        or payload["run_id"] != run_id
        or not isinstance(payload.get("blocked"), bool)
        or "reason" not in payload
        or not (payload["reason"] is None or isinstance(payload["reason"], str))
        or not isinstance(payload.get("legal_next_actions"), list)
        or not all(isinstance(action, str) for action in payload["legal_next_actions"])
        or payload.get("starts_automatically") is not False
    ):
        raise ValueError("invalid planning legal-actions response")
    return payload


def _render_projection(payload: dict[str, Any]) -> str:
    status = f"Planning blocked: {payload['reason'] or 'UNKNOWN'}" if payload["blocked"] else "Planning ready"
    actions = ", ".join(payload["legal_next_actions"]) or "none"
    return "\n".join(
        (
            status,
            f"Legal actions: {actions}",
            "Starts automatically: no",
        )
    )


def _run(raw_args: str) -> str:
    run_id = raw_args.strip()
    if not _SAFE_RUN_ID.fullmatch(run_id):
        return "usage: /coherence-plan <run-id>"

    command = _legal_actions_command(Path.cwd(), run_id)
    try:
        result = subprocess.run(
            command,
            cwd=Path.cwd(),
            capture_output=True,
            text=True,
            check=False,
            shell=False,
        )
        if result.returncode != 0:
            detail = (result.stderr or "backend exited unsuccessfully").strip()
            return f"planning blocked: {detail}"
        payload = _parse_projection(result.stdout or "", run_id)
    except (OSError, ValueError) as exc:
        detail = (getattr(locals().get("result", None), "stderr", "") or str(exc)).strip()
        return f"planning blocked: {detail}"
    return _render_projection(payload)


def register(ctx: Any) -> None:
    """Register the namespaced command without relying on optional host state."""
    ctx.register_command(
        "coherence-plan",
        _run,
        description="Inspect Coherence-authorized planning actions for a run",
    )
