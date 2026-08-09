"""Task implementation story: `query_story` tells one task's implementation
story from recorded evidence (increment B "V-cycle", forward half -- open a
task, see how it was implemented).

Composes existing loaders; never re-parses an artifact a loader already
owns:

- `factory.orchestrator.ledger` for the task record itself -- status,
  title, and the `satisfies` list its own frontmatter carries (the same
  field `factory.trace.model.extract_edges` reads to build a task's
  `satisfies` trace edge, so reading it through the ledger here is not a
  second parser; it is the one place task metadata is already parsed);
- `factory.evidence.manifests.list_run_manifests` for durable per-run
  evidence -- a manifest run's implementation detail (changed files) is
  `recorded`, never reconstructed from git;
- `factory.system.sessions.load_session_runs` for the thinner session
  record kept when no manifest exists for a run -- design: a session
  record never carries changed files or a commit range, so its
  `implementation` is always `missing`/`n/a`.

Where a manifest and a session record exist for the same `run_id`, the
manifest wins outright and the session record for that run is never read
into the story: a session record's absence of detail must never overwrite
detail that is already recorded elsewhere.

Runs are ordered by their own recorded `started_at`, then by citation path
-- never by array position across documents. `list_run_manifests` and
`load_session_runs` each carry their own internal ordering (by
`(ended_at, run_id)` reverse, and by `(started_at, run_id)` respectively);
neither is a legitimate ordering basis once runs from both sources are
merged into one story, so this module re-sorts the merged list itself.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

from factory.evidence import manifests as evidence_manifests
from factory.orchestrator import ledger
from factory.system import sessions
from factory.system.models import (
    ClaimClass,
    CitationKind,
    Freshness,
    FreshnessState,
    SystemCitation,
    SystemClaim,
    SystemScopeRef,
    to_dict,
)
from factory.system.queries import ScopeKindError, ScopeNotFoundError
from factory.system.refs import sr_ref_from_trace_id, trace_id_for_task


def _tasks_dir(repo_root: Path) -> Path:
    return repo_root / "tasks"


def _evidence_dir(repo_root: Path) -> Path:
    return repo_root / "evidence"


def _sha256_file(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def _fresh() -> Freshness:
    return Freshness(state=FreshnessState.FRESH, reason=None, dependencies=[])


def _missing_claim(text: str, reason: str) -> SystemClaim:
    return SystemClaim(
        kind=ClaimClass.MISSING,
        text=text,
        freshness=Freshness(state=FreshnessState.NA, reason=reason, dependencies=[]),
    )


def _task_id_from_scope(scope: SystemScopeRef) -> str:
    if scope.kind != "task":
        raise ScopeKindError(f"query_story only supports a task scope, got: {scope.kind!r}")
    prefix = "task:"
    if not scope.ref.startswith(prefix) or scope.ref == prefix:
        raise ScopeKindError(f"scope ref {scope.ref!r} does not match kind 'task'")
    return scope.ref[len(prefix):]


def _manifest_run(evidence_dir: Path, manifest: dict) -> dict:
    """One `runs[]` entry from a real, schema-valid evidence manifest.

    Cites `CitationKind.MANIFEST` (never `CitationKind.SESSION`); the
    manifest's own `implementation.changed_files` is recorded evidence, so
    the claim is `recorded`/`fresh`, never guessed or reconstructed.
    """
    run_id = str(manifest["run_id"])
    manifest_path = evidence_dir / "runs" / f"{run_id}.json"
    citation = SystemCitation(
        kind=CitationKind.MANIFEST,
        path=str(manifest_path),
        sha256=_sha256_file(manifest_path),
    )
    changed_files = list(manifest.get("implementation", {}).get("changed_files") or [])
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
        "source": "manifest",
        "outcome": manifest.get("outcome"),
        "started_at": manifest.get("started_at"),
        "ended_at": manifest.get("ended_at"),
        "start_commit": manifest.get("start_commit"),
        "result_commit": manifest.get("result_commit"),
        "implementation": implementation,
        "citation": to_dict(citation),
    }


def _session_run(run: sessions.SessionRun) -> dict:
    """One `runs[]` entry from a session record with no matching manifest.

    Cites `CitationKind.SESSION`, never `CitationKind.MANIFEST`; a session
    record never captures changed files or a commit range (design), so
    `implementation` is `missing`/`n/a` rather than derived from anything
    (e.g. `git.head`) the session record happens to also carry.
    """
    citation = SystemCitation(
        kind=CitationKind.SESSION,
        path=str(run.path),
        sha256=_sha256_file(run.path),
    )
    claim = _missing_claim(
        f"run {run.run_id}: implementation not recorded",
        "session records do not capture changed files or a commit range",
    )
    implementation = to_dict(claim)
    implementation["changed_files"] = None
    return {
        "run_id": run.run_id,
        "source": "session",
        "outcome": run.outcome,
        "started_at": run.started_at,
        "ended_at": run.ended_at,
        "start_commit": None,
        "result_commit": None,
        "implementation": implementation,
        "citation": to_dict(citation),
    }


def _requirements_for_task(task: ledger.Task) -> tuple[list[str], int]:
    """The task's requirements, from its own recorded `satisfies` list --
    the same field `factory.trace.model.extract_edges` reads to build a
    `satisfies` trace edge for `trace_id_for_task(task.id)`; read here
    through the ledger's own parse of that field rather than a second
    loader. Each bare id is mapped through `sr_ref_from_trace_id` and
    dropped -- never guessed -- when unmappable; the drop count feeds
    `degraded_reasons`.
    """
    requirements: list[str] = []
    dropped = 0
    for raw in task.satisfies:
        mapped = sr_ref_from_trace_id(raw)
        if mapped is None:
            dropped += 1
            continue
        requirements.append(mapped)
    return requirements, dropped


def _story_degraded_reasons(
    run_count: int, session_only_count: int, dropped_requirement_count: int
) -> list[str]:
    """Distinct, counted reasons `query_story`'s `degraded` is true --
    mirroring `query_timeline`'s discipline: each string corresponds to
    something actually counted, never an invented or generic explanation;
    no reason fires with a count of zero.
    """
    reasons: list[str] = []
    if run_count == 0:
        reasons.append("task has no recorded runs (no evidence manifest or session record found)")
    if session_only_count:
        reasons.append(
            f"{session_only_count} run(s) have no recorded implementation detail "
            "(session record only, no evidence manifest)"
        )
    if dropped_requirement_count:
        reasons.append(
            f"{dropped_requirement_count} satisfies reference(s) did not map to a known requirement"
        )
    return reasons


def query_story(repo_root: Path, scope: SystemScopeRef) -> dict:
    """Assemble the implementation story for a `task:` scope.

    Returns `{"scope": {...}, "task": {...}, "runs": [...],
    "requirements": [...], "degraded": bool, "degraded_reasons": [...]}`.
    Raises `ScopeNotFoundError` for a task id that does not resolve through
    `factory.orchestrator.ledger.get_task`, and `ScopeKindError` for any
    scope kind other than `task`.
    """
    task_id = _task_id_from_scope(scope)
    tasks = ledger.load_tasks(_tasks_dir(repo_root))
    task = ledger.get_task(tasks, task_id)
    if task is None:
        raise ScopeNotFoundError(f"task not found: {task_id!r}")

    evidence_dir = _evidence_dir(repo_root)
    manifest_runs = evidence_manifests.list_run_manifests(evidence_dir, task_id=task.id)

    runs: list[dict] = []
    seen_run_ids: set[str] = set()
    for manifest in manifest_runs:
        run = _manifest_run(evidence_dir, manifest)
        seen_run_ids.add(run["run_id"])
        runs.append(run)

    session_only_count = 0
    for session_run in sessions.load_session_runs(repo_root, task.id):
        if session_run.run_id in seen_run_ids:
            continue
        runs.append(_session_run(session_run))
        session_only_count += 1

    # Ordered by recorded started_at, then citation path -- never by array
    # position across documents (module docstring above).
    runs.sort(key=lambda r: (r["started_at"] or "", r["citation"]["path"]))

    requirements, dropped_requirement_count = _requirements_for_task(task)

    degraded_reasons = _story_degraded_reasons(len(runs), session_only_count, dropped_requirement_count)

    return {
        "scope": {"kind": scope.kind, "ref": scope.ref},
        "task": {
            "id": task.id,
            "title": task.title,
            "status": task.status,
            "ref": trace_id_for_task(task.id),
        },
        "runs": runs,
        "requirements": requirements,
        "degraded": bool(degraded_reasons),
        "degraded_reasons": degraded_reasons,
    }
