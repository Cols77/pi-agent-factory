from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import frontmatter

from coherence.register.closure import (
    ClosureFinding,
    RequirementState,
    classify,
    verify_sr_marker,
)
from coherence.register.register import (
    Requirement,
    content_checksum,
    is_checksum_current,
    load_register,
    parse_requirement,
)
from coherence.register.write import (
    ReasonRequiredError,
    UnboundRequirementError,
    reaffirm,
    stamp_checksum,
    write_binding,
    write_deferral,
)
from substrate.evidence.read import list_run_manifests
from substrate.freshness.model import GATE_FAILING_SEVERITIES, FreshnessSeverity
from substrate.ledger.tasks import Task, load_tasks

_ID_RE = re.compile(r"SR-(\d+)")

_TEMPLATE = """---
id: {id}
title: "{title}"
statement: "TODO: EARS statement -- When <trigger>, the <system> shall <response>."
domain: {domain}
upstream: []
---

## Rationale
TODO
"""


def _next_id(requirements_dir: Path) -> str:
    nums = [
        int(m.group(1))
        for p in requirements_dir.glob("SR-*.md")
        if (m := _ID_RE.search(p.name))
    ]
    return f"SR-{(max(nums) + 1) if nums else 1:03d}"


def cmd_new(requirements_dir: Path, title: str, domain: str) -> Path:
    requirements_dir.mkdir(parents=True, exist_ok=True)
    req_id = _next_id(requirements_dir)
    path = requirements_dir / f"{req_id}.md"
    path.write_text(_TEMPLATE.format(id=req_id, title=title, domain=domain), encoding="utf-8")
    return path


def cmd_index(requirements_dir: Path) -> dict:
    out: list[dict] = []
    for req in load_register(requirements_dir):
        if req.binding is None:
            out.append({"id": req.id, "checksum": None, "proposed": True})
            continue
        checksum = content_checksum(req)
        if req.checksum is None:
            stamp_checksum(req.path)
            out.append({"id": req.id, "checksum": checksum, "stale": False})
            continue
        if req.checksum == checksum:
            out.append({"id": req.id, "checksum": checksum, "stale": False})
            continue
        out.append({"id": req.id, "checksum": req.checksum, "stale": True})
    result = {"requirements": out}
    (requirements_dir / "index.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def cmd_status(requirements_dir: Path, stale_only: bool = False) -> str:
    lines: list[str] = []
    for req in load_register(requirements_dir):
        if req.binding is None:
            if not stale_only:
                lines.append(f"{req.id}  [proposed]  {req.title}")
            continue
        current = is_checksum_current(req)
        if stale_only and current:
            continue
        lines.append(f"{req.id}  [{'current' if current else 'STALE'}]  {req.title}")
    return "\n".join(lines) if lines else "no requirements"


def cmd_show(requirements_dir: Path, req_id: str) -> str:
    path = requirements_dir / f"{req_id}.md"
    if not path.exists():
        return f"not found: {req_id}"
    req = parse_requirement(path)
    b = req.binding
    if b is None:
        return (
            f"{req.id}  {req.title}\n"
            f"statement: {req.statement}\n"
            f"binding: (proposed -- not yet measurable)\n"
            f"source: {req.source or '(none)'}"
        )
    harness = b.harness if b.harness is not None else "(no harness)"
    return (
        f"{req.id}  {req.title}\n"
        f"statement: {req.statement}\n"
        f"binding: {harness}/{b.experiment} {b.metric} {b.assert_expr} (trials={b.trials})\n"
        f"checksum: {'current' if is_checksum_current(req) else 'STALE'}"
    )


def cmd_bind(
    requirements_dir: Path,
    req_id: str,
    *,
    experiment: str | None,
    metric: str | None,
    assert_expr: str | None,
    harness: str | None,
    trials: int,
    reaffirm_reason: str | None,
    window_json: str | None = None,
) -> str:
    path = requirements_dir / f"{req_id}.md"
    if not path.exists():
        return f"not found: {req_id}"
    if reaffirm_reason is not None:
        try:
            reaffirm(path, reaffirm_reason)
        except ReasonRequiredError:
            return f"{req_id}: a reason is required to reaffirm"
        except UnboundRequirementError:
            return (
                f"{req_id}: nothing to reaffirm -- this requirement is proposed and has no "
                f"binding; bind it with --experiment/--metric/--assert instead"
            )
        return f"{req_id}  reaffirmed: {reaffirm_reason}"
    if experiment is None or metric is None or assert_expr is None:
        missing = [
            name
            for name, value in (("--experiment", experiment), ("--metric", metric), ("--assert", assert_expr))
            if value is None
        ]
        return f"{req_id}: missing {', '.join(missing)} (or pass --reaffirm to keep the existing binding)"
    try:
        window = json.loads(window_json) if window_json else None
    except json.JSONDecodeError as exc:
        return f"{req_id}: --window-json is not valid JSON ({exc.msg})"
    write_binding(
        path,
        experiment=experiment,
        metric=metric,
        assert_expr=assert_expr,
        harness=harness,
        trials=trials,
        window=window,
    )
    harness_desc = harness if harness is not None else "no harness named yet"
    return f"{req_id}  bound to {harness_desc}: {metric} {assert_expr}"


def cmd_defer(requirements_dir: Path, req_id: str, reason: str, *, review_after: str | None = None) -> str:
    path = requirements_dir / f"{req_id}.md"
    if not path.exists():
        return f"not found: {req_id}"
    try:
        write_deferral(path, reason, review_after=review_after)
    except ReasonRequiredError:
        return f"{req_id}: a reason is required to defer"
    if review_after:
        return f"{req_id}  deferred until {review_after}: {reason}"
    return f"{req_id}  deferred: {reason}"


def _deferred_reason(req: Requirement) -> str | None:
    from coherence.deferrals import parse_deferral

    raw = frontmatter.load(str(req.path)).get("trace_deferred")
    if raw is None:
        return None
    return parse_deferral(raw).reason


def _linked_task_status(tasks: list[Task], req_id: str) -> str | None:
    matches = [t for t in tasks if req_id in t.satisfies]
    if not matches:
        return None
    live = next((t for t in matches if t.status != "done"), None)
    return (live or matches[0]).status


def _validation_state(manifests: list[dict], req_id: str) -> str | None:
    for manifest in manifests:
        results = [
            entry
            for validation in manifest.get("validation") or []
            if isinstance(validation, dict)
            for entry in validation.get("requirements", [])
            if isinstance(entry, dict) and entry.get("id") == req_id and "passed" in entry
        ]
        if not results:
            continue
        return "failing" if any(not entry["passed"] for entry in results) else "passing"
    return None


def _findings(
    project_root: Path, *, marker_errors: list[str] | None = None
) -> list[tuple[Requirement, ClosureFinding]]:
    reqs = load_register(project_root / "requirements")
    tasks = load_tasks(project_root / "tasks")
    manifests = list_run_manifests(project_root / "evidence")
    results: list[tuple[Requirement, ClosureFinding]] = []
    for req in reqs:
        results.append(
            (
                req,
                classify(
                    req,
                    validation=_validation_state(manifests, req.id),
                    linked_task_status=_linked_task_status(tasks, req.id),
                    deferred_reason=_deferred_reason(req),
                ),
            )
        )
        # Wire the SR test-marker closure check into the production `check`.
        # A bound .py experiment missing its @pytest.mark.sr marker surfaces as
        # a finding whose severity is the compiled test_marker obligation's
        # requiredness (BLOCKING -> gates, required -> visible WARNING); a
        # command / non-file experiment is a CONFIGURATION/WARNING finding the
        # closure never fabricates into a pass. cmd_check's existing
        # partitioning already routes BLOCKING -> pending and WARNING -> warning,
        # so no change there is required. UncompiledPresetError skips are
        # surfaced on the errors channel below so a skipped marker check stays
        # visible in cmd_check instead of being silently dropped.
        skipped: list[str] = []
        marker_finding = verify_sr_marker(req, project_root=project_root, errors=skipped)
        if marker_errors is not None:
            marker_errors.extend(skipped)
        if marker_finding is not None:
            results.append((req, marker_finding))
    return results


def cmd_check(project_root: Path) -> tuple[str, int]:
    marker_errors: list[str] = []
    results = _findings(project_root, marker_errors=marker_errors)
    findings = [finding for _, finding in results]
    pending = [f for f in findings if f.severity in GATE_FAILING_SEVERITIES]
    warning = [f for f in findings if f.severity is FreshnessSeverity.WARNING]
    passing = [f for f in findings if f.state is RequirementState.MEASURED_PASSING]
    failing = [f for f in findings if f.state is RequirementState.MEASURED_FAILING]
    declined = [f for _, f in results if f.state is RequirementState.DECLINED]
    declined_unbound = [
        f for req, f in results if f.state is RequirementState.DECLINED and req.binding is None
    ]

    lines = [
        f"requirements closure: {len(findings)} requirement(s) evaluated",
        f"{len(pending)} pending, {len(warning)} unmeasurable, "
        f"{len(passing)} measured-passing, {len(failing)} measured-failing, "
        f"{len(declined)} declined ({len(declined_unbound)} with no binding)",
    ]
    if pending:
        lines += ["", "undecided requirements (the gate fails on these):"]
        lines.extend(f"  ! {f.req_id:<10} {f.detail}" for f in pending)
    if failing:
        lines += ["", "measured failing \u2014 decided and measured; the system does not meet these:"]
        lines.extend(f"  x {f.req_id:<10} {f.detail}" for f in failing)
    if warning:
        lines += ["", "unmeasurable \u2014 warned, not blocking:"]
        lines.extend(f"  ~ {f.req_id:<10} {f.detail}" for f in warning)
    if marker_errors:
        lines += ["", "marker-closure skips \u2014 uncompiled profile; no marker gate applied:"]
        lines.extend(f"  ~ {message}" for message in marker_errors)
    if declined_unbound:
        lines += ["", "declined with no binding \u2014 deferred, but no measurement was ever decided:"]
        lines.extend(f"  - {f.req_id:<10} {f.detail}" for f in declined_unbound)
    return "\n".join(lines), (1 if pending else 0)


def cmd_next(project_root: Path) -> str:
    tasks = load_tasks(project_root / "tasks")
    for req, finding in _findings(project_root):
        if finding.state is not RequirementState.PENDING:
            continue
        candidates = [t.id for t in tasks if req.id in t.satisfies]
        return (
            f"{req.id}  {req.title}\n"
            f"statement: {req.statement}\n"
            f"candidate tasks: {', '.join(candidates) if candidates else 'none'}"
        )
    return "nothing pending -- every requirement is decided"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="factory-requirements")
    sub = parser.add_subparsers(dest="cmd", required=True)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--requirements-dir", default="requirements", type=Path)

    p_new = sub.add_parser("new", parents=[common])
    p_new.add_argument("title")
    p_new.add_argument("--domain", default="behavioral")
    sub.add_parser("index", parents=[common])
    p_status = sub.add_parser("status", parents=[common])
    p_status.add_argument("--stale", action="store_true")
    p_show = sub.add_parser("show", parents=[common])
    p_show.add_argument("id")

    p_bind = sub.add_parser("bind", parents=[common])
    p_bind.add_argument("id")
    p_bind.add_argument("--experiment", default=None)
    p_bind.add_argument("--metric", default=None)
    p_bind.add_argument("--assert", dest="assert_expr", default=None)
    p_bind.add_argument("--harness", default=None)
    p_bind.add_argument("--trials", type=int, default=1)
    p_bind.add_argument("--window-json", dest="window_json", default=None)
    p_bind.add_argument("--reaffirm", dest="reaffirm_reason", default=None)

    p_defer = sub.add_parser("defer", parents=[common])
    p_defer.add_argument("id")
    p_defer.add_argument("--reason", required=True)
    p_defer.add_argument("--review-after", default=None)

    p_check = sub.add_parser("check")
    p_check.add_argument("--project-root", default=Path("."), type=Path)
    p_next = sub.add_parser("next")
    p_next.add_argument("--project-root", default=Path("."), type=Path)

    args = parser.parse_args(argv)

    if args.cmd == "new":
        print(cmd_new(args.requirements_dir, args.title, args.domain))
    elif args.cmd == "index":
        result = cmd_index(args.requirements_dir)
        print(json.dumps(result, indent=2))
        return 1 if any(entry.get("stale") for entry in result["requirements"]) else 0
    elif args.cmd == "status":
        print(cmd_status(args.requirements_dir, stale_only=args.stale))
    elif args.cmd == "show":
        print(cmd_show(args.requirements_dir, args.id))
    elif args.cmd == "bind":
        print(
            cmd_bind(
                args.requirements_dir,
                args.id,
                experiment=args.experiment,
                metric=args.metric,
                assert_expr=args.assert_expr,
                harness=args.harness,
                trials=args.trials,
                reaffirm_reason=args.reaffirm_reason,
                window_json=args.window_json,
            )
        )
    elif args.cmd == "defer":
        print(cmd_defer(args.requirements_dir, args.id, args.reason, review_after=args.review_after))
    elif args.cmd == "check":
        text, code = cmd_check(args.project_root)
        print(text)
        return code
    elif args.cmd == "next":
        print(cmd_next(args.project_root))
    return 0


__all__ = [
    "cmd_bind",
    "cmd_check",
    "cmd_defer",
    "cmd_index",
    "cmd_new",
    "cmd_next",
    "cmd_show",
    "cmd_status",
    "main",
]
