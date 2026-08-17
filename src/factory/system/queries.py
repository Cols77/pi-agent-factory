"""System navigator query layer: brief, matrix, timeline, and scope listing.

Composes existing loaders -- never re-parses an artifact a loader already
owns:

- `factory.system.bundles` for declared feature-scope bundles (syntactic
  member parsing; Task 1's job);
- `factory.requirements.register` for SR content and binding, via the
  existing `SR-*.md` glob register (never a hardcoded path);
- `factory.orchestrator.ledger` for task implementation status (the task
  ledger, never plan checkbox state -- design SS3.4) and, for the timeline,
  the `satisfies` link from task to SR;
- `factory.trace.validation_status` for validation report outcomes and
  staleness;
- `factory.evidence.manifests` for the durable per-run evidence manifest,
  whose `reviews` array is `query_timeline`'s source of signed review
  decisions (see the comment above `_iter_decision_records` for exactly
  which artifacts back timeline events, why others were deliberately
  excluded rather than guessed at, and why this replaced an earlier,
  incorrect direct-glob approach that assumed a directory layout nothing in
  this repo actually writes).

A bundle member naming a spec/plan/task/SR that does not exist is resolved
here (real existence, not the syntactic-only check Task 1 could do) and
reported `missing`; it degrades the bundle without being dropped from the
output (design SS3.3, SS8).

Nothing here infers provenance or fuzzy-matches a scope ref: `bundle:` and
`sr:` refs must match an existing declaration/id exactly.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath

from factory.evidence import manifests as evidence_manifests
from factory.goals import registry as goal_registry
from factory.memory import durable as durable_memory
from factory.orchestrator import ledger
from factory.requirements import register
from factory.requirements.register import Requirement
from factory.simulation import evidence as sim_evidence
from factory.simulation import registry as sim_registry
from factory.system import adr as adr_module
from factory.system import bundles
from factory.system._claims import (
    evidence_dir as _evidence_dir,
    fresh as _fresh,
    manifest_path as _manifest_path,
    missing_claim as _missing,
    sha256_file as _sha256_file,
    tasks_dir as _tasks_dir,
)
from factory.system.bundles import BundleIdMismatchError
from factory.system.coverage import ArtifactLookup, build_artifact_lookup
from factory.system.models import (
    BundleDeclaration,
    ClaimClass,
    CitationKind,
    DecisionTimelineEvent,
    Freshness,
    FreshnessState,
    MatrixStatus,
    SystemCitation,
    SystemClaim,
    SystemScopeRef,
    TimelineAction,
    TimelineActor,
    ValidationMatrixRow,
    to_dict,
)
from factory.system.vcycle import VCycleSlice
from factory.trace import model as trace_model
from factory.trace import validation_status
from factory.trace.validation_status import SrStatus

_SCOPE_KINDS = ("bundle", "sr", "task", "file", "adr", "diag", "feat", "metric", "goal")

# Member kinds a declared bundle may name (mirrors factory.system.bundles).
_SPEC_PLAN_KINDS = ("spec", "plan")
_TRACE_MEMBER_KINDS = ("feat", "metric", "goal")


class ScopeError(Exception):
    """Base class for scope-resolution failures the CLI reports structurally."""


class ScopeKindError(ScopeError):
    """The scope ref is malformed or names a kind that is not a top-level scope."""


class ScopeNotFoundError(ScopeError):
    """The scope ref is well-formed but does not resolve to a declared scope."""


def parse_scope_ref(raw: str) -> SystemScopeRef:
    """Parse a `--scope` CLI argument into a `SystemScopeRef`.

    `bundle:<id>`, `sr:<id>`, `task:<id>`, `file:<path>`, `adr:<id>`,
    `diag:<id>`, `feat:<id>`, `metric:<id>`, and `goal:<id>` are
    legal top-level scopes. Anything else -- an unknown kind, a missing
    identifier, or a malformed string -- is rejected outright; there is no
    fuzzy fallback.
    """
    kind, sep, identifier = raw.partition(":")
    if not sep or kind not in _SCOPE_KINDS or not identifier:
        raise ScopeKindError(
            f"invalid scope ref: {raw!r} (expected bundle:<id>, sr:<id>, "
                f"task:<id>, file:<path>, adr:<id>, diag:<id>, feat:<id>, "
                f"metric:<id> or goal:<id>)"
        )
    return SystemScopeRef(kind=kind, ref=raw)


def _scope_identifier(scope: SystemScopeRef) -> str:
    if scope.kind not in _SCOPE_KINDS:
        raise ScopeKindError(f"unsupported scope kind: {scope.kind!r}")
    prefix = f"{scope.kind}:"
    if not scope.ref.startswith(prefix) or scope.ref == prefix:
        raise ScopeKindError(f"scope ref {scope.ref!r} does not match kind {scope.kind!r}")
    return scope.ref[len(prefix):]


def _bundles_dir(repo_root: Path) -> Path:
    return repo_root / "bundles"


def _requirements_dir(repo_root: Path) -> Path:
    return repo_root / "requirements"


def _load_bundle_or_raise(repo_root: Path, bundle_id: str) -> BundleDeclaration:
    try:
        return bundles.load_bundle(_bundles_dir(repo_root), bundle_id)
    except (FileNotFoundError, BundleIdMismatchError) as exc:
        # Both mean the exact scope ref does not resolve -- whether because
        # no file exists, or because the file that filename-matches declares
        # a different id (design SS5.1: exact resolution only). The
        # id-mismatch case is still visible elsewhere: list_bundle_errors
        # surfaces it instead of letting it disappear (finding 4/5).
        raise ScopeNotFoundError(str(exc)) from exc


def list_bundle_errors(repo_root: Path) -> list[dict]:
    """Bundle files that exist but failed to load, and why (design SS8).

    The companion to `list_scopes`: a malformed or misnamed bundle never
    becomes a scope, but it must not vanish without a trace either. The CLI
    `scope` command surfaces this alongside the resolvable scopes.
    """
    return [
        {"path": str(err.path), "bundle_id": err.bundle_id, "error": err.error}
        for err in bundles.list_bundle_errors(_bundles_dir(repo_root))
    ]


def _load_requirement_or_raise(repo_root: Path, sr_id: str) -> Requirement:
    reqs = register.load_register(_requirements_dir(repo_root))
    req = register.get_requirement(reqs, sr_id)
    if req is None:
        raise ScopeNotFoundError(f"sr not found: {sr_id!r}")
    return req


def _load_diagram_or_raise(repo_root: Path, diagram_id: str) -> trace_model.Node:
    for node in trace_model.load_nodes(repo_root):
        if node.kind == "diag" and node.id == diagram_id:
            return node
    raise ScopeNotFoundError(f"diagram not found: {diagram_id!r}")


def query_diagram(repo_root: Path, diagram_id: str) -> dict:
    """Return one diagram stub and its declared diagram-file availability.

    Diagram stubs are loaded through ``trace_model.load_nodes`` so the
    navigator and trace graph share the sole Markdown-frontmatter parser.
    A missing diagram file only degrades this payload: the stub remains
    addressable and its recorded title is returned.
    """
    diagram = _load_diagram_or_raise(repo_root, diagram_id)
    if diagram.diagram_file is None:
        return {
            "id": diagram.id,
            "title": diagram.title,
            "diagram_path": None,
            "errors": [f"diagram stub has no diagram_file: {diagram.path}"],
        }

    declared_path = Path(diagram.diagram_file)
    windows_path = PureWindowsPath(diagram.diagram_file)
    if (
        declared_path.is_absolute()
        or windows_path.is_absolute()
        or bool(windows_path.root)
        or PurePosixPath(diagram.diagram_file).is_absolute()
    ):
        return {
            "id": diagram.id,
            "title": diagram.title,
            "diagram_path": None,
            "errors": [f"absolute diagram file is not allowed: {diagram.diagram_file}"],
        }

    if windows_path.drive:
        return {
            "id": diagram.id,
            "title": diagram.title,
            "diagram_path": None,
            "errors": [f"invalid diagram file path: {diagram.diagram_file}"],
        }

    try:
        directory = diagram.path.parent.resolve()
        path = (directory / declared_path).resolve()
    except RuntimeError:
        return {
            "id": diagram.id,
            "title": diagram.title,
            "diagram_path": None,
            "errors": [f"invalid diagram file path: {diagram.diagram_file}"],
        }

    try:
        path.relative_to(directory)
    except ValueError:
        return {
            "id": diagram.id,
            "title": diagram.title,
            "diagram_path": None,
            "errors": [f"invalid diagram file path: {diagram.diagram_file}"],
        }

    if path.is_file():
        return {
            "id": diagram.id,
            "title": diagram.title,
            "diagram_path": str(path),
            "errors": [],
        }
    return {
        "id": diagram.id,
        "title": diagram.title,
        "diagram_path": None,
        "errors": [f"missing diagram file: {path}"],
    }


def query_goal(repo_root: Path, goal_id: str) -> dict:
    """Return one goal: contract, current state, latest evidence, history.

    Goals are loaded through the goals registry (never a re-glob), so the
    goal file's sole parser is `factory.goals.schema.parse_goal`. A goal id
    that no file declares is a resolution failure, not a guess.
    """
    goals = goal_registry.load_goals(repo_root)
    if goal_id not in goals:
        raise ScopeNotFoundError(f"no goal with id {goal_id!r}")
    goal = goals[goal_id]
    return {
        "id": goal.id,
        "title": goal.title,
        "state": goal.state,
        "version": goal.version,
        "feature": goal.feature,
        "requirements": goal.requirements,
        "metric": goal.metric,
        "target": goal.target,
        "evidence": goal.evidence,
        "history": goal.history,
        "scope_errors": goal.scope_errors,
    }


def _goal_query_kinds() -> tuple[str, ...]:
    # Inc 2's goal query scopes; `_SCOPE_KINDS` remains Inc 1-owned.
    return ("feat", "sr", "goal")


def query_goals(repo_root: Path, scope_ref: str) -> dict:
    """Return the goals bound to a `feat:<id>`, `sr:<id>` or `goal:<id>` scope.

    Binding is read from declared data, never inferred: a goal is bound to a
    feature or requirement when its frontmatter names it (`feature`/
    `requirements`) or when the trace graph carries a declared `demonstrates`
    edge from the goal to that id. Unknown kinds are rejected; a goal scope
    that no file declares resolves to nothing rather than a fuzzy match.
    """
    kind, sep, identifier = scope_ref.partition(":")
    if not sep or kind not in _goal_query_kinds() or not identifier:
        raise ScopeKindError(
            f"invalid goal scope ref: {scope_ref!r} (expected feat:<id>, sr:<id> or goal:<id>)"
        )

    goals = goal_registry.load_goals(repo_root)
    nodes = trace_model.load_nodes(repo_root)
    edges = trace_model.extract_edges(repo_root, nodes)
    demonstrated: set[str] = {e.src for e in edges if e.kind == "demonstrates" and e.dst == identifier}

    if kind == "goal":
        selected = [g for g in goals.values() if g.id == identifier]
    elif kind == "feat":
        selected = [g for g in goals.values() if identifier in g.feature or g.id in demonstrated]
    else:  # sr
        selected = [g for g in goals.values() if identifier in g.requirements or g.id in demonstrated]

    return {
        "scope": scope_ref,
        "goals": [
            {
                "id": g.id,
                "title": g.title,
                "state": g.state,
                "feature": g.feature,
                "requirements": g.requirements,
                "metric": g.metric,
                "target": g.target,
                "evidence": g.evidence,
                "history": g.history,
            }
            for g in selected
        ],
    }


def _run_metric_values(run: sim_registry.Run) -> dict[str, float]:
    """The run's recorded metrics from its bundle metrics.json, tolerant of a
    missing or unreadable file (empty map -- never a crash)."""
    try:
        raw = json.loads((run.path.parent / "metrics.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return sim_evidence.metric_values(run, raw) if isinstance(raw, dict) else {}


def _run_recording(repo_root: Path, run: sim_registry.Run) -> str | None:
    """Repo-relative path to the run's manifest (the recording), or None when
    the manifest file is missing -- honest incompleteness, never a guessed
    path outside the repo."""
    try:
        if not run.path.exists():
            return None
        return run.path.resolve().relative_to(repo_root.resolve()).as_posix()
    except (OSError, ValueError):
        return None


def _sim_run_payload(repo_root: Path, run: sim_registry.Run) -> dict:
    return {
        "run": run.run_id,
        "experiment": run.experiment,
        "feature": run.feature,
        "requirements": run.requirements,
        "goals": run.goals,
        "commit": run.commit,
        "result": run.result,
        "scope_errors": run.scope_errors,
        "metrics": _run_metric_values(run),
        "recording": _run_recording(repo_root, run),
        "recorded_ts": run.recorded_ts,
    }


def query_simulation_run(repo_root: Path, run_id: str) -> dict:
    """Return one simulation run by its run id (spec §20 bundle).

    Runs are loaded through the simulation registry — the same tolerant loader
    the rest of Inc 3 uses — so a run that no bundle declares is a resolution
    failure, never a fuzzy guess.
    """
    for run in sim_registry.load_runs(_evidence_dir(repo_root)):
        if run.run_id == run_id:
            return _sim_run_payload(repo_root, run)
    raise ScopeNotFoundError(f"no simulation run with id {run_id!r}")


def query_latest_simulation(repo_root: Path, feature: str) -> dict | None:
    """Latest simulation run for a feature (deterministic by run id).

    AC-01's "latest simulation evidence" slot: derived from the registry, so
    the answer matches what `query_simulation_run` reports for the same run.
    None is a legitimate state (no run yet), not an error.
    """
    latest = sim_registry.latest_run(_evidence_dir(repo_root), feature)
    return _sim_run_payload(repo_root, latest) if latest is not None else None


def query_latest_failure(repo_root: Path, feature: str) -> dict | None:
    """Most recent non-passed simulation run for a feature, or None."""
    failure = sim_evidence.latest_failure(_evidence_dir(repo_root), feature)
    return _sim_run_payload(repo_root, failure) if failure is not None else None


def query_metric_history(repo_root: Path, metric_id: str) -> list[dict]:
    """Ascending metric history across runs (spec §9.3 style), deterministic."""
    return sim_evidence.metric_history(_evidence_dir(repo_root), metric_id)


def query_goal_evidence(repo_root: Path, goal_id: str) -> dict:
    """Runs whose manifest lists ``goal_id`` (ascending by run id).

    Wraps ``factory.simulation.evidence.evidence_for_goal`` so the navigator
    and the sim registry share one loader; a goal with no runs resolves to an
    empty ``runs`` list, never a fuzzy guess.
    """
    runs = sim_evidence.evidence_for_goal(_evidence_dir(repo_root), goal_id)
    return {
        "goal": goal_id,
        "runs": [_sim_run_payload(repo_root, run) for run in runs],
    }


def query_memory(repo_root: Path, scope_ref: str) -> dict:
    """One read of durable memory: decisions, failures, hypotheses, goals, conflicts.

    Delegates to ``factory.memory.durable.query_memory`` (Inc 8 Task 2) so
    the projection and this navigator share one implementation -- the
    navigator never re-parses an artifact the durable module already loads.
    The projection composes the existing loaders (`adr:`, failure records,
    goals, evidence manifests) and renders every entry through the same
    citation/freshness plumbing as the other queries: each decision, record,
    hypothesis, goal and conflict carries a provenance citation and a
    freshness state, and no entry re-states the requirement/ADR/evidence
    prose it links.
    """
    return durable_memory.query_memory(repo_root, scope_ref)


@dataclass(frozen=True)
class _MemberResolution:
    """The outcome of resolving one declared bundle member against real loaders.

    `implementation_summary`/`implementation_summary_unreadable` are only
    ever set by `_resolve_task_member` (Task 5): the plain
    `{"runs", "latest_outcome", "changed_file_count", "latest_validation"}`
    dict attached to the *serialized* `member_claim` (never a dataclass
    field of `SystemClaim` itself -- `query_brief` merges it in after
    `to_dict()`, since the schema-validated claim shape stays fixed), and
    whether computing it hit a citation whose file could not be read.
    """

    member_claim: SystemClaim
    extra_claims: list[SystemClaim]
    resolved: bool
    implementation_summary: dict | None = None
    implementation_summary_unreadable: bool = False


def _resolve_spec_or_plan_member(repo_root: Path, member: SystemScopeRef, identifier: str) -> _MemberResolution:
    path = repo_root / identifier
    if not path.is_file():
        claim = _missing(member.ref, "bundle member does not exist in repo")
        return _MemberResolution(member_claim=claim, extra_claims=[], resolved=False)
    # Non-readmission rule (design SS4.5): an exported guide is an output
    # artifact, never evidence. `path.is_file()` above cannot tell an
    # exported guide apart from a real spec/plan file on its own, so this
    # explicitly refuses to cite one -- without it, a synthesized guide could
    # become a "recorded" spec/plan member of a later bundle, and the whole
    # claim-class discipline would leak in one hop. Import is deferred
    # (function-local) because `factory.system.guide` imports several
    # `query_*` functions from this module at its own module level -- a
    # module-level import here would be circular.
    from factory.system import guide as _guide

    if _guide.is_exported_guide(path):
        claim = _missing(
            member.ref, "cannot cite an exported guide as evidence (design SS4.5 non-readmission rule)"
        )
        return _MemberResolution(member_claim=claim, extra_claims=[], resolved=False)
    citation = SystemCitation(
        kind=CitationKind.TRACE,
        path=str(path),
        sha256=_sha256_file(path),
    )
    claim = SystemClaim(
        kind=ClaimClass.RECORDED,
        text=_member_label(repo_root, path, member.ref),
        freshness=_fresh(),
        citations=[citation],
    )
    return _MemberResolution(member_claim=claim, extra_claims=[], resolved=True)


def _resolve_trace_member(
    member: SystemScopeRef, identifier: str, nodes: list[trace_model.Node]
) -> _MemberResolution:
    """Resolve an id-based trace member through the existing trace-node loader."""
    node = next(
        (node for node in nodes if node.kind == member.kind and node.id == identifier),
        None,
    )
    if node is None:
        claim = _missing(member.ref, "bundle member does not exist in repo")
        return _MemberResolution(member_claim=claim, extra_claims=[], resolved=False)
    citation = SystemCitation(
        kind=CitationKind.TRACE,
        path=str(node.path),
        sha256=_sha256_file(node.path),
    )
    claim = SystemClaim(
        kind=ClaimClass.RECORDED,
        text=member.ref,
        freshness=_fresh(),
        citations=[citation],
    )
    return _MemberResolution(member_claim=claim, extra_claims=[], resolved=True)


def _document_titles(repo_root: Path) -> dict[Path, str]:
    """Recorded titles for every spec/plan/task/SR document, keyed by real path.

    Reuses `factory.trace.model.load_nodes` -- the loader that already derives
    a title from frontmatter or the first heading -- rather than re-parsing
    documents here. A brief whose claims are bare refs tells a reader nothing
    they could not get from `ls`, and the title is recorded content of the
    document the claim already cites, so surfacing it infers nothing.
    """
    titles: dict[Path, str] = {}
    try:
        for node in trace_model.load_nodes(repo_root):
            try:
                titles[node.path.resolve()] = node.title
            except OSError:
                continue
    except (OSError, ValueError):
        # A repo whose documents cannot be scanned still gets refs; titles are
        # an enrichment, never a precondition.
        return {}
    return titles


def _member_label(repo_root: Path, path: Path, ref: str) -> str:
    """`<title> — <ref>`, or the bare ref when no title is recorded.

    Never fabricates a title from the filename: a document with no heading and
    no frontmatter title has nothing recorded to show, and an invented one
    would be exactly the unsupported claim this navigator exists to avoid.

    `trace.model._file_node` falls back to the file's own name when it finds no
    heading, so a title equal to the filename is that fallback firing, not a
    recorded title -- it is rejected here rather than echoed back as though the
    document had said it.
    """
    try:
        title = _document_titles(repo_root).get(path.resolve())
    except OSError:
        title = None
    if not title or title == ref or title == path.name:
        return ref
    return f"{title} — {ref}"


def _validation_verdict(validation_entries: list) -> str | None:
    """A single pass/stale/failed verdict for one run's recorded validation
    entries (`manifest["validation"]`, schema-guaranteed a list of objects
    -- already loaded and schema-validated by `evidence_manifests.
    list_run_manifests`, so reading it here is not a new parser).

    `None` when the run recorded no validation entries at all, or none of
    them name any requirement -- there is nothing to verdict, so nothing is
    asserted (never guessed as "passed").

    Controller ruling (2026-08-09): a stale pass is never reported as a
    plain pass -- this whole subsystem exists so evidence quality is never
    flattened. Any requirement recorded `passed: false` makes the whole
    run "failed"; otherwise any requirement recorded `stale: true` makes it
    "stale"; only when every requirement passed and none is stale is it
    "passed". Never reads the `report` blob ref -- the verdict comes from
    the inline `requirements` array alone.
    """
    requirements = [
        req
        for entry in validation_entries
        if isinstance(entry, dict)
        for req in entry.get("requirements", [])
        if isinstance(req, dict)
    ]
    if not requirements:
        return None
    if any(not req.get("passed") for req in requirements):
        return "failed"
    if any(req.get("stale") for req in requirements):
        return "stale"
    return "passed"


def _task_implementation_summary(repo_root: Path, task_id: str) -> tuple[dict, SystemClaim | None]:
    """`implementation_summary` for one bundle `task:` member, and the
    `derived` claim documenting it (design SS4.3: run count, latest
    outcome, changed-file count, and latest validation result -- "what has
    been built and does it pass").

    Consumes `query_story` (Task 3) for the ordered run history -- never a
    second walk of the evidence. Import is deferred (function-local)
    because `factory.system.story` imports `ScopeKindError`/
    `ScopeNotFoundError` from this module at its own module level -- a
    module-level import here would be circular.

    `changed_file_count` mirrors `latest_outcome`: both describe the
    *latest* run only (`query_story`'s own oldest-first ordering,
    `runs[-1]`), never a total across every run. It is `None`, never `0`,
    whenever nothing was recorded -- no runs at all, or a session-only
    latest run (`story.py`'s own `changed_files: None` design for a
    session record) -- so "no runs" never reads as "changed nothing"
    (global constraint).

    `latest_validation` verdicts the latest run's own recorded `evidence/
    runs/<run_id>.json` `validation` array (re-read through
    `evidence_manifests.list_run_manifests`, the same loader `query_story`
    itself already reads through) via `_validation_verdict`; `None` when
    the latest run is session-sourced or recorded no validation entries.

    The returned claim reuses the latest run's own citation (already built
    by `story.py`, including its sha256 -- never re-hashed here) --
    `kind=derived` (an aggregate over recorded runs, not a single recorded
    fact), and `degraded` when that citation's `sha256` came back `None`
    (the cited manifest/session file could not be read).

    When the task has no recorded runs at all, no claim is returned (`None`)
    -- a legitimate, common state (a `todo` task simply has no history yet),
    not degradation, so it must not appear as an extra `missing` claim in
    the bundle's claims list: `guide._bundle_coverage_section` reads every
    task member's own claims and requires them all `fresh` before
    synthesizing prose, and a task with no runs otherwise has two entirely
    `fresh`, `recorded` claims (the ref and the ledger status) -- inserting
    a third, `n/a` claim here would silently flip that section from
    synthesized prose to a plain rollup for the ordinary, undegraded case of
    "not started yet". `implementation_summary` on the member claim already
    says `runs: 0` either way.
    """
    from factory.system.story import query_story  # deferred: story.py imports this module

    story = query_story(repo_root, SystemScopeRef(kind="task", ref=f"task:{task_id}"))
    runs = story["runs"]

    if not runs:
        summary = {
            "runs": 0,
            "latest_outcome": None,
            "changed_file_count": None,
            "latest_validation": None,
        }
        return summary, None

    latest = runs[-1]
    changed_files = latest["implementation"]["changed_files"]
    changed_file_count = len(changed_files) if changed_files is not None else None

    latest_validation = None
    if latest["source"] == "manifest":
        manifests = evidence_manifests.list_run_manifests(_evidence_dir(repo_root), task_id=task_id)
        manifest = next((m for m in manifests if m["run_id"] == latest["run_id"]), None)
        if manifest is not None:
            latest_validation = _validation_verdict(manifest.get("validation") or [])

    summary = {
        "runs": len(runs),
        "latest_outcome": latest["outcome"],
        "changed_file_count": changed_file_count,
        "latest_validation": latest_validation,
    }

    latest_citation = latest["citation"]
    citation = SystemCitation(
        kind=CitationKind(latest_citation["kind"]),
        path=latest_citation["path"],
        sha256=latest_citation["sha256"],
        anchor=latest_citation.get("anchor"),
    )
    unreadable = citation.sha256 is None
    freshness = (
        Freshness(
            state=FreshnessState.DEGRADED,
            reason="latest run's cited evidence file could not be read",
            dependencies=[],
        )
        if unreadable
        else _fresh()
    )
    claim = SystemClaim(
        kind=ClaimClass.DERIVED,
        text=f"task {task_id} implementation: {len(runs)} run(s), latest outcome {latest['outcome']}",
        freshness=freshness,
        citations=[citation],
    )
    return summary, claim


def _resolve_task_member(
    repo_root: Path, member: SystemScopeRef, identifier: str, tasks: list[ledger.Task]
) -> _MemberResolution:
    task = ledger.get_task(tasks, identifier)
    if task is None:
        claim = _missing(member.ref, "bundle member does not exist in repo")
        return _MemberResolution(member_claim=claim, extra_claims=[], resolved=False)
    citation = SystemCitation(
        kind=CitationKind.TASK,
        path=str(task.path),
        sha256=_sha256_file(task.path),
    )
    member_claim = SystemClaim(
        kind=ClaimClass.RECORDED,
        text=member.ref,
        freshness=_fresh(),
        citations=[citation],
    )
    # Implementation status comes only from the task ledger -- never from
    # plan checkbox state (design SS3.4).
    impl_claim = SystemClaim(
        kind=ClaimClass.RECORDED,
        text=f"task {identifier} status: {task.status}",
        freshness=_fresh(),
        citations=[citation],
    )
    summary, summary_claim = _task_implementation_summary(repo_root, identifier)
    extra_claims = [impl_claim] if summary_claim is None else [impl_claim, summary_claim]
    unreadable = summary_claim is not None and summary_claim.freshness.state is FreshnessState.DEGRADED
    return _MemberResolution(
        member_claim=member_claim,
        extra_claims=extra_claims,
        resolved=True,
        implementation_summary=summary,
        implementation_summary_unreadable=unreadable,
    )


def _validation_report_is_corrupt(repo_root: Path) -> bool:
    """True when the validation report file exists but either fails to parse
    as JSON or does not parse to a JSON object -- never merely because it
    parsed to zero usable entries.

    `validation_status.load_validation` swallows read/parse failures into
    `{}`, which made a genuinely corrupt file indistinguishable from a file
    that parsed fine and legitimately says "nothing has been validated yet"
    (an empty `requirements` array is exactly what
    `factory.validation.pipeline.validate_task_requirements` writes before
    anything has run -- not corruption). The fix is to attempt the parse
    ourselves, mirroring `load_validation`'s own try/except, rather than
    inferring corruption from its collapsed return value: a report that
    parses to an object is never corrupt, no matter how few (or how invalid)
    its entries are. Design SS3.1: "if a claim cannot be tied to recorded
    artifacts, it is shown as missing or degraded, never guessed" -- this
    cuts both ways, so we must not guess corruption either.

    A file that parses to something other than a JSON object (e.g. a bare
    array `[1,2,3]`) is also corrupt: `load_validation` calls `raw.get(...)`
    on whatever it parses, which raises `AttributeError` for anything
    non-dict. Left undetected, that crashes `brief`/`matrix`/`guide` for
    every scope instead of degrading the one SR whose report is unreadable
    (the Global Constraint: missing/corrupt evidence degrades one scope, not
    the whole navigator).
    """
    path = validation_status.report_path(repo_root)
    if not path.exists():
        return False
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return True
    return not isinstance(raw, dict)


def _sr_validation_claim(
    req: Requirement,
    status: SrStatus | None,
    report_citation: SystemCitation | None,
    report_corrupt: bool,
) -> SystemClaim:
    if req.binding is None:
        return _missing(
            f"{req.id}: proposed requirement has no binding to validate",
            "proposed requirement has no binding",
        )
    if status is None:
        if report_corrupt:
            # The report file exists but yielded nothing readable -- this is
            # not the recorded fact "never validated"; it is a claim that
            # cannot be tied to a readable artifact, so it degrades rather
            # than being guessed as an absence (design SS3.1).
            citations = [report_citation] if report_citation is not None else []
            return SystemClaim(
                kind=ClaimClass.DERIVED,
                text=f"{req.id}: validation report is unreadable (corrupt or unparseable)",
                freshness=Freshness(
                    state=FreshnessState.DEGRADED,
                    reason="validation report exists but could not be read",
                    dependencies=[],
                ),
                citations=citations,
            )
        return _missing(f"{req.id}: never validated", "no validation report entry recorded")
    freshness_state = FreshnessState.STALE if status.stale else FreshnessState.FRESH
    reason = (
        "requirement content changed since validation was recorded"
        if status.stale
        else "matches the recorded validation report entry"
    )
    suffix = f" ({status.error})" if status.error else ""
    citations = [report_citation] if report_citation is not None else []
    return SystemClaim(
        kind=ClaimClass.RECORDED,
        text=f"{req.id}: {status.state}{suffix}",
        freshness=Freshness(state=freshness_state, reason=reason, dependencies=[]),
        citations=citations,
    )


def _resolve_sr_member(
    repo_root: Path,
    member: SystemScopeRef,
    identifier: str,
    reqs: list[Requirement],
    statuses: dict[str, SrStatus],
    report_citation: SystemCitation | None,
    report_corrupt: bool,
) -> _MemberResolution:
    req = register.get_requirement(reqs, identifier)
    if req is None:
        claim = _missing(member.ref, "bundle member does not exist in repo")
        return _MemberResolution(member_claim=claim, extra_claims=[], resolved=False)
    citation = SystemCitation(
        kind=CitationKind.REQUIREMENT,
        path=str(req.path),
        sha256=_sha256_file(req.path),
    )
    member_claim = SystemClaim(
        kind=ClaimClass.RECORDED,
        text=member.ref,
        freshness=_fresh(),
        citations=[citation],
    )
    validation_claim = _sr_validation_claim(req, statuses.get(req.id), report_citation, report_corrupt)
    return _MemberResolution(member_claim=member_claim, extra_claims=[validation_claim], resolved=True)


def _validation_report_citation(repo_root: Path) -> SystemCitation | None:
    path = validation_status.report_path(repo_root)
    sha256 = _sha256_file(path)
    if sha256 is None:
        return None
    return SystemCitation(kind=CitationKind.VALIDATION, path=str(path), sha256=sha256)


def _load_validation_statuses(repo_root: Path, report_corrupt: bool) -> dict[str, SrStatus]:
    """`validation_status.load_validation`, skipped when the report is
    corrupt (`report_corrupt`, always from `_validation_report_is_corrupt`,
    computed first by every caller).

    Calling `load_validation` on a report that parses to something other
    than a JSON object (e.g. a bare `[1,2,3]`) crashes deep inside
    `factory.trace` (`raw.get("requirements", [])` on a non-dict raises
    `AttributeError`), which would take down `brief`/`matrix`/`guide` for
    every scope in the repo. Routing the corrupt case to `{}` here keeps
    every caller on the same already-correct degraded path
    `_sr_validation_claim`/`_sr_matrix_row` already use for an unreadable
    report, instead of ever reaching `factory.trace` with a shape it cannot
    handle.
    """
    if report_corrupt:
        return {}
    return validation_status.load_validation(repo_root)


def _sr_brief_claims(repo_root: Path, req: Requirement) -> list[SystemClaim]:
    req_citation = SystemCitation(
        kind=CitationKind.REQUIREMENT,
        path=str(req.path),
        sha256=_sha256_file(req.path),
    )
    claims = [
        SystemClaim(
            kind=ClaimClass.RECORDED,
            text=f"{req.id}: {req.statement}",
            freshness=_fresh(),
            citations=[req_citation],
        ),
        SystemClaim(
            kind=ClaimClass.RECORDED,
            text=(
                f"{req.id} upstream: {', '.join(req.upstream)}"
                if req.upstream
                else f"{req.id}: no upstream requirements declared"
            ),
            freshness=_fresh(),
            citations=[req_citation],
        ),
    ]
    if req.binding is not None:
        binding = req.binding
        claims.append(
            SystemClaim(
                kind=ClaimClass.RECORDED,
                text=(
                    f"{req.id} binding: {binding.harness}/{binding.experiment} "
                    f"{binding.metric} {binding.assert_expr} (trials={binding.trials})"
                ),
                freshness=_fresh(),
                citations=[req_citation],
            )
        )
    report_corrupt = _validation_report_is_corrupt(repo_root)
    statuses = _load_validation_statuses(repo_root, report_corrupt)
    report_citation = _validation_report_citation(repo_root)
    claims.append(_sr_validation_claim(req, statuses.get(req.id), report_citation, report_corrupt))
    return claims


def _brief_degraded_reasons(
    malformed_member_count: int, unresolved_member_count: int, unreadable_summary_count: int
) -> list[str]:
    """Distinct, counted reasons a bundle brief's `degraded` is true --
    mirroring `_timeline_degraded_reasons`'s discipline: each string
    corresponds to something actually counted over the bundle's own members,
    never an invented or generic explanation (IMPORTANT 5). Rendered
    verbatim by the browser instead of `system-page.ts` inventing its own
    fixed banner text, which was true only by coincidence of the current
    implementation.

    `unreadable_summary_count` (Task 5) mirrors `_story_degraded_reasons`'s
    own count-gated style: it fires only when a task member's
    `implementation_summary` claim cited a manifest or session record it
    could not read (`_task_implementation_summary`'s `degraded` branch) --
    never for the ordinary "no runs recorded yet" case, which is a
    legitimate state, not a degradation.
    """
    reasons: list[str] = []
    if malformed_member_count:
        reasons.append(f"{malformed_member_count} declared member ref(s) did not parse")
    if unresolved_member_count:
        reasons.append(f"{unresolved_member_count} declared member(s) do not exist in the repo")
    if unreadable_summary_count:
        reasons.append(
            f"{unreadable_summary_count} task member(s) implementation summary cites a "
            "manifest or session record that could not be read"
        )
    return reasons


def _adr_brief(repo_root: Path, scope: SystemScopeRef) -> dict:
    """Assemble an ADR's briefing: title, status, then each recorded section.

    An ADR renders Brief only -- it has no validation matrix, no runs and no
    reverse walk, and rendering five permanently-degraded tabs would teach a
    reader to ignore degraded states where they carry meaning.
    """
    adr_id = _scope_identifier(scope)
    adrs = adr_module.load_adrs(repo_root)
    doc = adrs.get(adr_id)
    if doc is None:
        raise ScopeNotFoundError(f"no ADR declares id {adr_id!r}")

    citation = SystemCitation(
        kind=CitationKind.DECISION,
        path=str(doc.path),
        sha256=_sha256_file(doc.path),
    )

    claims: list[SystemClaim] = []
    if doc.title is not None:
        claims.append(
            SystemClaim(
                kind=ClaimClass.RECORDED,
                text=doc.title,
                freshness=_fresh(),
                citations=[citation],
            )
        )
    if doc.status is not None:
        status_text = f"status: {doc.status}"
        if doc.superseded_by:
            status_text = f"{status_text} (superseded by {doc.superseded_by})"
        claims.append(
            SystemClaim(
                kind=ClaimClass.RECORDED,
                text=status_text,
                freshness=_fresh(),
                citations=[citation],
            )
        )
    for heading, body in doc.sections:
        claims.append(
            SystemClaim(
                kind=ClaimClass.RECORDED,
                text=f"{heading}: {body}",
                freshness=_fresh(),
                citations=[citation],
            )
        )
    for error in doc.schema_errors:
        claims.append(_missing(error, "ADR frontmatter is absent or schema-invalid"))

    return {"scope": to_dict(scope), "claims": [to_dict(c) for c in claims]}


def query_brief(repo_root: Path, scope: SystemScopeRef) -> dict:
    """Assemble the one-page briefing for `scope` (design SS4.1, SS4.2, SS5.2).

    Returns a JSON-able dict: `{"scope": {...}, "claims": [...], ...}`.
    Bundle scopes additionally carry `"degraded": bool` and
    `"degraded_reasons": list[str]` -- true, with each reason named, when any
    declared member (syntactically bad, per Task 1, or simply nonexistent,
    resolved here) failed to resolve.

    `sr:` scopes additionally carry `"member_of": list[str]` -- the ids of
    every bundle that declares the requirement as a member (multi-membership
    is otherwise invisible; Task 8). Other scope kinds omit the key.
    """
    if scope.kind == "adr":
        return _adr_brief(repo_root, scope)

    if scope.kind == "bundle":
        bundle_id = _scope_identifier(scope)
        bundle = _load_bundle_or_raise(repo_root, bundle_id)

        claims: list[SystemClaim] = [
            SystemClaim(
                kind=ClaimClass.RECORDED,
                text=bundle.label,
                freshness=_fresh(),
                citations=[bundle.citation],
            )
        ]

        tasks = ledger.load_tasks(_tasks_dir(repo_root))
        reqs = register.load_register(_requirements_dir(repo_root))
        report_corrupt = _validation_report_is_corrupt(repo_root)
        statuses = _load_validation_statuses(repo_root, report_corrupt)
        report_citation = _validation_report_citation(repo_root)
        trace_nodes: list[trace_model.Node] | None = None

        unresolved_member_count = 0
        unreadable_summary_count = 0
        # Index into `claims` -> the plain implementation_summary dict to
        # merge into that claim's *serialized* form below. Not a SystemClaim
        # field: the schema-validated claim shape stays fixed, so this is
        # attached to the dict after `to_dict()`, mirroring how `story.
        # _manifest_run` extends `to_dict(claim)` with `changed_files`.
        member_implementation_summaries: dict[int, dict] = {}
        for member in bundle.members:
            identifier = member.ref.split(":", 1)[1]
            if member.kind in _SPEC_PLAN_KINDS:
                resolution = _resolve_spec_or_plan_member(repo_root, member, identifier)
            elif member.kind == "task":
                resolution = _resolve_task_member(repo_root, member, identifier, tasks)
            elif member.kind == "sr":
                resolution = _resolve_sr_member(
                    repo_root, member, identifier, reqs, statuses, report_citation, report_corrupt
                )
            elif member.kind in _TRACE_MEMBER_KINDS:
                if trace_nodes is None:
                    trace_nodes = trace_model.load_nodes(repo_root)
                resolution = _resolve_trace_member(member, identifier, trace_nodes)
            else:  # pragma: no cover -- bundles.py restricts member kinds
                raise AssertionError(f"unexpected member kind: {member.kind!r}")
            claims.append(resolution.member_claim)
            if resolution.implementation_summary is not None:
                member_implementation_summaries[len(claims) - 1] = resolution.implementation_summary
            claims.extend(resolution.extra_claims)
            if not resolution.resolved:
                unresolved_member_count += 1
            if resolution.implementation_summary_unreadable:
                unreadable_summary_count += 1

        claims.extend(bundle.unresolved)

        degraded_reasons = _brief_degraded_reasons(
            len(bundle.unresolved), unresolved_member_count, unreadable_summary_count
        )

        claim_dicts = [to_dict(c) for c in claims]
        for index, summary in member_implementation_summaries.items():
            claim_dicts[index]["implementation_summary"] = summary

        return {
            "scope": {"kind": scope.kind, "ref": scope.ref},
            "claims": claim_dicts,
            "degraded": bool(degraded_reasons),
            "degraded_reasons": degraded_reasons,
        }

    if scope.kind == "sr":
        sr_id = _scope_identifier(scope)
        req = _load_requirement_or_raise(repo_root, sr_id)
        claims = _sr_brief_claims(repo_root, req)
        # Member-of affordance (Task 8): every bundle that declares this
        # requirement as a member, so a shared requirement reads as shared on
        # its own page. Multi-membership stays visible, in load order.
        return {
            "scope": {"kind": scope.kind, "ref": scope.ref},
            "claims": [to_dict(c) for c in claims],
            "member_of": bundles.bundles_containing(repo_root, scope.ref),
        }

    raise ScopeKindError(f"unsupported scope kind: {scope.kind!r}")


def _sr_matrix_row(req: Requirement, status: SrStatus | None, report_corrupt: bool) -> ValidationMatrixRow:
    subject = SystemScopeRef(kind="sr", ref=f"sr:{req.id}")
    if req.binding is None:
        # No recorded basis to be current about (there is nothing to
        # validate against), so freshness is n/a, not fresh -- "fresh"
        # against zero evidence would be an unfounded assertion, and the
        # brief's handling of this identical condition already uses n/a.
        return ValidationMatrixRow(
            subject=subject,
            status=MatrixStatus.BLOCKED,
            evidence=[],
            freshness=Freshness(
                state=FreshnessState.NA,
                reason="proposed requirement has no binding to validate",
                dependencies=[],
            ),
            summary="proposed requirement: no binding to validate",
        )
    if status is None:
        if report_corrupt:
            # `never-run` would assert a recorded fact the evidence does not
            # support -- and it would contradict the brief's `derived`/
            # `degraded` claim for the same SR (`_sr_validation_claim`'s
            # matching branch). The outcome is genuinely undetermined, so the
            # status says that (user ruling, 2026-08-08; design SS7.3).
            return ValidationMatrixRow(
                subject=subject,
                status=MatrixStatus.UNKNOWN,
                evidence=[],
                freshness=Freshness(
                    state=FreshnessState.DEGRADED,
                    reason="validation report exists but could not be read",
                    dependencies=[],
                ),
                summary="validation report unreadable",
            )
        return ValidationMatrixRow(
            subject=subject,
            status=MatrixStatus.NEVER_RUN,
            evidence=[],
            freshness=Freshness(
                state=FreshnessState.NA, reason="no validation report entry recorded", dependencies=[]
            ),
            summary="never validated",
        )
    status_map = {
        "passed": MatrixStatus.PASSED,
        "failed": MatrixStatus.FAILED,
        "error": MatrixStatus.ERROR,
        "never_validated": MatrixStatus.NEVER_RUN,
    }
    freshness_state = FreshnessState.STALE if status.stale else FreshnessState.FRESH
    reason = (
        "requirement content changed since validation was recorded"
        if status.stale
        else "matches the recorded validation report entry"
    )
    summary = status.error or f"metric={status.metric} assert={status.assert_expr} value={status.value}"
    return ValidationMatrixRow(
        subject=subject,
        status=status_map[status.state],
        evidence=list(status.artifacts),
        freshness=Freshness(state=freshness_state, reason=reason, dependencies=[]),
        summary=summary,
    )


def _sr_missing_matrix_row(ref: str) -> ValidationMatrixRow:
    # `never-run` would assert a validation outcome about a requirement that
    # does not exist to be validated -- there is nothing recorded to be
    # "never run" about. `unknown` states the truth: no outcome can be
    # determined for a ref that does not resolve (user ruling, 2026-08-08).
    return ValidationMatrixRow(
        subject=SystemScopeRef(kind="sr", ref=ref),
        status=MatrixStatus.UNKNOWN,
        evidence=[],
        freshness=Freshness(state=FreshnessState.NA, reason="referenced sr does not exist", dependencies=[]),
        summary="sr does not exist",
    )


def query_matrix(repo_root: Path, scope: SystemScopeRef) -> dict:
    """Assemble the validation matrix for `scope` (design SS5.2, SS7.3).

    One row per SR relevant to the scope. `status` carries the recorded
    validation outcome only; staleness and absence live on `freshness`
    (design SS7.3) -- never in `status`.
    """
    if scope.kind == "bundle":
        bundle_id = _scope_identifier(scope)
        bundle = _load_bundle_or_raise(repo_root, bundle_id)
        reqs = register.load_register(_requirements_dir(repo_root))
        report_corrupt = _validation_report_is_corrupt(repo_root)
        statuses = _load_validation_statuses(repo_root, report_corrupt)

        rows: list[ValidationMatrixRow] = []
        for member in bundle.members:
            if member.kind != "sr":
                continue
            identifier = member.ref.split(":", 1)[1]
            req = register.get_requirement(reqs, identifier)
            if req is None:
                rows.append(_sr_missing_matrix_row(member.ref))
                continue
            rows.append(_sr_matrix_row(req, statuses.get(req.id), report_corrupt))

        return {
            "scope": {"kind": scope.kind, "ref": scope.ref},
            "rows": [to_dict(r) for r in rows],
        }

    if scope.kind == "sr":
        sr_id = _scope_identifier(scope)
        req = _load_requirement_or_raise(repo_root, sr_id)
        report_corrupt = _validation_report_is_corrupt(repo_root)
        statuses = _load_validation_statuses(repo_root, report_corrupt)
        row = _sr_matrix_row(req, statuses.get(req.id), report_corrupt)
        return {
            "scope": {"kind": scope.kind, "ref": scope.ref},
            "rows": [to_dict(row)],
        }

    raise ScopeKindError(f"unsupported scope kind: {scope.kind!r}")


# ---------------------------------------------------------------------------
# Decision timeline (design SS4.3, SS7.4)
#
# The recorded-artifact source is the `reviews` array inside each durable run
# evidence manifest (`evidence/runs/<run_id>.json`), read through the
# existing `factory.evidence.manifests.list_run_manifests` loader -- never a
# parallel directory glob. `evidence/runs/<run_id>` is a *file*
# (`manifests.py:69`, `write_run_manifest`), not a directory.
#
# `factory.orchestrator.human_review.FileHumanReviewGate._archive` does write
# individual `review-{sequence:03}.json` files, but into `transcript_dir /
# "reviews"` -- per-run scratch under `sessions/.factory-transcripts/`, which
# `.gitignore` deliberately excludes from the repo. Those files are not
# durable evidence. `factory.evidence.finalize._review_evidence` is what
# turns them into durable evidence: it globs exactly that transcript
# directory (in the same `sorted(...)` order the archiving code's filenames
# encode) and folds each record into `manifest["reviews"]`
# (`finalize.py:230`), popping `diff` in favor of a published `patch` blob
# ref. `factory.evidence.reconcile.py:360-366` maintains that same array for
# legacy-migrated reviews. Either way, `manifest["reviews"]` is the one
# place a signed review decision durably lives.
#
# Because `finalize.py` preserves the archiving order when it builds this
# array, an entry's own position within `manifest["reviews"]` is a genuinely
# recorded structural fact about the durable manifest document -- and is used
# as the sequence-number fallback (1-based position) when `reviewed_at` is
# absent. Because array position is *always* available (every entry has
# one), a review record reaching this module always has *some* recorded
# ordering basis, so `_decision_event_from_record` never returns `None`
# (kept `DecisionTimelineEvent.__post_init__`'s own at-or-sequence check as
# the enforcement backstop regardless).
#
# Array position is, however, only meaningful *within* one manifest -- two
# different manifests' "1st review" are not comparable to each other by
# position alone; nothing records that one run's first review happened
# before or after another run's first review. So sequence-only events are
# ordered first by their *manifest's* recorded `ended_at` (required by
# `evidence_manifest.schema.json`, and already the field `list_run_manifests`
# itself sorts on) and only *then* by position within that manifest --
# `test_sequence_only_events_across_manifests_order_by_manifest_
# ended_at_then_position` in `test_timeline.py` pins this ordering.
#
# `evidence_manifest.schema.json` requires `reviews` on any manifest that
# validates at all (`schema.json`'s top-level `required` list), and
# `list_run_manifests` already skips -- individually, silently, matching the
# same discipline `bundles._load_all` already applies -- any manifest file
# that fails to parse or fails that schema validation. So a manifest reaching
# this module always has a `reviews` list already (possibly empty, never
# absent): there is no "absent vs. empty" ambiguity left for this module to
# resolve, because the loader it reuses already resolved it upstream.
#
# A manifest that fails to load is *silently* skipped by `list_run_manifests`
# -- correct for "don't crash", wrong for "don't hide" (design SS8: corrupt
# evidence must degrade a scope, not vanish). `_unreadable_manifest_count`
# compares the raw `evidence/runs/*.json` glob count against how many
# `list_run_manifests` actually returned, and `query_timeline` folds a
# nonzero count into `degraded`. This is a *count* comparison, not a second
# parser: no code here re-reads a manifest's content, so it cannot attribute
# an unreadable manifest to a specific task -- a corrupt/invalid manifest's
# own `task_id` field is exactly the thing that failed to load. The signal is
# therefore necessarily repo-wide (every scope's `query_timeline` call sees
# the same nonzero count while any manifest anywhere is unreadable), not
# scoped to the affected task alone -- a known tension with design SS8's
# "degrades only the affected scope" wording, accepted because there is no
# way to attribute an unreadable file's content without reading it.
#
# Two other candidate sources were deliberately excluded, not overlooked:
#   - `validation/validation-report.json` entries (`factory.trace.
#     validation_status`) carry no timestamp and no sequence number at all
#     (confirmed by reading `factory/validation/report.py` and
#     `validation_status.py`) -- there is nothing recorded to order by, so
#     no `validated` timeline event is ever synthesized from them.
#   - The task ledger (`factory.orchestrator.ledger.Task`) carries no
#     timestamp either, and its `todo/done/rejected/escalated` vocabulary has
#     no non-arbitrary mapping onto `TimelineAction` (the same reasoning
#     keeps `MatrixStatus` from absorbing task/decision vocabularies).
#
# This module never touches a `spec:`/`plan:` trace-node id (the
# `spec:<path>` vs. trace's `spec:<basename>` namespace collision in
# `trace/model.py:94-97` does not apply here): timeline events are always
# `task`-subject, keyed off the review record's own `task_id` field.
# ---------------------------------------------------------------------------

_DECISION_ACTION_MAP = {
    "approve": TimelineAction.APPROVED,
    "reject": TimelineAction.REJECTED,
}


def _iter_decision_records(repo_root: Path) -> list[tuple[dict, SystemCitation, int, str]]:
    """Read signed review decisions from the `reviews` array of every real
    run manifest (design SS4.3), via `factory.evidence.manifests.
    list_run_manifests` -- never a parallel directory glob.

    Yields `(review_record, citation, sequence, manifest_ended_at)` where
    `citation` points at the owning manifest file (with an `anchor` naming
    which array entry), `sequence` is that entry's 1-based position in
    `manifest["reviews"]`, and `manifest_ended_at` is the owning manifest's
    own recorded `ended_at` (required by `evidence_manifest.schema.json`, so
    always a real date-time string here) -- used to order sequence-only
    events across *different* manifests without comparing raw positions
    across documents (see the module-level comment above). A manifest file
    that fails to parse or fails schema validation is already skipped by
    `list_run_manifests` -- it degrades only itself, never the whole scan
    (design SS8), and never raises out of this function.
    """
    evidence_dir = _evidence_dir(repo_root)
    if not (evidence_dir / "runs").is_dir():
        return []
    records: list[tuple[dict, SystemCitation, int, str]] = []
    for manifest in evidence_manifests.list_run_manifests(evidence_dir):
        run_id = manifest.get("run_id")
        if not isinstance(run_id, str) or not run_id:
            continue  # cannot even locate the manifest file to cite -- unusable
        ended_at = manifest.get("ended_at")
        if not isinstance(ended_at, str) or not ended_at:
            continue  # schema guarantees this in practice; defensive only
        manifest_path = _manifest_path(evidence_dir, run_id)
        manifest_sha256 = _sha256_file(manifest_path)
        reviews = manifest.get("reviews")
        if not isinstance(reviews, list):
            continue  # schema guarantees this in practice; defensive only
        for index, review in enumerate(reviews):
            if not isinstance(review, dict):
                continue
            citation = SystemCitation(
                kind=CitationKind.DECISION,
                path=str(manifest_path),
                sha256=manifest_sha256,
                anchor=f"reviews[{index}]",
            )
            records.append((review, citation, index + 1, ended_at))
    return records


def _unreadable_manifest_count(repo_root: Path) -> int:
    """How many `evidence/runs/*.json` files exist but did not come back
    from `list_run_manifests` (unparseable JSON or schema-invalid content).

    A count comparison against the same glob `list_run_manifests` itself
    uses -- not a second parser: nothing here re-reads a manifest's content,
    so this cannot say *which* task an unreadable manifest belonged to (that
    is exactly the information that failed to load). Design SS8: corrupt
    evidence must degrade a scope's timeline, not silently vanish; see the
    module-level comment above for the repo-wide-signal tradeoff this
    creates.
    """
    evidence_dir = _evidence_dir(repo_root)
    runs_dir = evidence_dir / "runs"
    if not runs_dir.is_dir():
        return 0
    total = len(list(runs_dir.glob("*.json")))
    loaded = len(evidence_manifests.list_run_manifests(evidence_dir))
    return max(total - loaded, 0)


def _decision_event_from_record(
    record: dict, citation: SystemCitation, sequence: int
) -> DecisionTimelineEvent:
    """Build one `DecisionTimelineEvent` from a parsed review-decision record.

    Always succeeds: `sequence` (the record's position within its manifest's
    `reviews` array) is always a real int, so there is always at least one
    recorded ordering basis for anything reaching this function -- see the
    module-level comment above `_iter_decision_records`.
    """
    at_raw = record.get("reviewed_at")
    at = at_raw if isinstance(at_raw, str) and at_raw else None

    reasons: list[str] = []

    decision = record.get("decision")
    action = (
        _DECISION_ACTION_MAP.get(decision, TimelineAction.NOT_RECORDED)
        if isinstance(decision, str)
        else TimelineAction.NOT_RECORDED
    )
    if action is TimelineAction.NOT_RECORDED:
        reasons.append("review decision record does not carry a recognized decision value")

    # This artifact shape never names a reviewer identity (design SS4.3: "not
    # stated by a source record" -- there is no field for one at all here,
    # so this is not a guess, it is the recorded absence of one).
    actor = TimelineActor.NOT_RECORDED
    reasons.append("review decision record does not name an actor")

    if at is None:
        reasons.append(
            "reviewed_at not recorded; ordering falls back to the review's recorded "
            "position within its manifest's reviews array"
        )

    task_id = record.get("task_id")
    subject = SystemScopeRef(kind="task", ref=f"task:{task_id}")

    return DecisionTimelineEvent(
        actor=actor,
        action=action,
        subject=subject,
        citation=citation,
        freshness=Freshness(state=FreshnessState.DEGRADED, reason="; ".join(reasons), dependencies=[]),
        at=at,
        # `sequence` is only a within-manifest array-position fallback for
        # when no recorded timestamp exists (see `_timeline_sort_key`) --
        # emitting it alongside a real `at` would present that position as a
        # top-level ordinal beside a genuine timestamp, which nothing
        # recorded ever asserted.
        sequence=sequence if at is None else None,
    )


def _timeline_sort_key(event: DecisionTimelineEvent, manifest_ended_at: str) -> tuple:
    """Deterministic ordering key (design SS4.3): events with a recorded
    timestamp sort chronologically among themselves and before events that
    only have a recorded sequence number (there is no honest way to compare
    a timestamp to a bare sequence number, so the two groups are never
    interleaved by guesswork).

    Within the sequence-only group, `manifest_ended_at` (the *owning
    manifest's* recorded completion time) orders by which manifest completed
    first, then `citation.path` (the owning manifest's own file path, unique
    per manifest) groups every event from the same manifest together *before*
    `sequence` is ever compared -- so array position from two different
    manifests is never compared to each other, unconditionally, even when
    both manifests share the same `ended_at` (plausible for same-second
    completions in bulk runs: `ended_at` alone would tie, and comparing raw
    `sequence` next would reproduce the original cross-manifest interleaving
    bug). `citation.anchor` is the final tie-break for full determinism.
    """
    if event.at is not None:
        return (0, event.at, event.citation.path, event.citation.anchor or "")
    return (
        1,
        manifest_ended_at,
        event.citation.path,
        f"{event.sequence:020d}",
        event.citation.anchor or "",
    )


def _bundle_task_ids(bundle: BundleDeclaration) -> set[str]:
    return {member.ref.split(":", 1)[1] for member in bundle.members if member.kind == "task"}


def _sr_task_ids(repo_root: Path, sr_id: str) -> set[str]:
    tasks = ledger.load_tasks(_tasks_dir(repo_root))
    return {task.id for task in tasks if sr_id in task.satisfies}


def _timeline_degraded_reasons(events: list[DecisionTimelineEvent], unreadable_manifests: int) -> list[str]:
    """Distinct, counted reasons `query_timeline`'s `degraded` is true.

    A bare `degraded: bool` cannot tell a caller "this artifact shape never
    names an actor, routine" from "an evidence file is corrupt and needs
    attention" -- both make `degraded` true, for very different reasons.
    Each string here corresponds to something actually counted over `events`
    or the manifest scan, never an invented or generic explanation; an empty
    list means not degraded.
    """
    reasons: list[str] = []
    no_actor = sum(1 for e in events if e.actor is TimelineActor.NOT_RECORDED)
    if no_actor:
        reasons.append(f"{no_actor} event(s) do not have a recorded actor")
    no_action = sum(1 for e in events if e.action is TimelineAction.NOT_RECORDED)
    if no_action:
        reasons.append(f"{no_action} event(s) do not have a recognized recorded action")
    sequence_fallback = sum(1 for e in events if e.at is None)
    if sequence_fallback:
        reasons.append(
            f"{sequence_fallback} event(s) have no recorded timestamp and fall back to "
            "their manifest's recorded reviews-array position"
        )
    if unreadable_manifests:
        reasons.append(
            f"{unreadable_manifests} run manifest(s) under evidence/runs could not be read"
        )
    return reasons


def query_timeline(repo_root: Path, scope: SystemScopeRef) -> dict:
    """Assemble the decision timeline for `scope` (design SS4.3, SS5.2, SS7.4).

    Returns `{"scope": {...}, "events": [...], "degraded": bool,
    "degraded_reasons": [...]}`. `events` is chronologically ordered per
    `_timeline_sort_key`. `degraded` is true exactly when `degraded_reasons`
    is non-empty (`_timeline_degraded_reasons`) -- either because at least
    one included event itself carries degraded freshness (this artifact type
    never names an actor -- see `_decision_event_from_record` -- so this is
    true whenever `events` is non-empty), or because one or more
    `evidence/runs/*.json` manifests exist but could not be read
    (`_unreadable_manifest_count`) -- design SS8: corrupt evidence must
    degrade a scope, not silently disappear as an empty, clean-looking
    timeline. An empty `events` list with zero unreadable manifests means no
    recorded decisions exist yet for this scope, which is a legitimate
    state, not a degradation (`degraded_reasons` stays empty).
    """
    if scope.kind == "bundle":
        bundle_id = _scope_identifier(scope)
        bundle = _load_bundle_or_raise(repo_root, bundle_id)
        task_ids = _bundle_task_ids(bundle)
    elif scope.kind == "sr":
        sr_id = _scope_identifier(scope)
        _load_requirement_or_raise(repo_root, sr_id)  # exact-resolution check only
        task_ids = _sr_task_ids(repo_root, sr_id)
    else:
        raise ScopeKindError(f"unsupported scope kind: {scope.kind!r}")

    scored: list[tuple[DecisionTimelineEvent, str]] = []
    for record, citation, sequence, manifest_ended_at in _iter_decision_records(repo_root):
        task_id = record.get("task_id")
        if not isinstance(task_id, str) or task_id not in task_ids:
            continue
        event = _decision_event_from_record(record, citation, sequence)
        scored.append((event, manifest_ended_at))

    scored.sort(key=lambda pair: _timeline_sort_key(pair[0], pair[1]))
    events = [event for event, _ in scored]

    degraded_reasons = _timeline_degraded_reasons(events, _unreadable_manifest_count(repo_root))

    return {
        "scope": {"kind": scope.kind, "ref": scope.ref},
        "events": [to_dict(e) for e in events],
        "degraded": bool(degraded_reasons),
        "degraded_reasons": degraded_reasons,
    }


def list_scopes(repo_root: Path) -> list[SystemScopeRef]:
    """List every declared scope the browser can open (design SS5.2).

    Declared bundles, then declared ADRs, then trace-model
    feature/metric/goal/diagram nodes. `sr:` scopes are deliberately not
    listed (SP-B Task 3): requirements are reachable by search, not by
    listing -- `parse_scope_ref` still resolves `sr:` as a legal top-level
    scope. A malformed bundle file degrades only itself
    (`bundles.list_bundles` already skips it); it never aborts the rest of
    the listing. An ADR with no declared id has no ref to be opened under and
    is likewise skipped by `load_adrs`.
    """
    scopes: list[SystemScopeRef] = []
    for bundle in bundles.list_bundles(_bundles_dir(repo_root)):
        scopes.append(SystemScopeRef(kind="bundle", ref=f"bundle:{bundle.id}"))
    for adr_id in adr_module.load_adrs(repo_root):
        scopes.append(SystemScopeRef(kind="adr", ref=f"adr:{adr_id}"))
    for node in trace_model.load_nodes(repo_root):
        if node.kind in ("diag", "feat", "metric", "goal"):
            scopes.append(SystemScopeRef(kind=node.kind, ref=f"{node.kind}:{node.id}"))
    return scopes


def query_guide(repo_root: Path, scope: SystemScopeRef) -> dict:
    """Thin entry point for the grounded guide (design SS4.4, SS5.1, Task 5).

    All synthesis logic lives in `factory.system.guide` -- this only
    delegates, mirroring `query_brief`/`query_matrix`/`query_timeline`'s
    place in the CLI surface so `cli.py` can import all four `query_*`
    functions from this one module. The import is deferred (function-local,
    not module-level) because `factory.system.guide` itself imports
    `query_brief`/`query_matrix`/`query_timeline` from this module -- a
    module-level import here would be a circular import.
    """
    from factory.system import guide as _guide

    return _guide.query_guide(repo_root, scope)


def _traversal_for_sr(
    repo_root: Path, sr_id: str, edges: list, evidence_dir: Path, *, lookup: ArtifactLookup
) -> tuple[list[str], list[str], list[str]]:
    """One `sr:` chain from the real trace graph (Task 9, working traversal).

    Walks the same `factory.trace.model.extract_edges` edges `build_graph`
    already loads -- never a second parser:

    - `tasks`: `satisfies`-in edges whose `dst` is this SR (edges carry the
      bare `SR-001` id, matching `extract_edges`'s own `satisfies` dst);
    - the task's own `source_plan` -> plan ids, each plan's `spec_ref` ->
      spec ids (traversed so the design surface is reachable), and any
      `adr:`/design node the chain references -- here, the design decisions
      the requirement's feature actually records, i.e. the `adr:` members of
      every bundle that declares this SR (ADRs connect to the rest of the
      graph only through bundle membership; SP-A's bundle map is their sole
      link, so this reads that link rather than guessing one);
    - `files`: changed files recorded in the evidence manifests of the
      satisfying tasks -- the reverse of the same `changed_files` link
      `factory.system.reverse`/`story` read (task -> run -> files).

    All values come from recorded loaders; nothing is invented.
    """
    tasks = sorted(
        edge.src for edge in edges if edge.kind == "satisfies" and edge.dst == sr_id
    )

    plans: list[str] = []
    specs: list[str] = []
    for task_id in tasks:
        for edge in edges:
            if edge.kind == "source_plan" and edge.src == task_id:
                plans.append(edge.dst)
    for plan_id in plans:
        for edge in edges:
            if edge.kind == "spec_ref" and edge.src == plan_id:
                specs.append(edge.dst)

    # Design decisions = the `adr:` members of the bundles that declare this
    # SR (the only recorded link from a requirement to its design decisions).
    design: list[str] = []
    for bundle_id in bundles.bundles_containing(repo_root, f"sr:{sr_id}", lookup=lookup):
        try:
            bundle = bundles.load_bundle(_bundles_dir(repo_root), bundle_id)
        except (FileNotFoundError, ValueError):
            # A bundle that lists itself but fails to load degrades only its
            # own contribution -- never the whole traversal (standing rule).
            continue
        for member in bundle.members:
            if member.kind == "adr" and member.ref not in design:
                design.append(member.ref)

    # Changed files from the reverse walk on the satisfying tasks: the union
    # of the recorded `changed_files` across those tasks' evidence manifests.
    files: list[str] = []
    for task_id in tasks:
        for manifest in evidence_manifests.list_run_manifests(evidence_dir, task_id=task_id):
            for changed in manifest["implementation"]["changed_files"]:
                if changed not in files:
                    files.append(changed)
    return tasks, design, files


def query_traversal(repo_root: Path, scope: SystemScopeRef) -> dict:
    """Working traversal: requirement -> satisfying tasks -> design -> files.

    Anchored on an `sr:` scope, walks the real trace graph (no parser, no
    synthesis). A `bundle:` scope aggregates the traversal over its `sr:`
    members (the bundle's requirements), unioning tasks/design/files and
    naming every requirement. Returns a plain dict
    `{"requirement", "tasks", "design", "files"}`. Raises
    `ScopeKindError` for any other scope kind.
    """
    nodes = trace_model.load_nodes(repo_root)
    edges = trace_model.extract_edges(repo_root, nodes)
    evidence_dir = _evidence_dir(repo_root)
    lookup = build_artifact_lookup(repo_root, nodes=nodes)

    # A function-local import keeps the module import graph acyclic
    # (labels.py imports system.bundles and system.adr; neither reaches here).
    from factory.system.labels import build_alias_map

    aliases = build_alias_map(repo_root, nodes=nodes)

    def _ref(raw: str) -> str:
        # Unresolvable values are emitted unchanged so nothing is invented;
        # the browser renders them as "not in the label index".
        return aliases.get(raw, raw)

    def _file_ref(raw: str) -> str:
        # There are no file nodes in the graph (trace/model.py:102), so a path
        # can only be prefixed directly. The path is the file's identity.
        return raw if raw.startswith("file:") else f"file:{raw}"

    if scope.kind == "sr":
        sr_id = _scope_identifier(scope)
        tasks, design, files = _traversal_for_sr(
            repo_root, sr_id, edges, evidence_dir, lookup=lookup
        )
        return {
            "requirement": [_ref(sr_id)],
            "tasks": [_ref(t) for t in tasks],
            "design": [_ref(d) for d in design],
            "files": [_file_ref(f) for f in files],
        }

    if scope.kind == "bundle":
        bundle_id = _scope_identifier(scope)
        bundle = _load_bundle_or_raise(repo_root, bundle_id)
        sr_ids = sorted(m.ref.split(":", 1)[1] for m in bundle.members if m.kind == "sr")
        all_tasks: list[str] = []
        all_design: list[str] = []
        all_files: list[str] = []
        for sr_id in sr_ids:
            tasks, design, files = _traversal_for_sr(
                repo_root, sr_id, edges, evidence_dir, lookup=lookup
            )
            for t in tasks:
                if t not in all_tasks:
                    all_tasks.append(t)
            for d in design:
                if d not in all_design:
                    all_design.append(d)
            for f in files:
                if f not in all_files:
                    all_files.append(f)
        return {
            "requirement": [_ref(s) for s in sr_ids],
            "tasks": [_ref(t) for t in all_tasks],
            "design": [_ref(d) for d in all_design],
            "files": [_file_ref(f) for f in all_files],
        }

    raise ScopeKindError(
        f"query_traversal supports an sr: or bundle: anchor, got: {scope.kind!r}"
    )


def query_feature_context(repo_root: Path, scope: SystemScopeRef) -> dict:
    """Return the trace-backed dossier for one exact ``feat:`` scope."""
    if scope.kind != "feat":
        raise ScopeKindError(f"query_feature_context only supports a feat scope, got: {scope.kind!r}")
    feature_id = _scope_identifier(scope)
    from factory.system.feature import feature_context

    return {
        "scope": {"kind": scope.kind, "ref": scope.ref},
        "dossier": feature_context(repo_root, feature_id),
    }


def query_validation(repo_root: Path, scope: SystemScopeRef) -> dict:
    """Return one requirement's validation evidence (Inc 6 Task 4).

    Only ``sr:`` scopes carry validation. The projection combines recorded
    state only, never a guess:

    * raw state + staleness from the validation report;
    * the D5 goal-aware status (VALIDATED/REGRESSED/VERIFICATION_PENDING)
      derived by ``validation_status.requirement_validation`` from the
      goals bound to the requirement via declared ``demonstrates`` edges or
      the goal's own ``requirements`` frontmatter;
    * the goals that produced the state;
    * the simulation runs whose manifests declare the requirement;
    * the metric ids the bound goals evaluate.
    """
    if scope.kind != "sr":
        raise ScopeKindError(f"query_validation only supports sr scopes, got: {scope.kind!r}")
    req_id = _scope_identifier(scope)
    status = validation_status.load_validation(repo_root).get(req_id)
    raw_state = status.state if status is not None else "never_validated"
    stale = status.stale if status is not None else False
    error = status.error if status is not None else None

    # Inc 7 Task 4: derive VERIFICATION_STALE *live* -- the register checksum
    # is the fingerprint that records whether the requirement's content changed
    # since its last validation (spec §30 A→C). Recomputed now, not trusted
    # from the report alone; a requirement with no register entry falls back to
    # the report's recorded flag.
    from factory.requirements import register as req_register

    req = next(
        (r for r in req_register.load_register(repo_root / "requirements") if r.id == req_id),
        None,
    )
    if req is not None:
        stale = not req_register.is_checksum_current(req)

    goals = goal_registry.load_goals(repo_root)
    edges = trace_model.extract_edges(repo_root, trace_model.load_nodes(repo_root))
    demonstrated: set[str] = {e.src for e in edges if e.kind == "demonstrates" and e.dst == req_id}
    bound_goals = sorted(
        (g for g in goals.values() if req_id in g.requirements or g.id in demonstrated),
        key=lambda g: g.id,
    )
    goal_state = validation_status.requirement_validation(bound_goals, stale=stale)
    runs = sim_registry.runs_for(_evidence_dir(repo_root), requirement=req_id)
    metric_ids: set[str] = set()
    for goal in bound_goals:
        metric = goal.metric
        if isinstance(metric, dict) and metric.get("id"):
            metric_ids.add(str(metric["id"]))
        elif isinstance(metric, str):
            metric_ids.add(metric)

    return {
        "scope": {"kind": "sr", "ref": scope.ref},
        "validation": {
            "id": req_id,
            "raw_state": raw_state,
            "stale": stale,
            "error": error,
            "goal_state": goal_state,
            "goals": [{"id": g.id, "state": g.state} for g in bound_goals],
            "runs": [r.run_id for r in runs],
            "metrics": sorted(metric_ids),
        },
    }


def _vcycle_statuses(repo_root: Path, slice_: VCycleSlice) -> dict[str, dict[str, object]]:
    """Attach recorded state to each V-cycle slice node id (Inc 6 Task 2).

    Additive: the V-cycle payload is untouched. Every status is recorded
    state read from its own source, and nodes with no source are simply
    absent so the TS renders them neutral -- never guessed.

    * sr/br nodes  <- validation report (state + stale)
    * goal nodes   <- goal registry frontmatter state
    * task nodes   <- task ledger frontmatter status
    """
    ids: set[str] = set()
    for side in list(slice_.definition) + list(slice_.verification):
        ids.update(node.id for node in side.nodes)
    for group in (slice_.goals, slice_.metrics, slice_.runs):
        ids.update(node.id for node in group)

    validation = validation_status.load_validation(repo_root)
    goals = goal_registry.load_goals(repo_root)
    task_status = {task.id: task.status for task in ledger.load_tasks(repo_root / "tasks")}

    statuses: dict[str, dict[str, object]] = {}
    for node_id in sorted(ids):
        status = validation.get(node_id)
        if status is not None:
            statuses[node_id] = {
                "kind": "validation",
                "state": status.state,
                "stale": status.stale,
            }
            continue
        goal = goals.get(node_id)
        if goal is not None:
            statuses[node_id] = {"kind": "goal", "state": goal.state}
            continue
        task_state = task_status.get(node_id)
        if task_state is not None:
            statuses[node_id] = {"kind": "task", "state": task_state}
    return statuses


def query_vcycle(repo_root: Path, scope: SystemScopeRef) -> dict:
    """Return the typed V-cycle slice for one exact ``feat:`` or ``sr:`` scope."""
    if scope.kind not in {"feat", "sr"}:
        raise ScopeKindError(f"query_vcycle only supports feat or sr scopes, got: {scope.kind!r}")
    _scope_identifier(scope)
    from factory.system.vcycle import vcycle_slice

    try:
        slice_ = vcycle_slice(repo_root, scope.ref)
    except ValueError as exc:
        if str(exc) == f"vcycle anchor does not resolve: {scope.ref!r}":
            raise ScopeNotFoundError(f"{scope.kind} not found: {_scope_identifier(scope)!r}") from exc
        raise
    return {
        "scope": {"kind": scope.kind, "ref": scope.ref},
        "vcycle": to_dict(slice_),
        "statuses": _vcycle_statuses(repo_root, slice_),
    }


def query_catchup(repo_root: Path, feature: str) -> dict:
    """Return the recorded 'since your last review' delta for one feature.

    Read-only projection for the agent (Inc 4) and the SCC Catch-me-up view
    (Inc 7 Task 3): the recorded checkpoint commit is loaded (never inferred),
    the ``ContextDelta`` is computed deterministically from recorded sources,
    and nothing is written -- checkpoint upgrades are the `/catchup` command's
    job, not a query's.

    ``reviewed: false`` means no checkpoint is recorded yet -- legitimate,
    not an error (spec §31). Raises ``ScopeNotFoundError`` when the feature
    cannot be resolved, and ``ValueError`` when the recorded checkpoint
    commit no longer resolves.
    """
    from dataclasses import asdict

    from factory.delta.checkpoint import load_checkpoint
    from factory.delta.compute import compute_delta

    pi_dir = repo_root / ".pi"
    checkpoint = load_checkpoint(pi_dir, feature)
    if checkpoint is None:
        return {"feature": feature, "reviewed": False, "since_commit": None, "delta": None, "diagram": None}
    try:
        delta = compute_delta(repo_root, feature, checkpoint.commit)
    except ValueError as exc:
        if str(exc).startswith("feature not found"):
            raise ScopeNotFoundError(str(exc)) from exc
        raise
    from factory.delta.freshness import apply_freshness

    delta = apply_freshness(repo_root, delta)
    return {
        "feature": feature,
        "reviewed": True,
        "since_commit": checkpoint.commit,
        "reviewed_at": checkpoint.reviewed_at,
        "delta": asdict(delta),
        "diagram": _feature_diagram(repo_root, feature),
    }


def _feature_diagram(repo_root: Path, feature: str) -> dict | None:
    """The canonical D7 diagram of the feature, if one is declared (5b).
    Reuses query_diagram -- the sole diagram-dispatch path -- so the D7
    guards are shared, never forked. None when no diagram illustrates the
    feature (legitimate, not an error).
    """
    from factory.trace import model as trace_model

    nodes = trace_model.load_nodes(repo_root)
    edges = trace_model.extract_edges(repo_root, nodes)
    for edge in edges:
        if edge.kind == "illustrates" and edge.dst == feature:
            try:
                return query_diagram(repo_root, edge.src)
            except (ScopeNotFoundError, ValueError):
                continue
    return None
