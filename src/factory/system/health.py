"""Published bundle-readiness predicate (design §3.4, SP-B).

The only place that turns recorded trace/register/validation signals into a
Strong/Medium/Weak readiness judgement per bundle. It composes existing
loaders -- `requirements.register`, `trace.model`, `trace.gaps`,
`trace.validation_status` -- and never forks a parser. The browser only ever
renders the row produced here; it never computes readiness itself.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

from factory.goals.registry import load_goals
from factory.memory.durable import query_memory as _durable_query_memory
from factory.memory.failure_record import DuplicateFailureIdError, load_failures
from factory.requirements import register as register_module
from factory.simulation import registry as sim_registry
from factory.system import bundles as bundles_module
from factory.system._claims import evidence_dir as _evidence_dir
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
        "vcycle_findings": [asdict(f) for f in vcycle_health(root, nodes=nodes, edges=edges, validation=validation)],
        "freshness_findings": [asdict(f) for f in freshness_health(root, nodes=nodes, edges=edges)],
    }


@dataclass(frozen=True)
class Finding:
    """One derived V-cycle finding (Inc 7 Task 5).

    ``code`` is a stable machine id, ``subject`` the artifact ref
    (``sr:SR-001`` / ``task:T-001`` / ``goal:GOAL-001`` / ``run:RUN-...`` /
    ``feat:FEAT-...`` / ``fr:FR-...``), ``detail`` the recorded reason.
    Findings are derived from recorded signals only -- trace gaps, goal
    registry, sim run manifests, failure records, the durable-memory
    projection -- never guessed.
    """

    code: str
    severity: str
    subject: str
    detail: str


def vcycle_health(
    root: Path,
    *,
    nodes: list[trace_model.Node] | None = None,
    edges: list[trace_model.Edge] | None = None,
    validation: dict[str, SrStatus] | None = None,
) -> list[Finding]:
    """Derived-impact probe: missing/inconsistent V-cycle relationships.

    Reuses the trace gap engine, the goal registry and the simulation run
    registry; it never forks a parser. Findings compose:

    * ``REQ_NO_IMPLEMENTATION``  -- ``sr_unsatisfied`` gap (no task satisfies)
    * ``REQ_NO_TEST``            -- ``sr_unvalidated``/``sr_unvalidatable`` gap
    * ``REQ_STALE``              -- ``sr_stale`` gap (evidence predates a change)
    * ``IMPL_NO_REQ``            -- ``task_no_sr`` gap (no traceable requirement)
    * ``GOAL_NO_METRIC``         -- goal declares no metric
    * ``GOAL_NO_EXPERIMENT``     -- goal's metric has no source experiment
    * ``RUN_NO_COMMIT``          -- simulation run manifest records no commit
    * ``FEATURE_FAILING_VERIFICATION`` -- feature's latest run did not pass
    * ``FAILURE_NO_RUN``         -- failure record names no reproduction run
    * ``HYPOTHESIS_NO_OUTCOME``  -- rejected hypothesis carries no evidence ref
    * ``MEMORY_CONFLICT``        -- a memory link contradicts the artifact it
      cites (a ``reproduced_by``/hypothesis-``evidence`` run no manifest
      records); surfaced for the declared failure record the conflict
      anchors on (subject ``fr:<id>``)

    Only pending gaps are reported: a deferred/exempt gap is an explicit
    acceptance, not hidden staleness. Output is deterministic (sorted by
    code then subject).
    """
    if nodes is None:
        nodes = trace_model.load_nodes(root)
    if edges is None:
        edges = trace_model.extract_edges(root, nodes)
    if validation is None:
        validation = load_validation(root)
    gaps = gaps_module.find_gaps(nodes, edges, validation)

    findings: list[Finding] = []
    for gap in gaps:
        if gap.disposition != "pending":
            continue
        if gap.kind == "sr_unsatisfied":
            findings.append(
                Finding("REQ_NO_IMPLEMENTATION", "error", f"sr:{gap.node_id}", gap.detail)
            )
        elif gap.kind in ("sr_unvalidated", "sr_unvalidatable"):
            findings.append(Finding("REQ_NO_TEST", "error", f"sr:{gap.node_id}", gap.detail))
        elif gap.kind == "sr_stale":
            findings.append(Finding("REQ_STALE", "error", f"sr:{gap.node_id}", gap.detail))
        elif gap.kind == "task_no_sr":
            findings.append(
                Finding("IMPL_NO_REQ", "warning", f"task:{gap.node_id}", gap.detail)
            )

    for goal in load_goals(root).values():
        metric = goal.metric
        name = metric.get("name") if isinstance(metric, dict) else metric
        if not name:
            findings.append(
                Finding("GOAL_NO_METRIC", "warning", f"goal:{goal.id}", "goal declares no metric")
            )
        elif not (metric.get("source_experiment") if isinstance(metric, dict) else None):
            findings.append(
                Finding(
                    "GOAL_NO_EXPERIMENT",
                    "warning",
                    f"goal:{goal.id}",
                    "goal metric has no source experiment",
                )
            )

    evidence = _evidence_dir(root)
    for run in sim_registry.load_runs(evidence):
        if not run.commit:
            findings.append(
                Finding(
                    "RUN_NO_COMMIT",
                    "error",
                    f"run:{run.run_id}",
                    "simulation run manifest records no commit",
                )
            )

    for node in nodes:
        if node.kind == "feat":
            latest = sim_registry.latest_run(evidence, node.id)
            if latest is not None and latest.result not in (None, "passed"):
                findings.append(
                    Finding(
                        "FEATURE_FAILING_VERIFICATION",
                        "error",
                        f"feat:{node.id}",
                        f"latest run {latest.run_id} did not pass (result={latest.result})",
                    )
                )

    # Failure-record orphans (Inc 8 Task 4): composed from the existing
    # loader (`load_failures`), never a fork of its parser. A record that
    # names no reproduction run (`reproduced_by` absent/empty) is an orphan
    # the schema deliberately permits but health surfaces; a rejected
    # hypothesis with no evidence/outcome ref (only reachable in a degraded
    # record, since the schema requires the triple) is flagged per
    # hypothesis. Deterministic: iterate by declared id.
    try:
        failures = load_failures(root)
    except DuplicateFailureIdError:
        failures = {}
    for fr_id in sorted(failures):
        rec = failures[fr_id]
        if not (rec.reproduced_by or "").strip():
            findings.append(
                Finding(
                    "FAILURE_NO_RUN",
                    "warning",
                    f"fr:{rec.id}",
                    "failure record names no reproduction run (reproduced_by absent)",
                )
            )
        for index, hypothesis in enumerate(rec.rejected_hypotheses):
            if not isinstance(hypothesis, dict):
                continue
            if not str(hypothesis.get("evidence") or "").strip():
                findings.append(
                    Finding(
                        "HYPOTHESIS_NO_OUTCOME",
                        "warning",
                        f"fr:{rec.id}",
                        f"rejected hypothesis {index + 1} carries no evidence/outcome ref",
                    )
                )

    # MEMORY_CONFLICT: surface the structural conflicts the durable
    # projection already proves (`durable.query_memory(root, "all")` -- a
    # `reproduced_by`/hypothesis-`evidence` run no manifest records), with
    # subject `fr:<id>` per the finding contract. Only conflicts anchored on
    # a declared failure record are surfaced here; ADR supersession
    # conflicts are ADR concerns, not failure-record orphans. Fingerprint
    # conflicts (`query_conflicts` code-changed / commit-unreachable /
    # run-superseded) need a git baseline and are deliberately NOT derived
    # here -- health stays git-free and they remain queryable through
    # `factory memory conflicts`. A repo with duplicate FR ids is a loud
    # load error; health degrades by skipping this finding class rather
    # than inventing findings.
    try:
        conflicts = _durable_query_memory(root, "all")["conflicts"]
    except DuplicateFailureIdError:
        conflicts = []
    for conflict in conflicts:
        memory = conflict.get("memory") or {}
        memory_id = memory.get("id")
        if not isinstance(memory_id, str) or not memory_id.startswith("FR-"):
            continue
        kind = conflict.get("kind", "memory-conflict")
        field = memory.get("field") or ""
        evidence_text = conflict.get("evidence", "")
        detail = f"{kind} ({field}): {evidence_text}" if field else f"{kind}: {evidence_text}"
        findings.append(
            Finding("MEMORY_CONFLICT", "error", f"fr:{memory_id}", detail)
        )

    findings.sort(key=lambda f: (f.code, f.subject))
    return findings


def freshness_health(
    root: Path,
    *,
    nodes: list[trace_model.Node] | None = None,
    edges: list[trace_model.Edge] | None = None,
) -> list[Finding]:
    """Change-impact findings from the freshness engine (Inc 7 Task 5l).

    A pure query -- never executes refresh actions. Composes
    ``factory.freshness.deps.check_artifact`` (per-artifact freshness),
    ``factory.freshness.policy.refresh_decision``/``generators_for``
    (availability boundary) and ``freshness_closure`` (feature coherence):

    * ``IMPL_STALE``        -- implementation affected by a changed upstream
      requirement (semantic invalidation; refresh policy is ROUTE_TO_DEV).
    * ``EVIDENCE_STALE``    -- a run's recorded dependency fingerprints no
      longer match its sources.
    * ``EXPLAINER_STALE``   -- a visual explainer's recorded fingerprints no
      longer match the SRs/code it explains.
    * ``DIAGRAM_STALE``     -- a diagram's recorded fingerprints no longer
      match the content it illustrates.
    * ``MISSING_PROVENANCE``-- freshness cannot be verified (missing recorded
      fingerprint or vanished source); never assumed fresh.
    * ``REFRESH_BLOCKED``   -- the required action (REGENERATE/RERUN) has no
      registered generator/harness: explicitly blocked, never silently fresh.
    * ``REGENERATION_FAILED``-- a generated artifact is stale even though its
      generator is registered (it should have been auto-refreshed).
    * ``CLOSURE_UNRESOLVED``-- a feature's freshness closure is not reached.

    Refresh-loop detection is a runtime reconcile property (bounded attempts,
    policy.reconcile) and is deliberately NOT derived here: a pure query has
    no execution state to observe.
    """
    from factory.freshness import deps as freshness_deps
    from factory.freshness import policy as freshness_policy

    if nodes is None:
        nodes = trace_model.load_nodes(root)
    if edges is None:
        edges = trace_model.extract_edges(root, nodes)
    dep_edges = freshness_deps.collect_dependency_edges(root, nodes=nodes, edges=edges)

    findings: list[Finding] = []

    # IMPL_STALE: code affected by a changed upstream requirement.
    for ref in sorted(freshness_policy.semantically_invalidated_code(root, dep_edges=dep_edges)):
        findings.append(
            Finding(
                "IMPL_STALE",
                "error",
                ref,
                "upstream requirement changed: repair through the DEV workflow (ROUTE_TO_DEV)",
            )
        )

    # Per-artifact freshness over the declared dependency graph.
    refs: set[str] = set()
    for run in sim_registry.load_runs(_evidence_dir(root)):
        refs.add(f"run:{run.run_id}")
    for explainer in _load_explainers(root):
        refs.add(f"explainer:{explainer.id}")
    for node in nodes:
        if node.kind == "diag":
            refs.add(f"diag:{node.id}")

    for ref in sorted(refs):
        state = freshness_deps.check_artifact(root, ref, dep_edges=dep_edges)
        kind = ref.partition(":")[0]
        if state.state.value == "stale":
            if kind == "run":
                findings.append(Finding("EVIDENCE_STALE", "error", ref, "; ".join(state.reasons)))
            elif kind == "explainer":
                findings.append(Finding("EXPLAINER_STALE", "error", ref, "; ".join(state.reasons)))
            elif kind == "diag":
                findings.append(Finding("DIAGRAM_STALE", "error", ref, "; ".join(state.reasons)))
            if kind in ("explainer", "diag") and freshness_policy.generators_for(kind):
                findings.append(
                    Finding(
                        "REGENERATION_FAILED",
                        "warning",
                        ref,
                        "stale despite a registered generator: automatic refresh did not converge",
                    )
                )
        elif state.state.value == "unknown":
            findings.append(
                Finding("MISSING_PROVENANCE", "warning", ref, "; ".join(state.reasons))
            )
        decision = freshness_policy.refresh_decision(root, ref)
        if (
            state.state.value != "fresh"
            and decision.action.value in ("regenerate", "rerun-validation")
            and not freshness_policy.generators_for(kind)
        ):
            findings.append(
                Finding(
                    "REFRESH_BLOCKED",
                    "warning",
                    ref,
                    f"required action {decision.action.value} has no registered generator/harness",
                )
            )

    # CLOSURE_UNRESOLVED per feature.
    for node in nodes:
        if node.kind == "feat":
            closure = freshness_policy.freshness_closure(root, node.id, dep_edges=dep_edges)
            if not closure.closure_reached:
                remaining = ", ".join(f"{r}:{s}" for r, s in sorted(closure.remaining.items()))
                findings.append(
                    Finding(
                        "CLOSURE_UNRESOLVED",
                        "warning",
                        f"feat:{node.id}",
                        f"freshness closure not reached ({remaining})",
                    )
                )

    findings.sort(key=lambda f: (f.code, f.subject))
    return findings


def _load_explainers(root: Path):
    from factory.trace.explainers import load_explainers

    return load_explainers(root)
