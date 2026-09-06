"""Fail-closed adapter for the Coherence planning legal-actions projection."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Sequence

_SAFE_RUN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def build_legal_actions_command(project_root: Path, run_id: str) -> list[str]:
    """Build the argv-only backend command after validating its inputs."""
    if not isinstance(run_id, str) or _SAFE_RUN_ID.fullmatch(run_id) is None:
        raise ValueError("unsafe run ID")
    if not isinstance(project_root, Path) or not project_root.is_dir():
        raise ValueError("project root must be a directory")
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


def parse_projection(raw: str, run_id: str) -> dict[str, Any]:
    """Parse and validate a schema-1 legal-actions projection."""
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
        or type(payload.get("blocked")) is not bool
        or "reason" not in payload
        or not (payload["reason"] is None or isinstance(payload["reason"], str))
        or not isinstance(payload.get("legal_next_actions"), list)
        or not all(
            isinstance(action, str) for action in payload["legal_next_actions"]
        )
        or payload.get("starts_automatically") is not False
    ):
        raise ValueError("invalid planning legal-actions response")
    return payload


def query_legal_actions(project_root: Path, run_id: str) -> dict[str, Any]:
    """Query Coherence and return only a validated legal-actions projection."""
    resolved_project_root = project_root.resolve()
    command = build_legal_actions_command(resolved_project_root, run_id)
    result = subprocess.run(
        command,
        cwd=resolved_project_root,
        capture_output=True,
        text=True,
        check=False,
        shell=False,
    )
    if result.returncode not in (0, 1):
        detail = (result.stderr or "").strip()
        suffix = f": {detail[:200]}" if detail else ""
        raise ValueError(
            f"backend exited with unexpected status {result.returncode}{suffix}"
        )
    payload = parse_projection(result.stdout or "", run_id)
    expected_blocked = result.returncode == 1
    if payload["blocked"] is not expected_blocked:
        projection_status = "blocked" if payload["blocked"] else "ready"
        raise ValueError(
            f"backend exit code {result.returncode} contradicts "
            f"{projection_status} projection"
        )
    return payload


def _backend_invalid_projection(run_id: str, error: BaseException) -> dict[str, Any]:
    detail = str(error).strip()[:200] or type(error).__name__
    return {
        "schema": 1,
        "run_id": run_id,
        "blocked": True,
        "reason": "BACKEND_INVALID",
        "legal_next_actions": [],
        "starts_automatically": False,
        "error": detail,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    legal_actions = subparsers.add_parser("legal-actions")
    legal_actions.add_argument("--project-root", type=Path, required=True)
    legal_actions.add_argument("--run-id", required=True)

    run_id = ""
    try:
        args = parser.parse_args(argv)
        run_id = args.run_id
        payload = query_legal_actions(args.project_root, args.run_id)
    except SystemExit as exc:
        if exc.code == 0:
            raise
        payload = _backend_invalid_projection(
            run_id, ValueError("invalid command-line arguments")
        )
    except (OSError, RuntimeError, ValueError) as exc:
        payload = _backend_invalid_projection(run_id, exc)

    print(json.dumps(payload, sort_keys=True))
    return 1 if payload["blocked"] else 0


if __name__ == "__main__":
    sys.exit(main())
