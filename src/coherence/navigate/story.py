"""Task implementation story: `query_story` tells one task's implementation
story from recorded evidence (increment B "V-cycle", forward half -- open a
task, see how it was implemented).

Composes existing loaders; never re-parses an artifact a loader already
owns:

- `substrate.ledger.tasks` for the task record itself -- status,
  title, and the `satisfies` list its own frontmatter carries (the same
  field `coherence.trace.model.extract_edges` reads to build a task's
  `satisfies` trace edge, so reading it through the ledger here is not a
  second parser; it is the one place task metadata is already parsed);
- `factory.evidence.manifests.list_run_manifests` for durable per-run
  evidence -- a manifest run's implementation detail (changed files) is
  `recorded`, never reconstructed from git;
- `coherence.navigate.sessions.load_session_runs` for the thinner session
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

from pathlib import Path

from substrate.evidence import read as evidence_manifests
from coherence.navigate import sessions
from coherence.navigate._claims import (
    evidence_dir as _evidence_dir,
    fresh as _fresh,
    manifest_path as _manifest_path,
    missing_claim as _missing_claim,
    sha256_file as _sha256_file,
    tasks_dir as _tasks_dir,
)
from coherence.navigate.models import (
    ClaimClass,
    CitationKind,
    SystemCitation,
    SystemClaim,
    SystemScopeRef,
    to_dict,
)
from coherence.navigate.queries import ScopeKindError, ScopeNotFoundError
from coherence.navigate.refs import sr_ref_from_trace_id
from substrate.ledger import tasks as ledger
from substrate.ledger.plans import parse_plan_tasks


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

    `manifest` always came back from `evidence_manifests.list_run_manifests`,
    which already validates it against `evidence_manifest.schema.json`
    before returning it -- every field accessed below is in that schema's
    `required` list, so plain indexing (not `.get`) is used throughout,
    consistently.
    """
    run_id = manifest["run_id"]
    path = _manifest_path(evidence_dir, run_id)
    citation = SystemCitation(
        kind=CitationKind.MANIFEST,
        path=str(path),
        sha256=_sha256_file(path),
    )
    changed_files = list(manifest["implementation"]["changed_files"])
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
        "outcome": manifest["outcome"],
        "started_at": manifest["started_at"],
        "ended_at": manifest["ended_at"],
        "start_commit": manifest["start_commit"],
        "result_commit": manifest["result_commit"],
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
    the same field `coherence.trace.model.extract_edges` reads to build a
    `satisfies` trace edge for this task's node (`T-059`, unprefixed --
    verified against `tests/unit/trace/test_model_edges.py`); read here
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


def _plan_section(repo_root: Path, task: ledger.Task) -> dict | None:
    """The `### Task N:` section of the task's source plan -- the steps the
    implementer actually worked from, which the task file itself only points
    at.

    Resolved by title first and by `source_task` number second: until T-020
    landed, a plan's fenced fixtures produced duplicate section numbers, and a
    plan whose sections were reordered after export still names its task the
    same. `parse_plan_tasks` stays the one owner of the `### Task N:` grammar.

    Returns None -- never raises -- for a task with no `source_plan`, a plan
    file that cannot be read, or a plan with no matching section. The section
    is optional review context, never a gate.
    """
    if not task.source_plan:
        return None
    try:
        text = (repo_root / task.source_plan).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    sections = parse_plan_tasks(text)
    match = next((s for s in sections if s.title.strip() == task.title.strip()), None)
    if match is None and task.source_task is not None:
        match = next((s for s in sections if s.number == task.source_task), None)
    if match is None:
        return None
    return {
        "plan_path": task.source_plan,
        "heading": f"Task {match.number}: {match.title}",
        "body": match.body,
    }


def query_story(repo_root: Path, scope: SystemScopeRef) -> dict:
    """Assemble the implementation story for a `task:` scope.

    Returns `{"scope": {...}, "task": {...}, "runs": [...],
    "requirements": [...], "degraded": bool, "degraded_reasons": [...]}`.
    Raises `ScopeNotFoundError` for a task id that does not resolve through
    `substrate.ledger.tasks.get_task`, and `ScopeKindError` for any
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
            "dod": task.dod,
        },
        "runs": runs,
        "requirements": requirements,
        "degraded": bool(degraded_reasons),
        "degraded_reasons": degraded_reasons,
        "plan_section": _plan_section(repo_root, task),
    }

