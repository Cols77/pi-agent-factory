"""JSON-lines worker for the docs server (performance fast path).

The docs server starts one long-lived `coherence.navigate worker` process per
served repository root and speaks a tiny JSON-lines protocol over
stdin/stdout. A request is one line::

    {"id": 1, "cmd": "brief", "params": {"scope": "bundle:evidence-lifecycle"}}

and the worker answers with exactly one line::

    {"id": 1, "ok": true, "value": {...}}

or, for a structured command failure (bad scope ref, unreadable file, ...)::

    {"id": 1, "ok": false, "error": "...", "kind": "ScopeNotFoundError"}

Protocol rules, all enforced here:

* stdout carries **nothing but response lines** -- one response per request,
  in request order for a single-threaded worker, ids matched by the caller.
  Diagnostics belong on stderr, exactly like the CLI's error discipline.
* only read-only projections are served. `goal evaluate` (writes goal state)
  and `guide --export` (writes a file) have no worker handler: the worker is
  the browser's execution engine, and the browser has no write affordance.
* malformed requests, unknown commands, and missing params are answered with
  a structured `ok: false` (kind "WorkerProtocolError") so the caller can see
  the problem as JSON instead of a half-parse; the worker stays alive.
* the loop exits 0 on EOF (stdin closed) -- that is how the docs server shuts
  the worker down.

Every handler delegates to the same ``cmd_*`` function the CLI subcommand
uses, so a worker response is byte-for-byte the same *computed* JSON (module
startup and imports amortized across requests) -- no separate code path can
drift into a different answer.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import TextIO

from coherence.navigate.cli import (
    cmd_brief,
    cmd_diagram,
    cmd_goal_list,
    cmd_goal_show,
    cmd_guide,
    cmd_health,
    cmd_labels,
    cmd_matrix,
    cmd_reverse,
    cmd_scope,
    cmd_sim_failure,
    cmd_sim_goal_evidence,
    cmd_sim_latest,
    cmd_sim_metric,
    cmd_sim_run,
    cmd_story,
    cmd_timeline,
    cmd_traversal,
    cmd_validation,
    cmd_vcycle,
)
from coherence.navigate.actions import Action, execute_confirmed_action
from coherence.navigate.dossier import cmd_dossier
from coherence.navigate.queries import ScopeError

# Read-only projection handlers: command name -> (repo_root, params) -> dict.
# Param keys mirror the docs-server query parameters exactly; every key is
# required. This explicit table is the one place the worker's request
# vocabulary is defined -- the TypeScript caller and these lambdas must agree
# on it, and the worker tests pin that agreement down.
def _action(root: Path, params: dict[str, object]) -> dict:
    raw = params.get("action")
    if not isinstance(raw, dict) or not isinstance(raw.get("kind"), str) or not isinstance(raw.get("args"), dict):
        raise ValueError("action must contain string kind and object args")
    return execute_confirmed_action(
        root,
        Action(kind=raw["kind"], args=raw["args"]),
        confirmed=params.get("confirmed") is True,
    )


_HANDLERS: dict[str, object] = {
    "scope": lambda root, p: cmd_scope(root),
    "health": lambda root, p: cmd_health(root),
    "labels": lambda root, p: cmd_labels(root),
    "brief": lambda root, p: cmd_brief(root, p["scope"]),
    "matrix": lambda root, p: cmd_matrix(root, p["scope"]),
    "timeline": lambda root, p: cmd_timeline(root, p["scope"]),
    "guide": lambda root, p: cmd_guide(root, p["scope"], None),
    "traversal": lambda root, p: cmd_traversal(root, p["scope"]),
    "vcycle": lambda root, p: cmd_vcycle(root, p["scope"]),
    "validation": lambda root, p: cmd_validation(root, p["scope"]),
    "story": lambda root, p: cmd_story(root, p["scope"]),
    "reverse": lambda root, p: cmd_reverse(root, p["scope"]),
    "dossier": lambda root, p: cmd_dossier(root, p["scope"]),
    "goal_show": lambda root, p: cmd_goal_show(root, p["goal_id"]),
    "goal_list": lambda root, p: cmd_goal_list(root, p["scope"]),
    "sim_run": lambda root, p: cmd_sim_run(root, p["run_id"]),
    "sim_latest": lambda root, p: cmd_sim_latest(root, p["feature"]),
    "sim_failure": lambda root, p: cmd_sim_failure(root, p["feature"]),
    "sim_metric": lambda root, p: cmd_sim_metric(root, p["metric_id"]),
    "sim_goal_evidence": lambda root, p: cmd_sim_goal_evidence(root, p["goal_id"]),
    "diagram": lambda root, p: cmd_diagram(root, p["diagram_id"]),
    "action": _action,
}


def _protocol_error(request_id: object, message: str) -> dict:
    return {
        "id": request_id,
        "ok": False,
        "error": message,
        "kind": "WorkerProtocolError",
    }


def _answer(repo_root: Path, request_id: object, cmd: str, params: object) -> dict:
    handler = _HANDLERS.get(cmd)
    if handler is None:
        return _protocol_error(request_id, f"unknown worker command: {cmd!r}")
    try:
        value = handler(repo_root, params)  # type: ignore[operator]
    except KeyError as exc:
        return _protocol_error(request_id, f"missing worker param: {exc.args[0]!r}")
    except (ScopeError, FileNotFoundError, ValueError) as exc:
        return {"id": request_id, "ok": False, "error": str(exc), "kind": type(exc).__name__}
    return {"id": request_id, "ok": True, "value": value}


def run_worker(
    repo_root: Path,
    reader: TextIO,
    writer: TextIO,
) -> int:
    """Serve JSON-lines requests from ``reader`` to ``writer`` until EOF.

    Returns the process exit code (0 on a clean stdin-close shutdown). Each
    input line produces exactly one output line, even for malformed input.
    """
    for raw in reader:
        line = raw.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
            if not isinstance(request, dict):
                response = _protocol_error(None, "request must be a JSON object")
            else:
                cmd = request.get("cmd")
                if not isinstance(cmd, str) or not cmd:
                    response = _protocol_error(request.get("id"), "request field 'cmd' must be a non-empty string")
                elif not isinstance(request.get("params"), dict):
                    response = _protocol_error(request.get("id"), "request field 'params' must be an object")
                else:
                    response = _answer(repo_root, request.get("id"), cmd, request["params"])
        except json.JSONDecodeError as exc:
            response = _protocol_error(None, f"malformed request JSON: {exc}")
        writer.write(json.dumps(response) + "\n")
        writer.flush()
    return 0


def main() -> int:
    """CLI entry invoked as ``python -m coherence.navigate worker --repo-root``."""
    repo_root = Path(sys.argv[sys.argv.index("--repo-root") + 1]) if "--repo-root" in sys.argv else Path(".")
    return run_worker(repo_root, sys.stdin, sys.stdout)
