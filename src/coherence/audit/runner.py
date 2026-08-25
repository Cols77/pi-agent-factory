"""Deterministic coverage-run orchestrator.

Mirrors factory.orchestrator.runner's pattern (status file, child pi sessions,
human-gate blocking) without the full journal/recovery/lock machinery.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from coherence.audit.audit import validate_verdict
from coherence.audit.cli import cmd_audit, cmd_consolidate
from coherence.audit.policy import audit_max_workers
from coherence.audit.report import render_human_summary
from coherence.audit.scope import resolve_feature_scope
from coherence.gate.service import resolve_gate
from coherence.gate.store import decision_path, load_decision
from coherence.policy.compiler import (
    UncompiledPresetError,
    UnsupportedScopeError,
    compile_obligations,
)
from factory.orchestrator.pi_backend import PiAgentBackend
from factory.orchestrator.types import AgentRole
from substrate.agents.skills import load_skill_block
from substrate.paths import factory_skills_dir, scope_guard_extension

STATUS_FILENAME = "status.json"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _run_dir(root: Path, feat: str, run_id: str) -> Path:
    return root / "coverage-reviews" / f"{feat}-{run_id}"


def _write_status(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    tmp.replace(path)


def write_verdict_atomically(run_dir: Path, sr_id: str, verdict: dict) -> Path:
    """The only write a worker performs: atomically persist one SR's verdict.

    Same tmp-file-then-``Path.replace()`` pattern as :func:`_write_status`, so
    a reader (e.g. a later run's own resume check) never observes a partially
    written verdict file. The coordinator alone writes ``audit.json``,
    ``report.json``, and ``status.json``.
    """
    path = run_dir / "verdicts" / f"{sr_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(verdict, indent=2), encoding="utf-8")
    tmp.replace(path)
    return path


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


def _dispatch_sr(
    root: Path,
    ext: Path,
    feat: str,
    sr_id: str,
    sr_data: dict,
    overlap: dict | None,
    provider: str,
    model: str,
    run_dir: Path,
) -> dict:
    """Runs on a worker thread for exactly one SR.

    Constructs its own fresh ``PiAgentBackend`` (the plan's "each worker
    already gets its own backend instance naturally"), dispatches the child
    audit, and -- on a valid verdict -- performs the only write a worker is
    allowed to make: :func:`write_verdict_atomically`. Never touches
    ``status.json``, ``audit.json``, or ``report.json``; the coordinator
    thread applies the returned result after collecting every worker, sorted
    by SR id, so completion order can never affect what gets written.
    """
    prompt = compose_audit_prompt(feat, sr_id, sr_data, overlap)
    backend = PiAgentBackend(
        root,
        ext,
        provider=provider if provider else None,
        model=model if model else None,
    )
    result = backend.run(AgentRole.COVERAGE_AUDIT, prompt)

    if not result.ok:
        return {"ok": False, "issue": f"subagent failed: {result.raw[:200]}"}

    child_output = result.output if isinstance(result.output, dict) else {}
    verified, error = validate_verdict(child_output)
    if error or verified is None:
        return {"ok": False, "issue": f"invalid verdict: {error}"}

    write_verdict_atomically(run_dir, sr_id, verified)
    return {"ok": True, "session_id": result.session_id}


def _gate_item_ids(run_id: str, proposed: list[dict], warned: list[str]) -> list[str]:
    """The per-SR gate item ids a coverage run's DecisionFile must carry.

    Proposed requirements map to ``coverage:<run>:proposal:<sr_id>`` and
    warned SRs to ``coverage:<run>:warning:<sr_id>``, matching the
    ``coverage:<run>:...`` item-family the DecisionFile model accepts. This is
    the roster the runner surfaces when a human must author a decision.
    """
    ids: list[str] = []
    for proposal in proposed:
        ids.append(f"coverage:{run_id}:proposal:{proposal['candidate_id']}")
    ids.extend(f"coverage:{run_id}:warning:{w}" for w in warned)
    return ids


def run(
    root: Path,
    feat: str,
    provider: str = "",
    model: str = "",
    *,
    run_id: str | None = None,
    no_gates: bool = False,
    unattended: bool = False,
    max_workers: int | None = None,
    policy_bound: bool = False,
    max_reruns: int = 10,
) -> int:
    """Execute a full coverage review run.

    Phase 0 (scope/overlap), resume checks, consolidation, and the gate all
    stay serial and are owned exclusively by this coordinator. Only the
    per-SR audit dispatch (a fresh subagent per SR needing a verdict) runs on
    a bounded ``ThreadPoolExecutor`` -- I/O-bound subprocess/API work, not
    CPU-bound, so threads rather than processes. ``max_workers`` defaults to
    the ``audit.max_workers`` policy (see ``coherence.audit.policy``,
    default 4) and must be a positive integer.

    The human gate for proposed requirements / suggested actions is resolved
    through ``coherence.gate.resolve_gate``: when such items exist, an
    explicit `DecisionFile` is required before the run finalises.
    ``unattended=True`` means no human is available to author one, so running
    without a decision is a hard failure (``"blocked"``); ``unattended=False``
    and no decision surfaces the authoring need and returns non-zero WITHOUT
    writing a report -- an unreviewed run is never treated as reviewed by
    exhausting a timeout. An existing valid decision short-circuits and
    resumes without re-prompting. ``no_gates`` (the ``--no-gates`` CLI
    opt-out) is the sole explicit opt-out and skips the human gate entirely.

    ``policy_bound``/``max_reruns`` are inert unless ``policy_bound`` is set:
    without it, an SR with an already-recorded verdict is always accepted
    as-is (this coordinator's original resume semantics). With
    ``policy_bound``, an SR whose verdict already exists is instead
    resubmitted when its compiled ``verification_result`` obligation is not
    ``"satisfied"`` -- checking the verdict file *and* the obligation state,
    never the obligation alone (an SR can pass harness validation while
    never having had an audit verdict recorded at all; an SR with no verdict
    file is always submitted regardless of these flags). The resubmission
    set is sorted by SR id and capped at ``max_reruns`` (default 10; 0
    disables policy-bound resubmission entirely); the uncapped remainder
    keeps its existing verdict for this run and is recorded as
    ``skipped_by_max_reruns`` in ``audit.json`` and ``report.json`` (also
    surfaced in the human summary), with ``sr_progress`` state
    ``"stale_capped"`` -- distinct from a genuinely fresh ``"done"``
    verdict.

    Returns 0 (pass), 1 (fail), 2 (degraded), or 127 (runner error).
    """
    if run_id is None:
        run_id = _now()
    run_dir = _run_dir(root, feat, run_id)
    run_dir.mkdir(parents=True, exist_ok=True)
    status_path = run_dir / STATUS_FILENAME

    if max_workers is None:
        max_workers = audit_max_workers(root)
    if isinstance(max_workers, bool) or not isinstance(max_workers, int) or max_workers <= 0:
        raise ValueError(f"max_workers must be a positive integer, got {max_workers!r}")
    if isinstance(max_reruns, bool) or not isinstance(max_reruns, int) or max_reruns < 0:
        raise ValueError(f"max_reruns must be a nonnegative integer, got {max_reruns!r}")

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

    # Phase 2: per-SR audit. Serial pass first: classify every SR as
    # skipped/resumed/needing-a-worker, in the original scope order -- this
    # is also where a pre-existing verdict short-circuits a worker entirely.
    _status("auditing", srs=sr_progress)
    ext = scope_guard_extension()

    needs_worker: list[str] = []
    rerun_candidates: list[str] = []
    for sr_id, sr_data in srs.items():
        if not _sr_needs_subagent(sr_data):
            sr_progress[sr_id]["state"] = "skipped"
            continue

        # Resume support: an existing verdict file is accepted as-is, unless
        # --policy-bound requires resubmission (checked below) -- an SR with
        # no verdict file at all always falls through to needs_worker,
        # regardless of policy_bound/max_reruns.
        verdict_path = run_dir / "verdicts" / f"{sr_id}.json"
        if verdict_path.exists():
            try:
                existing = json.loads(verdict_path.read_text(encoding="utf-8"))
                _, error = validate_verdict(existing)
                if error is None:
                    if policy_bound:
                        try:
                            obligations = compile_obligations(root, f"sr:{sr_id}")
                        except (UnsupportedScopeError, UncompiledPresetError):
                            # Cannot prove the verification_result obligation
                            # satisfied (e.g. an SR declared but not in the
                            # requirements register, or a profile that isn't
                            # compiled yet) -- fail closed: treat exactly
                            # like an unsatisfied obligation, same as the
                            # branch below, never a silent skip.
                            rerun_candidates.append(sr_id)
                            continue
                        verification = next(
                            (o for o in obligations if o.kind == "verification_result"),
                            None,
                        )
                        if verification is not None and verification.state == "satisfied":
                            sr_progress[sr_id]["state"] = "done"
                            continue
                        # Verdict exists but its verification_result
                        # obligation is not satisfied: a resubmission
                        # candidate, subject to the --max-reruns cap below.
                        rerun_candidates.append(sr_id)
                        continue
                    sr_progress[sr_id]["state"] = "done"
                    continue
            except (OSError, json.JSONDecodeError):
                pass

        sr_progress[sr_id]["state"] = "running"
        needs_worker.append(sr_id)

    # Policy-bound resubmission: sort candidates by SR id, cap at
    # max_reruns, submit the capped set alongside needs_worker, and record
    # the uncapped remainder (not silently dropped) for the audit report.
    rerun_candidates.sort()
    to_resubmit = rerun_candidates[:max_reruns]
    skipped_by_max_reruns = rerun_candidates[max_reruns:]
    for sr_id in to_resubmit:
        sr_progress[sr_id]["state"] = "running"
        needs_worker.append(sr_id)
    for sr_id in skipped_by_max_reruns:
        # Distinct from a genuinely fresh "done" verdict: this SR's stale
        # verdict is being kept only because --max-reruns capped it out of
        # this run's resubmission set, not because it was proven satisfied.
        sr_progress[sr_id]["state"] = "stale_capped"

    _status("auditing", srs=sr_progress)

    # Bounded parallel dispatch: only the SRs collected above. Each worker
    # builds its own PiAgentBackend and, on a valid verdict, performs the
    # only write it is allowed to make (write_verdict_atomically). Results
    # are collected as futures resolve, but never applied to sr_progress or
    # tool_failures until every worker is done and sorted by SR id below --
    # this coordinator is the sole writer of status/audit/report artifacts,
    # and their content must never depend on completion order.
    tool_failures: list[dict] = []
    if needs_worker:
        worker_results: dict[str, dict] = {}
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(
                    _dispatch_sr,
                    root,
                    ext,
                    feat,
                    sr_id,
                    srs[sr_id],
                    overlaps.get(sr_id),
                    provider,
                    model,
                    run_dir,
                ): sr_id
                for sr_id in needs_worker
            }
            for future in as_completed(futures):
                sr_id = futures[future]
                worker_results[sr_id] = future.result()
                # Live progress: this runs on the coordinator thread (the
                # as_completed loop itself, not a worker thread), so writing
                # a progress-only status update here violates no
                # sole-writer rule. "worker_done" is distinct from
                # "running" (still in flight) and from the final
                # "done"/"failed" the sorted pass below assigns -- it only
                # marks "this worker finished, coordinator hasn't
                # finalized state yet". The sorted(worker_results) pass
                # below is unchanged: it alone decides the final,
                # order-independent done/failed state and tool_failures.
                sr_progress[sr_id]["state"] = "worker_done"
                _status("auditing", srs=sr_progress)

        for sr_id in sorted(worker_results):
            result = worker_results[sr_id]
            if result["ok"]:
                sr_progress[sr_id]["state"] = "done"
                sr_progress[sr_id]["session_id"] = result.get("session_id")
            else:
                tool_failures.append({"sr_id": sr_id, "issue": result["issue"]})
                sr_progress[sr_id]["state"] = "failed"

    _status("auditing", srs=sr_progress)

    # Phase 3+4: consolidate + gate
    _status("consolidating", srs=sr_progress)
    audit_path = run_dir / "audit.json"
    audit["tool_failures"] = tool_failures
    # Only recorded when --policy-bound is set: without it, this key never
    # existed before this task, and behaviour must stay byte-identical.
    if policy_bound:
        audit["skipped_by_max_reruns"] = skipped_by_max_reruns
    audit_path.write_text(json.dumps(audit, indent=2), encoding="utf-8")

    try:
        report_data = cmd_consolidate(root, feat, run_id)
        gate_outcome = report_data.get("gate", {}).get("outcome", "unknown")
    except Exception as exc:
        _status("failed", error=str(exc))
        print(f"coverage: consolidate failed: {exc}", file=sys.stderr)
        return 127

    _status("gate", srs=sr_progress, gate=report_data.get("gate"))

    # Phase 5: human gate for proposed requirements / suggested actions.
    proposed = _find_proposed_requirements(report_data)
    warned = report_data.get("gate", {}).get("warned", [])
    if (proposed or warned) and not no_gates:
        _status(
            "gates",
            srs=sr_progress,
            gate=report_data.get("gate"),
            proposed_requirements=proposed,
            suggested_actions=warned,
        )
        gate_id = f"coverage:{run_id}"
        items = _gate_item_ids(run_id, proposed, warned)
        resolved = resolve_gate(run_dir, gate_id, unattended=unattended)
        if resolved is None:
            # Attended but no decision authored: surface exactly where a
            # human must write one and DO NOT auto-finalise. No timeout is
            # exhausted to fake a "reviewed" outcome.
            target = decision_path(run_dir, gate_id)
            _status(
                "gates_blocked",
                srs=sr_progress,
                gate=report_data.get("gate"),
                proposed_requirements=proposed,
                suggested_actions=warned,
                decision_path=str(target),
                needed_items=items,
            )
            print(
                f"coverage: gate {gate_id!r} needs a human decision; "
                f"author a DecisionFile at {target} with items "
                f"{', '.join(items) or '(none)'}, then re-run",
                file=sys.stderr,
            )
            return 1
        if resolved == "blocked":
            # Unattended and no decision: nothing can author it, so this is a
            # hard failure -- never an auto-finalised "reviewed" run.
            _status(
                "gates_blocked",
                srs=sr_progress,
                gate=report_data.get("gate"),
                proposed_requirements=proposed,
                suggested_actions=warned,
                decision_path=str(decision_path(run_dir, gate_id)),
                needed_items=items,
            )
            print(
                f"coverage: gate {gate_id!r} has no decision file and the run is "
                "unattended; refusing to auto-finalise an unreviewed run",
                file=sys.stderr,
            )
            return 1

        # A durable decision exists (accept/defer/reject): resume without
        # re-prompting. The resolved file is the single source of truth.
        decision_file = load_decision(decision_path(run_dir, gate_id))
        report_data["human_decisions"] = decision_file.to_dict()
        if resolved == "reject":
            # A durable reject is a hard failure, recorded in the report.
            gate_outcome = "fail"

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


__all__ = ["compose_audit_prompt", "run", "write_verdict_atomically"]
