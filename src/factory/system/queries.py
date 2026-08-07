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

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from factory.evidence import manifests as evidence_manifests
from factory.orchestrator import ledger
from factory.requirements import register
from factory.requirements.register import Requirement
from factory.system import bundles
from factory.system.bundles import BundleIdMismatchError
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
from factory.trace import validation_status
from factory.trace.validation_status import SrStatus

_SCOPE_KINDS = ("bundle", "sr")

# Member kinds a declared bundle may name (mirrors factory.system.bundles).
_SPEC_PLAN_KINDS = ("spec", "plan")


class ScopeError(Exception):
    """Base class for scope-resolution failures the CLI reports structurally."""


class ScopeKindError(ScopeError):
    """The scope ref is malformed or names a kind that is not a top-level scope."""


class ScopeNotFoundError(ScopeError):
    """The scope ref is well-formed but does not resolve to a declared scope."""


def parse_scope_ref(raw: str) -> SystemScopeRef:
    """Parse a `--scope` CLI argument into a `SystemScopeRef`.

    Only `bundle:<id>` and `sr:<id>` are legal top-level scopes (design
    SS2 item 6, SS5.1). Anything else -- an unknown kind, a missing
    identifier, or a malformed string -- is rejected outright; there is no
    fuzzy fallback.
    """
    kind, sep, identifier = raw.partition(":")
    if not sep or kind not in _SCOPE_KINDS or not identifier:
        raise ScopeKindError(
            f"invalid scope ref: {raw!r} (expected bundle:<id> or sr:<id>)"
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


def _tasks_dir(repo_root: Path) -> Path:
    return repo_root / "tasks"


def _fresh(reason: str | None = None) -> Freshness:
    return Freshness(state=FreshnessState.FRESH, reason=reason, dependencies=[])


def _missing(text: str, reason: str) -> SystemClaim:
    return SystemClaim(
        kind=ClaimClass.MISSING,
        text=text,
        freshness=Freshness(state=FreshnessState.NA, reason=reason, dependencies=[]),
    )


def _sha256_file(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


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


@dataclass(frozen=True)
class _MemberResolution:
    """The outcome of resolving one declared bundle member against real loaders."""

    member_claim: SystemClaim
    extra_claims: list[SystemClaim]
    resolved: bool


def _resolve_spec_or_plan_member(repo_root: Path, member: SystemScopeRef, identifier: str) -> _MemberResolution:
    path = repo_root / identifier
    if not path.is_file():
        claim = _missing(member.ref, "bundle member does not exist in repo")
        return _MemberResolution(member_claim=claim, extra_claims=[], resolved=False)
    citation = SystemCitation(
        kind=CitationKind.TRACE,
        path=str(path),
        sha256=_sha256_file(path),
    )
    claim = SystemClaim(
        kind=ClaimClass.RECORDED,
        text=member.ref,
        freshness=_fresh(),
        citations=[citation],
    )
    return _MemberResolution(member_claim=claim, extra_claims=[], resolved=True)


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
    return _MemberResolution(member_claim=member_claim, extra_claims=[impl_claim], resolved=True)


def _validation_report_is_corrupt(repo_root: Path) -> bool:
    """True only when the validation report file exists but fails to parse
    as JSON -- never merely because it parsed to zero usable entries.

    `validation_status.load_validation` swallows read/parse failures into
    `{}`, which made a genuinely corrupt file indistinguishable from a file
    that parsed fine and legitimately says "nothing has been validated yet"
    (an empty `requirements` array is exactly what
    `factory.validation.pipeline.validate_task_requirements` writes before
    anything has run -- not corruption). The fix is to attempt the parse
    ourselves, mirroring `load_validation`'s own try/except, rather than
    inferring corruption from its collapsed return value: a report that
    parses is never corrupt, no matter how few (or how invalid) its entries
    are. Design SS3.1: "if a claim cannot be tied to recorded artifacts, it
    is shown as missing or degraded, never guessed" -- this cuts both ways,
    so we must not guess corruption either.
    """
    path = validation_status.report_path(repo_root)
    if not path.exists():
        return False
    try:
        json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return True
    return False


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
    statuses = validation_status.load_validation(repo_root)
    report_citation = _validation_report_citation(repo_root)
    report_corrupt = _validation_report_is_corrupt(repo_root)
    claims.append(_sr_validation_claim(req, statuses.get(req.id), report_citation, report_corrupt))
    return claims


def query_brief(repo_root: Path, scope: SystemScopeRef) -> dict:
    """Assemble the one-page briefing for `scope` (design SS4.1, SS4.2, SS5.2).

    Returns a JSON-able dict: `{"scope": {...}, "claims": [...], ...}`.
    Bundle scopes additionally carry `"degraded": bool` -- true when any
    declared member (syntactically bad, per Task 1, or simply nonexistent,
    resolved here) failed to resolve.
    """
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
        statuses = validation_status.load_validation(repo_root)
        report_citation = _validation_report_citation(repo_root)
        report_corrupt = _validation_report_is_corrupt(repo_root)

        degraded = bool(bundle.unresolved)
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
            else:  # pragma: no cover -- bundles.py restricts member kinds
                raise AssertionError(f"unexpected member kind: {member.kind!r}")
            claims.append(resolution.member_claim)
            claims.extend(resolution.extra_claims)
            degraded = degraded or not resolution.resolved

        claims.extend(bundle.unresolved)

        return {
            "scope": {"kind": scope.kind, "ref": scope.ref},
            "claims": [to_dict(c) for c in claims],
            "degraded": degraded,
        }

    if scope.kind == "sr":
        sr_id = _scope_identifier(scope)
        req = _load_requirement_or_raise(repo_root, sr_id)
        claims = _sr_brief_claims(repo_root, req)
        return {
            "scope": {"kind": scope.kind, "ref": scope.ref},
            "claims": [to_dict(c) for c in claims],
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
            return ValidationMatrixRow(
                subject=subject,
                status=MatrixStatus.NEVER_RUN,
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
    return ValidationMatrixRow(
        subject=SystemScopeRef(kind="sr", ref=ref),
        status=MatrixStatus.NEVER_RUN,
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
        statuses = validation_status.load_validation(repo_root)
        report_corrupt = _validation_report_is_corrupt(repo_root)

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
        statuses = validation_status.load_validation(repo_root)
        report_corrupt = _validation_report_is_corrupt(repo_root)
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
# parallel directory glob. This corrects an earlier version of this file that
# globbed `evidence/runs/<run_id>/reviews/review-*.json`: nothing in this
# repo ever writes that layout. `evidence/runs/<run_id>` is a *file*
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
# recorded structural fact about the durable manifest document -- not
# inferred from content or rationale, exactly like the old filename counter
# it replaces -- and is used as the sequence-number fallback (1-based
# position) when `reviewed_at` is absent. Because array position is *always*
# available (every entry has one), a review record reaching this module
# always has *some* recorded ordering basis; the "drop for lacking any
# ordering basis at all" case from the transcript-file era can no longer
# occur here, and `_decision_event_from_record` reflects that by never
# returning `None` (kept `DecisionTimelineEvent.__post_init__`'s own
# at-or-sequence check as the enforcement backstop regardless).
#
# Array position is, however, only meaningful *within* one manifest -- two
# different manifests' "1st review" are not comparable to each other by
# position alone; nothing records that one run's first review happened
# before or after another run's first review. So sequence-only events are
# ordered first by their *manifest's* recorded `ended_at` (required by
# `evidence_manifest.schema.json`, and already the field `list_run_manifests`
# itself sorts on) and only *then* by position within that manifest. This
# was a real bug in an earlier version of this file: the sort key put
# `sequence` ahead of `citation.path`, so sequence-only events from different
# manifests interleaved by raw position number -- asserting an order nothing
# recorded. `test_sequence_only_events_across_manifests_order_by_manifest_
# ended_at_then_position` in `test_timeline.py` pins the fix.
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
# scoped to the affected task alone; see the note above
# `_unreadable_manifest_count` and the "Concerns" section of the task report
# for the tension this creates with design SS8's "degrades only the affected
# scope" wording.
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
#     Task 2 already applied to keep `MatrixStatus` from absorbing task/
#     decision vocabularies -- see task-2-report.md finding on matrix scope).
#
# This module never touches a `spec:`/`plan:` trace-node id (the carried-
# forward `spec:<path>` vs. `spec:<basename>` namespace collision from
# `trace/model.py:94-97` does not apply here): timeline events are always
# `task`-subject, keyed off the review record's own `task_id` field.
# ---------------------------------------------------------------------------

_DECISION_ACTION_MAP = {
    "approve": TimelineAction.APPROVED,
    "reject": TimelineAction.REJECTED,
}


def _evidence_dir(repo_root: Path) -> Path:
    return repo_root / "evidence"


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
        manifest_path = evidence_dir / "runs" / f"{run_id}.json"
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
        sequence=sequence,
    )


def _timeline_sort_key(event: DecisionTimelineEvent, manifest_ended_at: str) -> tuple:
    """Deterministic ordering key (design SS4.3): events with a recorded
    timestamp sort chronologically among themselves and before events that
    only have a recorded sequence number (there is no honest way to compare
    a timestamp to a bare sequence number, so the two groups are never
    interleaved by guesswork).

    Within the sequence-only group, `manifest_ended_at` (the *owning
    manifest's* recorded completion time) is the primary key, and array
    position is only compared *within* that same manifest -- position
    numbers from different manifests are never compared to each other,
    because nothing recorded says which manifest's "1st review" came first.
    `citation.path` plus `citation.anchor` is the final, fully-deterministic
    tie-break in both groups.
    """
    if event.at is not None:
        return (0, event.at, event.citation.path, event.citation.anchor or "")
    return (
        1,
        manifest_ended_at,
        f"{event.sequence:020d}",
        event.citation.path,
        event.citation.anchor or "",
    )


def _bundle_task_ids(bundle: BundleDeclaration) -> set[str]:
    return {member.ref.split(":", 1)[1] for member in bundle.members if member.kind == "task"}


def _sr_task_ids(repo_root: Path, sr_id: str) -> set[str]:
    tasks = ledger.load_tasks(_tasks_dir(repo_root))
    return {task.id for task in tasks if sr_id in task.satisfies}


def query_timeline(repo_root: Path, scope: SystemScopeRef) -> dict:
    """Assemble the decision timeline for `scope` (design SS4.3, SS5.2, SS7.4).

    Returns `{"scope": {...}, "events": [...], "degraded": bool}`. `events`
    is chronologically ordered per `_timeline_sort_key`. `degraded` is true
    when at least one included event itself carries degraded freshness (this
    artifact type never names an actor -- see `_decision_event_from_record`
    -- so it is true whenever `events` is non-empty) **or** when one or more
    `evidence/runs/*.json` manifests exist but could not be read
    (`_unreadable_manifest_count`) -- design SS8: corrupt evidence must
    degrade a scope, not silently disappear as an empty, clean-looking
    timeline. An empty `events` list with zero unreadable manifests means no
    recorded decisions exist yet for this scope, which is a legitimate
    state, not a degradation.
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

    degraded = any(e.freshness.state is FreshnessState.DEGRADED for e in events) or (
        _unreadable_manifest_count(repo_root) > 0
    )

    return {
        "scope": {"kind": scope.kind, "ref": scope.ref},
        "events": [to_dict(e) for e in events],
        "degraded": degraded,
    }


def list_scopes(repo_root: Path) -> list[SystemScopeRef]:
    """List every declared scope the browser can open (design SS5.2).

    Declared bundles plus SRs from the requirements register. A malformed
    bundle file degrades only itself (`bundles.list_bundles` already skips
    it); it never aborts the rest of the listing.
    """
    scopes: list[SystemScopeRef] = []
    for bundle in bundles.list_bundles(_bundles_dir(repo_root)):
        scopes.append(SystemScopeRef(kind="bundle", ref=f"bundle:{bundle.id}"))
    for req in register.load_register(_requirements_dir(repo_root)):
        scopes.append(SystemScopeRef(kind="sr", ref=f"sr:{req.id}"))
    return scopes
