"""System navigator query layer: brief, matrix, and scope listing.

Composes existing loaders -- never re-parses an artifact a loader already
owns:

- `factory.system.bundles` for declared feature-scope bundles (syntactic
  member parsing; Task 1's job);
- `factory.requirements.register` for SR content and binding, via the
  existing `SR-*.md` glob register (never a hardcoded path);
- `factory.orchestrator.ledger` for task implementation status (the task
  ledger, never plan checkbox state -- design SS3.4);
- `factory.trace.validation_status` for validation report outcomes and
  staleness.

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

from factory.orchestrator import ledger
from factory.requirements import register
from factory.requirements.register import Requirement
from factory.system import bundles
from factory.system.bundles import BundleIdMismatchError
from factory.system.models import (
    BundleDeclaration,
    ClaimClass,
    CitationKind,
    Freshness,
    FreshnessState,
    MatrixStatus,
    SystemCitation,
    SystemClaim,
    SystemScopeRef,
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
