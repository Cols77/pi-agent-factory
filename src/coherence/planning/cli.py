from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from coherence.planning.bootstrap import BootstrapPrerequisiteError, bootstrap_planning
from coherence.planning.check import check_planning_input
from coherence.planning.model import PlanningFinding, PlanningInput, PlanningReport
from coherence.planning.run import (
    build_downstream_suggestion,
    read_review_decision,
    write_planning_run,
)

_REPORT_KEYS = (
    "schema",
    "run_id",
    "ok",
    "artifacts",
    "findings",
    "next_actions",
    "review_required",
    "suggestion",
)
_FINDING_KEYS = {"code", "severity", "subject", "detail"}


def _valid_run_id(run_id: object) -> bool:
    return (
        isinstance(run_id, str)
        and bool(run_id.strip())
        and run_id == run_id.strip()
        and not any(ord(char) < 32 for char in run_id)
        and run_id not in {".", ".."}
        and "/" not in run_id
        and "\\" not in run_id
    )


def _safe_root(value: object) -> Path | None:
    if not isinstance(value, Path):
        return None
    try:
        return value.resolve()
    except (OSError, RuntimeError, ValueError):
        return None


def _safe_stored_path(root: Path, *parts: str) -> Path | None:
    try:
        candidate = (root.joinpath(*parts)).resolve()
        candidate.relative_to(root)
    except (OSError, RuntimeError, ValueError):
        return None
    return candidate


def _source_path(value: Path, root: Path) -> Path:
    """Interpret relative source paths relative to the requested project root."""
    return value if value.is_absolute() else root / value


def _json_report(report: PlanningReport) -> str:
    return json.dumps(report.to_dict(), indent=2, ensure_ascii=False)


def _error_report(run_id: str, code: str, detail: str) -> dict[str, object]:
    return PlanningReport(
        schema=1,
        run_id=run_id,
        ok=False,
        artifacts=(),
        findings=(
            PlanningFinding(
                code=code,
                severity="error",
                subject="planning",
                detail=detail,
            ),
        ),
        next_actions=(),
        review_required=True,
        suggestion=None,
    ).to_dict()


def _blocked(run_id: str, reason: str, detail: str) -> dict[str, object]:
    return {
        "schema": 1,
        "run_id": run_id,
        "action": "blocked",
        "ok": False,
        "blocked": True,
        "reason": reason,
        "detail": detail,
        "suggestion": None,
    }


def _read_report(path: Path, run_id: str) -> PlanningReport:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("stored planning report is missing, unreadable, or invalid JSON") from exc

    if not isinstance(payload, dict) or tuple(payload) != _REPORT_KEYS:
        raise ValueError("stored planning report has an invalid schema")
    if type(payload.get("schema")) is not int or payload.get("schema") != 1:
        raise ValueError("stored planning report schema must equal 1")
    if payload.get("run_id") != run_id:
        raise ValueError("stored planning report run_id does not match the requested run")
    if type(payload.get("ok")) is not bool or type(payload.get("review_required")) is not bool:
        raise ValueError("stored planning report has invalid status fields")
    if payload.get("suggestion") is not None:
        raise ValueError("stored planning report cannot contain a suggestion")

    artifacts_payload = payload.get("artifacts")
    if not isinstance(artifacts_payload, list):
        raise ValueError("stored planning report artifacts must be a list")
    artifacts: list[dict[str, object]] = []
    for artifact in artifacts_payload:
        if not isinstance(artifact, dict) or set(artifact) != {"path", "sha256"}:
            raise ValueError("stored planning report contains an invalid artifact")
        if not isinstance(artifact.get("path"), str) or not isinstance(artifact.get("sha256"), str):
            raise ValueError("stored planning report contains an invalid artifact")
        artifact_path = artifact["path"]
        if (
            artifact_path.startswith("/")
            or artifact_path.startswith("\\")
            or ":" in artifact_path
            or ".." in Path(artifact_path).parts
            or any(part in {"", "."} for part in artifact_path.replace("\\", "/").split("/"))
        ):
            raise ValueError("stored planning report contains an unsafe artifact path")
        artifacts.append({"path": artifact["path"], "sha256": artifact["sha256"]})

    findings_payload = payload.get("findings")
    if not isinstance(findings_payload, list):
        raise ValueError("stored planning report findings must be a list")
    findings: list[PlanningFinding] = []
    for finding in findings_payload:
        if not isinstance(finding, dict) or set(finding) != _FINDING_KEYS:
            raise ValueError("stored planning report contains an invalid finding")
        code = finding.get("code")
        severity = finding.get("severity")
        subject = finding.get("subject")
        detail = finding.get("detail")
        if not all(isinstance(value, str) for value in (code, severity, subject, detail)):
            raise ValueError("stored planning report contains an invalid finding")
        if severity not in {"error", "warning"}:
            raise ValueError("stored planning report contains an invalid finding severity")
        findings.append(
            PlanningFinding(code=code, severity=severity, subject=subject, detail=detail)  # type: ignore[arg-type]
        )

    next_actions_payload = payload.get("next_actions")
    if not isinstance(next_actions_payload, list) or not all(
        isinstance(action, dict) for action in next_actions_payload
    ):
        raise ValueError("stored planning report next_actions must be a list of objects")

    return PlanningReport(
        schema=1,
        run_id=run_id,
        ok=payload["ok"],
        artifacts=tuple(artifacts),
        findings=tuple(findings),
        next_actions=tuple(next_actions_payload),
        review_required=payload["review_required"],
        suggestion=None,
    )


def _check(args: argparse.Namespace) -> int:
    root = _safe_root(args.project_root)
    if root is None:
        payload = _error_report(args.run_id, "CLI_INVALID_ARGUMENT", "project_root is invalid")
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 1
    if not _valid_run_id(args.run_id):
        payload = _error_report(args.run_id, "CLI_INVALID_ARGUMENT", "run_id must be a safe path component")
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 1

    planning_input = PlanningInput(
        intent_path=_source_path(args.intent, root),
        spec_path=_source_path(args.spec, root),
        plan_path=_source_path(args.plan, root),
        project_root=root,
        run_id=args.run_id,
    )
    try:
        report = check_planning_input(planning_input)
        write_planning_run(root, report)
    except (OSError, UnicodeError, ValueError, TypeError, json.JSONDecodeError):
        payload = _error_report(args.run_id, "CLI_ERROR", "planning check could not be completed")
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 1

    print(_json_report(report))
    return 1 if any(finding.severity == "error" for finding in report.findings) else 0


def _bootstrap(args: argparse.Namespace) -> int:
    root = _safe_root(args.project_root)
    if root is None:
        print(json.dumps(_blocked(args.run_id, "INVALID_PROJECT_ROOT", "project_root is invalid"), indent=2))
        return 1
    if not _valid_run_id(args.run_id):
        print(json.dumps(_blocked(args.run_id, "INVALID_RUN_ID", "run_id must be a safe path component"), indent=2))
        return 1
    planning_input = PlanningInput(
        intent_path=_source_path(args.intent, root),
        spec_path=_source_path(args.spec, root),
        plan_path=_source_path(args.plan, root),
        project_root=root,
        run_id=args.run_id,
    )
    try:
        report, created = bootstrap_planning(root, planning_input, decompose=args.decompose)
        write_planning_run(root, report)
    except BootstrapPrerequisiteError as exc:
        print(json.dumps(_blocked(args.run_id, "BOOTSTRAP_PREREQUISITE", str(exc)), indent=2))
        return 1
    except (OSError, UnicodeError, ValueError, TypeError, RuntimeError):
        print(
            json.dumps(
                _blocked(args.run_id, "BOOTSTRAP_ERROR", "planning bootstrap could not be completed"),
                indent=2,
            )
        )
        return 1

    payload = report.to_dict()
    payload["created_task_ids"] = list(created)
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 1 if any(finding.severity == "error" for finding in report.findings) else 0


def _suggest(args: argparse.Namespace) -> int:
    root = _safe_root(args.project_root)
    if root is None:
        print(json.dumps(_blocked(args.run_id, "INVALID_PROJECT_ROOT", "project_root is invalid"), indent=2))
        return 1
    if not _valid_run_id(args.run_id):
        print(json.dumps(_blocked(args.run_id, "INVALID_RUN_ID", "run_id must be a safe path component"), indent=2))
        return 1

    run_dir = _safe_stored_path(root, ".factory", "planning", args.run_id)
    if run_dir is None:
        print(json.dumps(_blocked(args.run_id, "INVALID_RUN_ID", "run_id is outside the planning directory"), indent=2))
        return 1
    report_path = _safe_stored_path(run_dir, "report.json")
    decision_path = _safe_stored_path(run_dir, "review-decision.json")
    if report_path is None or decision_path is None:
        print(json.dumps(_blocked(args.run_id, "REPORT_INVALID", "planning run files are outside the run directory"), indent=2))
        return 1
    try:
        report = _read_report(report_path, args.run_id)
    except (OSError, UnicodeError, ValueError, TypeError, json.JSONDecodeError) as exc:
        print(json.dumps(_blocked(args.run_id, "REPORT_INVALID", str(exc)), indent=2))
        return 1

    if not report.ok or not report.review_required:
        print(
            json.dumps(
                _blocked(
                    args.run_id,
                    "PLANNING_CHECK_FAILED",
                    "stored planning report is not structurally valid",
                ),
                indent=2,
            )
        )
        return 1

    decision = read_review_decision(decision_path, report)
    if decision is None:
        print(
            json.dumps(
                _blocked(
                    args.run_id,
                    "REVIEW_REQUIRED",
                    "a valid human review decision is required",
                ),
                indent=2,
            )
        )
        return 1
    if decision.get("decision") != "approve":
        print(
            json.dumps(
                _blocked(
                    args.run_id,
                    "REVIEW_NOT_APPROVED",
                    f"human review decision is {decision.get('decision')!r}",
                ),
                indent=2,
            )
        )
        return 1

    try:
        suggestion = build_downstream_suggestion(report, decision, root=root)
    except (OSError, UnicodeError, ValueError, TypeError, RuntimeError):
        print(
            json.dumps(
                _blocked(args.run_id, "SUGGESTION_BLOCKED", "downstream suggestion could not be evaluated"),
                indent=2,
            )
        )
        return 1
    if suggestion is None:
        print(
            json.dumps(
                _blocked(
                    args.run_id,
                    "SUGGESTION_BLOCKED",
                    "planning artifacts or generated tasks changed after review",
                ),
                indent=2,
            )
        )
        return 1

    print(json.dumps(suggestion, indent=2, ensure_ascii=False))
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="coherence plan")
    sub = parser.add_subparsers(dest="command", required=True)

    check = sub.add_parser("check")
    check.add_argument("--intent", required=True, type=Path)
    check.add_argument("--spec", required=True, type=Path)
    check.add_argument("--plan", required=True, type=Path)
    check.add_argument("--run-id", required=True)
    check.add_argument("--project-root", default=Path("."), type=Path)
    check.add_argument("--json", action="store_true")

    suggest = sub.add_parser("suggest")
    suggest.add_argument("--run-id", required=True)
    suggest.add_argument("--project-root", required=True, type=Path)
    suggest.add_argument("--json", action="store_true")

    bootstrap = sub.add_parser("bootstrap")
    bootstrap.add_argument("--intent", required=True, type=Path)
    bootstrap.add_argument("--spec", required=True, type=Path)
    bootstrap.add_argument("--plan", required=True, type=Path)
    bootstrap.add_argument("--run-id", required=True)
    bootstrap.add_argument("--project-root", default=Path("."), type=Path)
    bootstrap.add_argument("--decompose", action="store_true")
    bootstrap.add_argument("--json", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "check":
        return _check(args)
    if args.command == "bootstrap":
        return _bootstrap(args)
    return _suggest(args)


__all__ = ["main"]
