from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from coherence.trace.model import Edge, JUSTIFICATION_EDGE_KINDS, Node
from coherence.trace.validation_status import SrStatus

GapKind = Literal[
    "task_no_sr",
    "task_no_plan",
    "task_plan_missing",
    "plan_no_spec",
    "artifact_uncovered",
    "dangling_upstream",
    "sr_unsatisfied",
    "sr_proposed",
    "sr_unvalidatable",
    "sr_unvalidated",
    "sr_stale",
    "dangling_reference",
]

Disposition = Literal["pending", "exempt", "deferred"]

_KIND_ORDER: dict[str, int] = {
    "task_no_sr": 0,
    "task_no_plan": 1,
    "plan_no_spec": 2,
    "artifact_uncovered": 3,
    "sr_unsatisfied": 4,
    "sr_proposed": 5,
    "sr_unvalidatable": 6,
    "sr_unvalidated": 7,
    "sr_stale": 8,
    "dangling_upstream": 9,
    "dangling_reference": 10,
    "task_plan_missing": 11,
}


@dataclass(frozen=True)
class Gap:
    node_id: str
    kind: GapKind
    detail: str
    disposition: Disposition = "pending"


def _disposition_of(node: Node) -> tuple[Disposition, str]:
    # SRs are deliberately not exemptable (spec 4.4). Deferral is still allowed --
    # an SR may legitimately need more time -- but it can never be waived outright.
    if node.exempt and node.kind not in ("sr", "br"):
        return "exempt", "declared trace_exempt"
    if node.deferred:
        return "deferred", f"deferred: {node.deferred}"
    return "pending", ""


def find_gaps(
    nodes: list[Node], edges: list[Edge], validation: dict[str, SrStatus]
) -> list[Gap]:
    by_id = {n.id: n for n in nodes}
    gaps: list[Gap] = []

    def add(
        node: Node, kind: GapKind, detail: str, disposition: Disposition | None = None
    ) -> None:
        derived, note = _disposition_of(node)
        gaps.append(
            Gap(node.id, kind, f"{detail} ({note})" if note else detail, disposition or derived)
        )

    out = {n.id: [e for e in edges if e.src == n.id] for n in nodes}
    satisfied_srs = {e.dst for e in edges if e.kind == "satisfies"}
    # SR-057/AC-2: the reverse of plan_no_spec -- a spec/SR/FEAT that no
    # requirement's own relates_to reaches. `upstream` deliberately does NOT
    # count here even for the SR-to-SR case: a requirement's upstream lists
    # ITS OWN prerequisites (a different, "what I depend on" direction) and
    # SR-001/AC-3 already scopes it to requirement-to-requirement only --
    # widening it to also mean "is covered by" would blur that boundary and
    # still say nothing about spec/FEAT coverage, which upstream can never
    # reference at all. relates_to is the one field this SR gives a "this
    # artifact is covered" meaning, so it is the only channel that satisfies
    # this gap. See requirements/SR-057.md's AC-2 addendum for the same
    # reasoning written out in full.
    related_artifacts = {e.dst for e in edges if e.kind == "relates_to"}

    for node in nodes:
        node_edges = out[node.id]
        if node.kind == "task":
            if not any(e.kind in JUSTIFICATION_EDGE_KINDS for e in node_edges):
                add(
                    node,
                    "task_no_sr",
                    "task declares no justification "
                    "(satisfies/corrects/mitigates/implements/maintains/explores)",
                )
            # A task that declares no source_plan at all is just as untraceable as
            # one whose source_plan dangles -- both leave the task->plan slot unfilled.
            if not any(e.kind == "source_plan" for e in node_edges):
                add(node, "task_no_plan", "task declares no source_plan")
            for edge in node_edges:
                if edge.kind == "source_plan" and edge.dst not in by_id:
                    add(node, "task_plan_missing", f"source_plan target missing: {edge.dst}")
        elif node.kind == "plan":
            if not any(e.kind == "spec_ref" for e in node_edges):
                add(node, "plan_no_spec", "plan references no spec")
        elif node.kind == "sr":
            if node.id not in satisfied_srs:
                add(node, "sr_unsatisfied", "no task declares satisfies for this SR")
            if node.proposed:
                # Accepted in substance, measurement undecided. Deferred rather
                # than pending: the human accepted it knowing the binding was
                # open, which is exactly "discussed, still open".
                add(node, "sr_proposed", "binding not yet decided", disposition="deferred")
            else:
                status = validation.get(node.id)
                if status is None or status.state == "never_validated":
                    add(node, "sr_unvalidated", "absent from validation report")
                elif status.state == "error":
                    # Read from the report, never from config: keeping this out of
                    # the trace path is what stops `trace status` importing target
                    # code. Design section 8.1.
                    add(node, "sr_unvalidatable", status.error or "validation could not run")
                elif status.stale:
                    add(node, "sr_stale", "result predates a change to statement or binding")

        if node.kind in ("spec", "sr", "feat") and node.id not in related_artifacts:
            add(
                node,
                "artifact_uncovered",
                f"no requirement's relates_to reaches this {node.kind}",
            )

        for edge in node_edges:
            if edge.kind == "upstream" and edge.dst not in by_id:
                add(node, "dangling_upstream", f"upstream target missing: {edge.dst}")

    vcycle_kinds = {
        "parent_of",
        "verified_by",
        "demonstrates",
        "evaluates",
        "contains",
        "illustrates",
    }
    for edge in edges:
        if edge.kind not in vcycle_kinds:
            continue
        if edge.src not in by_id and edge.dst in by_id:
            add(
                by_id[edge.dst],
                "dangling_reference",
                f"{edge.kind} source missing: {edge.src}",
            )
        elif edge.dst not in by_id and edge.src in by_id:
            add(
                by_id[edge.src],
                "dangling_reference",
                f"{edge.kind} target missing: {edge.dst}",
            )

    gaps.sort(key=lambda g: (_KIND_ORDER[g.kind], g.node_id))
    return gaps
