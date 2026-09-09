"""Hash-bound, host-neutral planning summaries and downstream handoffs."""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Mapping

from coherence.planning.model import PlanningReport
from coherence.planning.gates import (
    PlanningGateError,
    compile_planning_gate_pack,
    validate_planning_gate_result,
)
from coherence.planning.paths import safe_resolve, safe_root

WORKFLOWS = (
    {"id": "standard-development", "label": "Standard governed development"},
    {"id": "health-recovery", "label": "Health recovery"},
    {"id": "feature-planning", "label": "Another feature-planning workflow"},
)


class HandoffError(ValueError):
    """The handoff is malformed, stale, or unsafe to use."""


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _safe_run_dir(root: Path, run_id: str) -> Path:
    if (
        not isinstance(run_id, str)
        or not run_id
        or run_id != run_id.strip()
        or run_id in {".", ".."}
        or "/" in run_id
        or "\\" in run_id
        or any(ord(char) < 32 or ord(char) == 127 for char in run_id)
    ):
        raise HandoffError("invalid run_id")
    safe = safe_root(root)
    if safe is None:
        raise HandoffError("project root is unsafe")
    run_dir = safe_resolve(safe, safe / ".factory" / "planning" / run_id)
    if run_dir is None:
        raise HandoffError("handoff directory is unsafe")
    return run_dir


def build_downstream_menu(selected: str | None = None) -> list[dict[str, object]]:
    """Return the stable legal choices; choosing one never launches anything."""
    if selected is not None and selected not in {item["id"] for item in WORKFLOWS}:
        raise HandoffError("unknown downstream workflow")
    return [
        {**item, "selected": item["id"] == selected, "starts_automatically": False}
        for item in WORKFLOWS
    ]


def _artifact_hashes(root: Path, report: PlanningReport) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    for item in report.artifacts:
        path, digest = item.get("path"), item.get("sha256")
        if not isinstance(path, str) or not isinstance(digest, str):
            raise HandoffError("invalid canonical artifact")
        source = safe_resolve(root, root / Path(path))
        if source is None or not source.is_file() or _sha(source.read_bytes()) != digest:
            raise HandoffError("canonical artifact is missing or changed")
        result.append({"path": path, "sha256": digest})
    return result


def _semantic_hashes(root: Path, run_id: str) -> dict[str, str]:
    run_dir = _safe_run_dir(root, run_id)
    result: dict[str, str] = {}
    for path in sorted(run_dir.glob("semantic-review-report*.json")):
        if path.is_file():
            result[path.stem] = _sha(path.read_bytes())
    return result


def _resolution_digest(root: Path, run_id: str) -> str:
    path = _safe_run_dir(root, run_id) / "resolution-events.jsonl"
    return _sha(path.read_bytes()) if path.is_file() else _sha(b"")


def build_handoff(
    root: Path,
    report: PlanningReport,
    *,
    workflow: str = "standard-development",
    gate_summary: Mapping[str, object] | None = None,
    semantic_report_hashes: Mapping[str, str] | None = None,
    model_metadata: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Build a deterministic handoff without invoking a downstream process."""
    if not isinstance(report, PlanningReport) or not report.ok:
        raise HandoffError("only a clean planning report can be handed off")
    build_downstream_menu(workflow)
    safe = safe_root(root)
    if safe is None:
        raise HandoffError("project root is unsafe")
    # ``gate_summary`` was an unauthenticated display field and historically
    # defaulted to pass.  Retaining it would create a second, bypassable gate
    # authority, so compatibility is deliberately fail-closed.
    if gate_summary is not None:
        raise HandoffError("legacy gate_summary cannot authorize a handoff")
    try:
        gate_pack = compile_planning_gate_pack("FEAT-017", "v1")
        gate_result = validate_planning_gate_result(safe, report.run_id, gate_pack)
    except PlanningGateError as exc:
        raise HandoffError("current validated planning gate result is required") from exc
    artifacts = _artifact_hashes(safe, report)
    stored_report = safe_resolve(safe, safe / ".factory" / "planning" / report.run_id / "report.json")
    try:
        if stored_report is None or json.loads(stored_report.read_text(encoding="utf-8")) != report.to_dict():
            raise HandoffError("handoff report does not match current gate evidence")
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise HandoffError("handoff report evidence is unreadable") from exc
    semantic = dict(semantic_report_hashes) if semantic_report_hashes is not None else _semantic_hashes(safe, report.run_id)
    if any(not isinstance(key, str) or not isinstance(value, str) or len(value) != 64 for key, value in semantic.items()):
        raise HandoffError("invalid semantic report hash")
    model = dict(model_metadata or {})
    forbidden = {"api_key", "secret", "password", "token", "credential"}
    if any(any(word in str(key).lower() for word in forbidden) for key in model):
        raise HandoffError("secret-shaped model metadata rejected")
    semantic_notes = tuple(
        finding.detail for finding in report.findings if finding.severity == "warning"
    )
    unresolved = tuple(
        str(action.get("detail", ""))
        for action in report.next_actions
        if isinstance(action, dict) and action.get("detail")
    )
    summary = render_summary(
        report,
        semantic_notes=semantic_notes,
        unresolved=unresolved,
        gate_summary={
            "status": "pass",
            "planning_gate_pack_sha256": gate_pack["sha256"],
            "planning_gate_result_sha256": gate_result["result_sha256"],
        },
    )
    return {
        "schema": 1,
        "run_id": report.run_id,
        "selected_workflow": workflow,
        "menu": build_downstream_menu(workflow),
        "canonical_artifacts": artifacts,
        "semantic_report_hashes": semantic,
        "resolution_journal_sha256": _resolution_digest(safe, report.run_id),
        "model_metadata": model,
        "planning_gate_pack_sha256": gate_pack["sha256"],
        "planning_gate_result_sha256": gate_result["result_sha256"],
        "gate_summary": {
            "status": "pass",
            "planning_gate_pack_sha256": gate_pack["sha256"],
            "planning_gate_result_sha256": gate_result["result_sha256"],
        },
        "summary": summary,
        "starts_automatically": False,
        "creation": {"source": "coherence-planning", "report_run_id": report.run_id},
    }


def render_summary(
    report: PlanningReport,
    *,
    semantic_notes: tuple[str, ...] = (),
    unresolved: tuple[str, ...] = (),
    gate_summary: Mapping[str, object] | None = None,
) -> str:
    """Render a concise text result suitable for a terminal or new session."""
    lines = [f"Planning run: {report.run_id}", f"Status: {'clean' if report.ok else 'blocked'}"]
    lines.append("Semantic notes: " + ("; ".join(semantic_notes) if semantic_notes else "none"))
    lines.append("Unresolved: " + ("; ".join(unresolved) if unresolved else "none"))
    lines.append("Artifacts: " + ", ".join(f"{x['path']} ({x['sha256']})" for x in report.artifacts))
    lines.append("Gates: " + json.dumps(dict(gate_summary or {}), sort_keys=True))
    lines.append("Downstream choices: standard-development, health-recovery, feature-planning")
    return "\n".join(lines)


def write_handoff(root: Path, payload: Mapping[str, object]) -> tuple[Path, Path]:
    run_id = payload.get("run_id")
    if not isinstance(run_id, str):
        raise HandoffError("handoff run_id is invalid")
    run_dir = _safe_run_dir(root, run_id)
    run_dir.mkdir(parents=True, exist_ok=True)
    json_path = run_dir / "handoff.json"
    md_path = run_dir / "handoff.md"
    encoded = json.dumps(dict(payload), indent=2, ensure_ascii=False, sort_keys=False, allow_nan=False) + "\n"
    prompt = (f"{payload.get('summary', f'Planning handoff for run {run_id}')}\n\n"
              f"Selected workflow: {payload.get('selected_workflow')}\n"
              f"Validated artifacts: {json.dumps(payload.get('canonical_artifacts', []), sort_keys=True)}\n"
              "Current status: validated\n\n"
              "Revalidate this handoff and all current source hashes before acting.\n"
              "Downstream choices: standard-development, health-recovery, feature-planning\n")
    for destination, content in ((json_path, encoded), (md_path, prompt)):
        fd, temporary = tempfile.mkstemp(prefix=".handoff-", dir=str(run_dir))
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, destination)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
    return json_path, md_path


def validate_handoff(root: Path, path: Path) -> dict[str, object]:
    safe = safe_root(root)
    if safe is None or safe_resolve(safe, path) != path.resolve():
        raise HandoffError("handoff path is outside the project")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise HandoffError("handoff JSON is unreadable") from exc
    if not isinstance(payload, dict) or payload.get("schema") != 1 or payload.get("starts_automatically") is not False:
        raise HandoffError("handoff schema is invalid")
    run_id = payload.get("run_id")
    if not isinstance(run_id, str) or _safe_run_dir(safe, run_id) != path.resolve().parent:
        raise HandoffError("handoff identity/path is invalid")
    selected = payload.get("selected_workflow")
    if not isinstance(selected, str):
        raise HandoffError("handoff workflow is invalid")
    try:
        expected_menu = build_downstream_menu(selected)
    except HandoffError as exc:
        raise HandoffError("handoff workflow is invalid") from exc
    if payload.get("menu") != expected_menu:
        raise HandoffError("handoff menu is invalid")
    artifacts = payload.get("canonical_artifacts")
    if not isinstance(artifacts, list):
        raise HandoffError("handoff artifacts are invalid")
    for item in artifacts:
        if not isinstance(item, dict) or not isinstance(item.get("path"), str) or not isinstance(item.get("sha256"), str):
            raise HandoffError("handoff artifact is invalid")
        source = safe_resolve(safe, safe / item["path"])
        if source is None or not source.is_file() or _sha(source.read_bytes()) != item["sha256"]:
            raise HandoffError("handoff source artifact changed")
    expected = _semantic_hashes(safe, run_id)
    if payload.get("semantic_report_hashes") != expected:
        raise HandoffError("semantic review report changed")
    if payload.get("resolution_journal_sha256") != _resolution_digest(safe, run_id):
        raise HandoffError("resolution journal changed")
    try:
        gate_pack = compile_planning_gate_pack("FEAT-017", "v1")
        gate_result = validate_planning_gate_result(safe, run_id, gate_pack)
    except PlanningGateError as exc:
        raise HandoffError("planning gate result is missing, stale, or invalid") from exc
    if (
        payload.get("planning_gate_pack_sha256") != gate_pack["sha256"]
        or payload.get("planning_gate_result_sha256") != gate_result["result_sha256"]
    ):
        raise HandoffError("handoff planning gate hashes are stale or invalid")
    executions = gate_result["executions"]
    assert isinstance(executions, list)  # guaranteed by gate-result validation
    report_execution = next(
        execution for execution in executions
        if execution["gate_id"] == "planning-report-current"
    )
    report_evidence = report_execution["evidence"]
    # The validated resolver attests report.json first, then its exact ordered
    # canonical artifacts. Use that evidence without rereading the report.
    if artifacts != report_evidence[1:]:
        raise HandoffError("handoff artifacts do not match the validated planning gate report")
    expected_summary = {
        "status": "pass",
        "planning_gate_pack_sha256": gate_pack["sha256"],
        "planning_gate_result_sha256": gate_result["result_sha256"],
    }
    if payload.get("gate_summary") != expected_summary:
        raise HandoffError("handoff gate summary is not derived from the validated gate result")
    return payload


__all__ = ["HandoffError", "WORKFLOWS", "build_downstream_menu", "build_handoff", "render_summary", "validate_handoff", "write_handoff"]
