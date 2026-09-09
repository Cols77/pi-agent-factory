"""Read-only cross-artifact trace review for generated planning tasks.

The planning task writer has no canonical ``affected_srs`` parser or artifact
classifier yet.  This module therefore takes those facts as typed input from
the producer that owns them; it does not infer them from task markdown.  The
only repository records it reads are requirement frontmatter and the existing
structured-relation resolver.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import frontmatter

from coherence.planning.model import PlanningFinding
from coherence.register.register import Requirement
from coherence.register.relations import ReferenceIssue, resolve_sr_relations
from substrate.codemap.build import build_index
from substrate.codemap.model import CodeIndex


@dataclass(frozen=True)
class GeneratedTaskReviewInput:
    """One generated task's already-classified trace facts.

    ``changes_production`` and ``changes_validation`` intentionally come from
    the task producer.  Path prefixes are not a stable artifact taxonomy, so
    this reviewer must not guess that (for example) a ``docs/`` path is a
    source artifact.  ``satisfies`` is optional because it is only supplied
    when the existing ledger task parser produced that legacy task mirror.
    """

    id: str
    artifact_paths: tuple[str, ...]
    changes_production: bool
    changes_validation: bool
    affected_srs: tuple[str, ...] | None
    satisfies: tuple[str, ...] | None = None

    @property
    def needs_sr_declaration(self) -> bool:
        return self.changes_production or self.changes_validation


@dataclass(frozen=True)
class CrossArtifactReview:
    """Stable deterministic findings for one set of generated tasks."""

    findings: tuple[PlanningFinding, ...]

    @property
    def ok(self) -> bool:
        return not any(finding.severity == "error" for finding in self.findings)

    def to_dict(self) -> dict[str, object]:
        return {"ok": self.ok, "findings": [finding.to_dict() for finding in self.findings]}


def _finding(code: str, subject: str, detail: str) -> PlanningFinding:
    return PlanningFinding(code=code, severity="error", subject=subject, detail=detail)


def _structured_entries(meta: dict, field: str) -> tuple[dict, ...]:
    raw = meta.get(field)
    if not isinstance(raw, list):
        return ()
    return tuple(entry for entry in raw if isinstance(entry, dict))


def _relation_paths(meta: dict) -> set[str]:
    paths: set[str] = set()
    for field in ("implemented_by", "verified_by"):
        for entry in _structured_entries(meta, field):
            path = entry.get("path")
            if isinstance(path, str) and path.strip():
                paths.add(path.strip())
    return paths


def _issue_code(issue: ReferenceIssue) -> str:
    if "duplicates an earlier declaration" in issue.detail:
        return "RELATION_DUPLICATE"
    # The source resolver owns exact schema/path/symbol semantics.  A
    # planning task can only state whether its intended trace target resolves,
    # so every non-duplicate resolver failure is one stable dangling class.
    return "RELATION_DANGLING"


def _metadata(req: Requirement) -> dict:
    """Use the register's canonical frontmatter shape; never parse task text."""
    return dict(frontmatter.load(str(req.path)).metadata)


def _read_only_index(root: Path, requirements: tuple[Requirement, ...]) -> CodeIndex:
    """Build only the declared, existing relation files without a cache write."""
    files: set[str] = set()
    for req in requirements:
        for path in _relation_paths(_metadata(req)):
            candidate = Path(path)
            if candidate.is_absolute() or ".." in candidate.parts:
                continue
            if (root / candidate).is_file():
                files.add(candidate.as_posix())
    return build_index(root, files=sorted(files))


def _review_requirement(
    root: Path,
    task: GeneratedTaskReviewInput,
    req: Requirement,
    index: CodeIndex,
) -> list[PlanningFinding]:
    meta = _metadata(req)
    findings: list[PlanningFinding] = []
    implementation = _structured_entries(meta, "implemented_by")
    validation = _structured_entries(meta, "verified_by")
    if not implementation:
        findings.append(
            _finding(
                "RELATION_MISSING",
                req.id,
                f"{req.id}: task {task.id} affects production or validation artifacts but has no structured implemented_by relation",
            )
        )
    if not validation:
        findings.append(
            _finding(
                "RELATION_MISSING",
                req.id,
                f"{req.id}: task {task.id} affects production or validation artifacts but has no structured verified_by relation",
            )
        )
        # A source-only relation is mechanically weaker than a source plus
        # validation relation.  This reports coverage, not whether either
        # artifact semantically proves the requirement.
        if implementation:
            findings.append(
                _finding(
                    "RELATION_WEAK",
                    req.id,
                    f"{req.id}: task {task.id} has implementation relation coverage without validation relation coverage",
                )
            )
    for issue in resolve_sr_relations(root, meta, index=index).issues:
        findings.append(_finding(_issue_code(issue), req.id, f"{req.id}: {issue.detail}"))

    relation_paths = _relation_paths(meta)
    if task.artifact_paths and relation_paths.isdisjoint(task.artifact_paths):
        findings.append(
            _finding(
                "RELATION_OVERSTATED",
                req.id,
                f"{req.id}: task {task.id} declares the requirement affected but none of its artifacts are canonically related",
            )
        )
    return findings


def review_cross_artifact_relations(
    root: Path,
    requirements: list[Requirement] | tuple[Requirement, ...],
    tasks: list[GeneratedTaskReviewInput] | tuple[GeneratedTaskReviewInput, ...],
) -> CrossArtifactReview:
    """Review explicit task impact declarations against canonical SR relations.

    This is deliberately read-only and deterministic.  It does not persist
    evidence or call a semantic reviewer, so it cannot accept consent or
    otherwise make a semantic decision.  Callers can use ``report.ok`` as a
    deterministic preflight before their reviewer callback.
    """
    root = root.resolve()
    by_id = {req.id: req for req in requirements}
    index = _read_only_index(root, tuple(by_id.values()))
    findings: list[PlanningFinding] = []
    for task in sorted(tasks, key=lambda item: item.id):
        if not task.needs_sr_declaration:
            continue
        if task.affected_srs is None:
            findings.append(
                _finding(
                    "TASK_SR_DECLARATION_MISSING",
                    task.id,
                    f"{task.id}: task changes production or validation artifacts and must declare affected_srs",
                )
            )
            continue
        if not task.affected_srs or tuple(sorted(set(task.affected_srs))) != task.affected_srs:
            findings.append(
                _finding(
                    "TASK_SR_DECLARATION_INVALID",
                    task.id,
                    f"{task.id}: affected_srs must be nonempty, unique, and sorted",
                )
            )
        declared = tuple(sorted(set(task.affected_srs)))
        if task.satisfies is not None and set(task.satisfies) != set(declared):
            findings.append(
                _finding(
                    "RELATION_CONTRADICTORY",
                    task.id,
                    f"{task.id}: affected_srs and the parsed satisfies mirror name different SR ids",
                )
            )
        for sr_id in declared:
            req = by_id.get(sr_id)
            if req is None:
                findings.append(
                    _finding(
                        "RELATION_DANGLING",
                        task.id,
                        f"{task.id}: affected_srs declares unknown requirement {sr_id}",
                    )
                )
                continue
            findings.extend(_review_requirement(root, task, req, index))
    findings.sort(key=lambda finding: (finding.code, finding.subject, finding.detail))
    return CrossArtifactReview(tuple(findings))


__all__ = ["CrossArtifactReview", "GeneratedTaskReviewInput", "review_cross_artifact_relations"]
