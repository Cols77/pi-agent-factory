"""Host-neutral coordinator for FEAT-017's three semantic review passes."""
from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from coherence.planning.semantic import (
    SemanticReviewPacket,
    SemanticReviewReport,
    build_review_packet,
    report_is_fresh,
    write_review_packet,
    write_review_report,
)


class WorkflowStage(str, Enum):
    SPEC_ALIGNMENT = "spec_alignment"
    PLAN_TASK_ALIGNMENT = "plan_task_alignment"
    DERIVATION_ALIGNMENT = "derivation_alignment"


@dataclass
class StageStatus:
    stage: WorkflowStage
    status: str = "pending"
    packet_sha256: str | None = None
    report_sha256: str | None = None
    artifact_hashes: dict[str, str] = field(default_factory=dict)
    detail: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "stage": self.stage.value,
            "status": self.status,
            "packet_sha256": self.packet_sha256,
            "report_sha256": self.report_sha256,
            "artifact_hashes": dict(sorted(self.artifact_hashes.items())),
            "detail": self.detail,
        }


@dataclass(frozen=True)
class WorkflowStatus:
    run_id: str
    ok: bool
    blocked: bool
    reason: str | None
    stages: tuple[StageStatus, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": 1,
            "run_id": self.run_id,
            "ok": self.ok,
            "blocked": self.blocked,
            "reason": self.reason,
            "stages": [stage.to_dict() for stage in self.stages],
        }


Reviewer = Callable[[SemanticReviewPacket], SemanticReviewReport]


class PlanningWorkflow:
    """Compose deterministic planning checks and semantic evidence.

    This object never writes source artifacts, consent, approval, or execution
    records. The reviewer callback is the sole semantic judgment boundary.
    """

    def __init__(
        self,
        project_root: Path,
        run_id: str,
        *,
        reviewer_model: dict[str, Any],
        reviewer: Reviewer,
        reviewer_role: str = "planning_semantic_reviewer",
        reviewer_session_id: str | None = None,
        deterministic_gate: Callable[[Path], bool] | None = None,
    ) -> None:
        self.project_root = project_root.resolve()
        self.run_id = run_id
        self.reviewer_model = dict(reviewer_model)
        self.reviewer = reviewer
        self.reviewer_role = reviewer_role
        self.reviewer_session_id = reviewer_session_id
        self.deterministic_gate = deterministic_gate
        self._stages = {stage: StageStatus(stage) for stage in WorkflowStage}
        self._reports: dict[WorkflowStage, SemanticReviewReport] = {}
        self._accepted_warnings: set[str] = set()
        self._blocked_reason: str | None = None

    def _hashes(self, paths: list[Path] | tuple[Path, ...]) -> dict[str, str]:
        result: dict[str, str] = {}
        for path in paths:
            resolved = path.resolve()
            relative = resolved.relative_to(self.project_root).as_posix()
            result[relative] = hashlib.sha256(resolved.read_bytes()).hexdigest()
        return dict(sorted(result.items()))

    def _invalidate_changed(self) -> None:
        for index, stage in enumerate(WorkflowStage):
            record = self._stages[stage]
            if record.status not in {"clean", "blocked"}:
                continue
            try:
                current = self._hashes(tuple(self.project_root / path for path in record.artifact_hashes))
            except (OSError, ValueError):
                current = {}
            if current != record.artifact_hashes:
                for downstream in tuple(WorkflowStage)[index:]:
                    self._stages[downstream].status = "invalidated"
                    self._stages[downstream].detail = "artifact changed; fresh review required"
                    self._reports.pop(downstream, None)

    def accept_warning(self, finding_id: str) -> None:
        self._accepted_warnings.add(finding_id)

    def run_stage(
        self,
        stage: WorkflowStage | str,
        artifact_paths: list[Path] | tuple[Path, ...],
        *,
        context: dict[str, Any],
        sr_context: Mapping[str, Any],
        iteration: int = 1,
    ) -> SemanticReviewReport | None:
        stage = WorkflowStage(stage)
        self._blocked_reason = None
        self._invalidate_changed()
        index = tuple(WorkflowStage).index(stage)
        for prior in tuple(WorkflowStage)[:index]:
            if self._stages[prior].status != "clean":
                self._blocked_reason = "prior_stage_required"
                return None
        unresolved = context.get("unresolved_questions", context.get("open_questions", ()))
        if unresolved:
            self._stages[stage].status = "blocked"
            self._stages[stage].detail = "unresolved questions require human input"
            self._blocked_reason = "unresolved_questions"
            return None
        if self.deterministic_gate is not None:
            try:
                if not self.deterministic_gate(self.project_root):
                    self._stages[stage].status = "blocked"
                    self._stages[stage].detail = "deterministic preflight failed"
                    self._blocked_reason = "deterministic_gate_failed"
                    return None
            except Exception as exc:
                self._stages[stage].status = "blocked"
                self._stages[stage].detail = str(exc)
                self._blocked_reason = "deterministic_gate_failed"
                return None
        effective_iteration = iteration + index
        try:
            hashes = self._hashes(artifact_paths)
            digest = hashlib.sha256(
                json.dumps(sr_context, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
            ).hexdigest()
            packet = build_review_packet(
                run_id=self.run_id, stage=stage.value, iteration=effective_iteration,
                artifact_paths=artifact_paths, project_root=self.project_root,
                context={**context, "sr_context": dict(sr_context)}, sr_context_digest=digest, model=self.reviewer_model,
                reviewer_role=self.reviewer_role, reviewer_session_id=self.reviewer_session_id,
            )
            write_review_packet(self.project_root, packet)
            report = self.reviewer(packet)
            if not isinstance(report, SemanticReviewReport) or (
                report.run_id != packet.run_id
                or report.stage != packet.stage
                or report.iteration != packet.iteration
                or report.packet_sha256 != packet.sha256
                or report.artifacts != packet.artifacts
                or report.context != packet.context
                or report.sr_context_digest != packet.sr_context_digest
                or report.model != packet.model
            ):
                raise ValueError("reviewer returned a stale or invalid report")
            write_review_report(self.project_root, report)
            if not report_is_fresh(self.project_root, packet, report):
                raise ValueError("reviewer report is not fresh against current artifacts")
        except (OSError, ValueError, TypeError, RuntimeError) as exc:
            self._stages[stage].status = "blocked"
            self._stages[stage].detail = str(exc)
            self._blocked_reason = "semantic_review_invalid"
            return None
        self._stages[stage].packet_sha256 = packet.sha256
        self._stages[stage].report_sha256 = hashlib.sha256(
            json.dumps(report.to_dict(), sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
        ).hexdigest()
        self._stages[stage].artifact_hashes = hashes
        blocking = [
            item for item in report.findings
            if item.get("disposition") == "escalate_to_human"
            or (item.get("disposition") == "resolve_in_loop" and item.get("id") not in self._accepted_warnings)
        ]
        if report.verdict == "escalate" or blocking:
            self._stages[stage].status = "blocked"
            self._stages[stage].detail = "semantic review requires human resolution"
            self._blocked_reason = "semantic_review_escalation"
        else:
            if self.deterministic_gate is not None:
                try:
                    if not self.deterministic_gate(self.project_root):
                        self._stages[stage].status = "blocked"
                        self._stages[stage].detail = "deterministic postflight failed"
                        self._blocked_reason = "deterministic_gate_failed"
                        return report
                except Exception as exc:
                    self._stages[stage].status = "blocked"
                    self._stages[stage].detail = str(exc)
                    self._blocked_reason = "deterministic_gate_failed"
                    return report
            self._stages[stage].status = "clean"
            self._stages[stage].detail = "informational semantic notes do not block"
            self._reports[stage] = report
        return report

    def status(self) -> WorkflowStatus:
        self._invalidate_changed()
        blocked = self._blocked_reason is not None or any(s.status == "blocked" for s in self._stages.values())
        complete = all(s.status == "clean" for s in self._stages.values())
        return WorkflowStatus(self.run_id, complete and not blocked, blocked, self._blocked_reason, tuple(self._stages.values()))


__all__ = ["PlanningWorkflow", "StageStatus", "WorkflowStage", "WorkflowStatus"]
