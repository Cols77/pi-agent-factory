from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import frontmatter

from coherence.register.register import Requirement
from coherence.register.relations import ReferenceIssue, resolve_sr_relations

# SR-050/AC-2: "The per-requirement review reports structural-coverage findings
# (missing/dangling relations, unresolved or duplicate declarations, changed
# production files or executed tests with no owning SR relation) and
# evidence-integrity findings (declared-vs-changed and declared-vs-executed
# reconciliation against manifests and validation output) as two categories,
# distinct from each other and from semantic-fidelity findings, never merged
# into one verdict." (requirements/SR-050.md)
#
# This module implements the source design's (docs/superpowers/specs/
# 2026-08-31-sr-code-validation-traceability-design.md #review-agents) two
# *deterministic* reviewers -- the structural trace reviewer and the evidence
# reconciliation reviewer. The third reviewer the design names, the fidelity
# reviewer, judges whether a link genuinely substantiates a claim; that is a
# judgement call, not a graph or file fact, and is explicitly out of scope
# here (SR-050/AC-4, work package T5).
#
# Both functions below are read-only and deterministic: they classify facts
# already recorded on disk (SR frontmatter, the code map, evidence run
# manifests). Neither writes anything, gates anything, or invents a verdict.
# `structural_review` and `evidence_reconciliation_review` return two
# STRUCTURALLY SEPARATE dataclasses -- AC-2 requires the two categories never
# merge into one verdict, so neither type nests inside, or extends, the other.


@dataclass(frozen=True)
class StructuralFinding:
    """One structural-coverage fact about a single SR's declared relations.

    ``category`` is exactly one of: ``missing``, ``dangling``, ``malformed``,
    ``duplicate``, ``out_of_scope`` (the design's per-SR categories), or
    ``unaccounted`` (the design's register-wide category -- see
    ``unaccounted_changed_files``, which is the only producer of that
    category; ``structural_review`` never emits it, because an unaccounted
    changed file or executed test has no single owning SR to attach it to
    by definition).

    ``field``/``index`` mirror ``coherence.register.relations.ReferenceIssue``
    when the finding originated from a declared relation entry; both are
    ``None`` for a finding that is not about one particular declared entry
    (a ``missing`` finding names the empty field via ``field`` with
    ``index=None``; an ``unaccounted`` finding names neither).
    """

    category: str
    detail: str
    field: str | None = None
    index: int | None = None


@dataclass(frozen=True)
class StructuralReview:
    """Structural-coverage findings for one SR (SR-050/AC-2, first category).

    Never includes ``unaccounted`` findings -- those are register-wide facts
    with no single owning SR; see ``unaccounted_changed_files``.
    """

    req_id: str
    findings: tuple[StructuralFinding, ...]

    @property
    def ok(self) -> bool:
        return not self.findings

    def by_category(self) -> dict[str, tuple[StructuralFinding, ...]]:
        out: dict[str, list[StructuralFinding]] = {}
        for finding in self.findings:
            out.setdefault(finding.category, []).append(finding)
        return {category: tuple(items) for category, items in out.items()}


@dataclass(frozen=True)
class ReconciliationFinding:
    """One evidence-integrity fact (SR-050/AC-2, second category)."""

    category: str
    detail: str


@dataclass(frozen=True)
class ReconciliationReview:
    """Evidence-reconciliation findings for one SR (SR-050/AC-2, second
    category). Structurally distinct from ``StructuralReview`` -- AC-2
    requires the two never merge into one verdict."""

    req_id: str
    findings: tuple[ReconciliationFinding, ...]

    @property
    def ok(self) -> bool:
        return not self.findings

    def by_category(self) -> dict[str, tuple[ReconciliationFinding, ...]]:
        out: dict[str, list[ReconciliationFinding]] = {}
        for finding in self.findings:
            out.setdefault(finding.category, []).append(finding)
        return {category: tuple(items) for category, items in out.items()}


# ---------------------------------------------------------------------------
# Structural trace reviewer
# ---------------------------------------------------------------------------

# How a `resolve_sr_relations` ReferenceIssue.detail maps onto the design's
# named structural categories. This is a judgement call about where a check
# that already exists in `relations.py` belongs in the design's taxonomy --
# documented explicitly, as `relations.py` itself does for its own choices:
#
# * "relation schema and target syntax" (the design's own phrase) covers
#   every check that rejects an entry before any resolution is attempted:
#   the field isn't a list, a required key is missing, a symbol/test string
#   uses a line number as identity, or does not even have the right shape
#   (`<module>:<name>` / `<path>::<node>`) -- these are all ``malformed``.
# * "path existence and project-scope confinement" is ``out_of_scope``.
# * "duplicate/conflicting declarations" is ``duplicate``.
# * "symbol and test-node resolution" is everything left over: the entry was
#   well-formed but does not identify a real definition (including a symbol
#   whose module disagrees with its own declared path -- the shape was
#   valid, but nothing in the code map matches it) -- these are ``dangling``.
_MALFORMED_MARKERS: tuple[str, ...] = (
    "must be a list of mappings",
    "missing required",
    "uses a line number as identity",
    "must be '<dotted.module>:<name>'",
    "must be a pytest node id",
    "path does not match declared path",
)
_OUT_OF_SCOPE_MARKERS: tuple[str, ...] = ("does not resolve inside the project",)
_DUPLICATE_MARKERS: tuple[str, ...] = ("duplicates an earlier declaration",)


def _categorize_reference_issue(issue: ReferenceIssue) -> str:
    detail = issue.detail
    if any(marker in detail for marker in _DUPLICATE_MARKERS):
        return "duplicate"
    if any(marker in detail for marker in _OUT_OF_SCOPE_MARKERS):
        return "out_of_scope"
    if any(marker in detail for marker in _MALFORMED_MARKERS):
        return "malformed"
    return "dangling"


def _raw_meta(req: Requirement) -> dict:
    return frontmatter.load(str(req.path)).metadata


def _declared_entries(meta: dict, field: str) -> list[dict]:
    """Every dict-shaped entry declared under ``field`` (a legacy plain-string
    ``verified_by: [T-001]`` entry is not a structured relation -- see
    ``relations.py``'s own module docstring -- and is skipped here too)."""
    raw = meta.get(field)
    if not isinstance(raw, list):
        return []
    return [entry for entry in raw if isinstance(entry, dict)]


def _declared_paths(meta: dict, field: str) -> set[str]:
    return {
        str(entry["path"]).strip()
        for entry in _declared_entries(meta, field)
        if entry.get("path") and str(entry["path"]).strip()
    }


def structural_review(root: Path, req: Requirement) -> StructuralReview:
    """Deterministic structural-coverage findings for one SR (SR-050/AC-2).

    Reuses ``resolve_sr_relations`` (SR-050/AC-1) for malformed/out_of_scope/
    dangling/duplicate findings -- see the categorisation table above -- and
    adds the one category that resolver does not cover:

    * ``missing``: the SR is bound (``req.binding is not None``, i.e. it has
      a decided measurement) and declares zero *structured* (dict-shaped)
      entries under ``implemented_by``, or zero under ``verified_by``.
      "Structured" is deliberate: a field holding only legacy plain-string
      entries (``verified_by: [T-001]``) counts as zero here too, even
      though that shape is a real, still-supported graph edge elsewhere
      (``coherence.trace.model.edges_from_frontmatter``) and is not itself
      malformed. AC-1/AC-2 exist specifically to require the canonical
      ``path``/``symbol``/``test`` relation this module and ``relations.py``
      resolve; a legacy string carries no path, symbol, or test-node
      identity at all, so treating its mere presence as satisfying
      ``missing`` would let a bound SR carry a real, resolving
      ``implemented_by`` relation while its ``verified_by`` field -- or
      vice versa -- stays permanently unstructured and unreviewable by
      ``resolve_sr_relations``, including across any future implementation
      slice that touches this SR again and never adds the new shape. A
      field that mixes a legacy string with at least one structured entry
      is NOT ``missing`` -- only the structured entries are what count, and
      one is enough.

    Never reports ``unaccounted`` -- see ``unaccounted_changed_files``.
    """
    meta = _raw_meta(req)
    findings: list[StructuralFinding] = []
    if req.binding is not None:
        for field in ("implemented_by", "verified_by"):
            if not _declared_entries(meta, field):
                findings.append(
                    StructuralFinding(
                        category="missing",
                        field=field,
                        detail=f"{req.id}: bound requirement declares no structured {field} entries",
                    )
                )
    resolution = resolve_sr_relations(root, meta)
    for issue in resolution.issues:
        findings.append(
            StructuralFinding(
                category=_categorize_reference_issue(issue),
                field=issue.field,
                index=issue.index,
                detail=issue.detail,
            )
        )
    return StructuralReview(req_id=req.id, findings=tuple(findings))


def _executed_test_paths(manifests: list[dict]) -> list[str]:
    """Repo-relative test file paths with at least one pytest node id
    recorded as executed by any manifest, in first-seen order.

    The evidence manifest schema (``evidence_manifest.schema.json``) types
    ``validation`` as a bare ``array of object`` -- it names no canonical
    field for "which test node ids ran". This repository's evidence
    writers do, consistently, populate two conventional fields inside each
    ``validation[*].requirements[*]`` entry: a flat ``tests`` list of
    pytest node ids, and (when the entry also reports per-acceptance
    -criterion detail) an ``acceptance[*].tests`` list. Every manifest
    under ``evidence/runs/`` in this repository today uses one or both.
    Reading them here -- rather than only ``implementation.changed_files``
    -- is what lets AC-2's "executed tests with no owning SR relation" half
    of its criterion (see the module docstring) actually have a code path
    that can fire; see ``unaccounted_changed_files``, the sole caller. A
    manifest that records no ``tests``/``acceptance[*].tests`` anywhere
    (an untyped ``validation`` blob carrying only, say, a bare pass/fail)
    contributes nothing here -- there is no field left to read, and this
    function does not guess.
    """
    node_ids: list[str] = []
    seen_nodes: set[str] = set()
    for manifest in manifests:
        for validation in manifest.get("validation") or []:
            if not isinstance(validation, dict):
                continue
            for entry in validation.get("requirements") or []:
                if not isinstance(entry, dict):
                    continue
                candidates = list(entry.get("tests") or [])
                for acceptance in entry.get("acceptance") or []:
                    if isinstance(acceptance, dict):
                        candidates.extend(acceptance.get("tests") or [])
                for node_id in candidates:
                    node_id = str(node_id)
                    if node_id not in seen_nodes:
                        seen_nodes.add(node_id)
                        node_ids.append(node_id)
    paths: list[str] = []
    seen_paths: set[str] = set()
    for node_id in node_ids:
        path = node_id.split("::", 1)[0]
        if path not in seen_paths:
            seen_paths.add(path)
            paths.append(path)
    return paths


def unaccounted_changed_files(
    root: Path, reqs: Iterable[Requirement], manifests: list[dict]
) -> tuple[StructuralFinding, ...]:
    """Register-wide ``unaccounted`` structural findings (SR-050/AC-2).

    Implements both halves of AC-2's own criterion text: "changed
    production files **or executed tests** with no owning SR relation" --
    two distinct cases per the source design's identical bullet ("changed
    production files and executed tests with no owning SR relation").

    * A changed file -- read from every evidence run manifest's
      ``implementation.changed_files`` (never from ``git diff``/``git
      log``, per the source plan's explicit "reuse... evidence readers
      rather than scanning Git as an authority" instruction) -- that is
      not named as the ``path`` of ANY SR's ``implemented_by``/
      ``verified_by`` entry anywhere in the whole register.
    * A test file -- read from every manifest's recorded executed pytest
      node ids (``_executed_test_paths``) -- that is likewise not named as
      the ``path`` of any SR's ``implemented_by``/``verified_by`` entry. A
      path already reported as an unaccounted *changed* file is not
      reported again just because it was also executed.

    This is necessarily computed once across the whole register, not per
    SR: an unaccounted file or test has, by definition, no single owning
    SR to attach the finding to, so it is never folded into any one
    ``StructuralReview`` -- a caller merges this tuple in as its own bucket
    (see ``coherence.register.cli.cmd_review``).
    """
    declared: set[str] = set()
    for req in reqs:
        meta = _raw_meta(req)
        declared |= _declared_paths(meta, "implemented_by")
        declared |= _declared_paths(meta, "verified_by")
    changed: list[str] = []
    seen: set[str] = set()
    for manifest in manifests:
        for path in manifest.get("implementation", {}).get("changed_files") or []:
            path = str(path)
            if path not in seen:
                seen.add(path)
                changed.append(path)
    findings = [
        StructuralFinding(
            category="unaccounted",
            detail=f"{path}: changed but not declared as implemented_by/verified_by by any SR",
        )
        for path in changed
        if path not in declared
    ]
    for path in _executed_test_paths(manifests):
        if path in seen or path in declared:
            continue
        findings.append(
            StructuralFinding(
                category="unaccounted",
                detail=(
                    f"{path}: executed as a test but not declared as "
                    "implemented_by/verified_by by any SR"
                ),
            )
        )
    return tuple(findings)


# ---------------------------------------------------------------------------
# Evidence reconciliation reviewer
# ---------------------------------------------------------------------------


def _validation_entries(manifests: list[dict], req_id: str) -> list[dict]:
    """Every ``validation[*].requirements[*]`` block across ``manifests``
    whose ``id`` matches ``req_id`` -- the exact read pattern
    ``coherence.register.cli._validation_state`` uses, except this does NOT
    require a ``passed`` key to be present: "executed" (below) only means a
    validation entry for this SR id exists somewhere, whether or not it
    carries a pass/fail verdict yet."""
    return [
        entry
        for manifest in manifests
        for validation in manifest.get("validation") or []
        if isinstance(validation, dict)
        for entry in validation.get("requirements", [])
        if isinstance(entry, dict) and entry.get("id") == req_id
    ]


def _manifest_recency_key(manifest: dict) -> str:
    """A manifest's ``ended_at`` (falling back to ``started_at``), or ``""``
    when neither is recorded. ISO-8601 timestamps sort lexicographically, so
    plain string comparison is enough to order manifests by recency without
    parsing dates. A manifest carrying neither field sorts as the oldest
    possible value and is never treated as "after" anything -- see
    ``_changed_after_recency``."""
    return str(manifest.get("ended_at") or manifest.get("started_at") or "")


def _last_validated_recency(manifests: list[dict], req_id: str) -> str | None:
    """The most recent recency key (``_manifest_recency_key``) among
    manifests carrying ANY validation entry for ``req_id`` (passed or not)
    -- ``None`` if no manifest ever recorded one."""
    keys = [_manifest_recency_key(m) for m in manifests if _validation_entries([m], req_id)]
    return max(keys) if keys else None


def _changed_after_recency(manifests: list[dict], paths: set[str], after: str) -> bool:
    """True when some manifest whose recency key sorts strictly after
    ``after`` changed one of ``paths``. A manifest with no timestamp at all
    (recency key ``""``) never sorts after anything, so untimestamped
    manifests can never trigger a false "changed after" result -- absent
    data yields no finding here, not a guess."""
    for manifest in manifests:
        if _manifest_recency_key(manifest) <= after:
            continue
        changed = {str(p) for p in (manifest.get("implementation", {}).get("changed_files") or [])}
        if changed & paths:
            return True
    return False


def evidence_reconciliation_review(
    root: Path, req: Requirement, manifests: list[dict]
) -> ReconciliationReview:
    """Deterministic evidence-integrity findings for one SR (SR-050/AC-2).

    Operational definitions (documented explicitly, as this reviewer must be
    a pure-fact reviewer with no judgement calls left implicit):

    * "declared" = the ``path`` of every dict-shaped ``implemented_by`` or
      ``verified_by`` entry this SR's frontmatter declares (legacy plain
      -string entries carry no path and are not "declared" here).
    * "changed" = the union of ``implementation.changed_files`` across every
      manifest that carries a validation entry for THIS SR id (i.e. every
      manifest scoped to this SR by its own recorded validation output --
      not the whole evidence store, which would make ``changed_but_undeclared``
      list every other SR's files too; and not ``git diff``, per the source
      plan). This is a judgement call: a manifest that changed this SR's
      files but has not yet recorded validation for it will not scope its
      files in here -- that gap surfaces as ``executed_but_unlinked``/
      ``declared_but_not_changed`` instead, never silently.
    * "executed" = a validation entry for this SR id exists in some manifest
      (``_validation_entries`` is non-empty), regardless of whether that
      entry carries a ``passed`` verdict yet.
    * "linked" = at least one ``verified_by`` entry is declared (evidence
      integrity is about validation coverage, so this reconciles against
      ``verified_by`` specifically, not ``implemented_by``).
    * "stale or failed" = linked, AND at least one of:

      - some validation entry for this SR says ``passed: false``
        ("failed");
      - no manifest covers this SR's relations at all, i.e. not executed
        ("no manifest covers it");
      - some manifest changed one of the *linked* (``verified_by``) paths
        more recently (by ``ended_at``, falling back to ``started_at``)
        than the most recent manifest that DID record a validation entry
        for this SR -- i.e. the linked code moved on since the last time
        this SR was actually validated, and nothing has re-validated it
        since ("stale"). This is genuine staleness detection, not just
        "never executed": a manifest that once passed can still go stale
        later. Manifests carrying neither ``ended_at`` nor ``started_at``
        are never treated as "after" any other manifest, so recency
        -blind callers get no stale findings rather than an unreliable
        guess -- see ``_changed_after_recency``.

      "failed" takes priority over "stale" when both are true (a linked SR
      whose most recent validation entry failed is reported as "failed").
    """
    meta = _raw_meta(req)
    declared = _declared_paths(meta, "implemented_by") | _declared_paths(meta, "verified_by")
    verified_paths = _declared_paths(meta, "verified_by")
    entries = _validation_entries(manifests, req.id)
    executed = bool(entries)
    scoped_manifests = [m for m in manifests if _validation_entries([m], req.id)]
    changed: set[str] = set()
    for manifest in scoped_manifests:
        changed |= {str(p) for p in (manifest.get("implementation", {}).get("changed_files") or [])}

    findings: list[ReconciliationFinding] = []
    for path in sorted(declared & changed):
        findings.append(
            ReconciliationFinding("declared_and_changed", f"{req.id}: {path} is declared and was changed")
        )
    for path in sorted(declared - changed):
        findings.append(
            ReconciliationFinding(
                "declared_but_not_changed", f"{req.id}: {path} is declared but no scoped manifest changed it"
            )
        )
    for path in sorted(changed - declared):
        findings.append(
            ReconciliationFinding(
                "changed_but_undeclared", f"{req.id}: {path} was changed by a scoped manifest but is not declared"
            )
        )

    if executed and declared:
        findings.append(
            ReconciliationFinding(
                "declared_and_executed", f"{req.id}: declares relations and has an executed validation entry"
            )
        )
    if executed and not verified_paths:
        findings.append(
            ReconciliationFinding(
                "executed_but_unlinked",
                f"{req.id}: a validation entry exists but no verified_by relation is declared",
            )
        )
    failed = any(entry.get("passed") is False for entry in entries)
    stale = False
    if verified_paths and not failed and executed:
        last_validated = _last_validated_recency(manifests, req.id)
        if last_validated is not None:
            stale = _changed_after_recency(manifests, verified_paths, last_validated)
    if verified_paths and (failed or not executed or stale):
        if failed:
            reason = "failed"
        elif not executed:
            reason = "no manifest covers it"
        else:
            reason = "linked paths changed after the last recorded validation (stale)"
        findings.append(
            ReconciliationFinding(
                "linked_but_stale_or_failed", f"{req.id}: verified_by is linked but {reason}"
            )
        )

    return ReconciliationReview(req_id=req.id, findings=tuple(findings))


__all__ = [
    "ReconciliationFinding",
    "ReconciliationReview",
    "StructuralFinding",
    "StructuralReview",
    "evidence_reconciliation_review",
    "structural_review",
    "unaccounted_changed_files",
]
