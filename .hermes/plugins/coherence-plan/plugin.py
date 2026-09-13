"""Thin Hermes adapter for governed Coherence planning operations.

The safety-critical logic (safe run-id grammar, argv-only command building,
JSON contract parsing, exit-code handling, and text rendering) lives in
``coherence.planning.legal_actions_adapter`` so it is not duplicated -- and
cannot silently re-diverge -- between this Hermes adapter and any other host
adapter (e.g. Claude Code's ``.claude/commands/coherence-plan.md``). This file
supplies the Hermes-specific framing: how raw command text arrives, the
Hermes-specific usage message, which project root the backend runs against,
argv-only workflow transport, and registration with the Hermes host.

Two framing decisions are load-bearing for a host that is not started inside
this checkout, and both are cheap to keep honest:

*   **The shared adapter is loaded by file path, not by package import.**
    ``import coherence.planning.legal_actions_adapter`` first executes
    ``coherence/planning/__init__.py``, which eagerly imports the whole
    planning chain (bootstrap -> check -> model -> semantic -> serialization ->
    ``python-frontmatter``). A host process that only wants to *render* a
    projection would then need this project's full runtime installed in its own
    interpreter -- including a matching Python version. The adapter module is
    stdlib-only, so loading it directly from the checkout keeps the host's
    environment untouched while still executing this repository's source
    verbatim. There is no second copy of the logic.

*   **The project root is resolved, not assumed.** The backend is invoked with
    an explicit ``--project-root``, so a host started outside the checkout
    (a user-level Hermes install, for example) still queries the right project.
    ``cwd`` remains the first choice when it is itself the checkout, which keeps
    the ordinary "run Hermes from the repository" path unchanged.
"""

from __future__ import annotations

import importlib.util
import json
import os
import shlex
import subprocess
from pathlib import Path
from types import ModuleType
from typing import Any

#: Explicit overrides, read at call time so a session can be redirected without
#: editing this file.
REPO_ROOT_ENV = "COHERENCE_REPO_ROOT"
PROJECT_ROOT_ENV = "COHERENCE_PROJECT_ROOT"

#: The shared, stdlib-only adapter, relative to a pi-agent-factory checkout.
_ADAPTER_RELATIVE = Path("src") / "coherence" / "planning" / "legal_actions_adapter.py"

#: Optional deployment marker written next to this file by an install that does
#: not live inside the checkout (a user-level Hermes plugin, for example). It
#: holds the path of the checkout that owns the shared adapter.
_MARKER_NAME = "repo_root.txt"

#: Depth of ``<repo>/.hermes/plugins/coherence-plan/plugin.py`` from the repo.
_LOCAL_INSTALL_PARENTS = 3

_SESSION_VERBS = frozenset(
    {"start", "resume", "status", "append", "propose-challenge", "resolve", "finalize"}
)
_PIPELINE_VERBS = frozenset(
    {
        "bootstrap",
        "check",
        "review",
        "write-artifact-manifest",
        "write-cross-artifact-review",
        "record-sr-consent",
        "run-planning-gates",
        "handoff",
    }
)
_WORKFLOW_VERBS = _SESSION_VERBS | _PIPELINE_VERBS


def _has_adapter(root: Path) -> bool:
    """Whether `root` is a checkout that carries the shared adapter."""
    return (root / _ADAPTER_RELATIVE).is_file()


def _repo_root() -> Path | None:
    """Locate the checkout that owns the shared adapter, or ``None``.

    Resolution order: the ``COHERENCE_REPO_ROOT`` override, a deployment marker
    file beside this plugin, then this file's own location when it is installed
    inside a checkout. Every candidate -- the explicit override included -- is
    accepted only when it actually carries the shared adapter, so a
    misconfigured override falls through to the remaining candidates and
    finally to ``None``: the failure surfaces as this plugin's own fail-closed
    "no checkout found" message instead of an opaque error from loading a
    nonexistent file.
    """
    candidates: list[Path] = []

    override = os.environ.get(REPO_ROOT_ENV, "").strip()
    if override:
        candidates.append(Path(override))

    marker = Path(__file__).resolve().parent / _MARKER_NAME
    try:
        marker_text = marker.read_text(encoding="utf-8").strip()
    except OSError:
        marker_text = ""
    if marker_text:
        candidates.append(Path(marker_text))

    here = Path(__file__).resolve()
    if len(here.parents) > _LOCAL_INSTALL_PARENTS:
        candidates.append(here.parents[_LOCAL_INSTALL_PARENTS])

    for candidate in candidates:
        if _has_adapter(candidate):
            return candidate
    return None


def _looks_like_checkout(path: Path) -> bool:
    """Whether `path` can serve as ``--project-root`` for the coherence CLI."""
    return (path / "pyproject.toml").is_file() and (path / "src" / "coherence").is_dir()


def _project_root() -> Path:
    """Resolve the Coherence project root the backend is invoked against."""
    override = os.environ.get(PROJECT_ROOT_ENV, "").strip()
    if override:
        return Path(override)

    cwd = Path.cwd()
    if _looks_like_checkout(cwd):
        return cwd

    repo_root = _repo_root()
    return repo_root if repo_root is not None else cwd


def _load_adapter() -> ModuleType:
    """Load the repository's shared legal-actions adapter by file path."""
    root = _repo_root()
    if root is None:
        raise FileNotFoundError(
            f"no pi-agent-factory checkout found carrying {_ADAPTER_RELATIVE}"
        )
    path = root / _ADAPTER_RELATIVE
    spec = importlib.util.spec_from_file_location(
        "_coherence_legal_actions_adapter", path
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load the coherence planning adapter from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_legal_actions_adapter() -> ModuleType:
    """Load and return the shared legal-actions adapter."""
    return _load_adapter()


def _legal_actions(run_id: str) -> str:
    """Render the read-only planning projection, or a block."""
    try:
        adapter = _load_legal_actions_adapter()
        is_safe_run_id = adapter.is_safe_run_id
        legal_actions_report = adapter.legal_actions_report
    except Exception as exc:  # deliberately broad at the foreign-code boundary
        return f"planning blocked: {exc}"
    if not is_safe_run_id(run_id):
        return "usage: /coherence-plan <run-id>"
    return legal_actions_report(_project_root(), run_id)


def _extract_run_id(tokens: list[str]) -> str | None:
    values: list[str] = []
    for index, token in enumerate(tokens):
        if token.startswith("--run-id="):
            values.append(token.partition("=")[2])
        elif token == "--run-id" and index + 1 < len(tokens):
            values.append(tokens[index + 1])
    if len(values) != 1:
        return None
    return values[0]


def _workflow_command(root: Path, tokens: list[str]) -> list[str]:
    """Build one explicit Coherence planning command without a shell."""
    verb = tokens[0]
    if verb not in _WORKFLOW_VERBS:
        raise ValueError("unsupported planning verb")
    if any(
        token == "--json"
        or token.startswith("--json=")
        or token == "--project-root"
        or token.startswith("--project-root=")
        for token in tokens[1:]
    ):
        raise ValueError("project root and JSON output are controlled by the Hermes adapter")
    run_id = _extract_run_id(tokens[1:])
    if run_id is None or not run_id or not _load_legal_actions_adapter().is_safe_run_id(run_id):
        raise ValueError("usage: /coherence-plan <verb> --run-id <run-id> ...")
    return [
        "uv",
        "run",
        "coherence",
        "plan",
        verb,
        "--project-root",
        str(root),
        *tokens[1:],
        "--json",
    ]


def _run_workflow(tokens: list[str]) -> str:
    """Transport one allowlisted planning verb, returning structured JSON or a block."""
    root = _project_root()
    try:
        command = _workflow_command(root, tokens)
    except Exception as exc:
        return str(exc) if str(exc).startswith("usage:") else f"planning blocked: {exc}"
    try:
        result = subprocess.run(
            command,
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
            shell=False,
        )
    except OSError as exc:
        return f"planning blocked: {exc}"
    if result.returncode not in (0, 1):
        detail = (result.stderr or "").strip()[:500]
        return f"planning blocked: backend exited with status {result.returncode}{(': ' + detail) if detail else ''}"
    try:
        payload = json.loads(result.stdout or "")
    except (json.JSONDecodeError, TypeError):
        detail = (result.stderr or "").strip()[:500]
        return f"planning blocked: invalid planning response{(': ' + detail) if detail else ''}"
    if not isinstance(payload, dict):
        return "planning blocked: invalid planning response"
    run_id = _extract_run_id(tokens[1:])
    if (
        type(payload.get("schema")) is not int
        or payload["schema"] != 2
        or not isinstance(payload.get("run_id"), str)
        or payload["run_id"] != run_id
    ):
        return "planning blocked: invalid planning response"
    return json.dumps(payload, sort_keys=True)


def _run(raw_args: str) -> str:
    """Inspect or transport a planning operation, never a host-level raise.

    ``_load_adapter()`` executes a file this plugin does not control, so the
    load path can surface arbitrary exception types -- a missing checkout
    (``FileNotFoundError``), an unreadable adapter file (``OSError``), a
    foreign or API-incompatible adapter (``ImportError``, ``AttributeError``),
    or a source file that does not even parse (``SyntaxError``). All of those
    are rendered as ``"planning blocked: ..."`` rather than escaping into the
    host. The required callables are bound inside the same handler so an
    adapter that does not expose them is caught too; ``legal_actions_report``
    itself is then invoked *outside* it, so a genuine backend result is never
    swallowed by this guard.
    """
    try:
        tokens = shlex.split(raw_args)
    except ValueError as exc:
        return f"planning blocked: invalid command arguments: {exc}"
    if not tokens:
        return "usage: /coherence-plan <run-id> | <verb> --run-id <run-id> ..."
    if len(tokens) == 1 and tokens[0] not in _WORKFLOW_VERBS:
        return _legal_actions(tokens[0])
    if tokens[0] == "legal-actions":
        run_id = _extract_run_id(tokens[1:])
        return _legal_actions(run_id or "")
    return _run_workflow(tokens)


def register(ctx: Any) -> None:
    """Register the namespaced command without relying on optional host state."""
    ctx.register_command(
        "coherence-plan",
        _run,
        description="Inspect or drive an explicit Coherence planning operation",
    )
