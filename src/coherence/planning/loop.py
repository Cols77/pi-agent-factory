"""Host-neutral fresh semantic review and resolution coordinator."""
from __future__ import annotations

import hashlib
import inspect
import json
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Protocol

from coherence.planning.resolution import ResolutionError, append_resolution_event
from coherence.planning.semantic import (
    SemanticReviewError,
    SemanticReviewPacket,
    SemanticReviewReport,
    build_review_packet,
    parse_review_report,
    report_is_fresh,
    write_review_packet,
    write_review_report,
)
from factory.orchestrator.types import AgentRole
from substrate.agents.model import AgentResult


class ReviewBackend(Protocol):
    def run(self, role: AgentRole, prompt: str, **kwargs: Any) -> AgentResult: ...


class LoopStatus(str, Enum):
    CLEAN = "clean"
    ESCALATED = "escalated"


@dataclass(frozen=True)
class FreshReviewResult:
    status: LoopStatus
    iterations: int
    reports: tuple[SemanticReviewReport, ...]
    escalation_prompts: tuple[str, ...]
    error: str | None = None


Fixer = Callable[..., Any]
Gate = Callable[[Path], bool]


class FreshReviewLoop:
    """Run immutable, hash-bound reviewer passes until clean or human-bound."""

    def __init__(
        self,
        *,
        project_root: Path,
        backend: ReviewBackend,
        model: dict[str, Any],
        reviewer_role: AgentRole = AgentRole.PLANNING_ALIGNMENT,
        fixer: Fixer | None = None,
        preflight: Gate | None = None,
        gate: Gate | None = None,
        max_iterations: int = 3,
    ) -> None:
        if max_iterations < 1:
            raise ValueError("max_iterations must be positive")
        self.project_root = project_root
        self.backend = backend
        self.model = dict(model)
        self.reviewer_role = reviewer_role
        self.fixer = fixer
        self.preflight = preflight
        self.gate = gate
        self.max_iterations = max_iterations

    def build_packet(
        self, run_id: str, stage: str, iteration: int, artifact_paths: list[Path],
        context: dict[str, Any], sr_context_digest: str,
    ) -> SemanticReviewPacket:
        return build_review_packet(
            run_id=run_id, stage=stage, iteration=iteration,
            artifact_paths=artifact_paths, project_root=self.project_root,
            context=context, sr_context_digest=sr_context_digest,
            model=self.model, reviewer_role=self.reviewer_role.value,
            reviewer_session_id=None,
        )

    def run(self, packet: SemanticReviewPacket) -> FreshReviewResult:
        reports: list[SemanticReviewReport] = []
        prompts: list[str] = []
        current = packet
        if self.preflight is not None:
            try:
                if not self.preflight(self.project_root):
                    return FreshReviewResult(LoopStatus.ESCALATED, 0, (), (), "preflight failed")
            except Exception as exc:
                return FreshReviewResult(LoopStatus.ESCALATED, 0, (), (), str(exc))
        for iteration in range(packet.iteration, self.max_iterations + 1):
            if not self._packet_current(current):
                return FreshReviewResult(LoopStatus.ESCALATED, len(reports), tuple(reports), tuple(prompts), "stale artifact")
            try:
                write_review_packet(self.project_root, current)
            except SemanticReviewError as exc:
                return FreshReviewResult(LoopStatus.ESCALATED, len(reports), tuple(reports), tuple(prompts), str(exc))
            prompt = self._prompt(current, prompts[-1] if prompts else None)
            try:
                result = self.backend.run(self.reviewer_role, prompt)
                if result.interruption is not None:
                    raise SemanticReviewError(f"reviewer interrupted: {result.interruption.value}")
                raw = result.raw or json.dumps(result.output, ensure_ascii=False)
                if not result.ok or not raw:
                    raise SemanticReviewError("reviewer did not return a valid report")
                report = parse_review_report(raw, packet=current)
                write_review_report(self.project_root, report)
            except (SemanticReviewError, OSError, ValueError, TypeError, StopIteration) as exc:
                return FreshReviewResult(LoopStatus.ESCALATED, len(reports), tuple(reports), tuple(prompts), str(exc))
            reports.append(report)
            if not report_is_fresh(self.project_root, current, report):
                return FreshReviewResult(LoopStatus.ESCALATED, len(reports), tuple(reports), tuple(prompts), "stale review report")
            if report.verdict == "clean":
                if self.gate is not None and not self.gate(self.project_root):
                    return FreshReviewResult(LoopStatus.ESCALATED, len(reports), tuple(reports), tuple(prompts), "deterministic gate failed")
                return FreshReviewResult(LoopStatus.CLEAN, len(reports), tuple(reports), tuple(prompts))
            if report.verdict == "escalate":
                prompts.extend(report.human_prompts or ("Human decision required for semantic review.",))
                return FreshReviewResult(LoopStatus.ESCALATED, len(reports), tuple(reports), tuple(prompts), "reviewer escalation")
            unresolved = [item for item in report.findings if item["disposition"] == "resolve_in_loop"]
            human = [item for item in report.findings if item["disposition"] == "escalate_to_human"]
            if human:
                prompts.extend(report.human_prompts or ("Resolve the semantic findings before continuing.",))
                return FreshReviewResult(LoopStatus.ESCALATED, len(reports), tuple(reports), tuple(prompts), "human escalation")
            if not unresolved:
                if self.gate is not None and not self.gate(self.project_root):
                    return FreshReviewResult(LoopStatus.ESCALATED, len(reports), tuple(reports), tuple(prompts), "deterministic gate failed")
                return FreshReviewResult(LoopStatus.CLEAN, len(reports), tuple(reports), tuple(prompts))
            if self.fixer is None:
                prompts.append("A scoped artifact fix is required.")
                return FreshReviewResult(LoopStatus.ESCALATED, len(reports), tuple(reports), tuple(prompts), "no fixer configured")
            try:
                self._apply_fixes(current, report, unresolved)
            except (OSError, RuntimeError, ResolutionError, ValueError, TypeError) as exc:
                return FreshReviewResult(LoopStatus.ESCALATED, len(reports), tuple(reports), tuple(prompts), str(exc))
            if iteration == self.max_iterations:
                prompts.append("Review budget exhausted; human resolution is required.")
                return FreshReviewResult(LoopStatus.ESCALATED, len(reports), tuple(reports), tuple(prompts), "iteration budget exhausted")
            current = self._fresh_packet(current, iteration + 1)
        return FreshReviewResult(LoopStatus.ESCALATED, len(reports), tuple(reports), tuple(prompts), "iteration budget exhausted")

    def _packet_current(self, packet: SemanticReviewPacket) -> bool:
        for artifact in packet.artifacts:
            path = self.project_root / artifact["path"]
            try:
                if hashlib.sha256(path.read_bytes()).hexdigest() != artifact["sha256"]:
                    return False
            except OSError:
                return False
        return True

    def _prompt(self, packet: SemanticReviewPacket, prior: str | None) -> str:
        payload = json.dumps(packet.to_dict(), sort_keys=True, ensure_ascii=False)
        return "Fresh semantic review. Return only the validated JSON report for this packet.\n" + payload + ("\nPrior escalation: " + prior if prior else "")

    def _apply_fixes(self, packet: SemanticReviewPacket, report: SemanticReviewReport, findings: list[dict[str, Any]]) -> None:
        before = {item["path"]: item["sha256"] for item in packet.artifacts}
        if not self._packet_current(packet):
            raise RuntimeError("artifact changed before scoped fix")
        fixer = self.fixer
        if fixer is None:
            raise RuntimeError("no fixer configured")
        for finding in findings:
            for path_text in before:
                path = self.project_root / path_text
                try:
                    signature = inspect.signature(fixer)
                    if len(signature.parameters) >= 3:
                        fixer(path, finding, report)
                    else:
                        fixer(path, finding)
                except (TypeError, ValueError):
                    fixer(path, finding)
                after = self._hash_paths(before)
                append_resolution_event(
                    self.project_root, run_id=packet.run_id, stage=packet.stage,
                    iteration=packet.iteration, finding_id=finding["id"],
                    disposition=finding["disposition"], actor_kind="planning-agent",
                    prompt=finding["evidence"], answer_or_fix="scoped artifact fix",
                    pre_artifact_hashes=before, post_artifact_hashes=after,
                )
                before = after

    def _hash_paths(self, paths: dict[str, str]) -> dict[str, str]:
        return {name: hashlib.sha256((self.project_root / name).read_bytes()).hexdigest() for name in paths}

    def _fresh_packet(self, packet: SemanticReviewPacket, iteration: int) -> SemanticReviewPacket:
        paths = [self.project_root / item["path"] for item in packet.artifacts]
        return self.build_packet(packet.run_id, packet.stage, iteration, paths, packet.context, packet.sr_context_digest)


def run_fresh_review(
    *, project_root: Path, backend: ReviewBackend, run_id: str, stage: str,
    artifact_paths: list[Path], context: dict[str, Any], sr_context_digest: str,
    model: dict[str, Any], fixer: Fixer | None = None, preflight: Gate | None = None,
    gate: Gate | None = None, max_iterations: int = 3,
) -> FreshReviewResult:
    """Convenience entry point that always starts at a fresh first packet."""
    loop = FreshReviewLoop(
        project_root=project_root, backend=backend, model=model, fixer=fixer,
        preflight=preflight, gate=gate, max_iterations=max_iterations,
    )
    packet = loop.build_packet(run_id, stage, 1, artifact_paths, context, sr_context_digest)
    return loop.run(packet)


__all__ = ["FreshReviewLoop", "FreshReviewResult", "LoopStatus", "ReviewBackend", "run_fresh_review"]
