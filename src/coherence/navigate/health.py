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

from coherence.goals.registry import load_goals
from factory.memory.durable import query_memory as _durable_query_memory
from factory.memory.failure_record import DuplicateFailureIdError, load_failures
from coherence.register import register as register_module
from coherence.simulation import registry as sim_registry
from coherence.navigate import bundles as bundles_module
from coherence.navigate._claims import evidence_dir as _evidence_dir
from coherence.navigate.coverage import build_artifact_lookup, bundle_coverage
from coherence.navigate.ordering import GitRecency, ordered_bundle_ids
from coherence.trace import gaps as gaps_module
from coherence.trace import model as trace_model
from coherence.trace.health import compute_health
from coherence.trace.validation_status import SrStatus, load_validation


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


@dataclass(frozen=True)
class DimensionCount:
    """One row of the eleven-dimension health vector (spec §6, narrowed by
    spec §13 amendment row 2). ``expected``/``satisfied`` are per-dimension
    and independent of the legacy scalar ``health.percent``.
    """

    name: str
    satisfied: int
    expected: int
    exempt: int


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


def _kind_total(kinds, kind: str) -> int:
    return next((k.total for k in kinds if k.kind == kind), 0)


def _class_satisfied(classes, name: str) -> int:
    return next((c.satisfied for c in classes if c.name == name), 0)


def _shape_sentence(requirements: int, features: int, tasks: int, validated: int) -> str:
    """Plain-words statement of what the project is made of.

    A template with recorded counts substituted -- never model prose. It is
    `derived`, and the browser badges it as such, so its provenance is as
    visible as any other claim's. Every count is pluralised on its own value
    -- "1 requirements" would undercut the whole point of the sentence.
    """
    req_noun = "requirement" if requirements == 1 else "requirements"
    if features:
        feature_noun = "feature" if features == 1 else "features"
        feature_part = f"grouped into {features} {feature_noun}"
    else:
        feature_part = "grouped into no features yet"
    task_noun = "task" if tasks == 1 else "tasks"
    task_verb = "implements" if tasks == 1 else "implement"
    pronoun = "it" if requirements == 1 else "them"
    those_requirements = "that requirement" if requirements == 1 else "those requirements"
    validated_verb = "has" if validated == 1 else "have"
    return (
        f"This project is described by {requirements} {req_noun}, {feature_part}. "
        f"{tasks} {task_noun} {task_verb} {pronoun}, and {validated} of "
        f"{those_requirements} {validated_verb} a passing validation."
    )


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

    requirements_total = _kind_total(cov.kinds, "sr")
    tasks_total = _kind_total(cov.kinds, "task")
    validated_total = _class_satisfied(health.classes, "SR validated")
    features_total = len(ordered_rows)

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
        "dimensions": [
            asdict(d)
            for d in compile_health_dimensions(
                root, nodes=nodes, edges=edges, validation=validation, degraded=degraded
            )
        ],
        "shape": {
            "sentence": _shape_sentence(
                requirements_total, features_total, tasks_total, validated_total
            ),
            "parts": {
                "requirements": requirements_total,
                "features": features_total,
                "tasks": tasks_total,
                "validated": validated_total,
            },
        },
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
    from coherence.trace.explainers import load_explainers

    return load_explainers(root)


_DIMENSION_ORDER = (
    "requirement_quality", "decomposition_allocation", "implementation_trace",
    "verification_strategy", "executed_evidence", "validation_scenarios",
    "evidence_freshness", "suspect_relationships", "nonconformance_closure",
    "deferrals_waivers", "human_review",
)

_FRESHNESS_STALE_CODES = ("EVIDENCE_STALE", "EXPLAINER_STALE", "DIAGRAM_STALE")


def _has_resolvable_acceptance(
    root: Path, req: register_module.Requirement | None,
) -> bool:
    """Dimension 1 (requirement_quality): does `req` carry at least one
    acceptance criterion whose verification binding is *resolvable*?

    `manual` is resolvable as-is -- the parser already guarantees a nonblank
    `reason`, and its verification method is a real `human_review` decision.
    `test_marker`/`harness` are resolvable only when `ref` exists on disk,
    resolved relative to `root`. This deliberately does NOT check whether a
    matching `@pytest.mark.sr` decorator actually appears at that path (that
    is a stricter, independent gate compiled elsewhere) and does NOT accept a
    merely well-formed-but-dangling `ref` (that is exactly the false-green
    this dimension exists to stop). `req is None` covers an SR node with no
    matching register entry -- it never satisfies the dimension.
    """
    if req is None:
        return False
    project_root = root.resolve()
    for criterion in req.acceptance:
        binding = criterion.verification
        if binding.kind == "manual":
            return True
        if binding.kind in ("test_marker", "harness") and binding.ref:
            candidate = (project_root / binding.ref).resolve()
            try:
                candidate.relative_to(project_root)
            except ValueError:
                continue
            if binding.kind == "test_marker":
                resolvable = candidate.suffix == ".py" and candidate.is_file()
            else:
                resolvable = candidate.exists()
            if resolvable:
                return True
    return False


def compile_health_dimensions(
    root: Path, *, nodes=None, edges=None, validation=None, degraded: list[str] | None = None,
) -> list[DimensionCount]:
    """Eleven independently-applicable dimensions (spec section 6, narrowed by
    spec section 13 amendment row 2 to match what is actually built): only
    dimensions 4 (verification_strategy), 5 (executed_evidence) and 11
    (human_review) are genuinely obligation-backed. Dimensions 1
    (requirement_quality), 2 (decomposition_allocation), 9
    (nonconformance_closure) and 10 (deferrals_waivers) are direct queries
    over existing recorded state -- register, trace, NC-*, gap data -- not
    obligation-backed; this function does not pretend otherwise. Dimensions 3
    (implementation_trace) and 7 (evidence_freshness) reclassify the existing
    vcycle_health/freshness_health findings -- they are not recomputed here.
    Dimension 8 (suspect_relationships) remains partial after Increment 6
    unless this function concretely consumes coherence.trace.suspect.edge_validity
    with integration tests proving the resulting health count; Increment 6's
    standalone classifier is not sufficient. Until then it reuses REQ_STALE as
    a proxy. Dimension 11 (human_review) correctly
    reports 0/0 until Increment 6 compiles that obligation kind.

    `degraded`, when passed (`query_health` passes its own already-built
    list), receives one message if the human_review computation cannot
    resolve a scope's profile -- it never raises past this function.
    """
    from coherence.policy.compiler import compile_obligations
    from factory.memory.nonconformance import load_nonconformances
    from substrate.policy.vocabulary import UncompiledPresetError

    if nodes is None:
        nodes = trace_model.load_nodes(root)
    if edges is None:
        edges = trace_model.extract_edges(root, nodes)
    if validation is None:
        validation = load_validation(root)
    if degraded is None:
        degraded = []
    vcycle = vcycle_health(root, nodes=nodes, edges=edges, validation=validation)
    fresh = freshness_health(root, nodes=nodes, edges=edges)
    gaps = gaps_module.find_gaps(nodes, edges, validation)

    sr_nodes = [n for n in nodes if n.kind == "sr"]
    feat_nodes = [n for n in nodes if n.kind == "feat"]
    task_nodes = [n for n in nodes if n.kind == "task"]

    # Dimension 1 (requirement_quality): an SR counts only when it carries at
    # least one acceptance criterion with a resolvable verification binding
    # (see `_has_resolvable_acceptance`). Loaded once here, not once per SR --
    # same hoisting discipline `bundle_readiness` already uses above.
    register_by_id = {}
    duplicate_register_ids: set[str] = set()
    for requirement in register_module.load_register(root / "requirements"):
        if requirement.id in register_by_id:
            duplicate_register_ids.add(requirement.id)
        else:
            register_by_id[requirement.id] = requirement
    # Do not select an arbitrary declaration when the register is ambiguous.
    # The SR-node denominator remains unchanged, while every affected SR fails
    # closed for requirement_quality.
    for duplicate_id in duplicate_register_ids:
        register_by_id.pop(duplicate_id, None)
    req_quality_ok = sum(
        1 for n in sr_nodes if _has_resolvable_acceptance(root, register_by_id.get(n.id))
    )
    decomposition_ok = sum(
        1 for f in feat_nodes if any(e.kind == "contains" and e.src == f.id for e in edges)
    )
    impl_no_req = {f.subject for f in vcycle if f.code == "IMPL_NO_REQ"}

    # Dimensions 4/5 share one obligation-derived universe. Only required and
    # blocking verification_result obligations participate; advisory and
    # not_applicable obligations are not denominator slots. The project-scope
    # ci_verification obligation is deliberately excluded: CI proves the
    # project gate, not an individual SR's verification result.
    # Waived obligations are counted only in `exempt`; they are removed before
    # both dimension numerators and the shared denominator are computed.
    verification_candidates = [
        o
        for n in sr_nodes
        for o in compile_obligations(root, f"sr:{n.id}", nodes=nodes, edges=edges)
        if o.kind == "verification_result"
        and o.requiredness in ("required", "blocking")
    ]
    verification_exempt = sum(1 for o in verification_candidates if o.state == "waived")
    verification_obligations = [
        o for o in verification_candidates if o.state != "waived"
    ]
    verification_expected = len(verification_obligations)
    verification_strategy_ok = sum(
        1
        for o in verification_obligations
        if any(command.strip() for command in (o.resolve_cmd or ()))
    )
    executed_evidence_ok = sum(
        1 for o in verification_obligations if o.state == "satisfied"
    )

    # Dimension 6 (validation_scenarios): a genuinely different signal from
    # dimension 5 (executed_evidence, harness pass/fail). Count SRs referenced
    # by at least one goal whose lifecycle has reached a terminal, recorded
    # evaluation (REACHED/NOT_REACHED), via the goal registry already imported
    # at module level (coherence.goals.registry).
    from coherence.goals.lifecycle import TERMINAL_GOAL_STATES

    goals = load_goals(root)
    validated_by_goal: set[str] = set()
    for goal in goals.values():
        if goal.state in TERMINAL_GOAL_STATES:
            validated_by_goal.update(goal.requirements)
    validation_scenarios_ok = sum(1 for n in sr_nodes if n.id in validated_by_goal)

    # Dimension 7 (evidence_freshness): freshness_health's findings are NEVER
    # subject-keyed by a bare SR id (only run:/explainer:/diag:/code:/feat:
    # prefixes) and only ever appear for a NON-fresh artifact -- a fresh
    # artifact has no finding at all. So the universe cannot be read off the
    # finding list alone; it is reconstructed the same way freshness_health
    # builds it internally (runs + explainers + diag nodes), the same three
    # enumerable collections its EVIDENCE_STALE/EXPLAINER_STALE/DIAGRAM_STALE
    # findings are drawn from. IMPL_STALE's subject is a code: ref from a
    # separate, non-enumerable domain (semantically-invalidated code, derived
    # per-SR-change, not a fixed count of trackable artifacts) -- it is
    # tracked by dimension 3 (implementation_trace)/vcycle instead and
    # deliberately excluded from this dimension's denominator, narrowing the
    # four staleness codes to the three whose universe is actually countable.
    freshness_universe: set[str] = set()
    for run in sim_registry.load_runs(_evidence_dir(root)):
        freshness_universe.add(f"run:{run.run_id}")
    for explainer in _load_explainers(root):
        freshness_universe.add(f"explainer:{explainer.id}")
    for node in nodes:
        if node.kind == "diag":
            freshness_universe.add(f"diag:{node.id}")
    freshness_stale = {
        f.subject for f in fresh if f.code in _FRESHNESS_STALE_CODES
    } & freshness_universe
    evidence_freshness_ok = len(freshness_universe) - len(freshness_stale)

    suspect_proxy = {f.subject for f in vcycle if f.code == "REQ_STALE"}
    try:
        nonconformances = load_nonconformances(root)
    except Exception:
        nonconformances = {}
    nc_closed = sum(1 for r in nonconformances.values() if r.status in ("corrected", "waived"))
    # `waived` is the canonical state wording. Raw `deferred`/`exempt` gap
    # dispositions are counted as waiver evidence; no source or authority is selected here.
    waived_gaps = sum(1 for g in gaps if g.disposition in ("deferred", "exempt"))

    # Dimension 11 (human_review): obligation-backed. Reuse the already-loaded
    # nodes/edges via compile_obligations'/resolve_profile's nodes=/edges=
    # passthrough (Increment 2B) so this loop never reloads the trace graph
    # per SR -- required to keep query_health's existing "load_nodes called
    # once" contract (tests/unit/system/test_health.py). SR-059/AC-1: the
    # compiler no longer emits `not_applicable` for this obligation kind
    # under any profile (a bare-floor `required` under everything but
    # high_assurance, which stays `blocking`), so every sr: scope now
    # participates in this dimension's denominator, not only high_assurance
    # ones -- the `("required", "blocking")` filter below is unchanged code,
    # but its effective set widened the moment the compiler did. A repo whose
    # profile cannot yet be compiled (UncompiledPresetError, e.g. an
    # exploration/product-profiled scope) degrades this dimension to 0/0
    # instead of crashing the whole health page.
    human_review_obligations: list = []
    try:
        human_review_obligations = [
            o
            for n in sr_nodes
            for o in compile_obligations(root, f"sr:{n.id}", nodes=nodes, edges=edges)
            if o.kind == "human_review"
        ]
    except UncompiledPresetError as exc:
        degraded.append(f"human_review dimension unresolved: {exc}")
    human_review_obligations = [
        o for o in human_review_obligations if o.requiredness in ("required", "blocking")
    ]
    human_review_exempt = sum(1 for o in human_review_obligations if o.state == "waived")
    human_review_obligations = [o for o in human_review_obligations if o.state != "waived"]

    return [
        DimensionCount("requirement_quality", req_quality_ok, len(sr_nodes), 0),
        DimensionCount("decomposition_allocation", decomposition_ok, len(feat_nodes), 0),
        DimensionCount(
            "implementation_trace", len(task_nodes) - len(impl_no_req), len(task_nodes), 0
        ),
        DimensionCount(
            "verification_strategy", verification_strategy_ok, verification_expected, verification_exempt
        ),
        DimensionCount(
            "executed_evidence", executed_evidence_ok, verification_expected, verification_exempt
        ),
        DimensionCount("validation_scenarios", validation_scenarios_ok, len(sr_nodes), 0),
        DimensionCount("evidence_freshness", evidence_freshness_ok, len(freshness_universe), 0),
        DimensionCount(
            "suspect_relationships", len(sr_nodes) - len(suspect_proxy), len(sr_nodes), 0
        ),
        DimensionCount("nonconformance_closure", nc_closed, len(nonconformances), 0),
        DimensionCount("deferrals_waivers", waived_gaps, len(gaps), 0),
        DimensionCount(
            "human_review",
            sum(1 for o in human_review_obligations if o.state == "satisfied"),
            len(human_review_obligations),
            human_review_exempt,
        ),
    ]
