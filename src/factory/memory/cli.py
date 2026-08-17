"""`factory memory` / `factory failure` command-line interface.

Additive on v1 (D3): a net-new ``python -m factory.memory`` entry model over
the same argparse-subparser + ``--repo``/``--json`` + deterministic-ordering
(by declared id, never mtime) conventions ``factory.evidence`` /
``factory.goals`` use. Subcommands:

* ``memory show [scope]``      -- one read of durable memory (decisions,
  failure records, rejected hypotheses, open goals, conflicts), delegated to
  ``factory.system.queries.query_memory`` -- the same projection the system
  navigator renders, never a re-implementation.
* ``memory conflicts [scope]`` -- structural + fingerprint conflicts for a
  scope, delegated to ``factory.system.queries.query_conflicts``.
* ``failure list``             -- every failure record under
  ``docs/failures/``, ordered by declared ``FR-`` id.
* ``failure show <id>``        -- one failure record by its declared id.
* ``failure add``              -- write a well-formed ``docs/failures/
  FR-*.md`` record through the existing frontmatter writer; the composed
  frontmatter is validated against ``failure.schema.json`` (id pattern
  ``^FR-[A-Z0-9-]+$``, required ``root_cause``/``fix``, the rejected-
  hypothesis triple) BEFORE anything is written. The existing parser is
  reused, never forked (D3).

Records are *recorded, never inferred* (brief §5.6): every root cause cites
evidence or an ADR, and ``add`` only records what the caller passes -- no
LLM, no prose inference.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import frontmatter

from factory.memory.failure_record import (
    DuplicateFailureIdError,
    FailureRecord,
    load_failures,
    parse_failure,
)
from factory.system import queries as system_queries
from factory.validation.schema_validator import SCHEMA_DIR, validate

_SCHEMA = SCHEMA_DIR / "failure.schema.json"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="factory.memory")
    sub = parser.add_subparsers(dest="command", required=True)

    memory = sub.add_parser("memory")
    memory_sub = memory.add_subparsers(dest="subcommand", required=True)

    show = memory_sub.add_parser("show")
    show.add_argument("scope", nargs="?", default="all")
    show.add_argument("--repo", default=".")
    show.add_argument("--json", action="store_true")

    conflicts = memory_sub.add_parser("conflicts")
    conflicts.add_argument("scope", nargs="?", default="all")
    conflicts.add_argument("--repo", default=".")
    conflicts.add_argument("--json", action="store_true")

    failure = sub.add_parser("failure")
    failure_sub = failure.add_subparsers(dest="subcommand", required=True)

    listing = failure_sub.add_parser("list")
    listing.add_argument("--repo", default=".")
    listing.add_argument("--json", action="store_true")

    show_failure = failure_sub.add_parser("show")
    show_failure.add_argument("failure_id")
    show_failure.add_argument("--repo", default=".")
    show_failure.add_argument("--json", action="store_true")

    add_failure = failure_sub.add_parser("add")
    add_failure.add_argument("--id", required=True)
    add_failure.add_argument("--title", required=True)
    add_failure.add_argument("--root-cause", required=True)
    add_failure.add_argument("--fix", required=True)
    add_failure.add_argument("--reproduced-by", default=None)
    add_failure.add_argument("--regression-link", default=None)
    add_failure.add_argument("--linked-req", action="append", default=[])
    add_failure.add_argument("--linked-feature", action="append", default=[])
    add_failure.add_argument(
        "--hypothesis",
        action="append",
        default=[],
        help='one rejected hypothesis as a JSON object, e.g. '
        '\'{"hypothesis": "...", "why_rejected": "...", "evidence": "..."}\'',
    )
    add_failure.add_argument("--repo", default=".")
    add_failure.add_argument("--json", action="store_true")
    return parser


def _emit(payload: dict, as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload))
    else:
        print(json.dumps(payload, indent=2))


def _load_records(repo: Path) -> dict[str, FailureRecord]:
    """Every failure record keyed by declared id; a duplicate id fails loudly."""
    try:
        return load_failures(repo)
    except DuplicateFailureIdError as exc:
        print(f"could not load failure records: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc


def _memory_read(repo: Path, scope: str, conflicts: bool, as_json: bool) -> int:
    try:
        payload = (
            system_queries.query_conflicts(repo, scope)
            if conflicts
            else system_queries.query_memory(repo, scope)
        )
    except ValueError as exc:
        kind = "conflicts" if conflicts else "memory"
        print(f"could not query {kind}: {exc}", file=sys.stderr)
        return 2
    _emit(payload, as_json)
    return 0


def _failure_list(repo: Path, as_json: bool) -> int:
    records = _load_records(repo)
    items = [
        {
            "id": rec.id,
            "title": rec.title,
            "reproduced_by": rec.reproduced_by,
            "linked_req": list(rec.linked_req),
            "linked_feature": list(rec.linked_feature),
            "scope_errors": list(rec.scope_errors),
        }
        for rec in sorted(records.values(), key=lambda r: r.id or "")
    ]
    _emit({"failures": items}, as_json)
    return 0


def _failure_show(repo: Path, failure_id: str, as_json: bool) -> int:
    records = _load_records(repo)
    rec = records.get(failure_id)
    if rec is None:
        print(f"no failure record with id {failure_id!r}", file=sys.stderr)
        return 2
    _emit(
        {
            "id": rec.id,
            "title": rec.title,
            "reproduced_by": rec.reproduced_by,
            "root_cause": rec.root_cause,
            "rejected_hypotheses": list(rec.rejected_hypotheses),
            "fix": rec.fix,
            "regression_link": rec.regression_link,
            "linked_req": list(rec.linked_req),
            "linked_feature": list(rec.linked_feature),
            "path": str(rec.path),
            "scope_errors": list(rec.scope_errors),
        },
        as_json,
    )
    return 0


def _failure_add(args: argparse.Namespace, repo: Path) -> int:
    meta: dict = {
        "id": args.id,
        "title": args.title,
        "root_cause": args.root_cause,
        "fix": args.fix,
    }
    if args.reproduced_by is not None:
        meta["reproduced_by"] = args.reproduced_by
    if args.regression_link is not None:
        meta["regression_link"] = args.regression_link
    if args.linked_req:
        meta["linked_req"] = list(args.linked_req)
    if args.linked_feature:
        meta["linked_feature"] = list(args.linked_feature)

    hypotheses: list[dict] = []
    for raw in args.hypothesis:
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            print(f"invalid --hypothesis JSON: {exc}", file=sys.stderr)
            return 2
        if not isinstance(parsed, dict):
            print("invalid --hypothesis: expected a JSON object", file=sys.stderr)
            return 2
        hypotheses.append(parsed)
    if hypotheses:
        meta["rejected_hypotheses"] = hypotheses

    errors = validate(meta, _SCHEMA)
    if errors:
        for err in errors:
            print(f"failure record invalid: {err}", file=sys.stderr)
        return 2

    failures_dir = repo / "docs" / "failures"
    failures_dir.mkdir(parents=True, exist_ok=True)
    path = failures_dir / f"{args.id}.md"
    if path.exists():
        print(f"failure record already exists: {path}", file=sys.stderr)
        return 2
    body = f"# {args.title}\n\nRecorded through `factory failure add`."
    post = frontmatter.Post(body, **meta)
    path.write_text(frontmatter.dumps(post), encoding="utf-8")
    rec = parse_failure(path)
    _emit({"id": rec.id, "path": str(path), "scope_errors": rec.scope_errors}, args.json)
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    repo = Path(args.repo).resolve()

    if args.command == "memory":
        return _memory_read(repo, args.scope, args.subcommand == "conflicts", args.json)
    if args.command == "failure":
        if args.subcommand == "list":
            return _failure_list(repo, args.json)
        if args.subcommand == "show":
            return _failure_show(repo, args.failure_id, args.json)
        return _failure_add(args, repo)
    # Unreachable today: the top-level subparser is required=True and routes
    # every command here. Defensive default kept so an unhandled command can
    # never be mistaken for success.
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
