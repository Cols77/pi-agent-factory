"""Reverse navigation: `query_reverse` walks a `file:` scope back to the
requirement it serves (increment B "V-cycle", reverse half -- open a file,
see where it came from).

Task 3's `query_story` walks forward: task -> runs -> requirements. This
module walks the same links backward: file -> (evidence manifest whose
`implementation.changed_files` names the file) -> `task_id` -> ledger task
-> `satisfies` edges mapped through `factory.system.refs.
sr_ref_from_trace_id`. Every hop is a recorded link already read by an
existing loader; nothing here infers a hop that was not recorded:

- `factory.evidence.manifests.list_run_manifests` for the durable per-run
  evidence -- a manifest's `implementation.changed_files` is the sole,
  recorded basis for "this run touched this file" (never reconstructed from
  git, never a directory listing);
- `substrate.ledger.tasks` for the task record a matched run's
  `task_id` names, and that task's own `satisfies` frontmatter -- the same
  field `factory.trace.model.extract_edges` reads to build the task's
  `satisfies` trace edge (see `story._requirements_for_task`'s comment; the
  same reasoning applies here unchanged).

Session records are never consulted: a session record carries no changed
files and no commit range (design), so it cannot participate in a
file-anchored walk at all -- there is nothing in one to match a file
against.

A file may be named by several runs' `changed_files` (rework, or one file
touched across several tasks); each such run yields its own path entry --
paths are never collapsed by file. Paths are ordered by the run's own
recorded `started_at`, then by the run's citation path -- never by array
position across documents (mirrors `story.py`'s discipline for its own
`runs` list; see that module's docstring).

`stops_at` on a path names the first hop that did not resolve -- `"task"`
when the manifest's `task_id` does not resolve in the ledger, `"satisfies"`
when the resolved task's `satisfies` list is empty or maps to no known
requirement -- or `None` when the chain completes. The walk never guesses
past an unresolved hop; it stops and says where.
"""
from __future__ import annotations

from pathlib import Path

from factory.evidence import manifests as evidence_manifests
from factory.system._claims import (
    evidence_dir as _evidence_dir,
    fresh as _fresh,
    manifest_path as _manifest_path,
    sha256_file as _sha256_file,
    tasks_dir as _tasks_dir,
)
from factory.system.models import (
    ClaimClass,
    CitationKind,
    SystemCitation,
    SystemClaim,
    SystemScopeRef,
    to_dict,
)
from factory.system.queries import ScopeKindError, ScopeNotFoundError
from factory.system.refs import sr_ref_from_trace_id
from substrate.ledger import tasks as ledger


def _resolve_scope_file(repo_root: Path, scope: SystemScopeRef) -> Path:
    """Resolve `scope` (`file:<repo-relative path>`) to a real, in-repo,
    non-exported-guide file -- or raise.

    Security-critical ordering (task 4 brief): the candidate path is
    resolved against the repo root with `.resolve()` *before* the
    containment check runs. Checking containment on the unresolved path
    first would let a `..`-laden ref slip past the check and only be
    resolved afterward -- the classic traversal bypass. Escaping the repo,
    not existing, and being a file this package itself exported (`factory.
    system.guide.is_exported_guide`, the design SS4.5 non-readmission rule)
    are all reported the same way: `ScopeNotFoundError`, not a fuzzy fallback.
    """
    if scope.kind != "file":
        raise ScopeKindError(f"query_reverse only supports a file scope, got: {scope.kind!r}")
    prefix = "file:"
    if not scope.ref.startswith(prefix) or scope.ref == prefix:
        raise ScopeKindError(f"scope ref {scope.ref!r} does not match kind 'file'")
    raw = scope.ref[len(prefix):]

    root = repo_root.resolve()
    resolved = (root / raw).resolve()
    if resolved == root or root not in resolved.parents:
        raise ScopeNotFoundError(f"file path escapes the repo root: {raw!r}")
    if not resolved.is_file():
        raise ScopeNotFoundError(f"file not found: {raw!r}")

    # Deferred import: factory.system.guide imports query_brief/query_matrix/
    # query_timeline from factory.system.queries at its own module level, so
    # a module-level import here would be circular (same reason queries.py's
    # own guide-export guard defers it).
    from factory.system import guide as _guide

    if _guide.is_exported_guide(resolved):
        raise ScopeNotFoundError(f"file is an exported guide, not a navigable source file: {raw!r}")
    return resolved


def _changed_files(manifest: dict) -> list[str]:
    """The manifest's recorded changed files, read tolerantly.

    `load_run_manifest` returns spec-§20 simulation bundles *unvalidated*
    (tolerant path), so such a bundle may carry no `implementation` block at
    all -- a run with no recorded changed files, not a corruption the walk
    should crash on. A manifest like that can never match a file scope; the
    honest answer is the designed `no recorded run touching it` degraded
    reason, never a KeyError that kills the whole reverse query (which was
    surfacing in the browser as a raw traceback behind `why this file:`).
    """
    implementation = manifest.get("implementation")
    changed = implementation.get("changed_files") if isinstance(implementation, dict) else None
    if not isinstance(changed, list):
        return []
    return [entry for entry in changed if isinstance(entry, str)]


def _run_entry(evidence_dir: Path, manifest: dict) -> dict:
    """One matched run: the manifest whose `implementation.changed_files`
    named the walked file. Mirrors `story._manifest_run`'s claim/citation
    construction -- `CitationKind.MANIFEST`, `recorded`/`fresh`, changed
    files reproduced verbatim, never reconstructed -- so a run reads the
    same whether the V-cycle is walked forward (`query_story`) or backward
    (here). `manifest` came back from `list_run_manifests`; the remaining
    fields (`run_id`, `outcome`, timestamps, commits) are schema-validated
    on every validation-tracked shape, and `changed_files` is read through
    `_changed_files` so the tolerant §20 path cannot break it either.
    """
    run_id = manifest["run_id"]
    path = _manifest_path(evidence_dir, run_id)
    citation = SystemCitation(kind=CitationKind.MANIFEST, path=str(path), sha256=_sha256_file(path))
    changed_files = _changed_files(manifest)
    claim = SystemClaim(
        kind=ClaimClass.RECORDED,
        text=f"run {run_id}: {len(changed_files)} changed file(s) recorded",
        freshness=_fresh(),
        citations=[citation],
    )
    implementation = to_dict(claim)
    implementation["changed_files"] = changed_files
    return {
        "run_id": run_id,
        "outcome": manifest["outcome"],
        "started_at": manifest["started_at"],
        "ended_at": manifest["ended_at"],
        "start_commit": manifest["start_commit"],
        "result_commit": manifest["result_commit"],
        "implementation": implementation,
        "citation": to_dict(citation),
    }


def _requirements_for_task(task: ledger.Task) -> list[str]:
    """The task's requirements from its own recorded `satisfies` list, each
    mapped through `sr_ref_from_trace_id` and dropped -- never guessed --
    when unmappable. Same source field, same mapping, same drop discipline
    as `story._requirements_for_task`."""
    requirements: list[str] = []
    for raw in task.satisfies:
        mapped = sr_ref_from_trace_id(raw)
        if mapped is not None:
            requirements.append(mapped)
    return requirements


def _path_entry(evidence_dir: Path, tasks: list[ledger.Task], file_ref: str, manifest: dict) -> dict:
    run = _run_entry(evidence_dir, manifest)
    task = ledger.get_task(tasks, manifest["task_id"])
    if task is None:
        return {
            "file": file_ref,
            "run": run,
            "task": None,
            "requirements": [],
            "stops_at": "task",
        }
    requirements = _requirements_for_task(task)
    return {
        "file": file_ref,
        "run": run,
        "task": {"id": task.id, "title": task.title, "status": task.status},
        "requirements": requirements,
        "stops_at": None if requirements else "satisfies",
    }


def _reverse_degraded_reasons(path_count: int, task_stop_count: int, satisfies_stop_count: int) -> list[str]:
    """Distinct, counted reasons `query_reverse`'s `degraded` is true --
    mirroring `story._story_degraded_reasons`'s discipline: each string
    corresponds to something actually counted, never an invented or generic
    explanation; no reason fires with a count of zero."""
    reasons: list[str] = []
    if path_count == 0:
        reasons.append(
            "file has no recorded run touching it (no evidence manifest's changed_files entry matches)"
        )
    if task_stop_count:
        reasons.append(
            f"{task_stop_count} path(s) reference a task id that no longer resolves in the ledger"
        )
    if satisfies_stop_count:
        reasons.append(
            f"{satisfies_stop_count} path(s) have no recorded satisfies requirement link"
        )
    return reasons


def query_reverse(repo_root: Path, scope: SystemScopeRef) -> dict:
    """Walk a `file:` scope back to the requirement(s) it serves.

    Returns `{"scope": {...}, "paths": [...], "degraded": bool,
    "degraded_reasons": [...]}`. Each path is `{"file": str, "run": {...},
    "task": {...} | None, "requirements": [...], "stops_at": str | None}`.
    Raises `ScopeNotFoundError` when the file ref escapes the repo, does not
    exist, or names an exported guide (`_resolve_scope_file`), and
    `ScopeKindError` for any scope kind other than `file`.
    """
    resolved = _resolve_scope_file(repo_root, scope)
    file_ref = resolved.relative_to(repo_root.resolve()).as_posix()

    evidence_dir_path = _evidence_dir(repo_root)
    tasks = ledger.load_tasks(_tasks_dir(repo_root))

    matched_manifests = [
        manifest
        for manifest in evidence_manifests.list_run_manifests(evidence_dir_path)
        if file_ref in _changed_files(manifest)
    ]

    paths = [
        _path_entry(evidence_dir_path, tasks, file_ref, manifest) for manifest in matched_manifests
    ]

    # Ordered by the run's own recorded started_at, then citation path --
    # never by array position across documents (module docstring above).
    paths.sort(key=lambda p: (p["run"]["started_at"] or "", p["run"]["citation"]["path"]))

    task_stop_count = sum(1 for p in paths if p["stops_at"] == "task")
    satisfies_stop_count = sum(1 for p in paths if p["stops_at"] == "satisfies")
    degraded_reasons = _reverse_degraded_reasons(len(paths), task_stop_count, satisfies_stop_count)

    return {
        "scope": {"kind": scope.kind, "ref": scope.ref},
        "paths": paths,
        "degraded": bool(degraded_reasons),
        "degraded_reasons": degraded_reasons,
    }
