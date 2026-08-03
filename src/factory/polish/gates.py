from __future__ import annotations

import dataclasses
import itertools
from collections.abc import Callable

from factory.polish.finding import Finding
from factory.polish.worker import LandedChange


def _seq_ids(prefix: str) -> Callable[[], str]:
    counter = itertools.count(1)
    return lambda: f"{prefix}{next(counter)}"


class Gate1:
    """Pre-queue glance: a synthesized finding waits here for accept/edit/discard
    before it enters the fix queue. Nothing is enqueued without passing Gate 1."""

    def __init__(self, next_id: Callable[[], str] | None = None) -> None:
        self._next_id = next_id or _seq_ids("g1-")
        self._pending: dict[str, Finding] = {}

    def add(self, finding: Finding) -> str:
        gid = self._next_id()
        self._pending[gid] = finding
        return gid

    def pending(self) -> dict[str, Finding]:
        return dict(self._pending)

    def accept(self, gid: str) -> Finding:
        return self._pending.pop(gid)

    def edit(self, gid: str, **changes) -> Finding:
        finding = dataclasses.replace(self._pending.pop(gid), **changes)
        return finding

    def discard(self, gid: str) -> None:
        self._pending.pop(gid, None)


@dataclasses.dataclass
class Gate2Row:
    gid: str
    change: LandedChange
    verdict: str = "pending"  # pending | accepted | wrong


class Gate2:
    """Post-fix acceptance checklist against the reloaded app. tick = accept
    (re-ground the SR if linked); comment = wrong -> a new linked rework finding."""

    def __init__(self, next_id: Callable[[], str] | None = None) -> None:
        self._next_id = next_id or _seq_ids("g2-")
        self._rows: dict[str, Gate2Row] = {}

    def add(self, change: LandedChange) -> str:
        gid = self._next_id()
        self._rows[gid] = Gate2Row(gid=gid, change=change)
        return gid

    def rows(self) -> list[Gate2Row]:
        return list(self._rows.values())

    def tick(self, gid: str) -> Finding | None:
        row = self._rows[gid]
        row.verdict = "accepted"
        return row.change.finding if row.change.finding.sr else None

    def comment(self, gid: str, text: str) -> Finding:
        row = self._rows[gid]
        row.verdict = "wrong"
        orig = row.change.finding
        return Finding(
            usecase=orig.usecase,
            description=f"[rework of {row.change.task_id}] {text}",
            snapshot={**orig.snapshot, "rework_of": row.change.task_id},
            sr=orig.sr,
            artifacts=list(orig.artifacts),
        )
