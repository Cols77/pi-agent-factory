"""Triage inbox (Increment 6 Task 4).

`list_items(root, now)` composes PURE source collectors into one
stable-sorted, de-duplicated `InboxItem` list. It is strictly read-only: it
never calls doctor/trace/register/KB writers and never executes a resolver;
``resolve_cmd`` is informational (a hint for the human who owns the item).

Sources wired concretely here:
* coverage gates -- a ``coverage-reviews/<run>/status.json`` whose ``phase``
  is ``gates_blocked`` (Task 2) lists the ``coverage:<run>:proposal|warning:<id>``
  items a human must decide on;
* expired deferrals -- a requirement whose structured ``trace_deferred`` is
  due (Task 3 ``deferral_is_due``);
* stale register bindings -- a requirement whose recorded checksum no longer
  matches its content (``coherence.register.cli.cmd_index``).

Item ids follow the Review Amendments vocabulary: ``coverage:<run>:proposal:<id>``,
``coverage:<run>:warning:<id>``, ``trace:<id>``. The list is stable-sorted by id
and de-duplicated; reading never creates a file.
"""
from __future__ import annotations

import json
from pathlib import Path

from coherence.deferrals import deferral_is_due, parse_deferral


class InboxItem:
    """One triage item. A plain frozen-ish value object (JSON-serializable);
    ``resolve_cmd`` is informational, ``review_after`` an optional ISO string.
    """

    __slots__ = (
        "id", "source", "kind", "ref", "summary", "evidence",
        "resolve_cmd", "review_after",
    )

    def __init__(
        self,
        id: str,
        source: str,
        kind: str,
        ref: str,
        summary: str,
        evidence: str = "",
        resolve_cmd: tuple[str, ...] | None = None,
        review_after: str | None = None,
    ) -> None:
        self.id = id
        self.source = source
        self.kind = kind
        self.ref = ref
        self.summary = summary
        self.evidence = evidence
        self.resolve_cmd = resolve_cmd
        self.review_after = review_after

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "source": self.source,
            "kind": self.kind,
            "ref": self.ref,
            "summary": self.summary,
            "evidence": self.evidence,
            "resolve_cmd": self.resolve_cmd,
            "review_after": self.review_after,
        }


def _coverage_gate_items(root: Path) -> list[InboxItem]:
    """Collect coverage gates awaiting a decision (Task 2 ``gates_blocked``)."""
    reviews_dir = root / "coverage-reviews"
    if not reviews_dir.is_dir():
        return []
    items: list[InboxItem] = []
    for status_path in sorted(reviews_dir.glob("*/status.json")):
        try:
            status = json.loads(status_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if status.get("phase") != "gates_blocked":
            continue
        needed = status.get("needed_items") or []
        for item_id in needed:
            prefix, rest = item_id.split(":", 1) if ":" in item_id else (item_id, "")
            kind = "proposal" if ":proposal:" in item_id else "warning"
            sr = item_id.rsplit(":", 1)[-1]
            items.append(
                InboxItem(
                    id=item_id,
                    source="coverage",
                    kind=kind,
                    ref=f"sr:{sr}",
                    summary=f"coverage gate needs a decision on {kind} {sr}",
                    evidence=str(status_path),
                )
            )
    return items


def _expired_deferral_items(root: Path, now: str) -> list[InboxItem]:
    """Collect requirements whose structured deferral is due (Task 3)."""
    import frontmatter

    req_dir = root / "requirements"
    if not req_dir.is_dir():
        return []
    items: list[InboxItem] = []
    for path in sorted(req_dir.glob("*.md")):
        try:
            meta = frontmatter.load(str(path)).metadata
        except Exception:
            continue
        raw = meta.get("trace_deferred")
        if raw is None:
            continue
        try:
            deferral = parse_deferral(raw)
        except ValueError:
            continue
        if deferral_is_due(deferral, now):
            sr_id = str(meta.get("id") or path.stem)
            items.append(
                InboxItem(
                    id=f"trace:{sr_id}",
                    source="deferrals",
                    kind="expired_deferral",
                    ref=f"sr:{sr_id}",
                    summary=f"deferral on {sr_id} expired at {deferral.review_after}",
                    evidence=deferral.reason,
                    resolve_cmd=(f"coherence register defer {sr_id} --reason ... --review-after <new>",),
                    review_after=deferral.review_after,
                )
            )
    return items


def _stale_binding_items(root: Path) -> list[InboxItem]:
    """Collect register bindings whose recorded checksum is stale (read-only).

    Uses `load_register` + `is_checksum_current` directly, never the
    writer `cmd_index` (which stamps checksums and writes index.json) -- the
    inbox must not create or modify files.
    """
    from coherence.register.register import is_checksum_current, load_register

    req_dir = root / "requirements"
    if not req_dir.is_dir():
        return []
    items: list[InboxItem] = []
    for req in load_register(req_dir):
        if not is_checksum_current(req):
            items.append(
                InboxItem(
                    id=f"trace:{req.id}",
                    source="register",
                    kind="stale_binding",
                    ref=f"sr:{req.id}",
                    summary=f"binding on {req.id} is stale (recorded checksum changed)",
                )
            )
    return items


def list_items(root: Path | str, now: str) -> list[InboxItem]:
    """Compose all inbox sources into one stable-sorted, de-duplicated list
    (pure read -- never writes, never executes a resolver)."""
    root = Path(root)
    collected: list[InboxItem] = []
    collected.extend(_coverage_gate_items(root))
    collected.extend(_expired_deferral_items(root, now))
    collected.extend(_stale_binding_items(root))

    # Stable sort by id; de-duplicate by id (first occurrence wins).
    seen: set[str] = set()
    deduped: list[InboxItem] = []
    for item in sorted(collected, key=lambda i: i.id):
        if item.id in seen:
            continue
        seen.add(item.id)
        deduped.append(item)
    return deduped


__all__ = ["InboxItem", "list_items"]