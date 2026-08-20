# src/factory/coverage/scope.py
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from factory.evidence.manifests import list_run_manifests
from factory.evidence.records import list_historical_records
from factory.requirements.register import is_checksum_current, load_register
from factory.trace.graph import build_graph


class EvidenceState(str, Enum):
    missing = "missing"
    empty = "empty"
    present = "present"


@dataclass(frozen=True)
class TaskScope:
    task_id: str
    changed_files: tuple[str, ...]
    manifests: tuple[str, ...]
    evidence_state: EvidenceState
    record_paths: tuple[str, ...]


@dataclass(frozen=True)
class SrScope:
    sr_id: str
    statement: str
    binding: dict | None
    checksum_state: str  # "current" | "stale" | "proposed"
    tasks: tuple[TaskScope, ...]
    measurement: dict | None
    deferred: bool
    domain: str


@dataclass(frozen=True)
class FeatureScope:
    feature_id: str
    declared: tuple[str, ...]
    contains: tuple[str, ...]
    linked: tuple[str, ...]
    register: tuple[str, ...]
    srs: dict[str, SrScope]
    completeness: tuple[dict, ...]
    tasks: dict[str, TaskScope]


def _latest_validation(manifests: list[dict], sr_id: str) -> dict | None:
    """Newest manifest (already newest-first) that measures this SR."""
    for manifest in manifests:
        results = [
            entry
            for validation in manifest.get("validation") or []
            if isinstance(validation, dict)
            for entry in validation.get("requirements", [])
            if isinstance(entry, dict) and entry.get("id") == sr_id and "passed" in entry
        ]
        if results:
            return results[0]
    return None


def _changed_files_from_manifest(manifest: dict) -> tuple[str, ...]:
    impl = manifest.get("implementation", {})
    if isinstance(impl, dict):
        raw = impl.get("changed_files", [])
        if isinstance(raw, list):
            return tuple(str(f) for f in raw)
    return ()


def _find_manifests_for_sr(manifests: list[dict], sr_id: str) -> list[dict]:
    out: list[dict] = []
    for m in manifests:
        for v in m.get("validation") or []:
            if isinstance(v, dict):
                for req_entry in v.get("requirements", []):
                    if isinstance(req_entry, dict) and req_entry.get("id") == sr_id:
                        out.append(m)
                        break
    return out


def _binding_dict(req: object) -> dict | None:
    from factory.requirements.register import Requirement

    if not isinstance(req, Requirement) or req.binding is None:
        return None
    b = req.binding
    return {
        "harness": b.harness,
        "experiment": b.experiment,
        "metric": b.metric,
        "assert_expr": b.assert_expr,
        "trials": b.trials,
    }


def _checksum_state(req: object) -> str:
    """Return 'current', 'stale', or 'proposed'."""
    from factory.requirements.register import Requirement

    if not isinstance(req, Requirement):
        return "proposed"
    if req.binding is None:
        return "proposed"
    return "current" if is_checksum_current(req) else "stale"


def _is_deferred(sr_path: Path) -> bool:
    import frontmatter

    try:
        post = frontmatter.load(str(sr_path))
        return bool(post.metadata.get("trace_deferred"))
    except Exception:
        return False


def resolve_feature_scope(root: Path, feat: str) -> FeatureScope:
    """Phase 0: resolve a feature's declared SRs, tasks, and changed files.

    The feat id is e.g. FEAT-001. The corresponding file is
    docs/features/FEAT-001.md. Missing nodes degrade to an empty scope rather
    than crashing.
    """
    if feat.startswith("feat:"):
        feat = feat.split(":", 1)[1]
    graph = build_graph(root)
    by_id = {n.id: n for n in graph.nodes}

    feat_node = by_id.get(feat)
    if feat_node is None:
        return FeatureScope(
            feature_id=feat,
            declared=(),
            contains=(),
            linked=(),
            register=(),
            srs={},
            completeness=(),
            tasks={},
        )

    # contains edges from feat → SRs (from the feat frontmatter requirements:)
    contains = tuple(
        sorted(e.dst for e in graph.edges if e.src == feat and e.kind == "contains")
    )
    declared = contains

    reqs = load_register(root / "requirements")
    req_by_id = {r.id: r for r in reqs}

    # Per-SR: tasks with a satisfies edge into a declared SR
    sr_to_tasks: dict[str, list[TaskScope]] = {}
    tasks_by_id: dict[str, TaskScope] = {}
    for edge in graph.edges:
        if edge.kind != "satisfies":
            continue
        sr_id = edge.dst
        if sr_id not in declared:
            continue
        task_id = edge.src
        if task_id not in tasks_by_id:
            manifests = list_run_manifests(root / "evidence", task_id=task_id)
            records = list_historical_records(root, root / "evidence", task_id=task_id)
            changed: set[str] = set()
            for m in manifests:
                changed.update(_changed_files_from_manifest(m))
            for record in records:
                changed.update(str(file) for file in record["changed_files"])
            evidence_state = (
                EvidenceState.missing
                if not manifests and not records
                else EvidenceState.present
                if changed
                else EvidenceState.empty
            )
            tasks_by_id[task_id] = TaskScope(
                task_id=task_id,
                changed_files=tuple(sorted(changed)),
                manifests=tuple(str(m.get("run_id", "?")) for m in manifests),
                evidence_state=evidence_state,
                record_paths=tuple(
                    sorted(
                        (Path("evidence") / "records" / f"{record['record_id']}.json").as_posix()
                        for record in records
                    )
                ),
            )
        sr_to_tasks.setdefault(sr_id, []).append(tasks_by_id[task_id])

    linked = tuple(sorted(sr_to_tasks.keys()))
    register_ids = tuple(sorted(req_by_id.keys()))

    all_manifests = list_run_manifests(root / "evidence", task_id=None)

    srs: dict[str, SrScope] = {}
    for sr_id in declared:
        req = req_by_id.get(sr_id)
        sr_path = root / "requirements" / f"{sr_id}.md"
        deferred = _is_deferred(sr_path) if sr_path.exists() else False
        sr_manifests = _find_manifests_for_sr(all_manifests, sr_id)
        srs[sr_id] = SrScope(
            sr_id=sr_id,
            statement=req.statement if req else "(not in register)",
            binding=_binding_dict(req),
            checksum_state=_checksum_state(req),
            tasks=tuple(sr_to_tasks.get(sr_id, [])),
            measurement=_latest_validation(sr_manifests, sr_id),
            deferred=deferred,
            domain=req.domain if req else "unknown",
        )

    # Completeness findings
    completeness: list[dict] = []
    for sr_id in declared:
        if sr_id not in req_by_id:
            completeness.append({"kind": "declared_not_in_register", "sr_id": sr_id})
        elif sr_id not in linked:
            completeness.append({"kind": "declared_not_linked", "sr_id": sr_id})

    # task_satisfies_undeclared: a task linked to a declared SR also satisfies
    # an undeclared SR.
    for edge in graph.edges:
        if edge.kind != "satisfies":
            continue
        if edge.dst in declared:
            continue
        if edge.src in tasks_by_id:
            completeness.append(
                {
                    "kind": "task_satisfies_undeclared",
                    "sr_id": edge.dst,
                    "task_id": edge.src,
                }
            )

    return FeatureScope(
        feature_id=feat,
        declared=declared,
        contains=contains,
        linked=linked,
        register=register_ids,
        srs=srs,
        completeness=tuple(completeness),
        tasks=tasks_by_id,
    )
