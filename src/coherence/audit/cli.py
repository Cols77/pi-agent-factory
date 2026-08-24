from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

import frontmatter

from coherence.audit.audit import classify, validate_verdict
from coherence.audit.gate import run_gate
from coherence.audit.report import render_human_summary
from coherence.audit.scope import EvidenceState, resolve_feature_scope
from substrate.codemap.imports import compute_overlap


_COVERAGE_REVIEWS = "coverage-reviews"


def _run_dir(root: Path, feat: str, run_id: str) -> Path:
    return root / _COVERAGE_REVIEWS / f"{feat}-{run_id}"


def cmd_audit(root: Path, feat: str, run_id: str | None = None) -> dict:
    """Phase 0 + 1: write scope + overlap to a run directory."""
    if run_id is None:
        run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = _run_dir(root, feat, run_id)
    run_dir.mkdir(parents=True, exist_ok=True)

    scope = resolve_feature_scope(root, feat)

    # Phase 1: overlap for each SR with a pytest binding
    overlaps: dict[str, dict] = {}
    for sr_id, sr in scope.srs.items():
        if sr.binding is None:
            continue
        experiment = sr.binding.get("experiment", "")
        if not experiment:
            continue
        missing_task_ids = [
            task.task_id
            for task in sr.tasks
            if task.evidence_state is EvidenceState.missing
        ]
        if missing_task_ids:
            overlaps[sr_id] = {
                "ok": False,
                "reason": "missing evidence for tasks",
                "missing_task_ids": missing_task_ids,
            }
            continue
        changed_files: list[str] = []
        for task in sr.tasks:
            changed_files.extend(task.changed_files)
        changed_files = list(set(changed_files))
        if not changed_files:
            overlaps[sr_id] = {
                "ok": False,
                "reason": "recorded evidence has no changed files",
                "empty_task_ids": [
                    task.task_id
                    for task in sr.tasks
                    if task.evidence_state is EvidenceState.empty
                ],
            }
        else:
            overlap_result = compute_overlap(root, experiment, changed_files)
            overlap_dict = asdict(overlap_result)
            if overlap_result.test_source is None:
                # The binding's selection path doesn't exist on disk (e.g. a
                # deleted or renamed test file) -- distinct from a selection
                # that resolves fine but simply doesn't reach the changed
                # files (a genuine zero-overlap result carries no "reason").
                overlap_dict["reason"] = "binding test selection missing"
            overlaps[sr_id] = overlap_dict

    audit = {
        "feature": feat,
        "run_id": run_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scope": {
            "declared": list(scope.declared),
            "contains": list(scope.contains),
            "linked": list(scope.linked),
            "register": list(scope.register),
        },
        "completeness": [dict(f) for f in scope.completeness],
        "srs": {
            sr_id: {
                "sr_id": sr.sr_id,
                "statement": sr.statement,
                "binding": sr.binding,
                "checksum_state": sr.checksum_state,
                "tasks": [
                    {
                        "task_id": t.task_id,
                        "changed_files": list(t.changed_files),
                        "manifests": list(t.manifests),
                        "record_paths": list(t.record_paths),
                        "evidence_state": t.evidence_state.value,
                    }
                    for t in sr.tasks
                ],
                "measurement": sr.measurement,
                "deferred": sr.deferred,
                "domain": sr.domain,
            }
            for sr_id, sr in scope.srs.items()
        },
        "overlaps": overlaps,
        "states": {},  # populated by consolidate
        "gate": None,  # populated by consolidate
        "tool_failures": [],  # appended via the failure verb
    }
    (run_dir / "audit.json").write_text(json.dumps(audit, indent=2), encoding="utf-8")
    return audit


def cmd_verdict(root: Path, feat: str, run_id: str, sr_id: str, verdict: dict) -> dict:
    """Validate and record a subagent verdict for one SR."""
    validated, error = validate_verdict(verdict)
    if error:
        return {"valid": False, "error": error}
    run_dir = _run_dir(root, feat, run_id)
    run_dir.mkdir(parents=True, exist_ok=True)
    verdict_dir = run_dir / "verdicts"
    verdict_dir.mkdir(parents=True, exist_ok=True)
    path = verdict_dir / f"{sr_id}.json"
    path.write_text(json.dumps(validated, indent=2), encoding="utf-8")
    return {"valid": True, "path": str(path)}


def cmd_record_failure(
    root: Path, feat: str, run_id: str, sr_id: str, issue: str
) -> dict:
    """Record a workflow/tool failure for an SR (subagent dispatch, etc.)."""
    run_dir = _run_dir(root, feat, run_id)
    audit_path = run_dir / "audit.json"
    if not audit_path.exists():
        return {"recorded": False, "error": f"no audit.json at {audit_path}"}
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    failures = audit.get("tool_failures", [])
    if not any(f.get("sr_id") == sr_id for f in failures):
        failures.append({"sr_id": sr_id, "issue": issue})
    audit["tool_failures"] = failures
    audit_path.write_text(json.dumps(audit, indent=2), encoding="utf-8")
    return {"recorded": True, "tool_failures": failures}


def _load_verdicts(run_dir: Path) -> dict[str, dict]:
    verdict_dir = run_dir / "verdicts"
    verdicts: dict[str, dict] = {}
    if not verdict_dir.exists():
        return verdicts
    for p in sorted(verdict_dir.glob("*.json")):
        sr_id = p.stem
        try:
            verdicts[sr_id] = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
    return verdicts


def cmd_consolidate(root: Path, feat: str, run_id: str) -> dict:
    """Phase 3 + 4: classify, gate, write report."""
    run_dir = _run_dir(root, feat, run_id)
    audit_path = run_dir / "audit.json"
    if not audit_path.exists():
        return {"error": f"no audit.json found at {audit_path}"}
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    verdicts = _load_verdicts(run_dir)

    tool_failures = audit.get("tool_failures", [])

    states: dict[str, list] = {}
    for sr_id, sr_data in audit.get("srs", {}).items():
        verdict = verdicts.get(sr_id)
        overlap = audit.get("overlaps", {}).get(sr_id)
        tool_failure = any(f.get("sr_id") == sr_id for f in tool_failures)
        state, notes = classify(sr_data, overlap, verdict, tool_failure)
        states[sr_id] = [state.value, notes]

    outcome, failed, warned, degraded = run_gate(
        {sr_id: (s[0], s[1]) for sr_id, s in states.items()},
        tool_failures,
    )

    report = {
        "feature": feat,
        "run_id": run_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scope": audit.get("scope", {}),
        "completeness": audit.get("completeness", []),
        "srs": _merge_states(audit.get("srs", {}), states),
        "overlaps": audit.get("overlaps", {}),
        "states": states,
        "gate": {
            "outcome": outcome.value,
            "failed": failed,
            "warned": warned,
            "degraded": degraded,
        },
        "workflow_issues": tool_failures,
    }
    (run_dir / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def _merge_states(srs: dict, states: dict) -> dict:
    """Attach each SR's classified state to its sr dict for the report."""
    merged: dict = {}
    for sr_id, sr_data in srs.items():
        item = dict(sr_data)
        if sr_id in states:
            item["states"] = [states[sr_id]]
        merged[sr_id] = item
    return merged


def cmd_gate(root: Path, feat: str, run_id: str) -> str:
    """Re-derive gate from disk (stateless)."""
    run_dir = _run_dir(root, feat, run_id)
    report_path = run_dir / "report.json"
    if not report_path.exists():
        return "no_report"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    return report.get("gate", {}).get("outcome", "unknown")


def cmd_report(root: Path, feat: str, run_id: str) -> str:
    """Render the human summary."""
    run_dir = _run_dir(root, feat, run_id)
    report_path = run_dir / "report.json"
    if not report_path.exists():
        consolidated = cmd_consolidate(root, feat, run_id)
        if "error" in consolidated:
            return consolidated["error"]
        report_path = run_dir / "report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    return render_human_summary(report)


def cmd_list_features(root: Path) -> list[dict]:
    """List features for the picker: id, title, declared SR count."""
    features: list[dict] = []
    feat_dir = root / "docs" / "features"
    if not feat_dir.exists():
        return features
    for p in sorted(feat_dir.glob("FEAT-*.md")):
        try:
            post = frontmatter.load(str(p))
        except Exception:
            continue
        reqs = post.metadata.get("requirements", [])
        if not isinstance(reqs, list):
            reqs = []
        title = str(post.metadata.get("title", p.stem))
        features.append(
            {
                "id": str(post.metadata.get("id", p.stem)),
                "title": title,
                "declared_srs": len(reqs),
            }
        )
    return features


def cmd_run(
    root: Path,
    feat: str,
    *,
    provider: str = "",
    model: str = "",
    run_id: str | None = None,
    no_gates: bool = False,
) -> int:
    """Execute the deterministic coverage run (Phase 0 -> 5)."""
    # Lazy import: runner.py imports this module, so importing it here at
    # module load would be a circular import.
    from coherence.audit.runner import run as run_coverage

    return run_coverage(
        root, feat, provider=provider, model=model, run_id=run_id, no_gates=no_gates
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="factory-coverage")
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--project-root", default=Path("."), type=Path)

    sub = parser.add_subparsers(dest="cmd", required=True)

    p_audit = sub.add_parser("audit", parents=[common])
    p_audit.add_argument("feat")
    p_audit.add_argument("--run-id", default=None)

    p_verdict = sub.add_parser("verdict", parents=[common])
    p_verdict.add_argument("feat")
    p_verdict.add_argument("run_id")
    p_verdict.add_argument("sr_id")
    p_verdict.add_argument(
        "--file", required=True, type=Path, help="path to verdict JSON file"
    )

    p_consolidate = sub.add_parser("consolidate", parents=[common])
    p_consolidate.add_argument("feat")
    p_consolidate.add_argument("run_id")

    p_gate = sub.add_parser("gate", parents=[common])
    p_gate.add_argument("feat")
    p_gate.add_argument("run_id")

    p_report = sub.add_parser("report", parents=[common])
    p_report.add_argument("feat")
    p_report.add_argument("run_id")

    p_failure = sub.add_parser("failure", parents=[common])
    p_failure.add_argument("feat")
    p_failure.add_argument("run_id")
    p_failure.add_argument("sr_id")
    p_failure.add_argument("--issue", required=True)

    sub.add_parser("list-features", parents=[common])

    p_run = sub.add_parser("run", parents=[common])
    p_run.add_argument("feat")
    p_run.add_argument("--provider", default="")
    p_run.add_argument("--model", default="")
    p_run.add_argument("--run-id", default=None)
    p_run.add_argument("--no-gates", action="store_true")

    args = parser.parse_args(argv)

    if args.cmd == "list-features":
        print(json.dumps(cmd_list_features(args.project_root), indent=2))
    elif args.cmd == "run":
        return cmd_run(
            args.project_root,
            args.feat,
            provider=args.provider,
            model=args.model,
            run_id=args.run_id,
            no_gates=args.no_gates,
        )
    elif args.cmd == "audit":
        print(json.dumps(cmd_audit(args.project_root, args.feat, run_id=args.run_id), indent=2))
    elif args.cmd == "failure":
        print(
            json.dumps(
                cmd_record_failure(
                    args.project_root, args.feat, args.run_id, args.sr_id, args.issue
                ),
                indent=2,
            )
        )
    elif args.cmd == "verdict":
        verdict = json.loads(args.file.read_text(encoding="utf-8"))
        result = cmd_verdict(
            args.project_root, args.feat, args.run_id, args.sr_id, verdict
        )
        print(json.dumps(result, indent=2))
        return 1 if not result.get("valid") else 0
    elif args.cmd == "consolidate":
        print(json.dumps(cmd_consolidate(args.project_root, args.feat, args.run_id), indent=2))
    elif args.cmd == "gate":
        outcome = cmd_gate(args.project_root, args.feat, args.run_id)
        print(outcome)
        if outcome == "fail":
            return 1
        if outcome == "degraded":
            return 2
    elif args.cmd == "report":
        print(cmd_report(args.project_root, args.feat, args.run_id))

    return 0


__all__ = [
    "cmd_audit",
    "cmd_consolidate",
    "cmd_gate",
    "cmd_list_features",
    "cmd_record_failure",
    "cmd_report",
    "cmd_run",
    "cmd_verdict",
    "main",
]
