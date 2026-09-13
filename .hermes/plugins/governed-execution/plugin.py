"""Thin Hermes adapter for the Coherence governed-execution command surface.

SR-034/SR-049 AC-10: this plugin gives a human working from a Hermes session
the same driving surface Codex's `.agents/skills/governed-execution/SKILL.md`
and Claude Code's `.claude/commands/governed-execution.md` already give their
hosts -- inspect legal actions, dispatch a task, and relay an explicit human
`retry`/`defer`/`block` decision -- without adding a second lifecycle, a
second journal, or any local interpretation of gates, stages, or evidence.
Python (`coherence.execution.cli`) remains the only authority; this file
transports argv in and renders JSON out.

Unlike `.hermes/plugins/coherence-plan/plugin.py` (which is purely
read-only -- it only ever renders a legal-actions projection), this plugin has
real parity with the Codex skill and Claude Code command: it can also call
`dispatch-task` and `resolve-human`, the same two mutating verbs those two
host adapters expose. `plugin.yaml`'s tags reflect that -- this plugin does
not carry coherence-plan's `read-only` tag.

**Why subprocess instead of coherence-plan's file-path adapter trick.**
`coherence-plan`'s plugin loads `src/coherence/planning/legal_actions_adapter.py`
directly by file path specifically because `coherence.planning`'s own
`__init__.py` eagerly imports the whole planning chain (bootstrap -> check ->
model -> semantic -> serialization -> `python-frontmatter`), and a host that
only wants to render a projection should not need that chain installed in its
own interpreter. `coherence.execution` does not have that problem: its
`__init__.py` is a one-line docstring, and Task 6's own Pi/TypeScript adapter
already invokes the CLI the same way this plugin does -- by shelling out to
`uv run coherence execution ...` and parsing the JSON on stdout. Reusing that
already-proven, already-tested seam is simpler than re-deriving
coherence-plan's by-file-path trick for a module that does not need it, and
`uv run` still gets a Hermes install that lives outside this checkout the
right interpreter and dependencies "for free", the same guarantee
coherence-plan's trick earns a different way.

**Project root resolution** mirrors `coherence-plan`'s plugin exactly:
`COHERENCE_PROJECT_ROOT` first, then the current working directory when it is
itself a checkout, then a checkout located via `COHERENCE_REPO_ROOT` or a
`repo_root.txt` marker beside this file, and finally the working directory as
a last resort. This plugin does not load any file from the located checkout
(it only asks the CLI to run from there), so "the checkout" here means only
"a directory carrying `pyproject.toml` and `src/coherence`".

**Command grammar.** One namespaced command, `/governed-execution`, takes the
Python CLI's own verb as its first word so the two vocabularies never drift:

    /governed-execution legal-actions <run-id> <task-id>
    /governed-execution dispatch-task <run-id> <task-id>
    /governed-execution resolve-human <run-id> <task-id> <request-sha256> \\
        <decision-id> retry|defer|block <response words...>
    /governed-execution stream-progress <run-id>

Both identifiers are validated against the same safe grammar
(`[A-Za-z0-9][A-Za-z0-9._-]*`) Codex and Claude Code document, and are
rejected -- before any subprocess runs -- if either is missing or unsafe.
`legal-actions` and `stream-progress` are pure reads. `dispatch-task` and
`resolve-human` are *gated*: this plugin always calls `legal-actions` first
and only forwards the mutating command when the backend's own
`legal_next_actions` for the current state names it, exactly as AC-10
requires ("calls `legal-actions` before `dispatch-task`"). A `needs_input`
projection is rendered exactly as the backend returned it and is never
answered by this plugin; `resolve-human` fires only when the caller supplies
an explicit `retry`/`defer`/`block` decision as this command's own argument --
never inferred from a Hermes Kanban `done` card, a model's own claim, or
anything else this plugin can see. `starts_automatically` is always whatever
the backend printed, which is always the literal `false` (`ExecutionCliError`
enforces that in Python); this plugin never claims otherwise.

A missing checkout, an unreadable `uv`/CLI, a subprocess exception, or a
non-zero exit outside the CLI's own canonical 0/1 pair are all rendered as an
`execution blocked: ...` string. Nothing here raises into the Hermes host.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
from pathlib import Path
from typing import Any

#: Explicit overrides, read at call time so a session can be redirected
#: without editing this file.
REPO_ROOT_ENV = "COHERENCE_REPO_ROOT"
PROJECT_ROOT_ENV = "COHERENCE_PROJECT_ROOT"

#: Optional deployment marker written next to this file by an install that
#: does not live inside the checkout (a user-level Hermes plugin, for
#: example). It holds the path of the checkout to pass as `--project-root`.
_MARKER_NAME = "repo_root.txt"

#: Depth of `<repo>/.hermes/plugins/governed-execution/plugin.py` from the repo.
_LOCAL_INSTALL_PARENTS = 3

#: Same grammar Codex's SKILL.md and Claude Code's command document, and the
#: same one `coherence.execution.cli` enforces server-side.
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")

#: The closed human-decision vocabulary (never widened here; the CLI's own
#: `DECISIONS` is the authority).
_DECISIONS = ("retry", "defer", "block")

_SUBPROCESS_TIMEOUT_SECONDS = 120

_USAGE = "\n".join(
    [
        "usage:",
        "  /governed-execution legal-actions <run-id> <task-id>",
        "  /governed-execution dispatch-task <run-id> <task-id>",
        "  /governed-execution resolve-human <run-id> <task-id> <request-sha256> "
        "<decision-id> retry|defer|block <response words...>",
        "  /governed-execution stream-progress <run-id>",
    ]
)


def _is_safe_id(value: str) -> bool:
    return bool(_SAFE_ID.match(value))


def _looks_like_checkout(path: Path) -> bool:
    """Whether `path` can serve as `--project-root` for the coherence CLI."""
    return (path / "pyproject.toml").is_file() and (path / "src" / "coherence").is_dir()


def _repo_root() -> Path | None:
    """Locate a checkout to pass as `--project-root`, or `None`.

    Resolution order: the `COHERENCE_REPO_ROOT` override, a deployment marker
    file beside this plugin, then this file's own location when it is
    installed inside a checkout. Every candidate is accepted only when it
    actually looks like a coherence checkout.
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
        if _looks_like_checkout(candidate):
            return candidate
    return None


def _project_root() -> Path:
    """Resolve the `--project-root` the backend CLI is invoked against."""
    override = os.environ.get(PROJECT_ROOT_ENV, "").strip()
    if override:
        return Path(override)

    cwd = Path.cwd()
    if _looks_like_checkout(cwd):
        return cwd

    repo_root = _repo_root()
    return repo_root if repo_root is not None else cwd


# -- backend invocation -------------------------------------------------------


def _build_argv(parts: list[str], project_root: Path) -> list[str]:
    return ["uv", "run", "coherence", "execution", *parts, "--project-root", str(project_root), "--json"]


def _render(returncode: int, stdout: str, stderr: str) -> str:
    """0/1 are the CLI's own canonical pair: forward the payload verbatim.

    Anything else (argparse usage errors, an unconfigured project a subprocess
    could still start against, `uv`/`coherence` themselves failing) is
    rendered as a block instead of guessed at.
    """
    if returncode in (0, 1):
        text = stdout.strip()
        if not text:
            detail = stderr.strip()
            return "execution blocked: empty response from the execution CLI" + (
                f": {detail}" if detail else f" (exit {returncode})"
            )
        try:
            json.loads(text)
        except json.JSONDecodeError as exc:
            return f"execution blocked: invalid JSON from the execution CLI: {exc}"
        return text
    detail = stderr.strip() or f"the execution CLI exited {returncode}"
    return f"execution blocked: {detail}"


def _call(parts: list[str]) -> str:
    """Invoke one `coherence execution <parts>` command, never raising."""
    root = _project_root()
    argv = _build_argv(parts, root)
    try:
        completed = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            cwd=str(root),
            timeout=_SUBPROCESS_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return f"execution blocked: cannot invoke the coherence execution CLI: {exc}"
    return _render(completed.returncode, completed.stdout, completed.stderr)


def _legal_next_actions(rendered: str) -> list[str] | None:
    """The `legal_next_actions` a rendered `legal-actions` call reported, or
    `None` when `rendered` is itself a block message or unparseable JSON."""
    if rendered.startswith("execution blocked:"):
        return None
    try:
        payload = json.loads(rendered)
    except json.JSONDecodeError:
        return None
    actions = payload.get("legal_next_actions") if isinstance(payload, dict) else None
    return actions if isinstance(actions, list) else None


def _gated_call(run_id: str, task_id: str, action_id: str, parts: list[str]) -> str:
    """Query `legal-actions` first; only forward a mutating command it permits.

    This is the one rule AC-10 states explicitly for `dispatch-task` and that
    every host adapter in this feature holds for every mutating verb: the
    backend's own projection is asked before anything changes, and its
    answer -- not this plugin's guess -- decides whether the call proceeds.
    """
    gate_text = _call(["legal-actions", "--run-id", run_id, "--task-id", task_id])
    allowed = _legal_next_actions(gate_text)
    if allowed is None:
        return gate_text
    if action_id not in allowed:
        return (
            f"execution blocked: {action_id} is not currently legal for "
            f"{run_id}/{task_id}\n{gate_text}"
        )
    return _call(parts)


# -- command dispatch ----------------------------------------------------------


def _run(raw_args: str) -> str:
    try:
        tokens = shlex.split(raw_args)
    except ValueError:
        return _USAGE
    if not tokens:
        return _USAGE
    action, *rest = tokens

    if action == "legal-actions":
        if len(rest) != 2:
            return _USAGE
        run_id, task_id = rest
        if not (_is_safe_id(run_id) and _is_safe_id(task_id)):
            return _USAGE
        return _call(["legal-actions", "--run-id", run_id, "--task-id", task_id])

    if action == "dispatch-task":
        if len(rest) != 2:
            return _USAGE
        run_id, task_id = rest
        if not (_is_safe_id(run_id) and _is_safe_id(task_id)):
            return _USAGE
        return _gated_call(
            run_id, task_id, "dispatch-task", ["dispatch-task", task_id, "--run-id", run_id]
        )

    if action == "resolve-human":
        if len(rest) < 5:
            return _USAGE
        run_id, task_id, request_sha256, decision_id, decision, *response_tokens = rest
        if not (_is_safe_id(run_id) and _is_safe_id(task_id)):
            return _USAGE
        if not _SHA256.match(request_sha256):
            return f"usage: request-sha256 must be a canonical lowercase sha256 digest\n{_USAGE}"
        if not decision_id.strip():
            return _USAGE
        if decision not in _DECISIONS:
            return f"usage: decision must be one of {_DECISIONS}\n{_USAGE}"
        response = " ".join(response_tokens).strip()
        if not response:
            return _USAGE
        return _gated_call(
            run_id,
            task_id,
            "resolve-human",
            [
                "resolve-human",
                "--run-id", run_id,
                "--task-id", task_id,
                "--request-sha256", request_sha256,
                "--decision-id", decision_id,
                "--decision", decision,
                "--response", response,
                "--decided-by", "human",
            ],
        )

    if action == "stream-progress":
        if len(rest) != 1:
            return _USAGE
        run_id = rest[0]
        if not _is_safe_id(run_id):
            return _USAGE
        return _call(["stream-progress", run_id])

    return _USAGE


def register(ctx: Any) -> None:
    """Register the namespaced command without relying on optional host state."""
    ctx.register_command(
        "governed-execution",
        _run,
        description=(
            "Drive one named governed execution run through the Python-owned "
            "Coherence execution commands (SR-034/SR-049)"
        ),
    )
