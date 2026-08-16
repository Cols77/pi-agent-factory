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
from factory.system.coverage import build_artifact_lookup, bundle_coverage
from factory.system.ordering import GitRecency, ordered_bundle_ids
from factory.trace import gaps as gaps_module
from factory.trace import model as trace_model
from factory.trace.health import compute_health
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
    description: str | None = None

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
    register: dict[str, register_module.Requirement],
    validation: dict[str, SrStatus],
) -> SrFlags:
    """Per-SR readiness signals from register, gaps and validation only.

    `register` and `validation` are parsed by the caller once per repo, not
    once per member SR; this fn never re-globs or re-parses them.
    """
    req = register.get(req_id)
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
    validated = _validation_passing(root, req_id, validation)
    return SrFlags(req_id, bound, covered, current, deferred, validated)


def bundle_readiness(
    root: Path,
    *,
    nodes: list[trace_model.Node] | None = None,
    edges: list[trace_model.Edge] | None = None,
    validation: dict[str, SrStatus] | None = None,
) -> dict[str, BundleReadinessRow]:
    """Readiness per bundle id, keyed by id. Pure predicate over recorded signals."""
    if nodes is None:
        nodes = trace_model.load_nodes(root)
    if edges is None:
        edges = trace_model.extract_edges(root, nodes)
    if validation is None:
        validation = load_validation(root)
    gaps = gaps_module.find_gaps(nodes, edges, validation)
    sr_gaps: dict[str, list[gaps_module.Gap]] = {}
    for g in gaps:
        sr_gaps.setdefault(g.node_id, []).append(g)

    # Hoisted so register and validation are each parsed exactly once, not once
    # per member SR (Task 2 quality note folded in from Task 1).
    register = {
        r.id: r for r in register_module.load_register(root / "requirements")
    }
    rows: dict[str, BundleReadinessRow] = {}
    for bundle in bundles_module.list_bundles(root / "bundles"):
        srs = [m.ref.partition(":")[2] for m in bundle.members if m.ref.startswith("sr:")]
        flags = [_sr_flags(root, r, sr_gaps, register, validation) for r in srs]
        if not flags:
            rows[bundle.id] = BundleReadinessRow(
                bundle.id, bundle.label, "weak", 0, 0, 0, 0, 0, 0,
                len(bundle.members), None,
                description=bundle.description,
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
            description=bundle.description,
        )
    return rows


def query_health(root: Path, recency_source=None) -> dict:
    """The single JSON document the browser renders as the landing page.

    Composes existing loaders/projections only -- compute_health, gaps,
    bundle_coverage, ordered_bundle_ids and bundle_readiness -- and never
    bicycles a parser. The browser only renders this document; it never
    computes health, ordering, coverage or readiness itself.
    """
    nodes = trace_model.load_nodes(root)
    edges = trace_model.extract_edges(root, nodes)
    validation = load_validation(root)
    gaps = gaps_module.find_gaps(nodes, edges, validation)
    health = compute_health(nodes, gaps)
    lookup = build_artifact_lookup(root, nodes=nodes)
    cov = bundle_coverage(root, lookup=lookup)
    git = recency_source if recency_source is not None else GitRecency()
    order, ordering_available = ordered_bundle_ids(root, git, lookup=lookup)
    rows = bundle_readiness(root, nodes=nodes, edges=edges, validation=validation)
    degraded: list[str] = []
    if not ordering_available:
        degraded.append("git unavailable: bundle ordering fell back to id ascending")

    def _row_dict(row: BundleReadinessRow) -> dict:
        return {
            "id": row.id,
            "label": row.label,
            "readiness": row.readiness,
            "readiness_counts": row.readiness_counts,
            "members": row.members,
            "description": row.description,
        }

    ordered_rows: list[dict] = []
    for bundle_id in order:
        row = rows.get(bundle_id)
        if row is None:
            continue
        ordered_rows.append(_row_dict(row))
    # Bundles not covered by git order (e.g. no git) append by id.
    for bundle_id in sorted(rows.keys() - set(order)):
        ordered_rows.append(_row_dict(rows[bundle_id]))

    return {
        "health": {
            "classes": [
                {"name": c.name, "satisfied": c.satisfied,
                 "expected": c.expected, "exempt": c.exempt}
                for c in health.classes
            ],
            "satisfied": health.satisfied,
            "expected": health.expected,
            "percent": health.percent,
            "dangling": health.dangling,
            "deferred": health.deferred,
            "proposed": health.proposed,
        },
        "coverage": {
            "total": cov.total,
            "bundled": cov.bundled,
            "unbundled": cov.unbundled,
            "kinds": [
                {"kind": k.kind, "total": k.total, "bundled": k.bundled,
                 "unbundled": k.unbundled}
                for k in cov.kinds
            ],
        },
        "bundles": ordered_rows,
        "unbundled": {k.kind: k.unbundled for k in cov.kinds},
        "ordering_available": ordering_available,
        "sr_listed": False,
        "degraded": degraded,
    }
