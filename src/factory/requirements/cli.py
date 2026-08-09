from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import frontmatter

from factory.requirements.register import (
    content_checksum,
    is_checksum_current,
    load_register,
    parse_requirement,
)
from factory.requirements.write import ReasonRequiredError, reaffirm, write_binding, write_deferral

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
            # Proposed: nothing to checksum, and rewriting the file would only
            # churn its formatting.
            out.append({"id": req.id, "checksum": None, "proposed": True})
            continue
        checksum = content_checksum(req)
        if req.checksum is None:
            # First stamp for a newly bound requirement.
            post = frontmatter.load(str(req.path))
            post["checksum"] = checksum
            req.path.write_text(frontmatter.dumps(post), encoding="utf-8")
            out.append({"id": req.id, "checksum": checksum, "stale": False})
            continue
        if req.checksum == checksum:
            out.append({"id": req.id, "checksum": checksum, "stale": False})
            continue
        # Stale. Re-stamping here would launder the one signal that says the
        # statement moved and nobody re-judged whether the binding still
        # measures it. Report and leave the file exactly as found; only `bind`
        # or `bind --reaffirm` may clear it.
        out.append({"id": req.id, "checksum": req.checksum, "stale": True})
    result = {"requirements": out}
    (requirements_dir / "index.json").write_text(
        json.dumps(result, indent=2), encoding="utf-8"
    )
    return result


def cmd_status(requirements_dir: Path, stale_only: bool = False) -> str:
    lines: list[str] = []
    for req in load_register(requirements_dir):
        if req.binding is None:
            # Never stale, so --stale must not list it.
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
    experiment: str,
    metric: str,
    assert_expr: str,
    harness: str | None,
    trials: int,
    reaffirm_reason: str | None,
) -> str:
    path = requirements_dir / f"{req_id}.md"
    if not path.exists():
        return f"not found: {req_id}"
    if reaffirm_reason is not None:
        reaffirm(path, reaffirm_reason)
    else:
        write_binding(
            path,
            experiment=experiment,
            metric=metric,
            assert_expr=assert_expr,
            harness=harness,
            trials=trials,
            window=None,
        )
    harness_desc = harness if harness is not None else "no harness named yet"
    return f"{req_id}  bound to {harness_desc}: {metric} {assert_expr}"


def cmd_defer(requirements_dir: Path, req_id: str, reason: str) -> str:
    path = requirements_dir / f"{req_id}.md"
    if not path.exists():
        return f"not found: {req_id}"
    try:
        write_deferral(path, reason)
    except ReasonRequiredError:
        return f"{req_id}: a reason is required to defer"
    return f"{req_id}  deferred: {reason}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="factory-requirements")
    sub = parser.add_subparsers(dest="cmd", required=True)

    # Shared parent so --requirements-dir is accepted AFTER the subcommand
    # (e.g. `status --requirements-dir X`), matching how the CLI is invoked.
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
    p_bind.add_argument("--experiment", required=True)
    p_bind.add_argument("--metric", required=True)
    p_bind.add_argument("--assert", dest="assert_expr", required=True)
    p_bind.add_argument("--harness", default=None)
    p_bind.add_argument("--trials", type=int, default=1)
    p_bind.add_argument("--reaffirm", dest="reaffirm_reason", default=None)

    p_defer = sub.add_parser("defer", parents=[common])
    p_defer.add_argument("id")
    p_defer.add_argument("--reason", required=True)

    args = parser.parse_args(argv)

    if args.cmd == "new":
        print(cmd_new(args.requirements_dir, args.title, args.domain))
    elif args.cmd == "index":
        print(json.dumps(cmd_index(args.requirements_dir), indent=2))
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
            )
        )
    elif args.cmd == "defer":
        print(cmd_defer(args.requirements_dir, args.id, args.reason))
    return 0
