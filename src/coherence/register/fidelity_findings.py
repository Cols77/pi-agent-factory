from __future__ import annotations

from dataclasses import dataclass, replace

from coherence.register.fidelity_packet import FidelityPacket
from coherence.register.relations import ReferenceIssue

# SR-050/AC-4 (docs/superpowers/plans/2026-09-03-sr050-t5-fidelity-reviewer-plan.md,
# T5.2): the fidelity findings schema, with construction-time validation.
#
# `FidelityReviewResult.status`/`.error` are one deliberate addition beyond
# the plan's literal field list, for the same reason `FidelityPacket.diagnostics`
# was (see that module's docstring): T5.3's own text requires that "a `judge`
# that fails to respond, times out, or returns an unparseable/invalid shape
# produces no silent pass: the result records a distinct `unavailable`/error
# status for that SR (never an empty `findings` tuple standing in for
# 'reviewed, found nothing')" -- but the plan's abbreviated
# `FidelityReviewResult` shape block does not itself list a field for that
# status. Without one, "the judge never ran" and "the judge ran and found
# nothing" would be the same tuple on disk, which is exactly the ambiguity
# this design elsewhere refuses (`_human_review_obligation`'s own docstring:
# "there is no default-to-reviewed path"). `status` ("ok" | "unavailable")
# and `error` (the failure detail, `None` when `status == "ok"`) close that
# gap the same way `ReachabilityResult.status`/`.diagnostics` already do for
# an analogous "the fact could not be established" case.

FINDING_KINDS: tuple[str, ...] = (
    "overstated_link",
    "incidental_helper",
    "weaker_subset_test",
    "different_behavior",
    "missing_link_compound",
)

# Open design question #5 (deliberate scoping call, matching how
# `coherence.register.review`'s `missing` check documents its own choice):
# `missing_link_compound` never fires for an SR with no `acceptance:` block
# at all -- a legacy SR carrying only a bare `statement`. There is no
# "compound" claim to check partial coverage of without a declared
# acceptance-criteria list; a judge (or this schema) has nothing to name via
# `acceptance_ref` for such an SR. `overstated_link`/`incidental_helper`/
# `weaker_subset_test`/`different_behavior` remain fully applicable -- they
# judge a single declared relation against the SR's own `statement`, which
# every SR has, compound or not.

FINDING_STATUSES: tuple[str, ...] = ("open", "escalated", "dispositioned")

_RESULT_STATUSES: tuple[str, ...] = ("ok", "unavailable")


class FidelityFindingError(ValueError):
    """A candidate fidelity finding failed construction-time validation."""


@dataclass(frozen=True)
class RelationRef:
    """The SAME ``(field, path, identity)`` triple T1's own duplicate
    -detection ``seen`` set keys on (``relations.py``) -- so a finding
    always names a relation T1 itself could locate again. ``identity`` is
    the symbol or test id; ``""`` for a file-only ``verified_by`` entry."""

    field: str  # "implemented_by" | "verified_by"
    path: str
    identity: str

    def to_dict(self) -> dict:
        return {"field": self.field, "path": self.path, "identity": self.identity}

    @classmethod
    def from_dict(cls, data: dict) -> "RelationRef":
        return cls(field=str(data["field"]), path=str(data["path"]), identity=str(data["identity"]))


def relation_exists_in_packet(packet: FidelityPacket, relation: RelationRef) -> bool:
    """True when ``relation`` names a ``(field, path, identity)`` triple the
    packet actually resolved -- i.e. it appears in ``packet.implemented`` or
    ``packet.verified``. Used at finding-construction time to reject a
    hallucinated relation reference before it can become a "real" finding
    (see ``build_finding``)."""
    if relation.field == "implemented_by":
        return any(p.path == relation.path and p.symbol == relation.identity for p in packet.implemented)
    if relation.field == "verified_by":
        return any(
            v.path == relation.path and (v.test or "") == relation.identity for v in packet.verified
        )
    return False


@dataclass(frozen=True)
class FidelityFinding:
    """One semantic-fidelity finding (SR-050/AC-4). A **supported** link
    produces no finding at all -- the reviewer's positive case is silence,
    matching every other deterministic checker in this design; there is no
    "supported" `kind`.

    Construction validates shape only (kind/confidence/citations/rationale/
    status) -- it does NOT cross-check `relation` against a packet (a bare
    `FidelityFinding(...)` call, e.g. from `from_dict` on a round trip, has
    no packet to check against). The packet cross-check is `build_finding`'s
    job, the only construction path `coherence.register.fidelity` uses for a
    freshly produced finding.
    """

    sr_id: str
    kind: str
    relation: RelationRef
    confidence: float
    citations: tuple[str, ...]
    rationale: str
    acceptance_ref: str | None
    status: str
    produced_at: str
    produced_by_run: str

    def __post_init__(self) -> None:
        if self.kind not in FINDING_KINDS:
            raise FidelityFindingError(f"kind {self.kind!r} must be one of {FINDING_KINDS}")
        if not isinstance(self.confidence, (int, float)) or not (0.0 <= float(self.confidence) <= 1.0):
            raise FidelityFindingError(f"confidence {self.confidence!r} must be in [0.0, 1.0]")
        if not self.citations:
            raise FidelityFindingError("citations must be non-empty -- a finding must cite something")
        if not self.rationale or not self.rationale.strip():
            raise FidelityFindingError("rationale must be non-blank")
        if self.status not in FINDING_STATUSES:
            raise FidelityFindingError(f"status {self.status!r} must be one of {FINDING_STATUSES}")

    def to_dict(self) -> dict:
        return {
            "sr_id": self.sr_id,
            "kind": self.kind,
            "relation": self.relation.to_dict(),
            "confidence": self.confidence,
            "citations": list(self.citations),
            "rationale": self.rationale,
            "acceptance_ref": self.acceptance_ref,
            "status": self.status,
            "produced_at": self.produced_at,
            "produced_by_run": self.produced_by_run,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "FidelityFinding":
        return cls(
            sr_id=str(data["sr_id"]),
            kind=str(data["kind"]),
            relation=RelationRef.from_dict(data["relation"]),
            confidence=float(data["confidence"]),
            citations=tuple(str(c) for c in data["citations"]),
            rationale=str(data["rationale"]),
            acceptance_ref=(str(data["acceptance_ref"]) if data.get("acceptance_ref") is not None else None),
            status=str(data["status"]),
            produced_at=str(data["produced_at"]),
            produced_by_run=str(data["produced_by_run"]),
        )

    def with_status(self, status: str) -> "FidelityFinding":
        """Re-run disposition tracking (T5.4) rewrites `status` only -- every
        other field is provenance from the run that produced the finding and
        must never change on disposition."""
        return replace(self, status=status)


def build_finding(
    packet: FidelityPacket,
    *,
    sr_id: str,
    kind: str,
    relation: RelationRef,
    confidence: float,
    citations: tuple[str, ...],
    rationale: str,
    acceptance_ref: str | None,
    status: str,
    produced_at: str,
    produced_by_run: str,
) -> FidelityFinding:
    """The only construction path that cross-checks `relation` against
    `packet` -- raises `FidelityFindingError` when `relation` does not
    resolve to any entry the packet actually carries. Prevents a
    hallucinated relation reference (an agent citing a symbol/test the
    packet never resolved) from silently becoming a "real" finding.
    """
    if not relation_exists_in_packet(packet, relation):
        raise FidelityFindingError(
            f"relation {relation!r} does not match any entry {packet.sr_id}'s packet resolved"
        )
    return FidelityFinding(
        sr_id=sr_id,
        kind=kind,
        relation=relation,
        confidence=confidence,
        citations=citations,
        rationale=rationale,
        acceptance_ref=acceptance_ref,
        status=status,
        produced_at=produced_at,
        produced_by_run=produced_by_run,
    )


@dataclass(frozen=True)
class FidelityReviewResult:
    """The top-level return/persisted shape for one SR's fidelity review run.

    `findings == ()` means "every declared, resolved relation is supported"
    ONLY when `status == "ok"`; when `status == "unavailable"` an empty
    `findings` tuple means nothing was ever judged -- see the module
    docstring. `unresolved` is a passthrough from the packet -- visible, but
    explicitly not a fidelity finding.
    """

    sr_id: str
    profile: str
    findings: tuple[FidelityFinding, ...]
    unresolved: tuple[ReferenceIssue, ...]
    run_id: str
    produced_at: str
    status: str = "ok"
    error: str | None = None

    def __post_init__(self) -> None:
        if self.status not in _RESULT_STATUSES:
            raise FidelityFindingError(f"result status {self.status!r} must be one of {_RESULT_STATUSES}")

    def to_dict(self) -> dict:
        return {
            "sr_id": self.sr_id,
            "profile": self.profile,
            "findings": [f.to_dict() for f in self.findings],
            "unresolved": [
                {"field": i.field, "index": i.index, "detail": i.detail} for i in self.unresolved
            ],
            "run_id": self.run_id,
            "produced_at": self.produced_at,
            "status": self.status,
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "FidelityReviewResult":
        return cls(
            sr_id=str(data["sr_id"]),
            profile=str(data["profile"]),
            findings=tuple(FidelityFinding.from_dict(f) for f in data.get("findings", [])),
            unresolved=tuple(
                ReferenceIssue(field=str(i["field"]), index=int(i["index"]), detail=str(i["detail"]))
                for i in data.get("unresolved", [])
            ),
            run_id=str(data["run_id"]),
            produced_at=str(data["produced_at"]),
            status=str(data.get("status", "ok")),
            error=(str(data["error"]) if data.get("error") is not None else None),
        )


__all__ = [
    "FINDING_KINDS",
    "FINDING_STATUSES",
    "FidelityFinding",
    "FidelityFindingError",
    "FidelityReviewResult",
    "RelationRef",
    "build_finding",
    "relation_exists_in_packet",
]
