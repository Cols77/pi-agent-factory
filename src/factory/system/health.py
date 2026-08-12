"""Published bundle-readiness predicate (design §3.4, SP-B).

The only place that turns recorded trace/register/validation signals into a
Strong/Medium/Weak readiness judgement per bundle. It composes existing
loaders -- `requirements.register`, `trace.model`, `trace.gaps`,
`trace.validation_status` -- and never forks a parser. The browser only ever
renders the row produced here; it never computes readiness itself.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from factory.requirements import register as register_module
from factory.system import bundles as bundles_module
from factory.trace import gaps as gaps_module
from factory.trace import model as trace_model
from factory.trace.validation_status import SrStatus, load_validation


@dataclass(frozen=True)
class SrFlags:
    req_id: str
    bound: bool
    covered: bool
    current: bool
    deferred: bool
    validated: bool


@dataclass(frozen=True)
class BundleReadinessRow:
    id: str
    label: str
    readiness: str                # "strong" | "medium" | "weak"
    sr_total: int
    bound: int
    covered: int
    current: int
    deferred: int
    validated: int
    members: int
    recency_iso: str | None

    @property
    def readiness_counts(self) -> dict[str, int]:
        return {
            "sr_total": self.sr_total,
            "bound": self.bound,
            "covered": self.covered,
            "current": self.current,
            "deferred": self.deferred,
            "validated": self.validated,
        }


def _validation_passing(
    root: Path, req_id: str, validation: dict[str, SrStatus] | None = None
) -> bool:
    status = (validation or load_validation(root)).get(req_id)
    return status is not None and status.state == "passed" and not status.stale


def _sr_flags(
    root: Path,
    req_id: str,
    sr_gaps: dict[str, list[gaps_module.Gap]],
) -> SrFlags:
    """Per-SR readiness signals from register, gaps and validation only."""
    req = next(
        (r for r in register_module.load_register(root / "requirements") if r.id == req_id),
        None,
    )
    # `bound` = a decided binding (register) that is not proposed in the trace.
    proposed = any(g.kind == "sr_proposed" for g in sr_gaps.get(req_id, []))
    bound = req is not None and req.binding is not None and not proposed
    # `covered` = at least one non-exempt satisfying task (no pending sr_unsatisfied).
    covered = not any(
        g.kind == "sr_unsatisfied" and g.disposition != "exempt"
        for g in sr_gaps.get(req_id, [])
    )
    # `current` = not proposed: the SR has a decided binding (registration),
    # so it is not an auto-declined placeholder waiting for a measurement.
    current = req is not None and req.binding is not None
    deferred = any(g.disposition == "deferred" for g in sr_gaps.get(req_id, []))
    validated = _validation_passing(root, req_id)
    return SrFlags(req_id, bound, covered, current, deferred, validated)


def bundle_readiness(root: Path) -> dict[str, BundleReadinessRow]:
    """Readiness per bundle id, keyed by id. Pure predicate over recorded signals."""
    nodes = trace_model.load_nodes(root)
    edges = trace_model.extract_edges(root, nodes)
    validation = load_validation(root)
    gaps = gaps_module.find_gaps(nodes, edges, validation)
    sr_gaps: dict[str, list[gaps_module.Gap]] = {}
    for g in gaps:
        sr_gaps.setdefault(g.node_id, []).append(g)

    rows: dict[str, BundleReadinessRow] = {}
    for bundle in bundles_module.list_bundles(root / "bundles"):
        srs = [m.ref.partition(":")[2] for m in bundle.members if m.ref.startswith("sr:")]
        flags = [_sr_flags(root, r, sr_gaps) for r in srs]
        if not flags:
            rows[bundle.id] = BundleReadinessRow(
                bundle.id, bundle.label, "weak", 0, 0, 0, 0, 0, 0,
                len(bundle.members), None,
            )
            continue
        if all(f.covered and f.current and f.validated for f in flags):
            readiness = "strong"
        elif all(f.bound and f.covered for f in flags):
            readiness = "medium"
        else:
            readiness = "weak"
        rows[bundle.id] = BundleReadinessRow(
            id=bundle.id,
            label=bundle.label,
            readiness=readiness,
            sr_total=len(flags),
            bound=sum(f.bound for f in flags),
            covered=sum(f.covered for f in flags),
            current=sum(f.current for f in flags),
            deferred=sum(f.deferred for f in flags),
            validated=sum(f.validated for f in flags),
            members=len(bundle.members),
            recency_iso=None,
        )
    return rows
