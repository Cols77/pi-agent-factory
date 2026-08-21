# src/factory/coverage/runner.py
"""Deterministic coverage-run orchestrator.

Mirrors factory.orchestrator.runner's pattern (status file, child pi sessions,
human-gate blocking) without the full journal/recovery/lock machinery.
"""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from factory.coverage.audit import validate_verdict
from factory.coverage.cli import cmd_audit, cmd_consolidate
from factory.coverage.report import render_human_summary
from factory.coverage.scope import resolve_feature_scope
from factory.orchestrator.pi_backend import PiAgentBackend
from factory.orchestrator.skills import load_skill_block
from factory.orchestrator.types import AgentRole
from factory.paths import factory_skills_dir, scope_guard_extension

STATUS_FILENAME = "status.json"
DECISIONS_FILENAME = "decisions.json"
POLL_INTERVAL_S = 1.0
GATE_TIMEOUT_S = 300.0


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _run_dir(root: Path, feat: str, run_id: str) -> Path:
    return root / "coverage-reviews" / f"{feat}-{run_id}"


def _write_status(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    tmp.replace(path)


def _sr_needs_subagent(sr_data: dict) -> bool:
    """Only SRs with tasks (linked) and not deferred need a semantic audit."""
    if sr_data.get("deferred"):
        return False
    return len(sr_data.get("tasks", [])) > 0


def _evidence_summary(tasks: list[dict]) -> str:
    summaries: list[str] = []
    for task in tasks:
        task_id = task.get("task_id", "?")
        if task.get("evidence_state") == "missing":
            summaries.append(f"{task_id}: evidence missing")
            continue
        sources: list[str] = []
        if task.get("manifests"):
            sources.append("run manifest")
        if task.get("record_paths"):
            sources.append("historical record")
        changed_files = task.get("changed_files", [])
        if changed_files:
            sources.append(f"changed files: {', '.join(changed_files)}")
        elif task.get("evidence_state") == "empty":
            sources.append("no changed files")
        summaries.append(f"{task_id}: {', '.join(sources) or 'evidence unavailable'}")
    return "; ".join(summaries) or "(no linked tasks)"


def compose_audit_prompt(feat: str, sr_id: str, sr_data: dict, overlap: dict | None) -> str:
    """Build the full prompt for a per-SR audit child: role header, skill
    block, and the injected evidence packet."""
    changed_files = []
    for t in sr_data.get("tasks", []):
        changed_files.extend(t.get("changed_files", []))
    olap = overlap or {}
    overlap_detail = {
        key: value
        for key, value in olap.items()
        if key not in {"reason", "missing_task_ids", "empty_task_ids"}
    }
    packet = (
        f"Statement: {sr_data.get('statement', '?')}\n"
        f"Binding: {sr_data.get('binding', '?')}\n"
        f"Checksum state: {sr_data.get('checksum_state', '?')}\n"
        f"Measurement: {json.dumps(sr_data.get('measurement')) if sr_data.get('measurement') else '(none)'}\n"
        f"Changed files: {', '.join(changed_files) or '(none)'}\n"
        f"Evidence: {_evidence_summary(sr_data.get('tasks', []))}\n"
        f"Import-graph overlap: {'OK' if olap.get('ok') else 'FAIL'}\n"
        f"Overlap detail: {json.dumps(overlap_detail, default=str)}\n"
    )
    lines: list[str] = []
    lines.append(f"# Role: {AgentRole.COVERAGE_AUDIT.value}")
    lines.append(
        f"You are auditing SR-{sr_id} of feature {feat}. Judge whether the "
        "implementation genuinely satisfies the statement and whether the "
        "binding test exercises the claimed behavior."
    )
    lines.append("")
    lines.append("## Loaded skills")
    lines.append(
        load_skill_block(factory_skills_dir(), "requirement-traceability-audit")
    )
    lines.append("")
    lines.append("## Evidence packet (injected)")
    lines.append(packet)
    lines.append(
        "Return ONLY a fenced ```json block with the verdict schema: "
        "sr_id, implemented, honest, confidence, margin, reasoning, checked, "
        "assumed, verify. reasoning, checked, and assumed are mandatory and "
        "must be non-empty."
    )
    return "\n".join(lines)


def run(
    root: Path,
    feat: str,
    provider: str = "",
    model: str = "",
    *,
    run_id: str | None = None,
    no_gates: bool = False,
) -> int:
    """Execute a full coverage review run.

    Returns 0 (pass), 1 (fail), 2 (degraded), or 127 (runner error).
    """
    if run_id is None:
        run_id = _now()
    run_dir = _run_dir(root, feat, run_id)
    run_dir.mkdir(parents=True, exist_ok=True)
    status_path = run_dir / STATUS_FILENAME
    decisions_path = run_dir / DECISIONS_FILENAME

    def _status(phase: str, srs: dict | None = None, **kw: object) -> None:
        payload: dict = {
            "run_id": run_id,
            "feature": feat,
            "phase": phase,
            "updated_at": _now(),
            "srs": srs or {},
            "gate": None,
            "error": None,
        }
        payload.update(kw)
        _write_status(status_path, payload)

    _status("audit")

    # Phase 0+1: machine audit
    try:
        resolve_feature_scope(root, feat)
        audit = cmd_audit(root, feat, run_id=run_id)
    except Exception as exc:
        _status("failed", error=str(exc))
        print(f"coverage: audit failed: {exc}", file=sys.stderr)
        return 127

    srs = audit.get("srs", {})
    overlaps = audit.get("overlaps", {})
    sr_progress = {sid: {"state": "pending", "session_id": None} for sid in srs}

    # Phase 2: per-SR audit (sequential; parallel is a future option)
    _status("auditing", srs=sr_progress)
    tool_failures: list[dict] = []
    ext = scope_guard_extension()

    for sr_id, sr_data in srs.items():
        if not _sr_needs_subagent(sr_data):
            sr_progress[sr_id]["state"] = "skipped"
            _status("auditing", srs=sr_progress)
            continue

        # Resume support: an existing verdict file is accepted as-is.
        verdict_path = run_dir / "verdicts" / f"{sr_id}.json"
        if verdict_path.exists():
            try:
                existing = json.loads(verdict_path.read_text(encoding="utf-8"))
                verified, error = validate_verdict(existing)
                if error is None:
                    sr_progress[sr_id]["state"] = "done"
                    _status("auditing", srs=sr_progress)
                    continue
            except (OSError, json.JSONDecodeError):
                pass

        sr_progress[sr_id]["state"] = "running"
        _status("auditing", srs=sr_progress)

        prompt = compose_audit_prompt(feat, sr_id, sr_data, overlaps.get(sr_id))
        backend = PiAgentBackend(
            root,
            ext,
            provider=provider if provider else None,
            model=model if model else None,
        )
        result = backend.run(AgentRole.COVERAGE_AUDIT, prompt)

        if not result.ok:
            tool_failures.append(
                {"sr_id": sr_id, "issue": f"subagent failed: {result.raw[:200]}"}
            )
            sr_progress[sr_id]["state"] = "failed"
            _status("auditing", srs=sr_progress)
            continue

        child_output = result.output if isinstance(result.output, dict) else {}
        verified, error = validate_verdict(child_output)
        if error:
            tool_failures.append({"sr_id": sr_id, "issue": f"invalid verdict: {error}"})
            sr_progress[sr_id]["state"] = "failed"
            _status("auditing", srs=sr_progress)
            continue

        verdict_dir = run_dir / "verdicts"
        verdict_dir.mkdir(parents=True, exist_ok=True)
        (verdict_dir / f"{sr_id}.json").write_text(
            json.dumps(verified, indent=2), encoding="utf-8"
        )
        sr_progress[sr_id]["state"] = "done"
        sr_progress[sr_id]["session_id"] = result.session_id
        _status("auditing", srs=sr_progress)

    # Phase 3+4: consolidate + gate
    _status("consolidating", srs=sr_progress)
    audit_path = run_dir / "audit.json"
    audit["tool_failures"] = tool_failures
    audit_path.write_text(json.dumps(audit, indent=2), encoding="utf-8")

    try:
        report_data = cmd_consolidate(root, feat, run_id)
        gate_outcome = report_data.get("gate", {}).get("outcome", "unknown")
    except Exception as exc:
        _status("failed", error=str(exc))
        print(f"coverage: consolidate failed: {exc}", file=sys.stderr)
        return 127

    _status("gate", srs=sr_progress, gate=report_data.get("gate"))

    # Phase 5: human gates for proposed requirements / suggested actions
    proposed = _find_proposed_requirements(report_data)
    warned = report_data.get("gate", {}).get("warned", [])
    if not no_gates and (proposed or warned):
        _status(
            "gates",
            srs=sr_progress,
            gate=report_data.get("gate"),
            proposed_requirements=proposed,
            suggested_actions=warned,
        )
        waited = 0.0
        while not decisions_path.exists():
            time.sleep(POLL_INTERVAL_S)
            waited += POLL_INTERVAL_S
            if waited >= GATE_TIMEOUT_S:
                _status("gates_timeout", srs=sr_progress, gate=report_data.get("gate"))
                break
        if decisions_path.exists():
            try:
                decisions = json.loads(decisions_path.read_text(encoding="utf-8"))
                report_data["human_decisions"] = decisions
            except (OSError, json.JSONDecodeError) as exc:
                print(f"coverage: could not read decisions file: {exc}", file=sys.stderr)

    report_data["generated_at"] = _now()
    (run_dir / "report.json").write_text(json.dumps(report_data, indent=2), encoding="utf-8")
    _status("done", srs=sr_progress, gate=report_data.get("gate"))

    print(render_human_summary(report_data))

    if gate_outcome == "fail":
        return 1
    if gate_outcome == "degraded":
        return 2
    return 0


def _find_proposed_requirements(report: dict) -> list[dict]:
    """Find declared SRs with no register entry (candidates for new requirements)."""
    proposed: list[dict] = []
    for f in report.get("completeness", []):
        if f.get("kind") == "declared_not_in_register":
            proposed.append(
                {
                    "candidate_id": f["sr_id"],
                    "rationale": "declared in feature but not in the requirements register",
                    "evidence_of_gap": (
                        f"feat.{report.get('feature')} lists {f['sr_id']} "
                        "but no SR-###.md file exists."
                    ),
                }
            )
    return proposed
